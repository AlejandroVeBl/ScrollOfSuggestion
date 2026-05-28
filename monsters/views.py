import json

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse

from monsters.models import Monster
from monsters.utils.scraper import scrape_monster_list, scrape_monster_detail
from monsters.utils.whoosh_index import search_monsters
from monsters.utils.whoosh_index import build_index

# ── Helpers ─────────────────────
available_fields = {
    "name":               "Name",
    "traits":             "Traits",
    "actions":            "Actions",
    "bonus_actions":      "Bonus Actions",
    "reactions":          "Reactions",
    "legendary_actions":  "Legendary Actions",
    "description":        "Description",
}

# ── Helper.SaveMonster ─────────────────────

def save_monster(name, detail_url):
    '''
    Loads the monsters inside the DB
    '''
    detail = scrape_monster_detail(detail_url)
    detail["name"] = name
    detail["detail_url"] = detail_url

    if "cr_full" in detail:
        detail["cr"] = detail.pop("cr_full")
    detail.pop("type_line", None)

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

# ── Home ─────────────────────

def home(request):
    return render(request, 'monsters/home.html')
    
# ── Load ─────────────────────

def load(request):
    if request.method == "POST":
        try:
            monster_list = scrape_monster_list()
            total   = len(monster_list)
            created = 0
            updated = 0

            for m in monster_list:
                _, was_created = save_monster(m["name"], m["detail_url"])
                if was_created:
                    created += 1
                else:
                    updated += 1
            
            # Build Whoosh index from the now-populated database
            indexed = build_index()

            return JsonResponse({
                "status":  "ok",
                "message": f"Done! {total} monsters processed — {created} new, {updated} updated.",
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return render(request, "monsters/load.html")


# ── Catalogue ─────────────────────

def catalogue(request):
    query_str      = request.GET.get("q", "").strip()
    name_query     = request.GET.get("name", "").strip()
    type_filter    = request.GET.get("type", "").strip()
    size_filter    = request.GET.get("size", "").strip()
    align_filter   = request.GET.get("alignment", "").strip()
    habitat_filter = request.GET.get("habitat", "").strip()
    cr_min         = request.GET.get("cr_min", "").strip()
    cr_max         = request.GET.get("cr_max", "").strip()
    sort_by        = request.GET.get("sort", "name")
    sort_order     = request.GET.get("order", "asc")

    selected_fields = request.GET.getlist("fields")
    if not selected_fields:
        selected_fields = list(available_fields.keys())

    # ── If text query: start from Whoosh results ──────────────────────
    if query_str:
        pks = search_monsters(query_str, fields=selected_fields)
        monsters = Monster.objects.filter(pk__in=pks)
    else:
        monsters = Monster.objects.all()

    # ── DB filters ────────────────────────────────────────────────────
    if name_query:
        monsters = monsters.filter(name__icontains=name_query)
    if type_filter:
        monsters = monsters.filter(type__icontains=type_filter)
    if size_filter:
        monsters = monsters.filter(size__iexact=size_filter)
    if align_filter:
        monsters = monsters.filter(alignment__icontains=align_filter)
    if habitat_filter:
        monsters = monsters.filter(habitat__icontains=habitat_filter)

    all_monsters = list(monsters)

    # ── CR filter ─────────────────────────────────────────────────────
    def cr_to_float(cr_str):
        raw = cr_str.split("(")[0].strip()
        if "/" in raw:
            n, d = raw.split("/")
            return float(n) / float(d)
        try:
            return float(raw)
        except ValueError:
            return 0.0

    if cr_min:
        all_monsters = [m for m in all_monsters if cr_to_float(m.cr) >= float(cr_min)]
    if cr_max:
        all_monsters = [m for m in all_monsters if cr_to_float(m.cr) <= float(cr_max)]

    # ── If Whoosh query: preserve relevance order, else sort ──────────
    if not query_str:
        SIZE_ORDER = {
            "Tiny": 1, "Small": 2, "Medium": 3,
            "Large": 4, "Huge": 5, "Gargantuan": 6,
        }
        reverse = sort_order == "desc"
        if sort_by == "cr":
            all_monsters.sort(key=lambda m: cr_to_float(m.cr), reverse=reverse)
        elif sort_by == "size":
            all_monsters.sort(key=lambda m: SIZE_ORDER.get(m.size, 99), reverse=reverse)
        else:
            all_monsters.sort(key=lambda m: m.name, reverse=reverse)

    # ── Dropdown options ──────────────────────────────────────────────
    all_types      = Monster.objects.values_list("type",      flat=True).distinct().order_by("type")
    all_sizes      = Monster.objects.values_list("size",      flat=True).distinct().order_by("size")
    all_alignments = Monster.objects.values_list("alignment", flat=True).distinct().order_by("alignment")
    all_habitats   = Monster.objects.values_list("habitat",   flat=True).distinct().order_by("habitat")

    next_order = "desc" if sort_order == "asc" else "asc"

    context = {
        "monsters":         all_monsters,
        "total":            len(all_monsters),
        "all_types":        all_types,
        "all_sizes":        all_sizes,
        "all_alignments":   all_alignments,
        "all_habitats":     all_habitats,
        "query_str":        query_str,
        "name_query":       name_query,
        "type_filter":      type_filter,
        "size_filter":      size_filter,
        "align_filter":     align_filter,
        "habitat_filter":   habitat_filter,
        "cr_min":           cr_min,
        "cr_max":           cr_max,
        "sort_by":          sort_by,
        "sort_order":       sort_order,
        "next_order":       next_order,
        "available_fields": available_fields,
        "selected_fields":  selected_fields,
    }
    return render(request, "monsters/catalogue.html", context)

# ── Detail ─────────────────────

def detail(request, pk):
    monster = get_object_or_404(Monster, pk=pk)
    abilities = [
        ("STR", monster.strength),
        ("DEX", monster.dexterity),
        ("CON", monster.constitution),
        ("INT", monster.intelligence),
        ("WIS", monster.wisdom),
        ("CHA", monster.charisma),
    ]
    return render(request, "monsters/detail.html", {
        "monster":   monster,
        "abilities": abilities,
    })  


# ── Search ─────────────────────
def search(request):
    query_str = request.GET.get("q", "").strip()

    # Which fields to search — user can narrow via checkboxes
    available_fields = {
        "name":               "Name",
        "traits":             "Traits",
        "actions":            "Actions",
        "bonus_actions":      "Bonus Actions",
        "reactions":          "Reactions",
        "legendary_actions":  "Legendary Actions",
        "description":        "Description",
    }

    # Default: all fields checked
    selected_fields = request.GET.getlist("fields")
    if not selected_fields:
        selected_fields = list(available_fields.keys())

    monsters = []
    total    = 0

    if query_str:
        pks = search_monsters(query_str, fields=selected_fields)
        # Preserve Whoosh relevance order
        monsters_map = {m.pk: m for m in Monster.objects.filter(pk__in=pks)}
        monsters     = [monsters_map[pk] for pk in pks if pk in monsters_map]
        total        = len(monsters)

    context = {
        "query_str":        query_str,
        "monsters":         monsters,
        "total":            total,
        "available_fields": available_fields,
        "selected_fields":  selected_fields,
    }
    return render(request, "monsters/search.html", context)

# ── Build Index ─────────────────────

def build_index_view(request):
    if request.method == "POST":
        try:
            count = build_index()
            return JsonResponse({
                "status":  "ok",
                "message": f"Index built successfully — {count} monsters indexed.",
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    return JsonResponse({"status": "error", "message": "POST only."})

# ── Suggest ─────────────────────

def suggest(request):
    return render(request, 'monsters/suggest.html')
