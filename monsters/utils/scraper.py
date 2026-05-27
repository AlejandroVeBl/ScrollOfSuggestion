import requests
from bs4 import BeautifulSoup

# from monsters.models import Monster

BASE_URL = "https://www.aidedd.org"
LIST_URL = f"{BASE_URL}/monster/"


def scrape_monster_list():
    """
    Scrapes only names and detail URLs from the main monster table.
    All stats are fetched from each monster's detail page.
    """
    response = requests.get(LIST_URL, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    monsters = []
    for row in soup.find_all("tr"):
        name_cell = row.find("td", class_="item")
        if not name_cell:
            continue
        a_tag = name_cell.find("a")
        if not a_tag:
            continue
        monsters.append({
            "name":       a_tag.get_text(strip=True),
            "detail_url": BASE_URL + a_tag["href"],
        })

    return monsters

def scrape_monster_detail(detail_url):
    """
    Scrapes a monster's individual page, e.g. aidedd.org/monster/ape
    Returns a dict with full stat block details.
    """
    response = requests.get(detail_url, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    data = {}

    red_div = soup.find("div", class_="red")
    if not red_div:
        return data

    # ── Parse type_line into size / type / alignment ──────────────────
    type_div = red_div.find("div", class_="type")
    if type_div:
        type_line = type_div.get_text(strip=True)
        data["type_line"] = type_line

        if "," in type_line:
            left, alignment = type_line.rsplit(",", 1)
            data["alignment"] = alignment.strip()
        else:
            left = type_line
            data["alignment"] = ""

        parts = left.strip().split(" ", 1)
        data["size"] = parts[0].strip()
        data["type"] = parts[1].strip() if len(parts) > 1 else ""

    # ── Initiative ────────────────────────────────────────────────────
    init_div = red_div.find("div", class_="init")
    if init_div:
        data["initiative"] = init_div.get_text(strip=True).replace("Initiative", "").strip()

    # ── AC / HP / Speed (text nodes after <strong> tags) ─────────────
    red_text = red_div.get_text(separator="\n")
    for line in red_text.splitlines():
        line = line.strip()
        if line.startswith("AC"):
            data["ac"] = line.replace("AC", "").strip()
        elif line.startswith("HP"):
            data["hp"] = line.replace("HP", "").strip()
        elif line.startswith("Speed"):
            data["speed"] = line.replace("Speed", "").strip()

    # ── Ability scores ────────────────────────────────────────────────
    label_map = {
        "Str": "strength", "Dex": "dexterity", "Con": "constitution",
        "Int": "intelligence", "Wis": "wisdom",  "Cha": "charisma",
    }
    labels = (
        [d.get_text(strip=True) for d in red_div.find_all("div", class_="car1")] +
        [d.get_text(strip=True) for d in red_div.find_all("div", class_="car4")]
    )
    values = (
        [d.get_text(strip=True) for d in red_div.find_all("div", class_="car2")] +
        [d.get_text(strip=True) for d in red_div.find_all("div", class_="car5")]
    )
    for label, value in zip(labels, values):
        key = label_map.get(label)
        if key:
            data[key] = value

    # ── Strong-tag fields: Skills / Immunities / Senses / Languages / CR ──
    for strong in red_div.find_all("strong"):
        label = strong.get_text(strip=True).rstrip(":")
        sibling = strong.next_sibling
        value = sibling.strip() if sibling and isinstance(sibling, str) else ""
        if not value:
            continue
        if label == "Skills":
            data["skills"] = value
        elif label == "Immunities":
            data["immunities"] = value
        elif label == "Senses":
            data["senses"] = value
        elif label == "Languages":
            data["languages"] = value
        elif label == "CR":
            data["cr_full"] = value   # e.g. "14 (XP 11 500; PB +5)"

    # ── Sections: Traits / Actions / Bonus Actions / Reactions / Legendary ──
    sections = {}
    for h2 in soup.find_all("h2", class_="rub"):
        section_name = h2.get_text(strip=True)
        paragraphs = []
        for sibling in h2.next_siblings:
            if getattr(sibling, "name", None) == "h2":
                break
            if getattr(sibling, "name", None) == "p":
                paragraphs.append(sibling.get_text(strip=True))
        sections[section_name] = "\n".join(paragraphs)

    data["traits"]             = sections.get("Traits", "")
    data["actions"]            = sections.get("Actions", "")
    data["bonus_actions"]      = sections.get("Bonus Actions", "")
    data["reactions"]          = sections.get("Reactions", "")
    data["legendary_actions"]  = sections.get("Legendary actions", "")
    data["mythic_actions"]     = sections.get("Mythic Actions", "")

    # ── Description ───────────────────────────────────────────────────
    description_div = soup.find("div", class_="description")
    if description_div:
        data["description"] = description_div.get_text(strip=True)

    # ── Habitat & Treasure (both use div.habitat) ─────────────────────
    for hab_div in soup.find_all("div", class_="habitat"):
        text = hab_div.get_text(strip=True)
        if text.startswith("Habitat"):
            data["habitat"] = text.replace("Habitat:", "").replace("Habitat", "").strip()
        elif text.startswith("Treasure"):
            data["treasure"] = text.replace("Treasure:", "").replace("Treasure", "").strip()

    # ── Source ────────────────────────────────────────────────────────
    source_div = soup.find("div", class_="source")
    if source_div:
        data["source"] = source_div.get_text(strip=True)

    # ── Image URL ─────────────────────────────────────────────────────
    picture_div = soup.find("div", class_="picture")
    if picture_div:
        img_tag = picture_div.find("img")
        if img_tag and img_tag.get("src"):
            src = img_tag["src"]
            data["image_url"] = src if src.startswith("http") else BASE_URL + "/monster/" + src

    return data

def save_monster(name, detail_url):
    detail = scrape_monster_detail(detail_url)
    detail["name"] = name
    detail["detail_url"] = detail_url

    # Map cr_full → cr, then drop fields the model doesn't have
    if "cr_full" in detail:
        detail["cr"] = detail.pop("cr_full")
    detail.pop("type_line", None)

    # Convert ability scores to int safely
    for stat in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"):
        try:
            detail[stat] = int(detail.get(stat, ""))
        except (ValueError, TypeError):
            detail[stat] = None

    monster, created = Monster.objects.update_or_create(
        name=name,
        defaults=detail,
    )
    return monster, created


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    monsters = scrape_monster_list()
    print(f"Found {len(monsters)} monsters\n")

    # Test detail scraping on the first 2
    for m in monsters[:2]:
        print(f"--- {m['name']} ---")
        detail = scrape_monster_detail(m["detail_url"])
        for k, v in detail.items():
            if v:
                print(f"  {k}: {v}")
        print()

    # Show tarrasque
    for m in monsters:
        if (m['name']!='Tarrasque'):
            continue
        print(f"--- {m['name']} ---")
        detail = scrape_monster_detail(m["detail_url"])
        for k, v in detail.items():
            print(f"  {k}: {v}")
        print()
