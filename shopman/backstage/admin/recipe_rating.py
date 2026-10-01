"""Nota de receita: os critérios (catálogo editável) e as avaliações (leitura).

Config, não operação: quem AVALIA é o operador, na receita do app de Produção;
aqui o gestor decide quais critérios a tela pergunta, com que nome, com que
explicação e em que ordem. O molde é o ``QualityDefectAdmin`` (``shop/admin/
quality.py``): nada fixo em código, critério não se apaga (há notas apontando
para ele), desativa-se.

As avaliações aparecem só para leitura: quem avaliou, quando e com que notas.
Nota é opinião de quem provou; o Admin não a reescreve.
"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import Avg
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from shopman.backstage.models import RecipeRatingCriterion, RecipeVersionRating, RecipeVersionRatingScore


@admin.register(RecipeRatingCriterion)
class RecipeRatingCriterionAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("name", "description", "position", "is_active")
    list_editable = ("position", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("position", "name")
    fieldsets = (
        ("Identificação", {"fields": ("name", "description", "is_active")}),
        (
            "Na tela de avaliar",
            {
                "fields": ("position",),
                "description": (
                    "O operador dá uma nota de 0 a 5 para cada critério ativo, nesta ordem. "
                    "Desativar tira o critério da tela e das médias; as notas antigas ficam guardadas."
                ),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        # As notas apontam para o critério; apagar reescreveria a média de
        # versões já avaliadas. Desativa-se editando.
        return False


class RecipeVersionRatingScoreInline(TabularInline):
    model = RecipeVersionRatingScore
    extra = 0
    fields = ("criterion", "score")
    readonly_fields = ("criterion", "score")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RecipeVersionRating)
class RecipeVersionRatingAdmin(ModelAdmin):
    list_display = ("version_ref_display", "operator_ref", "average_display", "updated_at")
    list_filter = ("entry_ref",)
    search_fields = ("entry_ref", "operator_ref")
    ordering = ("-updated_at",)
    fields = ("entry_ref", "version_number", "operator_ref", "created_at", "updated_at")
    readonly_fields = ("entry_ref", "version_number", "operator_ref", "created_at", "updated_at")
    inlines = (RecipeVersionRatingScoreInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(score_average=Avg("scores__score"))

    @display(description="versão", ordering="entry_ref")
    def version_ref_display(self, obj):
        return obj.version_ref

    @display(description="média das notas", ordering="score_average")
    def average_display(self, obj):
        value = getattr(obj, "score_average", None)
        if value is None:
            return "sem nota"
        return f"{value:.1f}".replace(".", ",")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
