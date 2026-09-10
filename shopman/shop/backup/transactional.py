"""Janela de conferência dos transacionais — export SOMENTE-LEITURA.

O transacional (pedidos, ledger de estoque, livro-caixa, pagamentos, fornadas)
entra no arquivo do cofre para ser LIDO: conferir num Sheets, cruzar com o
extrato, auditar um dia. Ele **não volta pelo import**, de propósito — o ledger
é imutável e o livro-caixa é append-only por lei da casa; a única restauração
legítima dessas tabelas é o backup do Postgres. O ``import_backup`` recusa
essas abas com erro, para que ninguém "conserte" um pedido por planilha.

Por serem só de leitura, os resources escolhem colunas pela LEGIBILIDADE
(``sku`` no lugar de FK numérica, ``order__ref`` no lugar de id) — sem o
compromisso de round-trip dos resources curados.
"""

from __future__ import annotations

from import_export import fields, resources
from shopman.cashman.models import Entry
from shopman.craftsman.models import WorkOrder
from shopman.orderman.models import Order, OrderItem
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Move

from shopman.shop.backup import registry


def _col(column_name: str, attribute: str) -> fields.Field:
    return fields.Field(column_name=column_name, attribute=attribute, readonly=True)


class OrderSnapshotResource(resources.ModelResource):
    """Pedidos sem o ``snapshot`` (pesado e redundante com as linhas de item)."""

    class Meta:
        model = Order
        fields = (
            "ref", "status", "channel_ref", "external_ref", "currency", "total_q",
            "data", "created_at", "accepted_at", "preparing_at", "ready_at",
            "dispatched_at", "delivered_at", "completed_at", "cancelled_at",
        )
        export_order = fields


class OrderItemSnapshotResource(resources.ModelResource):
    order = _col("order__ref", "order__ref")

    class Meta:
        model = OrderItem
        fields = ("order", "line_id", "sku", "name", "qty", "unit_price_q", "line_total_q")
        export_order = fields


class MoveSnapshotResource(resources.ModelResource):
    sku = _col("sku", "quant__sku")
    position = _col("position__ref", "quant__position__ref")
    batch = _col("batch", "quant__batch")

    class Meta:
        model = Move
        fields = ("id", "sku", "position", "batch", "kind", "delta", "reason", "timestamp")
        export_order = fields


class CashEntrySnapshotResource(resources.ModelResource):
    operator = _col("operator", "operator__username")

    class Meta:
        model = Entry
        fields = ("id", "at", "kind", "amount_q", "order_ref", "payment_ref", "reason", "operator")
        export_order = fields


class PaymentIntentSnapshotResource(resources.ModelResource):
    class Meta:
        model = PaymentIntent
        fields = (
            "ref", "order_ref", "method", "status", "amount_q", "currency", "gateway",
            "gateway_id", "created_at", "authorized_at", "captured_at", "cancelled_at",
            "cancel_reason",
        )
        export_order = fields


class WorkOrderSnapshotResource(resources.ModelResource):
    recipe = _col("recipe__ref", "recipe__ref")

    class Meta:
        model = WorkOrder
        fields = (
            "ref", "recipe", "output_sku", "quantity", "finished", "status",
            "target_date", "position_ref", "operator_ref", "started_at", "finished_at",
        )
        export_order = fields


def register_transactional_resources() -> None:
    """Abas somente-leitura, depois de toda a curadoria (tier alto de propósito)."""
    for name, resource in (
        ("orders", OrderSnapshotResource),
        ("order_items", OrderItemSnapshotResource),
        ("stock_moves", MoveSnapshotResource),
        ("cash_entries", CashEntrySnapshotResource),
        ("payment_intents", PaymentIntentSnapshotResource),
        ("work_orders", WorkOrderSnapshotResource),
    ):
        registry.register(name, resource, tier=9, read_only=True)
