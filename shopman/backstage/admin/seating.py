"""Os lugares do salão — o denominador da ociosidade.

Config pura: cadastra-se uma vez e ninguém no balcão passa por aqui. Não há tela
de "ocupar mesa" e não vai haver: o vínculo comanda↔mesa foi vetado porque no
ato de abrir a comanda a pessoa nem sabe onde vai sentar.

O campo que decide a leitura é **conta na capacidade oficial**. Bistrô em pé e
bancão externo ficam fora — não porque não existam, mas porque são o espaço que
a casa usa quando bateu no teto. Deixá-los na conta esconderia justamente o
momento que interessa medir.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import SeatingSpot


@admin.register(SeatingSpot)
class SeatingSpotAdmin(ModelAdmin):
    list_display = ("label", "kind", "area", "seats", "capacity_display", "active_from", "active_until")
    list_filter = ("kind", "counts_in_capacity", "area")
    ordering = ("kind", "ref")
    fields = (
        "ref", "label", "kind", "area", "seats",
        "counts_in_capacity", "active_from", "active_until",
    )

    def get_readonly_fields(self, request, obj=None):
        return ("ref",) if obj else ()

    @display(
        description="capacidade",
        label={"conta no teto": "success", "só em dia cheio": "warning"},
    )
    def capacity_display(self, obj):
        return "conta no teto" if obj.counts_in_capacity else "só em dia cheio"

    def has_delete_permission(self, request, obj=None):
        # Apagar uma mesa reescreveria a ocupação do passado, que a leitura já
        # calculou com ela. Sai de circulação com "existiu até".
        return False
