from django.contrib import admin
from monsters.models import Monster

@admin.register(Monster)
class MonsterAdmin(admin.ModelAdmin):
    list_display  = ("name", "size", "type", "alignment", "cr", "habitat")
    search_fields = ("name", "type", "alignment", "habitat")
    list_filter   = ("size", "type", "alignment")
    ordering      = ("name",)