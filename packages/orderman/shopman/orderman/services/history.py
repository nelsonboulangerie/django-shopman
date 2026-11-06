"""Customer order history contract exposed by Orderman."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import Coalesce
from shopman.orderman.models import Order


@dataclass(frozen=True)
class CustomerOrderRecord:
    """Sealed summary of a customer's order."""

    order_ref: str
    channel_ref: str
    ordered_at: object
    total_q: int
    items_count: int
    status: str
    items: list[dict]


@dataclass(frozen=True)
class CustomerOrderStats:
    """Aggregated customer order metrics."""

    total_orders: int
    total_spent_q: int
    first_order_at: object | None
    last_order_at: object | None
    average_order_q: int


class CustomerOrderHistoryService:
    """
    Public read contract from Orderman to identity/CRM consumers.

    The canonical link is ``order.data["customer_ref"]`` sealed by the
    customer resolution flow in the framework.
    """

    #: O que NÃO é compra: o pedido que não aconteceu (cancelado, inclusive o
    #: Pix ou cartão que venceu sem pagamento) e o que foi desfeito (devolvido).
    #: Contá-los fazia "Cliente fiel · 5 pedidos" de quem nunca pagou nada, com
    #: ticket médio e favorito tirados de pedidos que não existiram (beta 06/11,
    #: PIXEXP-07).
    NOT_PURCHASES = (Order.Status.CANCELLED, Order.Status.RETURNED)

    @classmethod
    def list_customer_orders(
        cls,
        customer_ref: str,
        *,
        limit: int = 10,
        include_not_purchases: bool = False,
    ) -> list[CustomerOrderRecord]:
        """Os pedidos do cliente, do mais recente.

        Por padrão, só as compras (o mesmo recorte de ``get_customer_stats``):
        favorito, "comprou da última vez" e RFM leem daqui. Quem LISTA o
        histórico com o status ao lado (o cadastro do cliente) pede
        ``include_not_purchases=True`` e mostra também o cancelado, rotulado.
        """
        qs = (
            Order.objects.filter(data__customer_ref=customer_ref)
            if include_not_purchases
            else cls._base_queryset(customer_ref)
        )
        orders = qs.order_by("-created_at")[:limit]
        return [
            CustomerOrderRecord(
                order_ref=order.ref,
                channel_ref=order.channel_ref or "",
                ordered_at=order.created_at,
                total_q=order.total_q,
                items_count=len((order.snapshot or {}).get("items", [])),
                status=order.status,
                items=list((order.snapshot or {}).get("items", [])),
            )
            for order in orders
        ]

    @classmethod
    def get_customer_stats(cls, customer_ref: str) -> CustomerOrderStats:
        qs = cls._base_queryset(customer_ref)
        stats = qs.aggregate(
            total_orders=Count("id"),
            first_order_at=Min("created_at"),
            last_order_at=Max("created_at"),
            # `Order.total_q` é o total selado de todo pedido. O `snapshot.pricing`
            # só existe quando a sessão passou pelo ModifyService (PDV, conta e seed
            # não passam), e somá-lo dava gasto zero ao cliente fiel.
            total_spent_q=Coalesce(Sum("total_q"), 0),
        )

        total_orders = stats["total_orders"] or 0
        total_spent_q = stats["total_spent_q"] or 0

        return CustomerOrderStats(
            total_orders=total_orders,
            total_spent_q=total_spent_q,
            first_order_at=stats["first_order_at"],
            last_order_at=stats["last_order_at"],
            average_order_q=total_spent_q // total_orders if total_orders > 0 else 0,
        )

    @classmethod
    def _base_queryset(cls, customer_ref: str):
        """As compras do cliente: tudo menos ``NOT_PURCHASES``."""
        return Order.objects.filter(data__customer_ref=customer_ref).exclude(status__in=cls.NOT_PURCHASES)
