"""O pedido nativo como venda canônica.

Cancelado e devolvido não são venda: saem da lista e voltam como contagem
(``cancelled``), porque número escondido é número que mente. Forma de
pagamento vem repartida por ``iter_order_payments`` — a mesma regra do
fechamento do dia, para que o B.I. e o caixa contem o mesmo dinheiro.
"""

from __future__ import annotations

from django.utils import timezone

from shopman.backstage.bi.canonical import CanonicalPayment, CanonicalSale, CanonicalSaleLine

SOURCE = "shopman"


def _excluded_statuses():
    from shopman.orderman.models import Order

    return (Order.Status.CANCELLED, Order.Status.RETURNED)


def read_sales(window) -> tuple[list[CanonicalSale], int]:
    """(vendas canônicas, pedidos cancelados/devolvidos) na janela [início, fim)."""
    from shopman.orderman.models import Order

    from shopman.backstage.projections.bi_payments import payment_method_label
    from shopman.backstage.services.payments import iter_order_payments

    excluded = _excluded_statuses()
    sales: list[CanonicalSale] = []
    cancelled = 0
    rows = Order.objects.filter(created_at__range=window).values_list(
        "id", "ref", "created_at", "total_q", "channel_ref", "status", "data"
    )
    for pk, ref, created_at, total_q, channel_ref, status, data in rows:
        if status in excluded:
            cancelled += 1
            continue
        local = timezone.localtime(created_at)
        data = data or {}
        payment = data.get("payment") or {}
        payments = tuple(
            CanonicalPayment(
                method=entry.method,
                label=payment_method_label(entry.method),
                amount_q=entry.amount_q,
                pending=entry.pending,
            )
            for entry in iter_order_payments(data, total_q)
        )
        # Duas assinaturas de dinheiro em espécie: o método da venda simples e
        # do dinheiro na entrega, e a parcela em espécie do pagamento misto
        # (método vira "mixed" e o dinheiro só aparece em `cash_received_q`).
        is_cash = any(entry.method == "cash" for entry in payments) or int(
            payment.get("cash_received_q") or 0
        ) > 0
        sales.append(
            CanonicalSale(
                source=SOURCE,
                key=pk,
                ref=f"{SOURCE}:{ref}",
                occurred_at=local,
                day=local.date(),
                channel_key=channel_ref,
                is_delivery=data.get("fulfillment_type") == "delivery",
                total_q=total_q,
                payments=payments,
                payment_known=bool(payment.get("method")),
                is_cash=is_cash,
                change_q=None if payment.get("change_q") is None else int(payment["change_q"]),
            )
        )
    return sales, cancelled


def read_lines(window) -> list[CanonicalSaleLine]:
    """As linhas dos pedidos que contam como venda (cancelado/devolvido fora)."""
    from shopman.orderman.models import OrderItem

    rows = (
        OrderItem.objects.filter(order__created_at__range=window)
        .exclude(order__status__in=_excluded_statuses())
        .values_list("order_id", "sku", "name", "qty", "line_total_q")
    )
    return [
        CanonicalSaleLine(
            source=SOURCE,
            sale_key=order_id,
            product_ref=sku or "",
            external_sku="",
            name=name or "",
            category="",
            qty=qty,
            line_total_q=line_total_q,
        )
        for order_id, sku, name, qty, line_total_q in rows
    ]
