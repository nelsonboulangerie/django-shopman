"""Day closing mutation service.

The DayClosing audit record is owned by Backstage, while physical stock
movements are delegated to Stockman. Views call this service so HTTP code does
not manipulate inventory directly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from shopman.stockman import Quant
from shopman.stockman.models import Move
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.models import DayClosing

logger = logging.getLogger(__name__)


def perform_day_closing(
    *,
    user,
    items: Iterable,
    quantities_by_sku: dict[str, str],
    closing_date: date | None = None,
) -> date:
    """Execute day closing and return the closing date."""
    closing_date = closing_date or timezone.localdate()
    if DayClosing.objects.filter(date=closing_date).exists():
        raise ValueError("Fechamento de hoje já foi realizado.")

    snapshot = []
    with transaction.atomic():
        for item in items:
            sku = item.sku
            qty_reported = _parse_qty(quantities_by_sku.get(sku, "0"))

            if qty_reported <= 0:
                snapshot.append(
                    _snapshot(item, qty_reported=qty_reported, qty_expired=0, qty_nonconforming=0)
                )
                continue

            qty_unsold = min(qty_reported, item.qty_available)

            # A sobra NÃO se move (C4 do D1-RETIREMENT): o LOTE decide.
            #   1. Não conforme não vai para o dia seguinte — write-off com o
            #      motivo carimbado (perda_nao_conformidade:<data>).
            #   2. Validade vencida/vencendo hoje (ou produto do dia sem lote)
            #      — write-off perda_vencido:<data>.
            #   3. O resto FICA onde está: o desconto (se houver) e a cerca de
            #      canal já vêm do lote (C1/C2), não de uma posição de véspera.
            qty_nonconforming = _write_off_lots(
                sku,
                qty_unsold,
                lot_refs=nonconforming_lot_refs(sku),
                reason=f"perda_nao_conformidade:{closing_date}",
            )
            qty_expired = _write_off_lots(
                sku,
                qty_unsold - qty_nonconforming,
                lot_refs=expired_lot_refs(sku, closing_date),
                include_batchless=day_product_expires_on_close(sku),
                reason=f"perda_vencido:{closing_date}",
            )

            snapshot.append(
                _snapshot(
                    item,
                    qty_reported=qty_reported,
                    qty_unsold=qty_unsold,
                    qty_expired=qty_expired,
                    qty_nonconforming=qty_nonconforming,
                )
            )

        DayClosing.objects.create(
            date=closing_date,
            closed_by=user,
            data={
                "items": snapshot,
                "production_summary": production_summary(closing_date),
                "pending_production": _pending_production_snapshot(closing_date),
                "cash_shift_summary": _cash_shift_summary(closing_date),
                "reconciliation_errors": _reconciliation_errors(
                    closing_date=closing_date,
                    items=snapshot,
                ),
            },
        )

    return closing_date


def _parse_qty(raw_qty) -> int:
    try:
        return max(0, int(str(raw_qty).strip()))
    except (ValueError, TypeError):
        return 0


def _snapshot(
    item, *, qty_reported: int, qty_unsold: int = 0, qty_expired: int, qty_nonconforming: int,
) -> dict:
    # qty_kept é derivada: o que sobrou, tem validade e FICA na posição — o
    # fechamento não move estoque são (C4).
    qty_kept = max(qty_unsold - qty_expired - qty_nonconforming, 0)
    return {
        "sku": item.sku,
        "qty_reported": qty_reported,
        "qty_applied": qty_unsold,
        "qty_discrepancy": qty_reported - qty_unsold,
        "qty_remaining": item.qty_available - qty_unsold,
        "qty_expired": qty_expired,
        "qty_nonconforming": qty_nonconforming,
        "qty_kept": qty_kept,
    }


def nonconforming_lot_refs(sku: str) -> set[str]:
    """Lotes marcados — não vão para o dia seguinte (regra da casa)."""
    from shopman.stockman.models import Batch

    return set(Batch.objects.for_sku(sku).nonconforming().values_list("ref", flat=True))


def expired_lot_refs(sku: str, closing_date: date) -> set[str]:
    """Lotes que não sobrevivem ao fechamento: vencem hoje ou já venceram."""
    from shopman.stockman.models import Batch

    return set(
        Batch.objects.for_sku(sku)
        .filter(expiry_date__lte=closing_date)
        .values_list("ref", flat=True)
    )


def day_product_expires_on_close(sku: str) -> bool:
    """Produto do dia SEM rastreio de lote: a validade implícita é o próprio
    dia (shelf_life_days == 0) — quant sem lote morre no fechamento."""
    try:
        from shopman.offerman.models import Product

        product = Product.objects.filter(sku=sku).only("shelf_life_days").first()
        return bool(product) and product.shelf_life_days == 0
    except Exception:
        logger.warning("shelf_life de %s indisponível; produto do dia não expira no fechamento", sku, exc_info=True)
        return False


def _write_off_lots(
    sku,
    quantity,
    *,
    lot_refs: set[str],
    reason: str,
    include_batchless: bool = False,
) -> int:
    """WASTE dos quants vendáveis cujo LOTE está em ``lot_refs``.

    ``include_batchless``: também baixa quants sem lote (produto do dia sem
    rastreio de lote — a validade implícita é o próprio dia). Retorna a
    quantidade efetivamente baixada, limitada a ``quantity``.
    """
    if quantity <= 0:
        return 0
    quants = (
        Quant.objects.filter(
            sku=sku,
            position__is_saleable=True,
            _quantity__gt=0,
        )
        .select_for_update()
        .order_by("pk")
    )
    remaining = Decimal(quantity)
    written_off = Decimal("0")
    for quant in quants:
        if remaining <= 0:
            break
        in_lots = bool(quant.batch) and quant.batch in lot_refs
        if not in_lots and not (include_batchless and not quant.batch):
            continue
        take = min(remaining, quant._quantity)
        # WASTE, não o ADJUST default do issue(): perda de fim de dia é perda.
        # Sem o kind, agrupar o ledger por tipo conta a perda como ajuste de
        # inventário e a métrica que o write-off existe para alimentar nasce torta.
        StockMovements.issue(
            quantity=take, quant=quant, reason=reason, kind=Move.Kind.WASTE
        )
        remaining -= take
        written_off += take
    return int(written_off)


def _pending_production_snapshot(closing_date: date) -> list[dict]:
    """WOs abertas no fechamento — registradas para auditoria (não bloqueiam)."""
    from shopman.craftsman.models import WorkOrder

    rows = []
    qs = (
        WorkOrder.objects.filter(
            status__in=(WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED),
            target_date__lte=closing_date,
        )
        .select_related("recipe")
        .order_by("status", "target_date", "ref")
    )
    for wo in qs:
        rows.append(
            {
                "ref": wo.ref,
                "output_sku": wo.output_sku,
                "recipe_ref": wo.recipe.ref,
                "status": str(wo.status),
                "quantity": str(wo.quantity),
                "target_date": wo.target_date.isoformat() if wo.target_date else "",
            }
        )
    return rows


def _json_qty(value: Decimal) -> int | float:
    """Quantidade em JSON sem truncar: inteiro quando inteiro, float quando não.

    ``int(...)`` transformava 2,5 kg em 2 — o resumo persistido mentia para
    receitas fracionárias (massa por peso).
    """
    return int(value) if value == value.to_integral_value() else float(value)


def production_summary(closing_date: date) -> dict:
    """Resumo de produção do dia por receita — dono único da pergunta.

    Consumido pelo fechamento (persistido em ``DayClosing.data``) e pela
    projection de pré-fechamento. Uma fonte, dois leitores.
    """
    from shopman.craftsman.models import WorkOrder, WorkOrderItem

    summary: dict[str, dict] = {}
    work_orders = WorkOrder.objects.filter(target_date=closing_date).select_related("recipe")
    by_pk: dict[int, str] = {}
    for wo in work_orders:
        recipe_ref = wo.recipe.ref
        by_pk[wo.pk] = recipe_ref
        row = summary.setdefault(
            recipe_ref,
            {
                "recipe_ref": recipe_ref,
                "output_sku": wo.output_sku,
                "planned": Decimal("0"),
                "finished": Decimal("0"),
                "loss": Decimal("0"),
            },
        )
        row["planned"] += wo.quantity or Decimal("0")
        if wo.finished is not None:
            row["finished"] += wo.finished or Decimal("0")
            started = wo.started_qty or wo.quantity
            row["loss"] += max(Decimal("0"), (started or Decimal("0")) - wo.finished)

    # Consolidação de qualidade do dia (ADR-017 §8): quantas unidades saíram em
    # cada grau, por receita. Linha sem grau (finish escalar) fica de fora — o
    # denominador dela já está em `finished`; grau só aparece quando declarado.
    if by_pk:
        quality_lines = (
            WorkOrderItem.objects.filter(
                work_order_id__in=by_pk, kind=WorkOrderItem.Kind.OUTPUT
            )
            .exclude(quality_grade_ref="")
            .values_list("work_order_id", "quality_grade_ref", "quantity")
        )
        for wo_id, grade_ref, quantity in quality_lines:
            row = summary[by_pk[wo_id]]
            grades = row.setdefault("quality", {})
            grades[grade_ref] = grades.get(grade_ref, Decimal("0")) + (quantity or Decimal("0"))

    for row in summary.values():
        for key in ("planned", "finished", "loss"):
            row[key] = _json_qty(row[key])
        if "quality" in row:
            row["quality"] = {ref: _json_qty(qty) for ref, qty in row["quality"].items()}
    return summary


def _reconciliation_errors(*, closing_date: date, items: list[dict]) -> list[dict]:
    from django.db.models import Q
    from shopman.orderman.models import Order

    from shopman.shop.services.order_helpers import get_commitment_date

    saleable_by_sku = {row["sku"]: int(row.get("qty_remaining", 0)) + int(row.get("qty_applied", 0)) for row in items}
    produced_by_sku: dict[str, int] = {}
    for row in production_summary(closing_date).values():
        produced_by_sku[str(row["output_sku"])] = produced_by_sku.get(str(row["output_sku"]), 0) + int(row["finished"])

    # Base do "vendido" é a DATA COMBINADA, não a data da venda (WP-D): a
    # encomenda feita hoje para sábado consome o estoque de sábado — contá-la
    # hoje fabricava deficit falso (baixa adiada), e ignorá-la no sábado
    # esconderia deficits reais. Financeiro/caixa seguem no dia do pagamento.
    sold_by_sku: dict[str, int] = {}
    orders = (
        Order.objects.filter(
            Q(created_at__date=closing_date) | Q(data__delivery_date=closing_date.isoformat()),
        )
        .exclude(status__in=["cancelled", "returned"])
        .prefetch_related("items")
    )
    for order in orders:
        commitment = get_commitment_date(order) or timezone.localtime(order.created_at).date()
        if commitment != closing_date:
            continue
        for item in order.items.all():
            sold_by_sku[item.sku] = sold_by_sku.get(item.sku, 0) + int(item.qty)

    errors: list[dict] = []
    for sku, sold in sorted(sold_by_sku.items()):
        available = saleable_by_sku.get(sku, 0) + produced_by_sku.get(sku, 0)
        if sold > available:
            errors.append({
                "sku": sku,
                "sold": sold,
                "available": available,
                "deficit": sold - available,
            })
    return errors


def _cash_shift_summary(closing_date: date) -> dict:
    """O caixa do dia, calculado do livro (``cashman``) no momento do fechamento.

    É snapshot: pode congelar números. O que não pode é ser uma segunda fonte
    viva — esperado, contado e diferença são somas do livro (``cashman.services``),
    e o mix de meios de pagamento é do ``payman``. Nada aqui reinterpreta o JSON
    do pedido para contar dinheiro.
    """
    from shopman.cashman import services as cash
    from shopman.cashman.models import Entry, Shift

    closed = (
        Shift.objects.filter(status=Shift.Status.CLOSED, closed_at__date=closing_date)
        .select_related("terminal", "operator")
        .order_by("closed_at")
    )
    open_shifts = Shift.objects.filter(status=Shift.Status.OPEN).select_related("terminal", "operator")

    shift_rows = []
    totals = {
        "opening_amount_q": 0,
        "blind_closing_amount_q": 0,
        "expected_amount_q": 0,
        "difference_q": 0,
    }
    for shift in closed:
        float_q = sum(e.amount_q for e in cash.timeline(shift) if e.kind == Entry.Kind.FLOAT_IN)
        row = {
            "id": shift.pk,
            "terminal_ref": shift.terminal.ref,
            "operator": shift.operator.get_username(),
            "opened_at": shift.opened_at.isoformat() if shift.opened_at else "",
            "closed_at": shift.closed_at.isoformat() if shift.closed_at else "",
            "opening_amount_q": float_q,
            "blind_closing_amount_q": cash.counted(shift) or 0,
            "expected_amount_q": cash.expected_before_count(shift),
            "difference_q": cash.difference(shift) or 0,
        }
        shift_rows.append(row)
        for key in totals:
            totals[key] += int(row[key])

    return {
        "closed_shifts": shift_rows,
        "open_shifts": [
            {
                "id": shift.pk,
                "terminal_ref": shift.terminal.ref,
                "operator": shift.operator.get_username(),
                "opened_at": shift.opened_at.isoformat() if shift.opened_at else "",
            }
            for shift in open_shifts
        ],
        "totals": totals,
        "payment_method_totals": _payment_method_totals(closing_date),
    }


def _payment_method_totals(closing_date: date) -> dict:
    """Recebido no dia por método, do ``payman`` — o único dono de "receita por método".

    Intents capturados no dia (``captured_at``), líquidos de estorno, agrupados
    por método. Dinheiro e ``external`` entram aqui desde que o PDV passou a
    liquidá-los no ``payman`` (ADR-022 §4); antes disso o mix saía de uma
    releitura do JSON do pedido, que era uma segunda fonte para a mesma pergunta.

    ``cod_pending_*`` continua sendo o que só o pedido sabe: cobrança na
    entrega ainda na rua não é pagamento, então não está no ``payman`` — é
    receita a receber, e sai daqui marcada para quem soma recebido a ignorar e
    quem quer saber o que está na rua a encontrar.
    """
    from django.db.models import Sum
    from shopman.orderman.models import Order
    from shopman.payman.models import PaymentIntent, PaymentTransaction

    from .payments import iter_order_payments

    settled = (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED)
    day_intents = PaymentIntent.objects.filter(status__in=settled, captured_at__date=closing_date)
    captured = day_intents.values("method").annotate(total=Sum("amount_q"))
    refunded = (
        PaymentTransaction.objects.filter(intent__in=day_intents, type=PaymentTransaction.Type.REFUND)
        .values("intent__method")
        .annotate(total=Sum("amount_q"))
    )
    totals: dict[str, int] = {}
    for row in captured:
        totals[str(row["method"])] = int(row["total"] or 0)
    for row in refunded:
        method = str(row["intent__method"])
        totals[method] = totals.get(method, 0) - int(row["total"] or 0)

    cod_pending_q = 0
    cod_pending_count = 0
    orders = Order.objects.filter(created_at__date=closing_date).exclude(status__in=["cancelled", "returned"])
    for order in orders:
        for entry in iter_order_payments(order.data, order.total_q):
            if entry.pending:
                cod_pending_q += entry.amount_q
                cod_pending_count += 1
    totals["cod_pending_q"] = cod_pending_q
    totals["cod_pending_count"] = cod_pending_count
    return totals
