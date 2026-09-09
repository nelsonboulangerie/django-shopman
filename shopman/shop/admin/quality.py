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
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("label", "ref", "rank", "markdown_display", "is_default", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active", "is_default")
    search_fields = ("ref", "label")
    ordering = ("-rank",)
    fieldsets = (
        ("Identificação", {"fields": ("ref", "label", "is_active")}),
        (
            "Política comercial",
            {
                "fields": (("rank", "markdown_percent"), "is_default"),
                "description": (
                    "O grau define sozinho o desconto. Exatamente um grau ativo deve ser o padrão, "
                    "e ao menos um grau ativo precisa representar preço cheio."
                ),
            },
        ),
    )

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
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("label", "ref", "hint", "veto_display", "position", "is_active")
    list_editable = ("position", "is_active")
    list_filter = ("is_active", "forces_discard")
    search_fields = ("ref", "label", "hint")
    ordering = ("position",)
    fieldsets = (
        ("Identificação", {"fields": ("ref", "label", "hint", "is_active")}),
        (
            "Política operacional",
            {
                "fields": (("forces_discard", "position"),),
                "description": (
                    "O defeito registra a causa. Somente risco de segurança alimentar deve "
                    "obrigar descarte; o grau continua sendo o único eixo de preço."
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        return ("ref",) if obj else ()

    @display(description="veto", label={"descarta": "danger", "vende com desconto": "success"})
    def veto_display(self, obj):
        return "descarta" if obj.forces_discard else "vende com desconto"

    def has_delete_permission(self, request, obj=None):
        # As refs permanecem em itens históricos; o catálogo usa inativação.
        return False
