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

2. **A meta de tempo por etapa** (``stage_goal``). O pedido novo usa o prazo da
   confirmação do canal (``ChannelConfig.confirmation``); as outras etapas, a
   meta do canal em ``ChannelConfig.fulfillment.stage_goal_minutes``, que herda
   os padrões decididos pelo dono em 04/10/2026 (``config.STAGE_GOAL_DEFAULTS``:
   iniciar 5, estação 15, balcão 10, despacho 30 da chegada, entregador 45,
   acerto 15).

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

from shopman.backstage.projections.feeds import ChannelSwitchProjection, ManagerOptionProjection
from shopman.shop.config import STAGE_GOAL_DEFAULTS

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

#: Meta padrão do pedido novo (e do bloqueado por pagamento), em minutos, quando o
#: canal não tem prazo de confirmação próprio.
CONFIRM_GOAL_MINUTES = 5

#: Qual meta do canal (``fulfillment.stage_goal_minutes``) vale para cada fato.
#: ``mark_ready`` é a mesma etapa da estação (o preparo terminar); ``blocked``
#: fora do pedido novo espera o pagamento, com a meta do pedido novo.
_GOAL_STAGE = {
    "start": "start",
    "station": "station",
    "mark_ready": "station",
    "handoff": "handoff",
    "dispatch": "dispatch",
    "courier_back": "courier_back",
    "settle": "settle",
}

#: Janela de "O sistema fez".
SYSTEM_WINDOW_MINUTES = 15


def _iso(moment) -> str:
    return moment.isoformat() if moment else ""


def _action(card, ref: str):
    return next((action for action in card.actions if action.ref == ref), None)


