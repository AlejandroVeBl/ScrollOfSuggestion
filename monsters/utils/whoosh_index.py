import os
import shutil
from django.conf import settings
from whoosh import index
from whoosh.fields import Schema, TEXT, KEYWORD, NUMERIC, ID
from whoosh.qparser import MultifieldParser, OrGroup
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
    Drops and rebuilds the Whoosh index from the Monster database.
    Call this from the load view after scraping.
    """
    from monsters.models import Monster

    if os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR)
    os.makedirs(INDEX_DIR)

    ix = index.create_in(INDEX_DIR, get_schema())
    writer = ix.writer()

    for m in Monster.objects.all():
        writer.add_document(
            id                = str(m.pk),
            name              = m.name              or "",
            traits            = m.traits            or "",
            actions           = m.actions           or "",
            bonus_actions     = m.bonus_actions     or "",
            reactions         = m.reactions         or "",
            legendary_actions = m.legendary_actions or "",
            description       = m.description       or "",
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
            parser = MultifieldParser(fields, schema=ix.schema, group=OrGroup)
            query  = parser.parse(query_str)
            hits   = searcher.search(query, limit=limit)

        results = [int(hit["id"]) for hit in hits]

    return results