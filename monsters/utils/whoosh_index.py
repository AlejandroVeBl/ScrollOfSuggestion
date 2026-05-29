import os
import shutil
from django.conf import settings
from whoosh import index
from whoosh.fields import Schema, TEXT, KEYWORD, NUMERIC, ID
from whoosh.qparser import MultifieldParser, OrGroup, AndGroup
from whoosh.query import Every


INDEX_DIR = os.path.join(settings.BASE_DIR, "whoosh_index")


def get_schema():
    return Schema(
        id                = ID(stored=True, unique=True),
        name              = TEXT(stored=True),
        traits            = TEXT(stored=True),
        actions           = TEXT(stored=True),
        bonus_actions     = TEXT(stored=True),
        reactions         = TEXT(stored=True),
        legendary_actions = TEXT(stored=True),
        description       = TEXT(stored=True),
    )


def build_index():
    """
    Rebuilds the Whoosh index by re-scraping text content for each monster.
    Used when the index is lost but the DB is intact.
    """
    from monsters.models import Monster
    from monsters.utils.scraper import scrape_monster_detail

    if os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR)
    os.makedirs(INDEX_DIR)

    ix = index.create_in(INDEX_DIR, get_schema())
    writer = ix.writer()

    for m in Monster.objects.all():
        detail = scrape_monster_detail(m.detail_url)
        writer.add_document(
            id                = str(m.pk),
            name              = m.name,
            traits            = detail.get("traits",            ""),
            actions           = detail.get("actions",           ""),
            bonus_actions     = detail.get("bonus_actions",     ""),
            reactions         = detail.get("reactions",         ""),
            legendary_actions = detail.get("legendary_actions", ""),
            description       = detail.get("description",       ""),
        )

    writer.commit()
    return ix.doc_count()


def open_index():
    if not os.path.exists(INDEX_DIR) or not index.exists_in(INDEX_DIR):
        return None
    return index.open_dir(INDEX_DIR)


def search_monsters(query_str, fields=None, limit=50):
    """
    Search the Whoosh index.
    fields: list of field names to search — defaults to all text fields.
    Returns a list of monster PKs in relevance order.
    """
    ix = open_index()
    if not ix:
        return []

    if not fields:
        fields = [
            "name",
            "traits",
            "actions",
            "bonus_actions",
            "reactions",
            "legendary_actions",
            "description",
        ]

    results = []
    with ix.searcher() as searcher:
        if not query_str.strip():
            # Empty query → return everything
            from whoosh.query import Every
            hits = searcher.search(Every(), limit=limit)
        else:
            parser = MultifieldParser(fields, schema=ix.schema, group=AndGroup)
            query  = parser.parse(query_str)
            hits   = searcher.search(query, limit=limit)

        results = [int(hit["id"]) for hit in hits]

    return results

def get_monster_text(pk):
    """
    Fetches the stored text fields for a single monster from the Whoosh index.
    Returns a dict with traits, actions, bonus_actions, reactions,
    legendary_actions and description.
    """
    ix = open_index()
    if not ix:
        return {}

    from whoosh.query import Term
    with ix.searcher() as searcher:
        results = searcher.search(Term("id", str(pk)), limit=1)
        if not results:
            return {}
        hit = results[0]
        return {
            "traits":             hit.get("traits",             ""),
            "actions":            hit.get("actions",            ""),
            "bonus_actions":      hit.get("bonus_actions",      ""),
            "reactions":          hit.get("reactions",          ""),
            "legendary_actions":  hit.get("legendary_actions",  ""),
            "description":        hit.get("description",        ""),
        }