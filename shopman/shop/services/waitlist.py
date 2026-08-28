"""
Fila de espera — quanto da fornada AINDA NÃO ASSADA a loja promete (WP-P2E).

O Stockman sempre soube somar fornada planejada: ``total_promisable`` é
``expected + planned`` para a política ``planned_ok``. O que faltava era a
PERGUNTA. Toda leitura da loja pergunta "e para HOJE?", e fornada de amanhã,
por construção, não conta para hoje — ``quants_eligible_for`` corta
``target_date > target`` e ``_planned_supply_for_target`` exige ``target >
today``. Resultado: o balde ``planned`` chega zerado em toda leitura de
cliente, o item lê "Esgotado" e não há fila em que entrar, mesmo com a
fornada de amanhã já planejada.

Este módulo é a pergunta certa, num lugar só: até que DIA de fornada
planejada este canal promete. As leituras (sacola, cardápio, PDP) passam
:func:`promise_horizon` como ``target_date``; a reserva passa
:func:`reserve_target_date`, que é a data da fornada de verdade — o hold
precisa ancorar no lote certo para que a sacola diga "Previsto para
<dia>" sem mentir.

Desligado (``waitlist.enabled=False``, o default) tudo devolve hoje: o
comportamento é exatamente o de sempre.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


def config(channel_ref: str | None = None):
    """Resolve o aspecto ``waitlist`` na cascata canal ← loja ← hardcoded."""
    from shopman.shop.config import ChannelConfig

    try:
        if channel_ref:
            return ChannelConfig.for_channel(channel_ref).waitlist
        return ChannelConfig().waitlist
    except Exception:
        logger.debug("waitlist.config degraded; using hardcoded defaults", exc_info=True)
        return ChannelConfig().waitlist


def is_enabled(channel_ref: str | None = None) -> bool:
    cfg = config(channel_ref)
    return bool(cfg.enabled and cfg.horizon_days > 0)


def promise_horizon(channel_ref: str | None = None) -> date:
    """Última data de fornada planejada que este canal promete.

    Fila desligada devolve HOJE — que é o que toda leitura já usava, então
    passar isto adiante não muda nada até alguém ligar a fila.
    """
    from django.utils import timezone

    today = timezone.localdate()
    cfg = config(channel_ref)
    if not (cfg.enabled and cfg.horizon_days > 0):
        return today
    return today + timedelta(days=cfg.horizon_days)


def next_batch_date(sku: str, *, channel_ref: str | None = None) -> date | None:
    """Data da próxima fornada PLANEJADA deste SKU dentro do horizonte.

    ``None`` quando não há fornada planejada alcançável — que é o caso
    honesto de "esgotou mesmo", e o chamador deve recusar.
    """
    if not sku:
        return None
    horizon = promise_horizon(channel_ref)
    from django.utils import timezone

    today = timezone.localdate()
    if horizon <= today:
        return None
    try:
        from shopman.stockman.models import Quant
    except Exception:
        logger.debug("waitlist.next_batch_date degraded; returning None", exc_info=True)
        return None

    return (
        Quant.objects.filter(
            sku=sku,
            _quantity__gt=0,
            target_date__gt=today,
            target_date__lte=horizon,
        )
        .order_by("target_date")
        .values_list("target_date", flat=True)
        .first()
    )


def reserve_target_date(
    sku: str,
    qty: Decimal,
    *,
    channel_ref: str | None = None,
) -> date | None:
    """Data que a reserva deve carregar para entrar na fila deste SKU.

    ``None`` = nada a fazer, siga com o comportamento de hoje. Só devolve a
    data da fornada quando o que existe para hoje NÃO cobre o pedido: a
    pronta-entrega continua sendo servida primeiro, e a fila só é acionada
    quando ela acaba (FCFS — quem chega antes leva o que já existe).
    """
    if not is_enabled(channel_ref) or not sku:
        return None
    try:
        from shopman.stockman.services.availability import availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref) if channel_ref else {}
        info = availability_for_sku(
            sku,
            safety_margin=int(scope.get("safety_margin") or 0),
            allowed_positions=scope.get("allowed_positions"),
            excluded_positions=scope.get("excluded_positions"),
            expiry_margin_days=int(scope.get("expiry_margin_days") or 0),
            include_nonconforming=bool(scope.get("sells_nonconforming", True)),
        )
    except Exception:
        logger.debug("waitlist.reserve_target_date degraded; returning None", exc_info=True)
        return None

    if info.get("is_paused"):
        return None
    promisable = Decimal(str(info.get("total_promisable") or 0))
    if promisable >= Decimal(str(qty)):
        return None
    return next_batch_date(sku, channel_ref=channel_ref)


# ──────────────────────────────────────────────────────────────────────
# Ciclo de vida da reserva (WP-P2E F2)
#
# A fila é uma compra em DUAS fases. A reserva (fermata) não cobra nada e
# não corre relógio: ela espera a fornada. Quando a fornada sai, a vaga não
# vira pedido sozinha — o cliente confirma, dentro de um prazo. Quem não
# confirma perde a vaga para o próximo da fila, e nem o cliente nem a loja
# ficam sabendo por acaso: liberação é sempre anunciada dos dois lados.
# ──────────────────────────────────────────────────────────────────────

NONE = "none"
FERMATA = "fermata"
CONFIRMING = "confirming"
CONFIRMED = "confirmed"
RELEASED = "released"

WAITLIST_KEY = "waitlist"


def _order_holds(order, *, sku: str | None = None):
    """Holds vivos deste pedido (opcionalmente de um SKU)."""
    try:
        from django.db.models import Q
        from django.utils import timezone
        from shopman.stockman.models import Hold, HoldStatus
    except Exception:
        logger.debug("waitlist._order_holds degraded", exc_info=True)
        return []

    qs = Hold.objects.filter(
        metadata__reference=f"order:{order.ref}",
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
    if sku:
        qs = qs.filter(sku=sku)
    return list(qs.order_by("created_at"))


def state_for(order) -> str:
    """Estado da fila deste pedido.

    ``fermata`` é DERIVADO do hold, não gravado: enquanto existir reserva
    planejada sem prazo, o pedido está esperando a fornada, e não há dois
    lugares para essa verdade divergirem. Os estados que carregam decisão e
    prazo (``confirming``/``confirmed``/``released``) ficam em
    ``Order.data['waitlist']``, porque deles não dá para derivar o relógio.
    """
    stored = ((order.data or {}).get(WAITLIST_KEY) or {}).get("state")
    if stored in (CONFIRMING, CONFIRMED, RELEASED):
        return stored
    for hold in _order_holds(order):
        if hold.expires_at is None and (hold.metadata or {}).get("planned"):
            return FERMATA
    return NONE


def planned_batch_date(order) -> date | None:
    """A fornada que este pedido espera, lida do hold.

    Enquanto o lote não sai, a data que interessa ao cliente é a DELE — e é o
    hold que a carrega, não o bloco gravado.
    """
    for hold in _order_holds(order):
        if (hold.metadata or {}).get("planned") and hold.target_date:
            return hold.target_date
    return None


def _write_state(order, **fields) -> None:
    data = dict(order.data or {})
    block = dict(data.get(WAITLIST_KEY) or {})
    block.update({k: v for k, v in fields.items() if v is not None})
    data[WAITLIST_KEY] = block
    order.data = data
    order.save(update_fields=["data"])


def queue_for(sku: str, target_date: date | None = None) -> list:
    """Pedidos em fermata para este SKU, em ordem FCFS.

    A ordem é a de criação do HOLD, não a do pedido: quem reservou primeiro
    entrou primeiro na fila, mesmo que tenha fechado o pedido depois.
    """
    try:
        from shopman.orderman.models import Order
        from shopman.stockman.models import Hold, HoldStatus
    except Exception:
        logger.debug("waitlist.queue_for degraded", exc_info=True)
        return []

    holds = Hold.objects.filter(
        sku=sku,
        expires_at__isnull=True,
        metadata__planned=True,
        metadata__reference__startswith="order:",
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    )
    if target_date is not None:
        holds = holds.filter(target_date__lte=target_date)
    holds = holds.order_by("created_at")

    seen: set[str] = set()
    refs: list[str] = []
    for hold in holds:
        ref = str((hold.metadata or {}).get("reference") or "")[len("order:"):]
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    if not refs:
        return []

    by_ref = {
        o.ref: o
        for o in Order.objects.filter(ref__in=refs).exclude(
            status__in=("cancelled", "rejected", "returned"),
        )
    }
    return [by_ref[ref] for ref in refs if ref in by_ref]


def _held_qty(order, sku: str) -> Decimal:
    return sum(
        (h.quantity for h in _order_holds(order, sku=sku)),
        Decimal("0"),
    )


def open_window(
    sku: str,
    *,
    qty_available: Decimal,
    channel_ref: str | None = None,
) -> list[str]:
    """A fornada saiu: abre a janela de confirmação para os primeiros da fila.

    Serve FCFS até a quantidade materializada acabar. Pedido que não cabe
    inteiro na sobra NÃO é servido pela metade — fica na fermata esperando a
    próxima fornada, porque meia reserva não é uma promessa que dê para
    cumprir.

    Devolve os refs dos pedidos que entraram em confirmação.
    """
    from django.utils import timezone

    remaining = Decimal(str(qty_available))
    if remaining <= 0:
        return []

    cfg = config(channel_ref)
    deadline = timezone.now() + timedelta(minutes=cfg.confirmation_minutes)
    opened: list[str] = []

    for order in queue_for(sku):
        if remaining <= 0:
            break
        if state_for(order) != FERMATA:
            continue
        needed = _held_qty(order, sku)
        if needed <= 0 or needed > remaining:
            continue
        remaining -= needed
        _write_state(
            order,
            state=CONFIRMING,
            sku=sku,
            opened_at=timezone.now().isoformat(),
            deadline=deadline.isoformat(),
            qty=str(needed),
        )
        _notify_customer(order, "waitlist_available", deadline=deadline.isoformat())
        opened.append(order.ref)

    if opened:
        logger.info(
            "waitlist.open_window sku=%s served=%s remaining=%s",
            sku, len(opened), remaining,
        )
    return opened


def confirm(order) -> bool:
    """O cliente confirmou dentro do prazo: a reserva vira pedido de verdade.

    A cobrança acontece AQUI (``charge_at=confirmation``) — nada foi cobrado
    na reserva, então quem desiste não precisa de estorno. Fora do prazo a
    confirmação é recusada: a vaga já é de outro.
    """
    from django.utils import timezone

    if state_for(order) != CONFIRMING:
        return False
    block = (order.data or {}).get(WAITLIST_KEY) or {}
    deadline = _parse_iso(block.get("deadline"))
    if deadline is not None and timezone.now() > deadline:
        release(order, reason="confirmation_timeout")
        return False

    _write_state(order, state=CONFIRMED, confirmed_at=timezone.now().isoformat())
    _charge(order)
    logger.info("waitlist.confirm order=%s", order.ref)
    return True


def _charge(order) -> None:
    """A cobrança da fila acontece AQUI, e só aqui (``charge_at=confirmation``).

    Nada foi cobrado na reserva — é o que torna desistir barato para os dois
    lados: quem sai da fila não precisa de estorno, e a loja não segura
    dinheiro de pedido que pode não acontecer. Quem confirma e não paga cai no
    payment-timeout que já existe, e a vaga volta pela mesma porta do
    ``release``.
    """
    cfg = config(order.channel_ref)
    if cfg.charge_at != "confirmation":
        return
    try:
        from shopman.shop.services import notification, payment

        payment.initiate(order)
        notification.send(order, "payment_requested")
    except Exception:
        logger.warning("waitlist._charge failed order=%s", order.ref, exc_info=True)


def release(order, *, reason: str) -> list[str]:
    """Devolve a vaga e conta para os dois lados.

    Liberação NUNCA é silenciosa: o cliente é avisado de que saiu da fila e
    a loja recebe alerta, porque a vaga que volta é decisão dela (servir o
    próximo ou pôr na gôndola). Com ``release_policy=serve_next`` a fila tem
    preferência e o próximo é servido na hora.
    """
    from django.utils import timezone

    block = (order.data or {}).get(WAITLIST_KEY) or {}
    sku = block.get("sku") or ""
    qty = Decimal(str(block.get("qty") or 0))
    if not sku:
        for hold in _order_holds(order):
            if (hold.metadata or {}).get("planned"):
                sku, qty = hold.sku, hold.quantity
                break

    freed = _release_holds(order, sku)
    _write_state(
        order,
        state=RELEASED,
        released_at=timezone.now().isoformat(),
        release_reason=reason,
    )
    _notify_customer(order, "waitlist_released", reason=reason)
    _alert_store(order, sku=sku, qty=qty, reason=reason)
    logger.info("waitlist.release order=%s sku=%s reason=%s", order.ref, sku, reason)

    if not sku or freed <= 0:
        return []
    cfg = config(order.channel_ref)
    if cfg.release_policy != "serve_next":
        return []
    return open_window(sku, qty_available=freed, channel_ref=order.channel_ref)


def sweep_expired() -> int:
    """Libera as janelas de confirmação vencidas. Chamado pelo maintenance worker."""
    from django.utils import timezone
    from shopman.orderman.models import Order

    now = timezone.now()
    released = 0
    candidates = Order.objects.filter(
        data__waitlist__state=CONFIRMING,
    ).exclude(status__in=("cancelled", "rejected", "returned"))
    for order in candidates:
        deadline = _parse_iso(((order.data or {}).get(WAITLIST_KEY) or {}).get("deadline"))
        if deadline is not None and now > deadline:
            release(order, reason="confirmation_timeout")
            released += 1
    if released:
        logger.info("waitlist.sweep_expired released=%s", released)
    return released


# ── Colaboradores: prazo, holds, aviso ao cliente, alerta à loja ──


def _parse_iso(value):
    if not value:
        return None
    try:
        from django.utils.dateparse import parse_datetime

        return parse_datetime(str(value))
    except Exception:
        logger.debug("waitlist._parse_iso degraded value=%s", value, exc_info=True)
        return None


def _release_holds(order, sku: str) -> Decimal:
    """Solta os holds planejados deste SKU e devolve a quantidade liberada."""
    from shopman.shop.adapters import get_adapter

    adapter = get_adapter("stock")
    planned = [
        hold
        for hold in _order_holds(order, sku=sku or None)
        if (hold.metadata or {}).get("planned")
    ]
    if not planned:
        return Decimal("0")
    try:
        adapter.release_holds([hold.hold_id for hold in planned])
    except Exception:
        logger.warning("waitlist._release_holds failed order=%s", order.ref, exc_info=True)
        return Decimal("0")
    return sum((hold.quantity for hold in planned), Decimal("0"))


def _notify_customer(order, template: str, **extra) -> None:
    """Aviso ativo ao cliente. Nunca silencioso — nem para dar, nem para tirar."""
    try:
        from shopman.shop.services import notification

        notification.send(order, template, **extra)
    except Exception:
        logger.warning(
            "waitlist._notify_customer failed order=%s template=%s",
            order.ref, template, exc_info=True,
        )


def _alert_store(order, *, sku: str, qty: Decimal, reason: str) -> None:
    """Alerta no Gestor: a vaga voltou e alguém precisa saber disso.

    A loja não descobre por acaso que abriu vaga — ela decide o que fazer
    com ela (a fila serve o próximo sozinha, mas a gôndola é decisão humana).
    """
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="waitlist_released",
        severity="warning",
        message=(
            f"Pedido {order.ref} saiu da fila de espera ({reason}). "
            f"{qty} un. de {sku or 'item'} voltaram a ficar disponíveis — "
            f"a fila serve o próximo; a gôndola é decisão sua."
        ),
        order_ref=order.ref,
        dedupe_key=f"waitlist_released:{order.ref}:{sku}",
    )


def _qty_display(value: Decimal) -> str:
    """Quantidade sem cauda de zeros: o relatório é lido por gente, e "5.000"
    numa fila de 5 pães parece milhar."""
    normalized = Decimal(str(value)).normalize()
    if normalized == normalized.to_integral_value():
        normalized = normalized.to_integral_value()
    return format(normalized, "f")


def report() -> list[dict]:
    """Retrato da fila viva, por SKU e em ordem FCFS (WP-P2E F3).

    Quem decide pôr a vaga na gôndola precisa saber quanta gente está
    esperando e há quanto tempo — o selo do card conta um pedido de cada vez,
    e essa é a pergunta do outro lado: "vale abrir a fornada extra?".
    """
    from django.utils import timezone
    from shopman.stockman.models import Hold, HoldStatus

    now = timezone.now()
    skus = (
        Hold.objects.filter(
            expires_at__isnull=True,
            metadata__planned=True,
            metadata__reference__startswith="order:",
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        )
        .values_list("sku", flat=True)
        .distinct()
    )

    rows: list[dict] = []
    for sku in sorted(set(skus)):
        entries = []
        for position, order in enumerate(queue_for(sku), start=1):
            batch_date = planned_batch_date(order)
            entries.append({
                "position": position,
                "order_ref": order.ref,
                "state": state_for(order),
                "qty": _qty_display(_held_qty(order, sku)),
                "batch_date": batch_date.isoformat() if batch_date else None,
                "waiting_minutes": int((now - order.created_at).total_seconds() // 60),
            })
        if entries:
            rows.append({
                "sku": sku,
                "waiting": len(entries),
                "qty_reserved": _qty_display(sum((Decimal(e["qty"]) for e in entries), Decimal("0"))),
                "queue": entries,
            })
    return rows
