import os
import re
import shelve
import numpy as np
from collections import Counter

from django.conf import settings

from monsters.utils.whoosh_index import open_index

SHELF_PATH = os.path.join(settings.BASE_DIR, "monster_vectors")

# ── Weights per feature group ─────────────────────────────────────────────────
WEIGHTS = {
    "cr":        3.0,   # high — also gets a hard ±2 filter at query time
    "habitat":   2.5,   # high
    "type":      1.5,
    "keywords":  1.5,
    "size":      1.0,
    "alignment": 0.8,
    "abilities": 0.5,
}

SIZE_ORDER = {
    "tiny": 1, "small": 2, "medium": 3,
    "large": 4, "huge": 5, "gargantuan": 6,
}

# Alignment decomposed into two independent axes
LAW_AXIS = {
    "lawful": 1.0, "neutral": 0.0, "chaotic": -1.0,
    "unaligned": 0.0, "any": 0.0,
}
GOOD_AXIS = {
    "good": 1.0, "neutral": 0.0, "evil": -1.0,
    "unaligned": 0.0, "any": 0.0,
}

NUM_KEYWORDS = 15   # top terms to extract per monster

# ── Keywords ────────────────────────────────────────────────────────────
def is_meaningful(word):
    """Filter out numbers, dice notation, and short tokens."""
    if re.search(r'[^a-z]', word):            return False  # anything non-alpha, avoid dice 2d+3...
    if len(word) < 4:                          return False  # too short
    return True


def get_keywords(pk):
    ix = open_index()
    if not ix:
        return set()

    from whoosh.query import Term
    with ix.searcher() as searcher:
        results = searcher.search(Term("id", str(pk)), limit=1)
        if not results:
            return set()

        docnum = results[0].docnum
        keywords = set()
        for field in ("description", "traits", "actions"):
            try:
                terms = searcher.key_terms([docnum], field, numterms=NUM_KEYWORDS)
                keywords.update(
                    word for word, score in terms
                    if is_meaningful(word)
                )
            except Exception:
                pass

    return keywords


# ── Vector builder ────────────────────────────────────────────────────────────

def build_vector_with_keywords(monster, monster_keywords, vocab, all_types, all_habitats):
    parts = []

    parts.append([monster.cr_numeric() / 30.0 * WEIGHTS["cr"]])

    size_val = SIZE_ORDER.get(monster.size.lower(), 3) / 6.0
    parts.append([size_val * WEIGHTS["size"]])

    type_vec = [WEIGHTS["type"] if t == monster.type else 0.0 for t in all_types]
    parts.append(type_vec)

    align = monster.alignment.lower()
    law_val  = next((v for k, v in LAW_AXIS.items()  if k in align), 0.0)
    good_val = next((v for k, v in GOOD_AXIS.items() if k in align), 0.0)
    parts.append([law_val * WEIGHTS["alignment"], good_val * WEIGHTS["alignment"]])

    monster_habitats = {h.strip().lower() for h in monster.habitat.split(",")}
    hab_vec = [WEIGHTS["habitat"] if h.lower() in monster_habitats else 0.0 for h in all_habitats]
    parts.append(hab_vec)

    abilities = [
        monster.strength     or 10,
        monster.dexterity    or 10,
        monster.constitution or 10,
        monster.intelligence or 10,
        monster.wisdom       or 10,
        monster.charisma     or 10,
    ]
    parts.append([(a / 30.0) * WEIGHTS["abilities"] for a in abilities])

    parts.append([
        WEIGHTS["keywords"] if w in monster_keywords else 0.0
        for w in vocab
    ])

    return np.array([v for part in parts for v in part], dtype=np.float32)


# ── Shelf read / write ────────────────────────────────────────────────────────

