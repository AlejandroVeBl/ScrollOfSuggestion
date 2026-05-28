import requests
from bs4 import BeautifulSoup

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# from monsters.models import Monster

BASE_URL = "https://www.aidedd.org"
LIST_URL = f"{BASE_URL}/monster/"

def get_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,        # waits 2s, 4s, 8s between retries
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    return session


def scrape_monster_list():
    """
    Scrapes only names and detail URLs from the main monster table.
    All stats are fetched from each monster's detail page.
    """
    session = get_session()
    response = session.get(LIST_URL, timeout=15)
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
    session = get_session()
    response = session.get(detail_url, timeout=15)
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

    # ── AC / HP / Speed ───────────────────────────────────────────────
    for strong in red_div.find_all("strong"):
        label = strong.get_text(strip=True)
        sibling = strong.next_sibling
        value = sibling.strip() if sibling and isinstance(sibling, str) else ""
        if label == "AC":
            data["ac"] = value
        elif label == "HP":
            data["hp"] = value
        elif label == "Speed":
            data["speed"] = value
        elif label == "Skills":
            data["skills"] = value
        elif label == "Resistances":
            data["resistances"] = value
        elif label == "Immunities":
            data["immunities"] = value
        elif label == "Senses":
            data["senses"] = value
        elif label == "Languages":
            data["languages"] = value
        elif label == "CR":
            data["cr_full"] = value

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

    # ── Sections ──────────────────────────────────────────────────────
    sections = {}
    for h2 in soup.find_all("h2", class_="rub"):
        section_name = h2.get_text(strip=True).lower()
        paragraphs = []
        for sibling in h2.next_siblings:
            if getattr(sibling, "name", None) == "h2":
                break
            if getattr(sibling, "name", None) == "p":
                paragraphs.append(sibling.get_text(strip=True))
        sections[section_name] = "\n".join(paragraphs)

    data["traits"]            = sections.get("traits", "")
    data["actions"]           = sections.get("actions", "")
    data["bonus_actions"]     = sections.get("bonus actions", "")
    data["reactions"]         = sections.get("reactions", "")
    data["legendary_actions"] = sections.get("legendary actions", "")

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
