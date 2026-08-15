"""Motivos de episódio e o histórico do que houve.

Config, não operação: quem responde "o que houve?" é o operador no fechamento;
aqui o gestor edita o vocabulário — quais motivos aparecem como opção, em que
ordem, e **quais atrapalharam a venda** (esses tiram o dia da amostra que ensina
quanto produzir).

O histórico de episódios entra só para leitura: o registro nasce da detecção
automática e da resposta do operador, e reescrevê-lo à mão apagaria a diferença
entre o que o sistema mediu e o que alguém explicou.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import OperationEpisode, OperationEpisodeKind


@admin.register(OperationEpisodeKind)
class OperationEpisodeKindAdmin(ModelAdmin):
    list_display = ("label", "ref", "hint", "demand_display", "position", "is_active")
    list_editable = ("position", "is_active")
    ordering = ("position",)
    fields = ("ref", "label", "hint", "affects_demand", "position", "is_active")

    def get_readonly_fields(self, request, obj=None):
        # O código é fixo (episódios gravados apontam para ele); o rótulo edita.
        return ("ref",) if obj else ()

    @display(
        description="efeito na venda",
        label={"tira o dia da previsão": "danger", "mantém o dia": "success"},
    )
    def demand_display(self, obj):
        return "tira o dia da previsão" if obj.affects_demand else "mantém o dia"

    def has_delete_permission(self, request, obj=None):
        # Apagar um motivo já usado deixaria episódios órfãos e mudaria a
        # leitura do passado. Sai de circulação desativando.
        return False


@admin.register(OperationEpisode)
class OperationEpisodeAdmin(ModelAdmin):
    list_display = (
        "started_at", "signal_display", "kind", "status_display", "resolved_by",
    )
    list_filter = ("status", "kind", "detector")
    date_hierarchy = "started_at"
    ordering = ("-started_at",)

    def has_add_permission(self, request):
        return False  # o registro nasce da detecção, não do teclado

    def has_change_permission(self, request, obj=None):
        return False  # a resposta é dada no fechamento, com as opções

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="o que o sistema mediu")
    def signal_display(self, obj):
        return obj.detected_signal or "—"

    @display(
        description="situação",
        label={
            "A confirmar": "warning",
            "Confirmado": "success",
            "Descartado": "info",
        },
    )
    def status_display(self, obj):
        return obj.get_status_display()