def build_vectors():
    """
    Builds feature vectors for every monster and persists them in a shelf.
    Call this after scraping (or when the shelf is stale).
    Returns the number of monsters indexed.
    """
    from monsters.models import Monster
    from monsters.utils.whoosh_index import get_monster_text

    monsters  = list(Monster.objects.all())
    all_types = sorted({m.type for m in monsters if m.type})
    all_habitats = sorted({
        h.strip() for m in monsters if m.habitat
        for h in m.habitat.split(",") if h.strip()
    })

    # Build vocab from Whoosh key_terms across all monsters
    all_keywords = Counter()
    monster_keywords_cache = {}

    for m in monsters:
        kws = get_keywords(m.pk)
        monster_keywords_cache[m.pk] = kws
        all_keywords.update(kws)

    # Keep terms that appear in at least 2 monsters but fewer than 70%
    n = len(monsters)
    vocab = sorted([
        w for w, count in all_keywords.most_common(300)
        if 2 <= count <= n * 0.7
    ][:150])

    with shelve.open(SHELF_PATH) as shelf:
        shelf["__vocab__"]    = vocab
        shelf["__types__"]    = all_types
        shelf["__habitats__"] = all_habitats

        for m in monsters:
            # Pass cached keywords so we don't re-query Whoosh
            vec = build_vector_with_keywords(
                m, monster_keywords_cache[m.pk],
                vocab, all_types, all_habitats
            )
            shelf[str(m.pk)] = vec

    return len(monsters)


def load_all_vectors():
    try:
        with shelve.open(SHELF_PATH) as shelf:
            vocab        = shelf.get("__vocab__",    [])
            all_types    = shelf.get("__types__",    [])
            all_habitats = shelf.get("__habitats__", [])
            vectors = {
                int(k): v for k, v in shelf.items()
                if not k.startswith("__")
            }
        return vectors, vocab, all_types, all_habitats
    except Exception:
        return {}, [], [], []


def load_vector(pk):
    try:
        with shelve.open(SHELF_PATH) as shelf:
            return shelf.get(str(pk))
    except Exception:
        return None

# ── Profile vector ────────────────────────────────────────────────────────────────

def build_profile_vector(monster_pks):
    """
    Combines the vectors of the selected monsters into a single profile vector.
    monster_pks is ordered oldest → newest (last = most recent).
    More recent monsters get exponentially higher weight.
    Returns a numpy array or None if no vectors could be loaded.
    """
    # Exponential recency weights — last monster counts most
    # e.g. 3 monsters → weights [1, 2, 4], normalised to [0.14, 0.29, 0.57]
    n = len(monster_pks)
    raw_weights = [2 ** i for i in range(n)]
    total = sum(raw_weights)
    weights = [w / total for w in raw_weights]

    profile = None
    for pk, weight in zip(monster_pks, weights):
        vec = load_vector(pk)
        if vec is None:
            continue
        if profile is None:
            profile = vec * weight
        else:
            profile += vec * weight

    return profile

# ── Similarity ────────────────────────────────────────────────────────────────

def cosine_similarity(a, b):
    """Cosine similarity between two numpy vectors. Returns float in [0, 1]."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

# ── Recommendations ────────────────────────────────────────────────────────────────

def get_recommendations(monster_pks, top_n=20, cr_range=2.0):
    """
    Given an ordered list of monster PKs (oldest → newest), returns the
    top_n recommended monsters by cosine similarity to the profile vector.

    Hard filters applied before scoring:
      - Monster must not already be in monster_pks
      - Monster CR must be within ±cr_range of the most recent monster's CR

    Returns a list of (Monster, score) tuples sorted by score descending.
    """
    from monsters.models import Monster

    if not monster_pks:
        return []

    # Build the profile from the selected monsters
    profile = build_profile_vector(monster_pks)
    if profile is None:
        return []

    # CR of the most recent monster (last in list) — used for hard filter
    most_recent = Monster.objects.get(pk=monster_pks[-1])
    recent_cr   = most_recent.cr_numeric()
    cr_min      = max(0.0, recent_cr - cr_range)
    cr_max      = recent_cr + cr_range

    # Load all vectors
    all_vectors, _, _, _ = load_all_vectors()

    selected_set = set(monster_pks)

    scores = []
    for pk, vec in all_vectors.items():
        # Skip already selected monsters
        if pk in selected_set:
            continue

        # CR hard filter
        try:
            monster = Monster.objects.get(pk=pk)
        except Monster.DoesNotExist:
            continue

        if not (cr_min <= monster.cr_numeric() <= cr_max):
            continue

        score = cosine_similarity(profile, vec)
        scores.append((monster, score))

    # Sort by score descending, return top_n
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_n]