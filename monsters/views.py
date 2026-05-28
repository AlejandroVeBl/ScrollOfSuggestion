import json

from django.shortcuts import render
from django.http import JsonResponse

from monsters.models import Monster
from monsters.utils.scraper import scrape_monster_list, scrape_monster_detail

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

def home(request):
    return render(request, 'monsters/home.html')

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

            return JsonResponse({
                "status":  "ok",
                "message": f"Done! {total} monsters processed — {created} new, {updated} updated.",
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return render(request, "monsters/load.html")



def catalogue(request):
    return render(request, 'monsters/catalogue.html')

def search(request):
    return render(request, 'monsters/search.html')

def suggest(request):
    return render(request, 'monsters/suggest.html')
