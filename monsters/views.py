from django.shortcuts import render
from django.http import JsonResponse
import json
from django.shortcuts import render
from django.http import JsonResponse
from monsters.utils.scraper import scrape_monster_list, save_monster


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
