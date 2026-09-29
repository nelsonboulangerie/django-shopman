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
    from shopman.shop.services import order_composition
    from shopman.shop.services.order_helpers import exclude_test_orders
    from shopman.shop.services.payment_provenance import exclude_provider_simulated_orders

    excluded = _excluded_statuses()
    sales: list[CanonicalSale] = []
    cancelled = 0
    # O pedido de teste do marketplace sai INTEIRO, não vira contagem de
    # cancelado: ele não é venda que a casa perdeu, é venda que nunca existiu.
    # O filtro de confirmação simulada ao lado só olha
    # ``data.payment.confirmation_mode``, chave que o iFood nunca grava.
    rows = exclude_test_orders(
        exclude_provider_simulated_orders(Order.objects.filter(created_at__range=window))
    ).values_list(
        "id", "ref", "created_at", "total_q", "channel_ref", "status", "data"
    )
    for pk, ref, created_at, total_q, channel_ref, status, data in rows:
        if status in excluded:
            cancelled += 1
            continue
        local = timezone.localtime(created_at)
        data = data or {}
        # Pedido + ajustes: o faturamento é o que a plataforma paga pelo pedido
        # que VALE. ``data`` já veio na consulta, então a composição sai daqui
        # mesmo — o B.I. não pode somar por conta própria.
        adjustment = data.get(order_composition.KEY)
        if isinstance(adjustment, dict) and adjustment.get("total_q") is not None:
            total_q = int(adjustment["total_q"])
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
    # The helper targets Order fields; apply the same exact predicate through
    # the relation for line reads so simulated test baskets cannot leak into
    # product/revenue consumers.
    from django.db.models import Q
    from shopman.orderman.models import Order, OrderItem

    from shopman.shop.services import order_composition
    from shopman.shop.services.payment_provenance import PROVIDER_SIMULATED_CONFIRMATION_MODE

    eligible = (
        Order.objects.filter(created_at__range=window)
        .exclude(status__in=_excluded_statuses())
        .filter(
            Q(data__payment__confirmation_mode__isnull=True)
            | ~Q(data__payment__confirmation_mode=PROVIDER_SIMULATED_CONFIRMATION_MODE)
        )
    )
    # Pedido + ajustes: o pedido que o cliente alterou tem as linhas dele lidas
    # do ajuste. Ler as duas fontes somaria o item removido ao item que ficou.
    adjusted = order_composition.adjusted_order_ids(eligible.values_list("pk", flat=True))
    rows = (
        OrderItem.objects.filter(order_id__in=eligible.values("pk"))
        .exclude(order_id__in=adjusted)
        .values_list("order_id", "sku", "name", "qty", "line_total_q")
    )
    lines = [
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
    for order_id, items in order_composition.effective_items_by_order_id(adjusted).items():
        lines.extend(
            CanonicalSaleLine(
                source=SOURCE,
                sale_key=order_id,
                product_ref=item.sku,
                external_sku="",
                name=item.name,
                category="",
                qty=item.qty,
                line_total_q=item.line_total_q,
            )
            for item in items
        )
    return lines
