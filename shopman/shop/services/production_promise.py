"""A promessa de produção que um pedido aceito perdeu (F-6 do plano do Gestor, #2547, #2594).

Cancelar um lote solta as reservas que ficaram sem lastro
(``handlers._stock_receivers.on_production_voided``). Até aqui só a SACOLA aberta
ficava sabendo; o pedido aceito, pago e com "Pedido garantido para amanhã" na tela
do cliente perdia a reserva em silêncio, e o Gestor não mostrava nada.

Este módulo transforma a perda em FATO DO PEDIDO, sem decidir nada por ninguém:

- um evento na linha do tempo do pedido (``production_hold_lost``), com o item, a
  quantidade, a data e o lote;
- um aviso no sino do Gestor (``order_promise_lost``, público ``orders``), um por
  pedido e item, nomeando o pedido, o item e o que fazer.

Três fatos chegam aqui, cada um com o seu evento e a sua frase:

- o lote CANCELADO (``production_voided``, #2547): a reserva sai;
- o lote que RENDEU MENOS do que as reservas (``production_short``, #2594): a
  reserva fica, presa a um saldo que não existe;
- o lote ATRASADO com encomenda da data (``production_late``, #2594): passou da
  hora de prontidão do produto e o lote ainda não fechou.

Nunca cancela, remarca nem fala com o cliente: a conversa é decisão de gente, como
no dia fechado (``closed_day_orders``).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.shop.services.observability import create_operator_alert

logger = logging.getLogger(__name__)

ALERT_TYPE = "order_promise_lost"
EVENT_TYPE = "production_hold_lost"
EVENT_TYPE_SHORT = "production_hold_short"
EVENT_TYPE_LATE = "production_lot_late"

REASON_VOIDED = "production_voided"
REASON_SHORT = "production_short"
REASON_LATE = "production_late"

_EVENT_BY_REASON = {
    REASON_VOIDED: EVENT_TYPE,
    REASON_SHORT: EVENT_TYPE_SHORT,
    REASON_LATE: EVENT_TYPE_LATE,
}

#: Pedido que ainda vai sair da loja. Os demais já saíram (ou acabaram) e o
#: lote cancelado não os alcança mais.
OPEN_STATUSES = ("new", "accepted", "preparing", "ready")

ORDER_REFERENCE_PREFIX = "order:"


def order_ref_from_hold_reference(reference) -> str:
    """``"order:PDV-1"`` → ``"PDV-1"``; qualquer outra coisa (sacola) → ``""``."""
    raw = str(reference or "")
    return raw[len(ORDER_REFERENCE_PREFIX):] if raw.startswith(ORDER_REFERENCE_PREFIX) else ""


def _format_qty(qty) -> str:
    value = Decimal(str(qty or 0))
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return format(value.normalize(), "f").replace(".", ",")


def _product_name(sku: str) -> str:
    try:
        from shopman.offerman.models import Product

        product = Product.objects.filter(sku=sku).only("name").first()
    except Exception:
        logger.debug("production_promise: product lookup failed for %s", sku, exc_info=True)
        product = None
    return (product.name if product is not None else "") or sku


def _what_happened(reason: str, *, name: str, day: str, lot: str, qty_text: str) -> str:
    """A frase do fato, do jeito que o operador lê no sino."""
    lacks = "falta" if qty_text == "1" else "faltam"
    if reason == REASON_SHORT:
        return f"o lote de {name} para {day} rendeu menos que o reservado{lot}: {lacks} {qty_text} un."
    if reason == REASON_LATE:
        waiting = "espera" if qty_text == "1" else "esperam"
        return f"o lote de {name} para {day} passou da hora de ficar pronto{lot}: {qty_text} un. {waiting} por ele."
    return f"a produção de {name} para {day} foi cancelada{lot}: {lacks} {qty_text} un."


def _already_recorded(order, event_type: str, *, sku: str, date_text: str) -> bool:
    """O mesmo fato (tipo, item e dia) já está na linha do tempo deste pedido?

    O cancelamento acontece uma vez; o rendimento menor e o atraso são lidos de
    novo a cada varredura, e a linha do tempo não pode repetir o mesmo fato.
    """
    return order.events.filter(type=event_type, payload__sku=sku, payload__date=date_text).exists()


def _emit_fact(order, event_type, payload) -> None:
    order.emit_event(event_type=event_type, actor="system", payload=payload)


def announce_lost_holds(
    lost_by_order: dict[str, Decimal], *, sku: str, date, work_order=None, reason: str = REASON_VOIDED,
) -> int:
    """Registra no pedido e avisa o Gestor. Devolve quantos avisos saíram.

    ``lost_by_order``: ``{order_ref: quantidade em risco}`` deste SKU.
    ``reason``: ``production_voided`` (padrão), ``production_short`` ou
    ``production_late``. Best-effort por pedido: um pedido que falha não impede o
    aviso dos outros.
    """
    if not lost_by_order:
        return 0

    from shopman.orderman.models import Order

    event_type = _EVENT_BY_REASON.get(reason, EVENT_TYPE)
    name = _product_name(sku)
    day = date.strftime("%d/%m") if hasattr(date, "strftime") else str(date)
    date_text = date.isoformat() if hasattr(date, "isoformat") else str(date)
    wo_ref = str(getattr(work_order, "ref", "") or "")
    created = 0
    orders = Order.objects.filter(ref__in=list(lost_by_order), status__in=OPEN_STATUSES).order_by("ref")
    for order in orders:
        qty_text = _format_qty(lost_by_order.get(order.ref) or Decimal("0"))
        try:
            if not _already_recorded(order, event_type, sku=sku, date_text=date_text):
                payload = {
                    "sku": sku,
                    "product_name": name,
                    "qty": qty_text,
                    "date": date_text,
                    "work_order_ref": wo_ref,
                    "reason": reason,
                }
                # Um ramo por tipo, cada um com a constante: a trava dos rótulos da
                # linha do tempo lê o tipo do evento no código.
                if reason == REASON_SHORT:
                    _emit_fact(order, EVENT_TYPE_SHORT, payload)
                elif reason == REASON_LATE:
                    _emit_fact(order, EVENT_TYPE_LATE, payload)
                else:
                    _emit_fact(order, EVENT_TYPE, payload)
        except Exception:
            logger.warning("production_promise: could not record event on %s", order.ref, exc_info=True)

        lot = f" (lote {wo_ref})" if wo_ref else ""
        fact = _what_happened(reason, name=name, day=day, lot=lot, qty_text=qty_text)
        message = f"Pedido {order.ref}: {fact} Avise o cliente, remarque ou cancele o pedido."
        alert = create_operator_alert(
            type=ALERT_TYPE,
            severity="error",
            message=message,
            order_ref=order.ref,
            # Por pedido + item + data + motivo: o mesmo fato não avisa duas vezes,
            # outro item do mesmo pedido avisa à parte, e o atraso que vira
            # cancelamento avisa de novo, porque é outro fato.
            dedupe_key=f"de {name} para {day} ({reason})",
            debounce_minutes=24 * 60,
            sku=sku,
            work_order_ref=wo_ref,
        )
        if alert is not None:
            created += 1
    return created


def _order_hold_rows(holds) -> list[tuple[str, Decimal]]:
    rows = []
    for hold in holds:
        order_ref = order_ref_from_hold_reference((hold.metadata or {}).get("reference"))
        if order_ref:
            rows.append((order_ref, Decimal(str(hold.quantity))))
    return rows


def _by_order(rows) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for order_ref, qty in rows:
        out[order_ref] = out.get(order_ref, Decimal("0")) + qty
    return out


def announce_short_lot(product_ref: str, date, *, work_order=None) -> int:
    """O lote fechou com menos do que as reservas de pedido que ele levava (#2594).

    As reservas que não couberam no que o lote rendeu ficam ativas, presas ao saldo
    de produção que zerou (``realize`` leva a reserva inteira ou nada). Vira fato do
    pedido, sem soltar a reserva: outro lote do dia ainda pode cobri-la, e soltar é
    decisão de gente. A sobra livre dos outros saldos de produção do mesmo dia cobre
    primeiro quem reservou antes; só o que nem ela cobre é avisado.
    """
    from shopman.stockman.models import Quant

    from shopman.shop.handlers._stock_receivers import _overbooked_holds_on_production_quants

    uncovered = [
        hold for hold in _overbooked_holds_on_production_quants(product_ref, date)
        if order_ref_from_hold_reference((hold.metadata or {}).get("reference"))
    ]
    if not uncovered:
        return 0

    overbooked_quants = {hold.quant_id for hold in uncovered}
    spare = Decimal("0")
    for quant in Quant.objects.filter(sku=product_ref, target_date=date).exclude(pk__in=overbooked_quants):
        spare += max(Decimal(str(quant.quantity)) - Decimal(str(quant.held)), Decimal("0"))

    lost = []
    for hold in sorted(uncovered, key=lambda h: h.pk):  # quem reservou antes é coberto antes
        qty = Decimal(str(hold.quantity))
        if spare >= qty:
            spare -= qty
            continue
        lost.append(hold)
    return announce_lost_holds(
        _by_order(_order_hold_rows(lost)), sku=product_ref, date=date, work_order=work_order, reason=REASON_SHORT,
    )


def announce_late_lots(*, now=None) -> int:
    """O lote de hoje (ou de antes) que passou da hora com encomenda esperando (#2594).

    A hora é a de prontidão do produto (``product_readiness``), a mesma que a
    promessa em risco do Gestor usa para dizer "atrasado". O lote de um dia que já
    passou e não fechou também conta. Avisa cada pedido uma vez por item e dia.
    """
    from datetime import datetime

    from django.utils import timezone
    from shopman.craftsman.models import WorkOrder
    from shopman.stockman.models import Hold

    from shopman.shop.services import product_readiness

    now = now or timezone.now()
    today = timezone.localdate(now)
    open_lots = list(
        WorkOrder.objects.filter(
            status__in=(WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED), target_date__lte=today,
        ).order_by("target_date", "pk")
    )
    if not open_lots:
        return 0

    lots_by_key: dict[tuple, object] = {}
    for lot in open_lots:
        lots_by_key.setdefault((lot.output_sku, lot.target_date), lot)
    try:
        ready_times = product_readiness.ready_times_for(sorted({sku for sku, _day in lots_by_key}))
    except Exception:
        # Sem a hora, não se inventa atraso (a mesma regra da promessa em risco).
        logger.warning("production_promise: prontidão indisponível", exc_info=True)
        ready_times = {}

    created = 0
    for (sku, day), lot in lots_by_key.items():
        if day == today:
            ready = ready_times.get(sku)
            if ready is None or now <= timezone.make_aware(datetime.combine(today, ready)):
                continue
        holds = Hold.objects.filter(quant__sku=sku, quant__target_date=day).active().order_by("pk")
        late = _by_order(_order_hold_rows(holds))
        if late:
            created += announce_lost_holds(late, sku=sku, date=day, work_order=lot, reason=REASON_LATE)
    return created
