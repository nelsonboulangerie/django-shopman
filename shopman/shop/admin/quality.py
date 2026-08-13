"""Catálogos de qualidade da fornada — escala e defeitos editáveis (ADR-017).

Config, não operação: quem FECHA a fornada é o quiosque de produção; aqui o
gestor edita a política — rótulos, percentuais por grau, dicas e o veto.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import QualityDefect, QualityGrade


@admin.register(QualityGrade)
class QualityGradeAdmin(ModelAdmin):
    list_display = ("label", "ref", "rank", "markdown_display", "is_default")
    ordering = ("-rank",)
    fields = ("ref", "label", "rank", "markdown_percent", "is_default")

    def get_readonly_fields(self, request, obj=None):
        # O código é fixo (o quiosque e o finish falam por ele); o rótulo edita.
        return ("ref",) if obj else ()

    @display(description="desconto")
    def markdown_display(self, obj):
        # Preço cheio fica visualmente distinto de degrau com desconto.
        return "preço cheio" if not obj.markdown_percent else f"−{obj.markdown_percent}%"

    def has_delete_permission(self, request, obj=None):
        # A escala tem 4 degraus por desenho; apagar degrau órfão de lote
        # gravado quebraria a leitura do histórico. Desativa-se editando.
        return False


@admin.register(QualityDefect)
class QualityDefectAdmin(ModelAdmin):
    list_display = ("label", "ref", "hint", "veto_display", "position", "is_active")
    list_editable = ("position", "is_active")
    ordering = ("position",)
    fields = ("ref", "label", "hint", "forces_discard", "position", "is_active")

    def get_readonly_fields(self, request, obj=None):
        return ("ref",) if obj else ()

    @display(description="veto", label={"descarta": "danger", "vende com desconto": "success"})
    def veto_display(self, obj):
        return "descarta" if obj.forces_discard else "vende com desconto"
