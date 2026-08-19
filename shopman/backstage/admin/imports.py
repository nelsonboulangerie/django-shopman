"""O que entrou de fora no B.I. — lotes de importação e vendas históricas.

Trilha, não operação: nada aqui se edita. O lote nasce do comando de ingestão
(``ingest_yooga``) e a venda histórica é o dado do sistema antigo como o export
o entregou; reescrever qualquer um à mão apagaria a diferença entre "o que a
fonte disse" e "o que alguém achou melhor". Corrigir é reimportar (``--rebuild``).

Duas perguntas do gestor moram aqui: "que arquivo entrou, quando, e deu certo?"
(lote, com hash e contagens — inclusive os que FALHARAM, com o motivo) e "o que
o histórico diz desta venda?" (a venda com os itens embaixo, no contexto que
lhes dá sentido).
"""

from __future__ import annotations

from django.contrib import admin
from shopman.utils import unfold_badge, unfold_badge_numeric
from shopman.utils.monetary import format_money
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import DailySalesFact, HistoricalSale, HistoricalSaleItem, ImportBatch


class _ReadOnly:
    """Trilha: lê-se, não se escreve. Vale para lista, formulário e inline."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImportBatch)
class ImportBatchAdmin(_ReadOnly, ModelAdmin):
    list_display = (
        "imported_at", "source", "file_name", "status_display",
        "sales_created", "sales_skipped", "sales_completed", "items_created",
    )
    list_filter = ("source", "status")
    date_hierarchy = "imported_at"
    ordering = ("-imported_at",)
    search_fields = ("file_name", "file_sha256", "notes")
    fields = (
        "source", "status", "imported_at", "imported_by", "file_name", "file_sha256",
        "rows_read", "sales_created", "sales_skipped", "sales_completed", "items_created",
        "error", "notes",
    )
    readonly_fields = fields

    @display(description="estado", label={"concluído": "success", "falhou": "danger"})
    def status_display(self, obj):
        return obj.get_status_display()


class HistoricalSaleItemInline(_ReadOnly, admin.TabularInline):
    model = HistoricalSaleItem
    extra = 0
    fields = ("seq", "product_name", "sku", "category", "qty", "unit_price_display", "line_total_display")
    readonly_fields = fields

    @display(description="preço unitário")
    def unit_price_display(self, obj):
        return f"R$ {format_money(obj.unit_price_q)}"

    @display(description="total da linha")
    def line_total_display(self, obj):
        return f"R$ {format_money(obj.line_total_q)}"


@admin.register(HistoricalSale)
class HistoricalSaleAdmin(_ReadOnly, ModelAdmin):
    list_display = (
        "occurred_at", "source", "external_id", "total_display", "payment",
        "channel_display", "customer_name", "batch",
    )
    list_filter = ("source", "is_delivery", "batch")
    date_hierarchy = "occurred_at"
    ordering = ("-occurred_at",)
    search_fields = ("external_id", "customer_name", "operator")
    list_select_related = ("batch",)
    inlines = (HistoricalSaleItemInline,)
    fields = (
        "source", "external_id", "batch", "occurred_at", "total_display", "discount_q",
        "surcharge_q", "payment", "operator", "channel_display", "modality", "origin",
        "table_label", "customer_external_id", "customer_name", "metadata", "ingested_at",
    )
    readonly_fields = fields

    @display(description="total")
    def total_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.total_q)}", "base")

    @display(description="canal")
    def channel_display(self, obj):
        # O único rótulo confiável do histórico. Mesa/balcão crus ficam nos
        # campos deles, sem virar canal.
        return unfold_badge("delivery" if obj.is_delivery else "loja", "blue" if obj.is_delivery else "base")


@admin.register(DailySalesFact)
class DailySalesFactAdmin(_ReadOnly, ModelAdmin):
    """A série diária como a projeção a lê — para conferir, não para editar.

    Recomputável do zero (`refresh_bi_daily_series --all`); editar à mão criaria
    um número que nenhuma fonte sustenta. `refreshed_at` diz há quanto tempo o
    worker passou por aquele dia.
    """

    list_display = (
        "date", "source", "orders", "revenue_display", "cash_orders", "payments_known",
        "historical_dropped", "refreshed_at",
    )
    list_filter = ("source",)
    date_hierarchy = "date"
    ordering = ("-date",)
    fields = (
        "date", "source", "orders", "revenue_display", "cash_orders", "payments_known",
        "historical_dropped", "refreshed_at",
    )
    readonly_fields = fields

    @display(description="faturamento")
    def revenue_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.revenue_q)}", "base")
