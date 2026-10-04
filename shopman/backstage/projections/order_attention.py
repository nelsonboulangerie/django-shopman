"""A Fila "Precisa de você" do Gestor (V4-G4, prévia v4 ``gestor-fila4.html``).

Duas leituras que o quadro de três colunas não tinha, na MESMA projeção do quadro
(``order_queue.build_two_zone_queue``), sem endpoint paralelo:

1. **O que espera um fato humano** (``card_attention``). Cada cartão diz se há algo
   que só uma pessoa pode fazer agora (aceitar, entregar, despachar, o "Pronto" da
   estação sem tela, receber o entregador, acertar o dinheiro) ou se o pedido está
   bloqueado esperando um fato de fora (o Pix cair). O resto está em andamento, e a
   Fila o resume num número. A régua lê as AÇÕES que o cartão já oferece (as mesmas
   ``operator_orders.operational_actions`` que decidem o botão): o que é botão
   primário é fato humano; nenhuma segunda régua de estado.

2. **A meta de tempo por etapa** (``STAGE_GOAL_MINUTES``). O sistema só tinha um
   prazo, o da confirmação (``ChannelConfig.confirmation``). As outras metas são
   PROPOSTA desta frente, à espera do dono (estão no PR como pergunta): até lá
   valem os números abaixo, iguais para todos os canais.

3. **A consciência ao lado** (``build_queue_awareness``): o que o sistema fez nos
   últimos 15 minutos (pronto automático, aceite e recusa por prazo, aviso do
   canal), com o desfazer onde a janela ainda vale, e o estado do cardápio
   (esgotados e pausas abertos em ``ShelfOutage``) e dos canais de venda
   (ligado/desligado, ``channel_switch``).

Chaves em inglês; frases em português, prontas para a tela.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

#: O fato humano que o pedido espera, ou ``""`` quando não espera ninguém.
ATTENTION_KINDS = (
    "confirm",       # aceitar ou recusar o pedido novo
    "blocked",       # bloqueado por um fato de fora (pagamento): avança sozinho
    "start",         # iniciar o preparo (canal com ``prep_start=operator``)
    "station",       # "Pronto de X": a estação sem tela terminou no papel
    "mark_ready",    # marcar pronto à mão (sem a Cozinha para concluir)
    "handoff",       # entregar ao cliente no balcão
    "dispatch",      # despachar a entrega
    "courier_back",  # o entregador voltou com dinheiro ou maquininha
    "settle",        # acertar o dinheiro da entrega
)

#: Meta de tempo por etapa, em minutos (proposta, ver o docstring). ``confirm`` e
#: ``blocked`` do pedido novo usam o prazo do canal quando ele existe.
STAGE_GOAL_MINUTES = {
    "confirm": 5,
    "blocked": 5,
    "start": 5,
    "station": 20,
    "mark_ready": 20,
    "handoff": 10,
    "dispatch": 30,
    "courier_back": 45,
    "settle": 15,
}

#: Janela de "O sistema fez".
SYSTEM_WINDOW_MINUTES = 15


def _iso(moment) -> str:
    return moment.isoformat() if moment else ""


def _action(card, ref: str):
    return next((action for action in card.actions if action.ref == ref), None)


def _confirmation_goal(channel_config) -> int:
    """O prazo do pedido novo: o do canal (confirmação automática ou o do marketplace)."""
    goal = STAGE_GOAL_MINUTES["confirm"]
    if channel_config is None:
        return goal
    confirmation = channel_config.confirmation
    candidates = []
    if confirmation.mode in ("auto_confirm", "auto_cancel") and confirmation.timeout_minutes > 0:
        candidates.append(confirmation.timeout_minutes)
    if confirmation.external_sla_minutes > 0:
        candidates.append(confirmation.external_sla_minutes)
    return min(candidates) if candidates else goal


def attention_kind(order: Order, card) -> str:
    """O fato humano que o pedido espera agora (``ATTENTION_KINDS``) ou ``""``."""
    status = card.status
    advance = _action(card, "advance")
    advance_ready = bool(advance and advance.enabled and advance.priority == "primary")
    if status == Order.Status.NEW:
        # Só o pagamento que ainda não caiu bloqueia "de fora" (avança sozinho
        # quando cair). Qualquer outra recusa do aceite (falta de estoque, por
        # exemplo) pede uma pessoa: recusar ou resolver.
        return "blocked" if not card.can_confirm and card.payment_pending else "confirm"
    if status == Order.Status.ACCEPTED:
        if advance_ready and card.next_status == Order.Status.PREPARING:
            return "start"
        return "blocked" if card.payment_pending and card.advance_block_reason else ""
    if status == Order.Status.PREPARING:
        stations = card.kitchen.stations if card.kitchen else ()
        if any(station.can_mark_ready for station in stations):
            return "station"
        return "mark_ready" if advance_ready else ""
    if status == Order.Status.READY:
        if _action(card, "undo-handoff") or advance_ready:
            return "dispatch" if card.fulfillment_type == "delivery" else "handoff"
        return "blocked" if card.advance_block_reason else ("dispatch" if card.fulfillment_type == "delivery" else "handoff")
    if status in (Order.Status.DISPATCHED, Order.Status.DELIVERED):
        if _action(card, "courier-back"):
            return "courier_back"
        if card.can_settle_delivery_cash:
            return "settle"
    return ""


def card_attention(order: Order, card, channel_config=None) -> dict:
    """Os campos de atenção do cartão: o fato, desde quando conta e a meta."""
    kind = attention_kind(order, card)
    if not kind:
        return {}
    if kind in ("confirm",) or (kind == "blocked" and order.status == Order.Status.NEW):
        goal, since = _confirmation_goal(channel_config), order.created_at
    else:
        goal = STAGE_GOAL_MINUTES[kind]
        since = {
            "blocked": order.accepted_at or order.created_at,
            "start": order.accepted_at or order.created_at,
            "station": order.preparing_at or order.created_at,
            "mark_ready": order.preparing_at or order.created_at,
            # A entrega promete o tempo todo, da chegada à saída ("27 min · meta 30").
            "dispatch": order.created_at,
            "courier_back": order.dispatched_at or order.created_at,
            "settle": order.delivered_at or order.dispatched_at or order.created_at,
        }.get(kind)
    since_iso = _iso(since)
    if kind == "handoff":
        # No balcão o relógio é o do pronto ("6 min no balcão").
        since_iso = card.ready_at_iso or _iso(order.ready_at) or _iso(order.created_at)
    return {
        "attention": kind,
        "attention_since_iso": since_iso,
        "goal_minutes": goal,
        "goal_label": "no balcão" if kind == "handoff" else f"meta {goal}",
    }


# ── A consciência ao lado da Fila ────────────────────────────────────────


@dataclass(frozen=True)
class SystemActionProjection:
    """Uma linha de "O sistema fez": o que mudou sozinho e por quê."""

    order_ref: str
    #: "Pronto" · "Aceito" · "Cancelado" · "Entregue"…
    verb: str
    #: "Cozinha concluiu" · "prazo de confirmação" · "iFood avisou"…
    reason: str
    at_iso: str
    #: "21:52"
    at_display: str
    #: ``undo-ready`` enquanto a janela do pronto automático vale (a ação mora no cartão).
    undo_action: str = ""
    undo_until_iso: str = ""


@dataclass(frozen=True)
class MenuOutageProjection:
    """Um produto que não dá para comprar agora (esgotado ou pausado)."""

    sku: str
    name: str
    #: "sold_out" · "paused"
    reason: str
    #: "Bichon au Citron esgotado"
    line: str
    #: "fora da Loja online e do iFood desde 21:40"
    detail: str


@dataclass(frozen=True)
class MenuChannelProjection:
    """Um canal de venda: recebe pedido agora?"""

    ref: str
    name: str
    active: bool
    #: "iFood ligado" · "Loja online desligada até 18:00"
    line: str
    focus_path: str


@dataclass(frozen=True)
class QueueAwarenessProjection:
    system_actions: tuple[SystemActionProjection, ...] = ()
    system_window_minutes: int = SYSTEM_WINDOW_MINUTES
    menu_outages: tuple[MenuOutageProjection, ...] = ()
    #: Quantos esgotados/pausas existem além dos listados.
    menu_outages_more: int = 0
    menu_channels: tuple[MenuChannelProjection, ...] = ()
    #: Quem gerencia o catálogo abre os canais a partir da linha.
    can_open_channels: bool = False


_VERBS = {
    Order.Status.ACCEPTED: "Aceito",
    Order.Status.PREPARING: "Em preparo",
    Order.Status.READY: "Pronto",
    Order.Status.DISPATCHED: "Saiu",
    Order.Status.DELIVERED: "Entregue",
    Order.Status.COMPLETED: "Concluído",
    Order.Status.CANCELLED: "Cancelado",
    Order.Status.RETURNED: "Devolvido",
}

MAX_SYSTEM_ACTIONS = 6
MAX_MENU_OUTAGES = 5


def _clock(moment) -> str:
    return timezone.localtime(moment).strftime("%H:%M") if moment else ""


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _channel_names() -> dict[str, str]:
    from shopman.shop.models import Channel

    return {ref: name or ref for ref, name in Channel.objects.values_list("ref", "name")}


def _system_reason(event, order: Order, channel_names: dict[str, str]) -> str:
    """Por que o sistema fez, ou ``""`` quando quem fez foi uma pessoa."""
    actor = str(event.actor or "")
    payload = event.payload if isinstance(event.payload, dict) else {}
    new_status = payload.get("new_status", "")
    if actor == "confirmation.timeout":
        return "prazo de confirmação"
    if actor.startswith("auto_reject"):
        return "item indisponível"
    if actor == "fulfillment.sync":
        return f"{channel_names.get(order.channel_ref, order.channel_ref)} avisou"
    if new_status == Order.Status.READY:
        from shopman.shop.services import order_undo

        at = _parse(order_undo.auto_ready_record(order).get("at"))
        if at is not None and abs((event.created_at - at).total_seconds()) <= 10:
            return "Cozinha concluiu"
    return ""


def system_actions(*, now: datetime, channel_names: dict[str, str]) -> tuple[SystemActionProjection, ...]:
    """O que o sistema fez sozinho nos últimos minutos, o mais recente primeiro."""
    from shopman.orderman.models import OrderEvent

    from shopman.shop.services import order_undo
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    since = now - timedelta(minutes=SYSTEM_WINDOW_MINUTES)
    rows: list[SystemActionProjection] = []
    events = (
        OrderEvent.objects.filter(type="status_changed", created_at__gte=since)
        .select_related("order")
        .order_by("-created_at", "-pk")[:200]
    )
    for event in events:
        order = event.order
        if is_pos_counter_order(order):
            continue
        reason = _system_reason(event, order, channel_names)
        if not reason:
            continue
        new_status = (event.payload or {}).get("new_status", "")
        undo_action, undo_until = "", ""
        if reason == "Cozinha concluiu":
            hold = order_undo.ready_hold(order, now=now)
            if hold and not order_undo.pending_handoff(order):
                undo_action, undo_until = "undo-ready", str(hold.get("undo_until") or "")
        rows.append(SystemActionProjection(
            order_ref=order.ref,
            verb=_VERBS.get(new_status, new_status),
            reason=reason,
            at_iso=event.created_at.isoformat(),
            at_display=_clock(event.created_at),
            undo_action=undo_action,
            undo_until_iso=undo_until,
        ))
        if len(rows) >= MAX_SYSTEM_ACTIONS:
            break
    return tuple(rows)


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} e {names[-1]}"


def menu_outages(*, channel_names: dict[str, str]) -> tuple[tuple[MenuOutageProjection, ...], int]:
    """Os esgotados e pausas abertos, um por produto, o mais recente primeiro."""
    from shopman.offerman.models import Product

    from shopman.backstage.models import OutageReason, ShelfOutage

    open_rows = list(ShelfOutage.objects.filter(ended_at__isnull=True).order_by("-started_at"))
    by_sku: dict[str, list] = {}
    for row in open_rows:
        by_sku.setdefault(row.sku, []).append(row)
    names = dict(Product.objects.filter(sku__in=list(by_sku)).values_list("sku", "name"))
    items = []
    for sku, rows in list(by_sku.items())[:MAX_MENU_OUTAGES]:
        paused = any(row.reason == OutageReason.PAUSED for row in rows)
        name = names.get(sku) or sku
        channels = [channel_names.get(row.channel_ref, row.channel_ref) for row in rows]
        started = min(row.started_at for row in rows)
        items.append(MenuOutageProjection(
            sku=sku,
            name=name,
            reason="paused" if paused else "sold_out",
            line=f"{name} {'pausado' if paused else 'esgotado'}",
            detail=f"fora de {_join(channels)} desde {_clock(started)}",
        ))
    return tuple(items), max(0, len(by_sku) - MAX_MENU_OUTAGES)


def menu_channels(*, now: datetime) -> tuple[MenuChannelProjection, ...]:
    """Os canais de venda com interruptor: ligados ou desligados agora."""
    from shopman.shop.models import Channel
    from shopman.shop.services import channel_switch as switches

    rows = []
    for channel in Channel.objects.filter(commerce_policy=Channel.CommercePolicy.ORDER).order_by("display_order", "name"):
        if not switches.is_switchable(channel):
            continue
        name = channel.name or channel.ref
        active = switches.effective_active(channel, now=now)
        rows.append(MenuChannelProjection(
            ref=channel.ref,
            name=name,
            active=active,
            line=f"{name} {'recebendo pedidos' if active else 'sem receber pedidos'}",
            focus_path=f"/feeds?focus={channel.ref}",
        ))
    return tuple(rows)


def build_queue_awareness(*, user=None, now: datetime | None = None) -> QueueAwarenessProjection:
    now = now or timezone.now()
    names = _channel_names()
    try:
        outages, more = menu_outages(channel_names=names)
    except Exception:
        # Ausência de resposta não é resposta: sem a leitura, a seção some.
        logger.warning("order_attention.menu_outages_failed", exc_info=True)
        outages, more = (), 0
    try:
        channels = menu_channels(now=now)
    except Exception:
        logger.warning("order_attention.menu_channels_failed", exc_info=True)
        channels = ()
    return QueueAwarenessProjection(
        system_actions=system_actions(now=now, channel_names=names),
        menu_outages=outages,
        menu_outages_more=more,
        menu_channels=channels,
        can_open_channels=bool(user is not None and user.has_perm("shop.manage_catalog")),
    )


__all__ = [
    "ATTENTION_KINDS",
    "STAGE_GOAL_MINUTES",
    "SYSTEM_WINDOW_MINUTES",
    "MenuChannelProjection",
    "MenuOutageProjection",
    "QueueAwarenessProjection",
    "SystemActionProjection",
    "attention_kind",
    "build_queue_awareness",
    "card_attention",
]
