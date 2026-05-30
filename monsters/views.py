import json
import os
import shutil

from whoosh import index as whoosh_index_module

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator

from monsters.models import Monster
from monsters.utils.scraper import scrape_monster_list, scrape_monster_detail
from monsters.utils.whoosh_index import (
    open_index, get_schema, INDEX_DIR,
    build_index, search_monsters, get_monster_text
)
from monsters.utils.recommender import build_vectors, get_recommendations, build_profile_vector, load_all_vectors

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

TEXT_FIELDS = ("traits", "actions", "bonus_actions", "reactions",
               "legendary_actions", "mythic_actions", "description")

# ── Helper.SaveMonster ─────────────────────

def save_monster(name, detail_url):
    detail = scrape_monster_detail(detail_url)
    detail["name"] = name
    detail["detail_url"] = detail_url

    if "cr_full" in detail:
        detail["cr"] = detail.pop("cr_full")
    detail.pop("type_line", None)

    # Convert ability scores to int safely
    for stat in ("strength", "dexterity", "constitution",
                 "intelligence", "wisdom", "charisma"):
        try:
            detail[stat] = int(detail.get(stat, ""))
        except (ValueError, TypeError):
            detail[stat] = None

    # Separate text fields for Whoosh before saving to DB
    text_data = {field: detail.pop(field, "") or "" for field in TEXT_FIELDS}

    # Save structured data to SQLite
    monster, created = Monster.objects.update_or_create(
        name=name,
        defaults=detail,
    )

    # Save text data to Whoosh
    ix = open_index()
    if ix:
        writer = ix.writer()
        writer.update_document(
            id                = str(monster.pk),
            name              = monster.name,
            traits            = text_data.get("traits",            ""),
            actions           = text_data.get("actions",           ""),
            bonus_actions     = text_data.get("bonus_actions",     ""),
            reactions         = text_data.get("reactions",         ""),
            legendary_actions = text_data.get("legendary_actions", ""),
            description       = text_data.get("description",       ""),
        )
        writer.commit()

    return monster, created

# ── Home ─────────────────────

def home(request):
    return render(request, 'monsters/home.html')
    
# ── Load ─────────────────────

@staff_member_required
def load(request):
    if request.method == "POST":
        try:
            # Create a fresh empty index before scraping
            if os.path.exists(INDEX_DIR):
                shutil.rmtree(INDEX_DIR)
            os.makedirs(INDEX_DIR)
            whoosh_index_module.create_in(INDEX_DIR, get_schema())

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
            
            build_vectors()

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
    
    paginator = Paginator(all_monsters, 40)   # 40 per page
    page_num  = request.GET.get("page", 1)
    page_obj  = paginator.get_page(page_num)

    context = {
        "monsters":         page_obj,         # ← page_obj instead of all_monsters
        "page_obj":         page_obj,
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

    # Text content comes from Whoosh, not SQLite
    text = get_monster_text(pk)

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
        "text":      text,
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

@staff_member_required
def build_index_view(request):
    if request.method == "POST":
        try:
            count   = build_index()
            vectors = build_vectors()    
            return JsonResponse({
                "status":  "ok",
                "message": f"Index built — {count} monsters indexed, {vectors} vectors built.",
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    return JsonResponse({"status": "error", "message": "POST only."})

# ── Suggest ─────────────────────

def suggest_autocomplete(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    monsters = Monster.objects.filter(name__icontains=q).values("id", "name", "cr", "type")[:10]
    return JsonResponse({"results": list(monsters)})

def suggest(request):
    # Warn the template if vectors haven't been built yet
    vecs, _, _, _ = load_all_vectors()
    return render(request, "monsters/suggest.html", {"vectors_ready": bool(vecs)})


def recommend(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST only."})

    try:
        # Check shelf exists
        vecs, _, _, _ = load_all_vectors()
        if not vecs:
            return JsonResponse({
                "status":  "error",
                "message": "Vectors not built yet — go to Load Data and click 'Build Index'.",
            })

        data = json.loads(request.body)
        pks  = [int(pk) for pk in data.get("ids", [])]

        if not pks:
            return JsonResponse({"status": "error", "message": "No monsters selected."})

        results = get_recommendations(pks, top_n=20)

        if not results:
            return JsonResponse({
                "status":  "error",
                "message": "No recommendations found — try different monsters or a wider CR range.",
            })

        recommendations = [
            {
                "id":        m.pk,
                "name":      m.name,
                "cr":        m.cr,
                "type":      m.type,
                "size":      m.size,
                "alignment": m.alignment,
                "habitat":   m.habitat,
                "ac":        m.ac,
                "hp":        m.hp,
                "image_url": m.image_url,
                "score":     round(score, 3),
            }
            for m, score in results
        ]
        return JsonResponse({"status": "ok", "results": recommendations})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})