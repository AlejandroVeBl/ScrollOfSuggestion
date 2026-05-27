from django.db import models


class Monster(models.Model):

    # ── Identity ──────────────────────────────────────────────────────
    name        = models.CharField(max_length=200, unique=True)
    size        = models.CharField(max_length=50,  blank=True)
    type        = models.CharField(max_length=100, blank=True)  # e.g. "Dragon (Chromatic)"
    alignment   = models.CharField(max_length=100, blank=True)
    source      = models.CharField(max_length=200, blank=True)
    image_url   = models.URLField(blank=True)
    detail_url  = models.URLField(blank=True)

    # ── Core stats ────────────────────────────────────────────────────
    ac          = models.CharField(max_length=50,  blank=True)  # e.g. "19" or "17 (natural armor)"
    hp          = models.CharField(max_length=100, blank=True)  # e.g. "195 (17d12 + 85)"
    speed       = models.CharField(max_length=200, blank=True)  # e.g. "40 ft., Fly 80 ft."
    initiative  = models.CharField(max_length=50,  blank=True)  # e.g. "+2 (12)"
    cr          = models.CharField(max_length=50,  blank=True)  # e.g. "14 (XP 11 500; PB +5)"

    # ── Ability scores ────────────────────────────────────────────────
    strength     = models.PositiveSmallIntegerField(null=True, blank=True)
    dexterity    = models.PositiveSmallIntegerField(null=True, blank=True)
    constitution = models.PositiveSmallIntegerField(null=True, blank=True)
    intelligence = models.PositiveSmallIntegerField(null=True, blank=True)
    wisdom       = models.PositiveSmallIntegerField(null=True, blank=True)
    charisma     = models.PositiveSmallIntegerField(null=True, blank=True)

    # ── Proficiencies & senses ────────────────────────────────────────
    skills      = models.CharField(max_length=300, blank=True)
    immunities  = models.CharField(max_length=300, blank=True)
    senses      = models.CharField(max_length=300, blank=True)
    languages   = models.CharField(max_length=300, blank=True)

    # ── Abilities & actions (long text) ───────────────────────────────
    traits              = models.TextField(blank=True)
    actions             = models.TextField(blank=True)
    bonus_actions       = models.TextField(blank=True)
    reactions           = models.TextField(blank=True)
    legendary_actions   = models.TextField(blank=True)

    # ── Flavour ───────────────────────────────────────────────────────
    description = models.TextField(blank=True)
    habitat     = models.CharField(max_length=200, blank=True)
    treasure    = models.CharField(max_length=200, blank=True)

    # ── Metadata ──────────────────────────────────────────────────────
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (CR {self.cr})"

    def cr_numeric(self):
        """Returns CR as a float for sorting/filtering (e.g. '1/2' → 0.5)."""
        raw = self.cr.split("(")[0].strip()  # drop the XP part
        if "/" in raw:
            num, den = raw.split("/")
            return float(num) / float(den)
        try:
            return float(raw)
        except ValueError:
            return 0.0