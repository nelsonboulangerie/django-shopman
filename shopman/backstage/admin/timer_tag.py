"""Etiquetas de timer — a fileira de disparo rápido do fournil.

Config, não operação: quem DISPARA é a página ``/timers`` do app de Produção;
aqui o gestor decide o que fica na fileira, com que nome, por quanto tempo e em
que ordem. A coluna ``origem`` é a razão principal desta tela existir: o que o
operador criou no turno aparece marcado, para ser curado — renomeado, ajustado
no tempo, desativado — em vez de virar entulho invisível.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import TimerTag, TimerTagOrigin


@admin.register(TimerTag)
class TimerTagAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("label", "ref", "duration_display", "origin_display", "position", "is_active")
    list_editable = ("position", "is_active")
    list_filter = ("is_active", "origin")
    search_fields = ("ref", "label")
    ordering = ("position", "label")
    fieldsets = (
        ("Identificação", {"fields": ("ref", "label", "is_active")}),
        (
            "Disparo",
            {
                "fields": (("minutes", "position"),),
                "description": (
                    "Um toque no chip dispara esta duração, sem digitação e sem confirmação. "
                    "O operador ainda pode somar minutos depois, no card."
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        # O ref é a chave do chip na tela; o rótulo edita à vontade. A origem é
        # fato de como a etiqueta nasceu — curar não reescreve isso.
        return ("ref", "origin") if obj else ()

    # Apagar é permitido aqui, ao contrário dos outros catálogos da casa, e o
    # motivo é factual: nenhum fato guarda a ref de uma etiqueta. O timer vive
    # no dispositivo (localStorage) e nada no banco aponta para cá, então apagar
    # não reescreve passado nenhum. Curar o entulho de um turno não deveria
    # custar uma lista de inativas crescendo para sempre.

    @display(description="duração")
    def duration_display(self, obj):
        if obj.minutes < 60:
            return f"{obj.minutes} min"
        hours, rest = divmod(obj.minutes, 60)
        return f"{hours} h {rest} min" if rest else f"{hours} h"

    @display(
        description="origem",
        label={"do fournil": "warning", "da casa": "success"},
    )
    def origin_display(self, obj):
        return "do fournil" if obj.origin == TimerTagOrigin.OPERATOR else "da casa"