def stage_goal(kind: str, channel_config=None) -> int:
    """A meta, em minutos, da etapa que o fato ``kind`` espera, no canal do pedido.

    O canal manda (``fulfillment.stage_goal_minutes``, já com a cascata loja e
    padrões); sem config, valem os padrões do dono.
    """
    stage = _GOAL_STAGE.get(kind)
    if stage is None:
        return CONFIRM_GOAL_MINUTES
    goals = channel_config.fulfillment.stage_goal_minutes if channel_config is not None else {}
    value = goals.get(stage) if isinstance(goals, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return STAGE_GOAL_DEFAULTS[stage]
    return value


def _confirmation_goal(channel_config) -> int:
    """O prazo do pedido novo: o do canal (confirmação automática ou o do marketplace)."""
    goal = CONFIRM_GOAL_MINUTES
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
        goal = stage_goal(kind, channel_config)
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


# ── "Na Cozinha · próximo pronto em ~4 min" (G10) ───────────────────────

#: Janela dos preparos reais que medem o tempo da Cozinha agora.
PREP_SAMPLE_HOURS = 3
#: Abaixo disto a mediana não diz nada: vale a meta da estação.
PREP_MIN_SAMPLES = 3


@dataclass(frozen=True)
class PrepExpectation:
    """Quanto um preparo está levando agora: a mediana real ou, sem amostra, a meta."""

    #: Minutos medidos (mediana de ``preparing_at`` → ``ready_at``); ``None`` sem amostra.
    minutes: float | None
    samples: int

    @property
    def basis(self) -> str:
        if self.minutes is None:
            return "pela meta da estação (sem preparos suficientes nas últimas 3 horas)"
        return f"pela mediana de {self.samples} preparos nas últimas {PREP_SAMPLE_HOURS} horas"


def prep_expectation(*, now: datetime) -> PrepExpectation:
    """A mediana dos preparos que terminaram nas últimas horas (uma consulta)."""
    since = now - timedelta(hours=PREP_SAMPLE_HOURS)
    rows = Order.objects.filter(
        ready_at__gte=since, ready_at__lte=now, preparing_at__isnull=False,
    ).order_by("-ready_at").values_list("preparing_at", "ready_at")[:60]
    minutes = sorted((ready - start).total_seconds() / 60 for start, ready in rows if ready > start)
    if len(minutes) < PREP_MIN_SAMPLES:
        return PrepExpectation(minutes=None, samples=len(minutes))
    middle = len(minutes) // 2
    median = minutes[middle] if len(minutes) % 2 else (minutes[middle - 1] + minutes[middle]) / 2
    return PrepExpectation(minutes=median, samples=len(minutes))


def ready_eta(order: Order, expectation: PrepExpectation, channel_config=None, *, now: datetime) -> datetime | None:
    """Quando o pedido na Cozinha deve ficar pronto: o início real mais o tempo de agora.

    O início é o primeiro "Iniciar" do KDS (``Order.data["kds_started"]``) ou o
    ``preparing_at``; o tempo é a mediana real (``prep_expectation``) ou a meta da
    estação do canal. Pedido que ainda não começou não fica pronto antes de começar:
    conta a partir de agora.
    """
    if order.status not in (Order.Status.ACCEPTED, Order.Status.PREPARING):
        return None
    expected = expectation.minutes if expectation.minutes is not None else stage_goal("station", channel_config)
    starts = []
    for record in ((order.data or {}).get("kds_started") or {}).values():
        at = _parse(record.get("at")) if isinstance(record, dict) else None
        if at is not None:
            starts.append(at)
    start = min(starts) if starts else order.preparing_at
    return (start or now) + timedelta(minutes=expected)


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
    #: O interruptor da linha (G09): o MESMO de Canais, que abre o
    #: ``ChannelSwitchDialog`` com período, motivo e a aprovação do gerente.
    switch: ChannelSwitchProjection | None = None


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
    #: De onde vem o "próximo pronto em ~N min" (a mediana real ou a meta).
    kitchen_eta_basis: str = ""
    #: Quem autoriza ligar/desligar um canal (a lista de Canais) e quem opera.
    managers: tuple[ManagerOptionProjection, ...] = ()
    viewer_name: str = ""


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


def menu_channels(*, now: datetime, user=None) -> tuple[MenuChannelProjection, ...]:
    """Os canais de venda com interruptor: ligados ou desligados agora, com o gesto."""
    from shopman.backstage.projections.feeds import _build_switch, switch_authority
    from shopman.shop.models import Channel
    from shopman.shop.services import business_calendar
    from shopman.shop.services import channel_switch as switches

    authorized, is_manager = switch_authority(user)
    state = business_calendar.current_business_state(now=now)
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
            switch=_build_switch(channel, user=user, authorized=authorized, is_manager=is_manager, state=state, now=now),
        ))
    return tuple(rows)


def build_queue_awareness(*, user=None, now: datetime | None = None, expectation: PrepExpectation | None = None) -> QueueAwarenessProjection:
    now = now or timezone.now()
    names = _channel_names()
    try:
        outages, more = menu_outages(channel_names=names)
    except Exception:
        # Ausência de resposta não é resposta: sem a leitura, a seção some.
        logger.warning("order_attention.menu_outages_failed", exc_info=True)
        outages, more = (), 0
    try:
        channels = menu_channels(now=now, user=user)
    except Exception:
        logger.warning("order_attention.menu_channels_failed", exc_info=True)
        channels = ()
    from shopman.backstage.projections.feeds import switch_managers

    managers, viewer = switch_managers(user)
    return QueueAwarenessProjection(
        system_actions=system_actions(now=now, channel_names=names),
        menu_outages=outages,
        menu_outages_more=more,
        menu_channels=channels,
        can_open_channels=bool(user is not None and user.has_perm("shop.manage_catalog")),
        kitchen_eta_basis=expectation.basis if expectation is not None else "",
        managers=managers,
        viewer_name=viewer,
    )


__all__ = [
    "ATTENTION_KINDS",
    "CONFIRM_GOAL_MINUTES",
    "SYSTEM_WINDOW_MINUTES",
    "MenuChannelProjection",
    "PrepExpectation",
    "MenuOutageProjection",
    "QueueAwarenessProjection",
    "SystemActionProjection",
    "attention_kind",
    "build_queue_awareness",
    "card_attention",
    "prep_expectation",
    "ready_eta",
    "stage_goal",
]
