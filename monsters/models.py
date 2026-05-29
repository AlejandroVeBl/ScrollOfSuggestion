from django.db import models


class Monster(models.Model):

    # ── Identity ──────────────────────────────────────────────────────
    name        = models.CharField(max_length=200, unique=True)
    size        = models.CharField(max_length=50,  blank=True)
    type        = models.CharField(max_length=100, blank=True)
    alignment   = models.CharField(max_length=100, blank=True)
    source      = models.CharField(max_length=200, blank=True)
    image_url   = models.URLField(blank=True)
    detail_url  = models.URLField(blank=True)

    # ── Core stats ────────────────────────────────────────────────────
    ac          = models.CharField(max_length=50,  blank=True)
    hp          = models.CharField(max_length=100, blank=True)
    speed       = models.CharField(max_length=200, blank=True)
    initiative  = models.CharField(max_length=50,  blank=True)
    cr          = models.CharField(max_length=50,  blank=True)

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
    resistances = models.CharField(max_length=300, blank=True)
    senses      = models.CharField(max_length=300, blank=True)
    languages   = models.CharField(max_length=300, blank=True)

    # ── Flavour (non-text) ────────────────────────────────────────────
    habitat     = models.CharField(max_length=200, blank=True)
    treasure    = models.CharField(max_length=200, blank=True)

    # ── Metadata ──────────────────────────────────────────────────────
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (CR {self.cr})"

    def cr_numeric(self):
        raw = self.cr.split("(")[0].strip()
        if "/" in raw:
            num, den = raw.split("/")
            return float(num) / float(den)
        try:
            return float(raw)
        except ValueError:
            return 0.0