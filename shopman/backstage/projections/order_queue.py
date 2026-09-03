"""OrderQueueProjection — read models for the operator order queue (Fase 4).

Translates the active order queue into immutable projections for the operator
dashboard. Replaces the inline ``_enrich_order`` / ``_status_counts`` logic
from ``shopman.backstage.views.orders``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.backstage.presentation.status import (
    order_status_label,
    payment_method_label,
    status_color,
)
from shopman.shop.projections.types import (
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.shop.services import operator_orders
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.order_helpers import get_commitment_date, get_fulfillment_type

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────

ACTIVE_STATUSES = ("new", "accepted", "preparing", "ready", "dispatched", "delivered")

_PAYMENT_COMPLETE = frozenset({"captured", "paid"})
_OFFLINE_METHODS = frozenset({"cash", "credit", "debit", "external", ""})
# Um tender de balcão nasce ``received`` ao ser liquidado no PDV; o dinheiro na
# entrega (COD) nasce ``pending`` e vira ``received`` quando o entregador acerta.
# Ver shop/services/pos.py (status do tender) e operator_orders.settle_delivery_cash.
_SETTLED_TENDER_STATUSES = frozenset({"received", "captured", "paid", ""})

CHANNEL_ICONS: dict[str, str] = {
    "web": "language",
    "whatsapp": "chat",
    "ifood": "fastfood",
    "pos": "storefront",
}
_DEFAULT_CHANNEL_ICON = "shopping_bag"

NEXT_ACTION_LABELS: dict[str, str] = {
    "accepted": "Iniciar preparo",
    "preparing": "Marcar pronto",
    "ready": "Marcar como Retirado",
    "dispatched": "Marcar como Entregue",
    "delivered": "Concluir",
}

READY_DELIVERY_LABEL = "Marcar saída para entrega"


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AwaitingWorkOrderProjection:
    """A compact production dependency shown on order cards and detail."""

    ref: str
    status: str
    status_label: str
    output_sku: str
    planned_qty: str
    finished_qty: str
    progress_pct: int


@dataclass(frozen=True)
class EquipmentOptionProjection:
    """Um aparelho que o entregador pode levar no despacho (ref do canal + rótulo)."""

    ref: str
    label: str


@dataclass(frozen=True)
class EquipmentOutProjection:
    """Onde está o aparelho agora: saiu com o entregador deste pedido e não voltou."""

    ref: str
    label: str
    order_ref: str
    customer_name: str
    out_at: str


@dataclass(frozen=True)
class OrderCardProjection:
    """A single order card in the operator queue."""

    ref: str
    status: str
    status_label: str
    status_color: str
    channel_ref: str
    channel_icon: str
    customer_name: str
    created_at_display: str
    created_at_iso: str
    server_now_iso: str
    elapsed_seconds: int
    timer_class: str  # "timer-ok", "timer-warning", "timer-urgent", "timer-muted"
    items_summary: str
    items_count: int
    total_display: str
    fulfillment_icon: str  # Material Symbol ligature
    fulfillment_label: str
    fulfillment_type: str  # "delivery" | "pickup" — eixo de triagem no board
    # Para onde vai o pedido. Vazios na retirada. Sem estes dois campos o Gestor
    # não tinha endereço em tela nenhuma, e quem despacha ficava sem destino.
    delivery_address: str
    delivery_instructions: str
    can_confirm: bool
    can_advance: bool
    next_status: str
    next_action_label: str
    payment_method: str
    payment_method_label: str
    payment_status: str
    payment_pending: bool
    # Tom do pill de pagamento. Três estados, não dois: dinheiro/externo não é
    # "pago" nem "devendo" — é cobrança fora do site, e pintá-lo de verde diria
    # que entrou dinheiro que não entrou.
    payment_tone: str  # "warning" (esperando) | "success" (pago) | "neutral" (offline)
    # Por que não dá para avançar agora. O botão sumia quando bloqueado, e o
    # operador ficava sem saber se faltava algo ou se a tela tinha falhado.
    advance_block_label: str
    advance_block_reason: str
    can_settle_delivery_cash: bool
    fiscal_status_label: str
    fiscal_status: str
    # Duas notas, dois donos (data-schemas): ``kitchen_note`` é a nota do
    # OPERADOR; ``order_notes`` é a observação do CLIENTE no checkout. O antigo
    # ``has_notes`` só olhava a nota do operador — a voz do cliente chegava ao
    # KDS e nunca ao Gestor. O card só INDICA presença (selo compacto); o
    # conteúdo mora no detalhe, cada nota com seu nome.
    has_kitchen_note: bool
    has_customer_note: bool
    # Presente: quem embala precisa saber sem abrir o detalhe. O destinatário é
    # opcional na retirada (gift.py) — o selo distingue "entregar a alguém" de
    # "só embalar", e o nome/recado ficam no detalhe.
    is_gift: bool
    gift_has_recipient: bool
    assigned_operator: str
    awaiting_work_orders: tuple[AwaitingWorkOrderProjection, ...]
    # Prazo da confirmação otimista (só em pedidos NEW com timer agendado). Vazio
    # quando não há timer (confirmação manual, fora de NEW). O gestor renderiza um
    # countdown para o cliente não ficar no escuro sobre o prazo.
    confirmation_deadline_iso: str = ""
    confirmation_action: str = ""  # "confirm" | "cancel" — ação do directive ao vencer
    # Corrida externa (Machine): letra crua + label p/ badge no board. Vazios
    # quando não há corrida registrada no pedido.
    courier_status: str = ""
    courier_status_label: str = ""
    # Encomenda (WP-D): pedido com data futura. ``commitment_date`` ISO +
    # display curto ("amanhã", "sáb, 19/07") para o badge do card. Um pedido
    # deixa de ser encomenda no dia (mesma régua do lifecycle).
    is_preorder: bool = False
    commitment_date: str = ""
    commitment_date_display: str = ""
    # Troco da entrega (WP-9): o que a loja coletou no checkout e o que o livro
    # do caixa diz. ``change_for_q`` é com quanto o cliente paga (0 = não disse);
    # ``change_out_suggested_q`` é o troco que a loja sugere levar
    # (``change_for − total``, enquanto não acertado); ``change_out_q`` é o que
    # de fato saiu da gaveta com o entregador (``courier_out``);
    # ``change_back_pending`` enquanto o acerto não disser quanto voltou;
    # ``change_back_q`` o que voltou (``courier_in``). ``change_label`` é a frase
    # pronta para o card/painel, vazia quando não há troco na história.
    change_for_q: int = 0
    change_out_suggested_q: int = 0
    change_out_q: int = 0
    change_back_pending: bool = False
    change_back_q: int = 0
    change_label: str = ""
    # Aparelho que saiu com o entregador (maquininha): custódia no pedido
    # (``Order.data.dispatch``), não no caixa. ``equipment_options`` é o que o
    # canal permite levar (o despacho pergunta só quando há opção);
    # ``equipment_out`` o que saiu; ``equipment_back_pending`` enquanto não voltou.
    equipment_options: tuple[EquipmentOptionProjection, ...] = ()
    equipment_out: tuple[str, ...] = ()
    equipment_label: str = ""
    equipment_back_pending: bool = False
    # Fila de espera (WP-P2E): o pedido que espera fornada não está parado por
    # descuido, e o que tem janela de confirmação aberta tem relógio correndo do
    # lado do CLIENTE. Sem o selo os dois se parecem com "pedido travado" no
    # board, e alguém cutuca o que não devia.
    # "" | "fermata" | "confirming" | "confirmed" | "released"
    waitlist_state: str = ""
    waitlist_deadline_iso: str = ""
    waitlist_label: str = ""


@dataclass(frozen=True)
class OperatorOrderProjection:
    """Expanded detail for a single order (operator side-panel)."""

    ref: str
    status: str
    status_label: str
    status_color: str
    customer_name: str
    channel_ref: str
    channel_icon: str
    fulfillment_label: str
    fulfillment_type: str  # "delivery" | "pickup"
    # Idem ao cartão: quem abre o detalhe para despachar precisa do endereço.
    delivery_address: str
    delivery_instructions: str
    total_display: str
    items: tuple[OrderItemProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    kitchen_note: str
    # Observação do CLIENTE (``order_notes``, escrita no checkout). Dona
    # diferente da ``kitchen_note`` (do operador): o Gestor mostra as duas, e
    # só a da cozinha é editável.
    customer_note: str
    payment_method: str
    payment_method_label: str
    payment_status: str
    # As MESMAS respostas que o board usa, calculadas pelo mesmo serviço. O
    # detalhe não as tinha e a tela chutava: a guarda do "Avançar" era
    # ``can_settle_delivery_cash !== undefined``, que é sempre verdadeira, e o
    # "Aceitar" não tinha guarda nenhuma. O operador via os dois botões cheios
    # num pedido `new` e levava 400 do servidor. Com o board e o detalhe lendo a
    # mesma fonte, os dois não podem mais discordar sobre o que é possível.
    can_confirm: bool
    can_advance: bool
    # Cancelar tem três camadas e a tela precisa das três numa resposta só:
    # `can_cancel` já é régua + política + permissão deste usuário, e
    # `cancel_requires_approval` avisa que virá o desafio de gerente ANTES do
    # operador digitar o motivo. Ver `OrderCancelView`.
    can_cancel: bool
    cancel_requires_approval: bool
    cancel_block_label: str
    next_action_label: str
    advance_block_label: str
    advance_block_reason: str
    can_settle_delivery_cash: bool
    fiscal_status_label: str
    fiscal_status: str
    fiscal_links: tuple[dict[str, str], ...]
    awaiting_work_orders: tuple[AwaitingWorkOrderProjection, ...]
    is_gift: bool
    gift_recipient_name: str
    gift_recipient_phone: str
    gift_message: str
    gift_hide_values: bool
    cancellation_presets: tuple[str, ...]
    kitchen_note_tags: tuple[str, ...]
    # Corrida de entrega na logística externa (Machine). None quando não se
    # aplica (retirada, ou canal sem adapter courier e sem corrida registrada).
    courier: dict | None = None
    # Troco da entrega (WP-9): o que a loja coletou no checkout e o que o livro
    # do caixa diz. ``change_for_q`` é com quanto o cliente paga (0 = não disse);
    # ``change_out_suggested_q`` é o troco que a loja sugere levar
    # (``change_for − total``, enquanto não acertado); ``change_out_q`` é o que
    # de fato saiu da gaveta com o entregador (``courier_out``);
    # ``change_back_pending`` enquanto o acerto não disser quanto voltou;
    # ``change_back_q`` o que voltou (``courier_in``). ``change_label`` é a frase
    # pronta para o card/painel, vazia quando não há troco na história.
    change_for_q: int = 0
    change_out_suggested_q: int = 0
    change_out_q: int = 0
    change_back_pending: bool = False
    change_back_q: int = 0
    change_label: str = ""
    # Aparelho que saiu com o entregador (maquininha): custódia no pedido
    # (``Order.data.dispatch``), não no caixa. ``equipment_options`` é o que o
    # canal permite levar (o despacho pergunta só quando há opção);
    # ``equipment_out`` o que saiu; ``equipment_back_pending`` enquanto não voltou.
    equipment_options: tuple[EquipmentOptionProjection, ...] = ()
    equipment_out: tuple[str, ...] = ()
    equipment_label: str = ""
    equipment_back_pending: bool = False
    # Link de pagamento do pedido remoto (WP-PAGAMENTO, frente 5). O botão
    # "Reenviar link" só existe quando o servidor vai aceitar o gesto
    # (``notification.payment_link_resend_refusal``): forma ``link`` com URL,
    # pedido vivo, não pago, link não vencido. A cadência (cedo demais, envio
    # em andamento) é recusa da hora do clique, com toast — não esconde botão.
    # ``payment_link_notice`` é a prova de envio, lida da última Directive do
    # aviso: "Enviando…", "Link enviado às 14h32" ou "falhou — reenvie".
    can_resend_payment_link: bool = False
    payment_link_notice: str = ""


@dataclass(frozen=True)
class OrderQueueProjection:
    """Top-level read model for the operator order queue."""

    orders: tuple[OrderCardProjection, ...]
    counts: dict[str, int]  # status → count, includes "all"
    active_filter: str


@dataclass(frozen=True)
class TwoZoneQueueProjection:
    """Operator queue grouped by action area: intake, prep and expedition
    (rendered as the Entrada, Preparo and Saída columns)."""

    intake: tuple[OrderCardProjection, ...]
    preparing_count: int
    prep: tuple[OrderCardProjection, ...]
    expedition_pickup: tuple[OrderCardProjection, ...]
    expedition_delivery: tuple[OrderCardProjection, ...]
    expedition_delivery_transit: tuple[OrderCardProjection, ...]
    expedition_delivery_count: int
    expedition_count: int
    total_count: int
    # Encomendas para datas futuras (WP-D): fora das colunas do dia, ordenadas
    # pela data combinada. Inclui pedidos NOVOS (ainda a aceitar) e confirmados —
    # ambos carregam o badge "Agendado · <data>", então pertencem aqui, não na
    # Entrada (o badge e a seção precisam concordar). O card novo mantém prazo de
    # confirmação e ação de aceitar. No dia, o despertador (preorder.activate)
    # devolve o pedido ao fluxo normal.
    preorders: tuple[OrderCardProjection, ...] = ()
    preorders_count: int = 0
    # Aparelhos na rua (saíram com o entregador e não voltaram), para o quadro
    # responder "onde está a maquininha" sem procurar card por card.
    equipment_out: tuple[EquipmentOutProjection, ...] = ()


# ── Builders ───────────────────────────────────────────────────────────


def build_order_queue(
    *,
    filter_status: str = "all",
) -> OrderQueueProjection:
    """Build the operator order queue projection.

    Queries all active orders, counts per status, then applies filter.
    """
    all_orders = list(
        Order.objects.filter(status__in=ACTIVE_STATUSES)
        .prefetch_related("items")
        .order_by("created_at")
    )

    counts = _status_counts(all_orders)

    if filter_status != "all" and filter_status in ACTIVE_STATUSES:
        filtered = [o for o in all_orders if o.status == filter_status]
    else:
        filtered = all_orders
        filter_status = "all"

    courier_change = operator_orders.courier_change_by_order([o.ref for o in filtered])
    cards = tuple(_build_card(o, courier_change=courier_change) for o in filtered)

    return OrderQueueProjection(
        orders=cards,
        counts=counts,
        active_filter=filter_status,
    )


def _cancel_capability(order: Order, user) -> dict:
    """Régua + política + permissão numa resposta só, para a tela não adivinhar.

    O botão Cancelar vivia sem guarda nenhuma e o servidor respondia
    ``200 {"ok": true}`` sem cancelar. Agora a capability é a mesma que a view
    aplica — e é ela que decide, não a tela.

    ``user`` ausente (projeção fora de request, teste, job) resolve só régua e
    política: sem ator não há o que autorizar, e um ``True`` otimista aqui
    devolveria o botão mentiroso pela porta dos fundos.
    """
    from shopman.shop.services import cancellation as cancellation_service

    policy = cancellation_service.operator_cancel_policy(order)
    if not policy.allowed:
        return {
            "can_cancel": False,
            "cancel_requires_approval": False,
            "cancel_block_label": policy.reason,
        }

    if cancellation_service.is_advanced_cancel(order):
        autorizado = bool(user and user.has_perm(cancellation_service.ADVANCED_CANCEL_PERMISSION))
        if not autorizado:
            return {
                "can_cancel": False,
                "cancel_requires_approval": False,
                "cancel_block_label": f"Cancelar pedido em {order.get_status_display()} é do gerente.",
            }

    return {
        "can_cancel": True,
        "cancel_requires_approval": policy.requires_approval,
        "cancel_block_label": "",
    }


def build_operator_order(order: Order, *, user=None) -> OperatorOrderProjection:
    """Build the expanded detail projection for a single order."""
    items = tuple(
        OrderItemProjection(
            sku=it.sku,
            name=it.name or it.sku,
            qty=int(it.qty),
            unit_price_display=_money(it.unit_price_q),
            total_display=_money(it.line_total_q),
        )
        for it in order.items.all()
    )

    timeline = _build_timeline(order)
    customer_data = order.data.get("customer", {})
    customer_name = _format_customer_display(
        customer_data.get("name", "")
        or customer_data.get("phone", "")
        or order.data.get("customer_phone", "")
        or order.handle_ref
        or ""
    )
    payment_data = order.data.get("payment", {})
    method = payment_data.get("method", "")
    payment_status = _payment_status(order)
    payment_method_label = _payment_method_label(method, payment_data)
    fiscal_status, fiscal_status_label, fiscal_links = _fiscal_status(order)

    recipient = order.data.get("recipient") if isinstance(order.data.get("recipient"), dict) else {}
    is_delivery = _is_delivery(order)
    delivery_address, delivery_instructions = _delivery_address(order)
    bloqueio = operator_orders.advance_block(order)
    next_status = operator_orders.next_status_for(order) if not bloqueio else ""

    return OperatorOrderProjection(
        ref=order.ref,
        status=order.status,
        status_label=order_status_label(order.status),
        status_color=status_color(order.status),
        customer_name=customer_name,
        channel_ref=order.channel_ref or "",
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        fulfillment_label=_fulfillment_label(is_delivery),
        fulfillment_type="delivery" if is_delivery else "pickup",
        delivery_address=delivery_address,
        delivery_instructions=delivery_instructions,
        total_display=_money(order.total_q),
        items=items,
        timeline=timeline,
        kitchen_note=order.data.get("kitchen_note", ""),
        customer_note=str(order.data.get("order_notes", "") or ""),
        payment_method=method,
        payment_method_label=payment_method_label,
        payment_status=payment_status,
        can_confirm=order.status == "new",
        can_advance=bool(next_status),
        **_cancel_capability(order, user),
        next_action_label=_next_label(order),
        advance_block_label=_advance_block_label(bloqueio),
        advance_block_reason=operator_orders.advance_block_message(bloqueio),
        can_settle_delivery_cash=_can_settle_delivery_cash(order, payment_data),
        fiscal_status=fiscal_status,
        fiscal_status_label=fiscal_status_label,
        fiscal_links=fiscal_links,
        awaiting_work_orders=_awaiting_work_orders(order),
        is_gift=bool(order.data.get("is_gift")),
        gift_recipient_name=str(recipient.get("name", "") or ""),
        gift_recipient_phone=str(recipient.get("phone", "") or ""),
        gift_message=str(order.data.get("gift_message", "") or ""),
        gift_hide_values=bool(order.data.get("gift_hide_values")),
        cancellation_presets=_cancellation_presets(),
        kitchen_note_tags=_kitchen_note_tags(),
        courier=_courier_block(order),
        **_courier_change_fields(order),
        **_equipment_fields(order),
        **_payment_link_fields(order, method),
    )


#: Letra Machine → label pt-BR do operador (fonte única do gestor).
COURIER_STATUS_LABELS = {
    "D": "Procurando entregador",
    "G": "Aguardando aceite",
    "P": "Procurando entregador",
    "A": "Entregador a caminho da loja",
    "S": "Entregador na loja",
    "E": "Saiu para entrega",
    "F": "Entregue",
    "N": "Não atendida",
    "C": "Corrida cancelada",
    "U": "Agrupada",
}


def _courier_block(order: Order) -> dict | None:
    """Read-model da corrida (Order.data['courier']) + ações possíveis.

    None quando entrega externa não se aplica ao pedido. Nunca falha a
    projection: qualquer erro degrada para None com log.
    """
    try:
        if not _is_delivery(order):
            return None

        from django.core.cache import cache

        from shopman.shop.adapters import get_adapter
        from shopman.shop.adapters.courier_machine import (
            CANCELLABLE_STATUSES,
            TERMINAL_STATUSES,
        )

        data = order.data or {}
        block = data.get("courier") if isinstance(data.get("courier"), dict) else {}
        adapter_on = get_adapter("courier") is not None
        if not block and not adapter_on:
            return None

        ride_status = str(block.get("status") or "")
        active = bool(block.get("id_mch")) and ride_status not in TERMINAL_STATUSES
        order_can_ride = order.status in (Order.Status.READY, Order.Status.DISPATCHED)

        estimate = block.get("estimate") if isinstance(block.get("estimate"), dict) else {}
        estimate_display = ""
        if estimate.get("value_q") is not None:
            parts = [_money(int(estimate["value_q"]))]
            if estimate.get("minutes"):
                parts.append(f"{int(estimate['minutes'])} min")
            if estimate.get("km"):
                parts.append(f"{float(estimate['km']):.1f} km".replace(".", ","))
            estimate_display = " · ".join(parts)

        position = None
        if active and block.get("id_mch"):
            position = cache.get(f"courier:pos:{block['id_mch']}")

        error = block.get("error") if isinstance(block.get("error"), dict) else None

        return {
            "provider": str(block.get("provider") or ("machine" if adapter_on else "")),
            "status": ride_status,
            "status_label": COURIER_STATUS_LABELS.get(ride_status, ""),
            "active": active,
            "driver": block.get("driver") if isinstance(block.get("driver"), dict) else None,
            "tracking_url": str(block.get("tracking_url") or ""),
            "confirmation_code": str(block.get("confirmation_code") or ""),
            "estimate_display": estimate_display,
            "final_value_display": (
                _money(int(block["final_value_q"]))
                if block.get("final_value_q") is not None
                else ""
            ),
            "requested_at": str(block.get("requested_at") or ""),
            "dispatched_at": str(block.get("dispatched_at") or ""),
            "finished_at": str(block.get("finished_at") or ""),
            "attempts_count": len(block.get("attempts") or []),
            "position": position,
            "error": error,
            "can_quote": adapter_on and not active and order.status not in ("cancelled", "completed"),
            "can_dispatch": adapter_on and not active and order_can_ride,
            "can_cancel": active and ride_status in CANCELLABLE_STATUSES,
        }
    except Exception:
        logger.debug("orders.courier_block_failed order=%s", order.ref, exc_info=True)
        return None


def _cancellation_presets() -> tuple[str, ...]:
    """Store-configured reject/cancel justification presets (Admin/Unfold).

    The operator injects one with a tap in the gestor; the chosen text is sent to
    the customer in the cancellation notification. Read from the Shop singleton;
    never fails the projection.
    """
    try:
        from shopman.shop.models import Shop

        presets = Shop.load().cancellation_presets or []
    except Exception:
        logger.debug("orders.cancellation_presets_read_failed", exc_info=True)
        return ()
    return tuple(str(p).strip() for p in presets if str(p).strip())


def _kitchen_note_tags() -> tuple[str, ...]:
    """Store-configured kitchen-note tags (Admin/Unfold).

    The operator appends one with a tap in the gestor; the resulting note is shown
    on the KDS ticket for the kitchen. Read from the Shop singleton; never fails
    the projection.
    """
    try:
        from shopman.shop.models import Shop

        tags = Shop.load().kitchen_note_tags or []
    except Exception:
        logger.debug("orders.kitchen_note_tags_read_failed", exc_info=True)
        return ()
    return tuple(str(t).strip() for t in tags if str(t).strip())


def build_order_card(order: Order) -> OrderCardProjection:
    """Build a single order card projection (for HTMX partial re-renders)."""
    return _build_card(order)


def build_two_zone_queue() -> TwoZoneQueueProjection:
    """Build the operator queue grouped by the next physical action."""
    all_orders = list(
        Order.objects.filter(status__in=ACTIVE_STATUSES)
        .prefetch_related("items")
        .order_by("created_at")
    )

    new_orders = [o for o in all_orders if o.status == "new"]
    deadlines = _confirmation_deadlines([o.ref for o in new_orders])
    # Uma consulta ao livro para todos os cards: o troco que saiu e voltou.
    courier_change = operator_orders.courier_change_by_order([o.ref for o in all_orders if _is_delivery(o)])
    # Encomenda para data futura não é trabalho do dia — vive no grupo "Agendados",
    # nunca na Entrada/Preparo do dia. Vale para pedido NOVO (ainda a aceitar) e
    # confirmado: o card de encomenda carrega o badge "Agendado · <data>", então
    # tê-lo na Entrada com esse badge é contraditório para o operador. O card novo
    # mantém o prazo de confirmação (auto-confirm) e o botão de aceitar; o
    # despertador (preorder.activate) devolve o pedido ao fluxo na data (WP-D).
    intake = tuple(
        _build_card(o, deadline=deadlines.get(o.ref))
        for o in new_orders
        if not _is_future_preorder(o)
    )
    prep_orders = [o for o in all_orders if o.status in ("accepted", "preparing")]
    prep = tuple(_build_card(o, courier_change=courier_change) for o in prep_orders if not _is_future_preorder(o))
    # Só estados pré-fulfillment viram "Agendados"; ready/dispatched/delivered
    # seguem nas colunas de expedição mesmo que a data combinada seja futura.
    future_preorders = [
        o for o in all_orders
        if o.status in ("new", "accepted", "preparing") and _is_future_preorder(o)
    ]
    preorders = tuple(
        _build_card(o, deadline=deadlines.get(o.ref))
        for o in sorted(future_preorders, key=lambda o: (get_commitment_date(o), o.created_at))
    )
    preparing_count = len(prep)

    ready_orders = [o for o in all_orders if o.status == "ready"]
    expedition_pickup = tuple(_build_card(o) for o in ready_orders if not _is_delivery(o))
    expedition_delivery = tuple(_build_card(o, courier_change=courier_change) for o in ready_orders if _is_delivery(o))
    expedition_delivery_transit = tuple(
        _build_card(o, courier_change=courier_change)
        for o in all_orders
        if o.status in ("dispatched", "delivered")
    )

    return TwoZoneQueueProjection(
        equipment_out=_equipment_out(),
        intake=intake,
        preparing_count=preparing_count,
        prep=prep,
        expedition_pickup=expedition_pickup,
        expedition_delivery=expedition_delivery,
        expedition_delivery_transit=expedition_delivery_transit,
        expedition_delivery_count=len(expedition_delivery) + len(expedition_delivery_transit),
        expedition_count=len(expedition_pickup)
        + len(expedition_delivery)
        + len(expedition_delivery_transit),
        total_count=len(all_orders),
        preorders=preorders,
        preorders_count=len(preorders),
    )


# ── Internals ──────────────────────────────────────────────────────────


def _confirmation_deadlines(refs: list[str]) -> dict[str, tuple[str, str]]:
    """{order_ref: (expires_at_iso, action)} dos timers de confirmação pendentes.

    Batch (sem N+1): busca os directives confirmation.timeout queued uma vez e
    filtra em Python (normalmente há poucos pendentes)."""
    if not refs:
        return {}
    from shopman.orderman.models import Directive

    out: dict[str, tuple[str, str]] = {}
    # Filtra no DB pelos refs em questão (não traz TODOS os timers queued) — casa
    # a query ao conjunto pequeno de pedidos NEW mesmo se a fila acumular.
    directives = (
        Directive.objects.filter(
            topic="confirmation.timeout", status="queued", payload__order_ref__in=list(refs)
        )
        .order_by("available_at", "id")
    )
    for d in directives:
        ref = (d.payload or {}).get("order_ref")
        if ref and ref not in out:
            out[ref] = (str((d.payload or {}).get("expires_at") or ""), str((d.payload or {}).get("action") or ""))
    return out


def _is_future_preorder(order: Order) -> bool:
    """Encomenda = data combinada no futuro (régua do lifecycle)."""
    commitment = get_commitment_date(order)
    return commitment is not None and commitment > timezone.localdate()


def _commitment_date_display(commitment) -> str:
    """Display curto da data combinada para o badge do card do operador."""
    from datetime import timedelta

    from django.utils import formats

    today = timezone.localdate()
    if commitment == today:
        return "hoje"
    if commitment == today + timedelta(days=1):
        return "amanhã"
    return f"{formats.date_format(commitment, 'D')}, {formats.date_format(commitment, 'd/m')}"


_WAITLIST_LABELS = {
    "fermata": "Na fila da fornada",
    "confirming": "Aguardando o cliente confirmar",
    "confirmed": "Confirmado pelo cliente",
    "released": "Vaga liberada",
}


def _waitlist_badge(order: Order) -> tuple[str, str, str]:
    """Estado da fila para o card do board (WP-P2E).

    Pedido esperando fornada não é pedido travado, e a diferença precisa estar
    na tela: sem o selo, os dois se parecem, e quem opera cutuca o que não deve.
    """
    try:
        from shopman.shop.services import waitlist

        state = waitlist.state_for(order)
    except Exception:
        logger.debug("order_queue._waitlist_badge degraded ref=%s", order.ref, exc_info=True)
        return "", "", ""
    if state == "none":
        return "", "", ""
    block = (order.data or {}).get("waitlist") or {}
    deadline = str(block.get("deadline") or "") if state == "confirming" else ""
    return state, deadline, _WAITLIST_LABELS.get(state, "")


def _build_card(
    order: Order,
    deadline: tuple[str, str] | None = None,
    courier_change: dict[str, tuple[int, int | None]] | None = None,
) -> OrderCardProjection:
    now = timezone.now()
    elapsed = (now - order.created_at).total_seconds()

    timer_class = _timer_class(order.status, elapsed)

    items_qs = list(order.items.all()[:4])
    items_summary = ", ".join(
        f"{int(it.qty)}x {it.name or it.sku}" for it in items_qs[:3]
    )
    if len(items_qs) > 3:
        items_summary += "..."

    items_count = order.items.count()

    is_delivery = _is_delivery(order)
    fulfillment_icon = "local_shipping" if is_delivery else "storefront"
    fulfillment_label = _fulfillment_label(is_delivery)
    delivery_address, delivery_instructions = _delivery_address(order)

    customer_data = order.data.get("customer", {})
    customer_name = _format_customer_display(
        customer_data.get("name", "")
        or customer_data.get("phone", "")
        or order.data.get("customer_phone", "")
        or order.handle_ref
        or ""
    )

    bloqueio = operator_orders.advance_block(order)
    next_status = operator_orders.next_status_for(order) if not bloqueio else ""
    next_label = _next_label(order)

    payment_data = order.data.get("payment", {})
    method = payment_data.get("method", "")
    payment_status = _payment_status(order)
    payment_method_label = _payment_method_label(method, payment_data)
    fiscal_status, fiscal_status_label, _fiscal_links = _fiscal_status(order)
    commitment = get_commitment_date(order)
    is_preorder = commitment is not None and commitment > timezone.localdate()
    waitlist_state, waitlist_deadline_iso, waitlist_label = _waitlist_badge(order)
    recipient = order.data.get("recipient") if isinstance(order.data.get("recipient"), dict) else {}

    return OrderCardProjection(
        ref=order.ref,
        status=order.status,
        status_label=order_status_label(order.status),
        status_color=status_color(order.status),
        channel_ref=order.channel_ref or "",
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        created_at_display=_format_datetime(order.created_at),
        created_at_iso=order.created_at.isoformat(),
        server_now_iso=now.isoformat(),
        elapsed_seconds=int(elapsed),
        timer_class=timer_class,
        items_summary=items_summary,
        items_count=items_count,
        total_display=_money(order.total_q),
        fulfillment_icon=fulfillment_icon,
        fulfillment_label=fulfillment_label,
        fulfillment_type="delivery" if is_delivery else "pickup",
        delivery_address=delivery_address,
        delivery_instructions=delivery_instructions,
        can_confirm=order.status == "new",
        can_advance=bool(next_status),
        next_status=next_status,
        next_action_label=next_label,
        payment_method=method,
        payment_method_label=payment_method_label,
        payment_status=payment_status,
        payment_pending=_is_payment_pending(order, method, payment_status),
        payment_tone=_payment_tone(order, method, payment_status, payment_data),
        advance_block_label=_advance_block_label(bloqueio),
        advance_block_reason=operator_orders.advance_block_message(bloqueio),
        can_settle_delivery_cash=_can_settle_delivery_cash(order, payment_data),
        fiscal_status_label=fiscal_status_label,
        fiscal_status=fiscal_status,
        has_kitchen_note=bool(order.data.get("kitchen_note")),
        has_customer_note=bool(str(order.data.get("order_notes", "") or "").strip()),
        is_gift=bool(order.data.get("is_gift")),
        gift_has_recipient=bool((recipient or {}).get("name")),
        assigned_operator=str((order.data.get("assignment") or {}).get("operator_name") or ""),
        awaiting_work_orders=_awaiting_work_orders(order),
        confirmation_deadline_iso=deadline[0] if deadline else "",
        confirmation_action=deadline[1] if deadline else "",
        courier_status=_card_courier_status(order),
        courier_status_label=COURIER_STATUS_LABELS.get(_card_courier_status(order), ""),
        is_preorder=is_preorder,
        commitment_date=commitment.isoformat() if commitment else "",
        commitment_date_display=_commitment_date_display(commitment) if is_preorder else "",
        **_courier_change_fields(order, courier_change),
        **_equipment_fields(order),
        waitlist_state=waitlist_state,
        waitlist_deadline_iso=waitlist_deadline_iso,
        waitlist_label=waitlist_label,
    )


#: Rótulo pt-BR dos aparelhos (a ref é contrato do canal; o texto é da tela).
EQUIPMENT_LABELS = {"card_machine": "Maquininha"}


def _equipment_label(ref: str) -> str:
    return EQUIPMENT_LABELS.get(ref, ref)


def _equipment_fields(order: Order) -> dict:
    if not _is_delivery(order):
        return {}
    options = tuple(
        EquipmentOptionProjection(ref=ref, label=_equipment_label(ref))
        for ref in operator_orders.equipment_options(order.channel_ref or "")
    )
    custody = operator_orders.equipment_custody(order)
    label = ""
    if custody.equipment:
        names = ", ".join(_equipment_label(ref) for ref in custody.equipment)
        label = f"Entregador levou {names.lower()}" if custody.pending else f"{names} voltou"
    return {
        "equipment_options": options,
        "equipment_out": custody.equipment,
        "equipment_label": label,
        "equipment_back_pending": custody.pending,
    }


def _equipment_out() -> tuple[EquipmentOutProjection, ...]:
    rows = []
    for ref, order in operator_orders.equipment_out():
        customer = order.data.get("customer", {}) if isinstance(order.data, dict) else {}
        rows.append(
            EquipmentOutProjection(
                ref=ref,
                label=_equipment_label(ref),
                order_ref=order.ref,
                customer_name=str(customer.get("name") or ""),
                out_at=operator_orders.equipment_custody(order).out_at,
            )
        )
    return tuple(rows)


def _courier_change_fields(order: Order, by_order: dict[str, tuple[int, int | None]] | None = None) -> dict:
    """Os campos de troco da entrega do card/painel, lidos do pedido e do livro.

    ``by_order`` é o mapa de ``courier_change_by_order`` quando quem chama tem
    muitos cards (uma consulta); sem ele, consulta só este pedido.
    """
    if not _is_delivery(order):
        return {}
    payment = order.data.get("payment") or {}
    if payment.get("method") != "cash" or payment.get("collection") != "on_delivery":
        return {}
    if by_order is None:
        change = operator_orders.courier_change(order)
        out_q, back_q = change.out_q, change.back_q
    else:
        out_q, back_q = by_order.get(order.ref, (0, None))
    change_for_q = operator_orders._change_for_q(order)
    suggested_q = operator_orders.change_out_suggested_q(order)
    pending = out_q > 0 and back_q is None
    return {
        "change_for_q": change_for_q,
        "change_out_suggested_q": suggested_q,
        "change_out_q": out_q,
        "change_back_pending": pending,
        "change_back_q": int(back_q or 0),
        "change_label": _change_label(change_for_q, suggested_q, out_q, back_q, settled=bool(payment.get("cod_settled_at"))),
    }


def _change_label(change_for_q: int, suggested_q: int, out_q: int, back_q: int | None, *, settled: bool) -> str:
    """A frase do troco, na ordem em que a história acontece.

    Antes do despacho: o que o cliente disse ("paga com R$ 50, levar R$ 20").
    Na rua: o que saiu da gaveta. Depois do acerto: o que voltou.
    """
    if back_q is not None:
        return f"Voltou R$ {format_money(back_q)} de troco" if out_q else ""
    if out_q > 0:
        return f"Entregador levou R$ {format_money(out_q)} de troco"
    if settled or not change_for_q:
        return ""
    if suggested_q > 0:
        return f"Cliente paga com R$ {format_money(change_for_q)} · levar R$ {format_money(suggested_q)} de troco"
    return f"Cliente paga com R$ {format_money(change_for_q)}"


def _card_courier_status(order: Order) -> str:
    block = (order.data or {}).get("courier")
    if not isinstance(block, dict):
        return ""
    return str(block.get("status") or "")


def _awaiting_work_orders(order: Order) -> tuple[AwaitingWorkOrderProjection, ...]:
    refs = tuple(dict.fromkeys((order.data or {}).get("awaiting_wo_refs") or ()))
    if not refs:
        return ()

    try:
        from shopman.craftsman.models import WorkOrder

        from shopman.backstage.projections.production import WO_STATUS_LABELS, _qty, _work_order_progress_pct
    except Exception:
        logger.debug("orders.awaiting_work_orders_import_failed order=%s", order.ref, exc_info=True)
        return ()

    work_orders = WorkOrder.objects.filter(ref__in=refs).select_related("recipe").prefetch_related("events")
    by_ref = {wo.ref: wo for wo in work_orders}
    result: list[AwaitingWorkOrderProjection] = []
    for ref in refs:
        wo = by_ref.get(ref)
        if not wo:
            continue
        result.append(
            AwaitingWorkOrderProjection(
                ref=wo.ref,
                status=wo.status,
                status_label=WO_STATUS_LABELS.get(wo.status, wo.status),
                output_sku=wo.output_sku,
                planned_qty=_qty(wo.quantity),
                finished_qty=_qty(wo.finished) if wo.finished is not None else "",
                progress_pct=_work_order_progress_pct(wo),
            )
        )
    return tuple(result)


def _is_payment_pending(order: Order, method: str, payment_status: str) -> bool:
    """True when the order needs payment capture before physical work can start."""
    if order.status not in {"new", "accepted"}:
        return False
    if method in _OFFLINE_METHODS:
        return False
    if order.status == "new" and not ((order.data or {}).get("payment") or {}).get("intent_ref"):
        return False
    return payment_status not in _PAYMENT_COMPLETE


def _has_no_payment_info(payment_data: dict) -> bool:
    """True quando o pedido não traz nenhum rastro de cobrança: sem meio, sem
    intent de Pix/cartão e sem tender de balcão/entrega.

    Um pedido assim avançando no board é um vão: sem este sinal o card fica MUDO
    (o pill some quando não há rótulo de meio) e um pedido pronto sem pagamento
    registrado se confunde no olho com um pedido pago. O operador precisa VER que
    não sabemos o status do pagamento.
    """
    return (
        not payment_data.get("method")
        and not payment_data.get("intent_ref")
        and not (payment_data.get("tenders") or [])
    )


def _offline_payment_settled(payment_data: dict) -> bool:
    """True quando um tender de balcão/entrega já foi de fato recebido.

    Venda de balcão liquida no PDV (tender ``received``); dinheiro na entrega
    (COD) nasce ``pending`` e vira ``received`` quando acertado. Pedido web para
    pagar na retirada ainda não tem tender — fica de fora, corretamente.
    """
    tenders = payment_data.get("tenders") or []
    return any(
        int(tender.get("amount_q") or 0) > 0
        and str(tender.get("status") or "") in _SETTLED_TENDER_STATUSES
        for tender in tenders
    )


def _payment_tone(order: Order, method: str, payment_status: str, payment_data: dict) -> str:
    """Tom do pill de pagamento — explícito, em vez de deduzido na superfície.

    Pagamento só ESPERANDO não é falha: é ampulheta (``warning``), não alarme
    (``danger``). Quem não paga a tempo é cancelado por ``PaymentTimeoutHandler``
    (reason ``payment_timeout``) e sai do board (``cancelled`` ∉ ``ACTIVE_STATUSES``),
    então ``danger`` no card seria alarme para um pedido que, se falhar, some sozinho.
    """
    # Pago é pago, em qualquer canal ou meio: verde primeiro. Uma captura
    # registrada (pix/cartão) vale para qualquer canal (web, whatsapp, pdv).
    if payment_status in _PAYMENT_COMPLETE:
        return "success"
    # Marketplace / "pago online": o pedido chega pré-pago (iFood comita só o que
    # já foi pago), então o dinheiro está garantido — verde, mesmo sem captura nossa.
    if method == "external":
        return "success"
    if _has_no_payment_info(payment_data):
        # Nenhum rastro de cobrança: âmbar de atenção, não o neutro de "cobra no
        # balcão". Não afirmamos "pago" nem "esperando" — apenas que não sabemos.
        return "warning"
    if method in _OFFLINE_METHODS or not method:
        # Dinheiro/cartão no balcão: verde SÓ quando de fato liquidado — tender
        # recebido no PDV, ou COD acertado na entrega. Pedido web para pagar na
        # retirada e COD ainda pendente ficam neutros: não afirmamos "pago" sem
        # recebimento. (Decisão do Pablo: "verde ao liquidar no PDV".)
        if _offline_payment_settled(payment_data):
            return "success"
        return "neutral"
    if _is_payment_pending(order, method, payment_status):
        return "warning"
    return "neutral"


_ADVANCE_BLOCK_LABELS: dict[operator_orders.AdvanceBlock, str] = {
    operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED: "Aguardando pagamento…",
    operator_orders.AdvanceBlock.PREORDER_NOT_DUE: "Encomenda do dia…",
    operator_orders.AdvanceBlock.WAITLIST_FERMATA: "Esperando a fornada…",
}


def _advance_block_label(bloqueio: operator_orders.AdvanceBlock) -> str:
    """Rótulo curto para o botão desabilitado (o motivo inteiro vai no title).

    Só ganha rótulo o bloqueio TEMPORÁRIO — aquele que a espera resolve. Pedido
    cancelado ou concluído não tem próxima etapa e por isso não ganha botão
    nenhum: lugar ocupado por algo que nunca vai destravar é ruído.
    """
    return _ADVANCE_BLOCK_LABELS.get(bloqueio, "")


def _payment_status(order: Order) -> str:
    """Return the operator-facing payment status without duplicating Payman."""
    return payment_svc.get_payment_status(order) or ""


def _payment_method_label(method: str, payment_data: dict) -> str:
    if _has_no_payment_info(payment_data):
        # Pill explícito em vez de rótulo vazio (que sumiria o pill). Ver
        # _has_no_payment_info: card mudo se confunde com pedido pago.
        return "Pagamento não informado"
    label = payment_method_label(method)
    if payment_data.get("collection") == "on_delivery":
        if payment_data.get("cod_settled_at"):
            return f"{label} entregue no caixa"
        return f"{label} na entrega"
    return label


def _can_settle_delivery_cash(order: Order, payment_data: dict) -> bool:
    return (
        _is_delivery(order)
        and payment_data.get("method") == "cash"
        and payment_data.get("collection") == "on_delivery"
        and not payment_data.get("cod_settled_at")
        and order.status in {Order.Status.DISPATCHED, Order.Status.DELIVERED, Order.Status.COMPLETED}
    )


def _payment_link_fields(order: Order, method: str) -> dict:
    """Só o pedido de LINK paga o custo (uma leitura no Payman + uma Directive)."""
    if method != "link":
        return {}
    from shopman.shop.services import notification as notification_svc

    return {
        "can_resend_payment_link": notification_svc.payment_link_resend_refusal(order) is None,
        "payment_link_notice": payment_link_notice(order),
    }


def payment_link_notice(order: Order) -> str:
    """O estado do último aviso ``payment_link_sent``, na frase que o operador lê.

    Lê a Directive mais recente do aviso (envio original ou reenvio): em fila
    ou rodando é "Enviando…"; concluída é "Link enviado às 14h32" (o handler
    não grava POR QUAL canal saiu — só que saiu); falhou é o convite ao gesto.
    Sem Directive nenhuma, nada: o pedido de link da loja online não passa por
    este aviso.
    """
    from shopman.shop.services import notification as notification_svc

    directive = notification_svc.latest_delivery(order, notification_svc.PAYMENT_LINK_TEMPLATE)
    if directive is None:
        return ""
    if directive.status in ("queued", "running"):
        return "Enviando o link ao cliente…"
    if directive.status == "done":
        return f"Link enviado {_format_time_of_day(directive.updated_at)}"
    return "O envio do link falhou. Reenvie ou copie o link."


def _format_time_of_day(dt) -> str:
    """"às 14h32" hoje; "em 02/09 às 14h32" em outro dia."""
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    hour = f"{local.hour}h{local.minute:02d}"
    if local.date() == timezone.localdate():
        return f"às {hour}"
    return f"em {local:%d/%m} às {hour}"


def _fiscal_status(order: Order) -> tuple[str, str, tuple[dict[str, str], ...]]:
    data = order.data or {}
    if data.get("nfce_cancelled"):
        status = "cancelled"
        label = "NFC-e cancelada"
    elif data.get("nfce_access_key"):
        status = "authorized"
        label = "NFC-e autorizada"
    elif not _fiscal_emission_expected(order):
        # A mesma regra que decide emitir decide o rótulo. Perguntar só ao
        # toggle escondia como "não solicitado" a falha da nota de cartão/pix
        # e a do fiado — casos em que o resolver emite sem o operador marcar.
        status = "not_requested"
        label = "Fiscal não solicitado"
    else:
        directive_status = _latest_fiscal_directive_status(order.ref)
        if directive_status == "failed":
            status = "failed"
            label = "NFC-e com falha"
        elif directive_status in {"queued", "running"}:
            status = "pending"
            label = "NFC-e pendente"
        elif order.status != Order.Status.COMPLETED:
            status = "waiting_completion"
            label = "Fiscal na conclusão"
        else:
            status = "pending"
            label = "NFC-e pendente"

    links = []
    if data.get("nfce_danfe_url"):
        links.append({"label": "DANFE", "url": data["nfce_danfe_url"]})
    if data.get("nfce_qrcode_url"):
        links.append({"label": "QR Code", "url": data["nfce_qrcode_url"]})
    return status, label, tuple(links)


def _fiscal_emission_expected(order: Order) -> bool:
    try:
        from shopman.shop.services import fiscal as fiscal_service

        return fiscal_service.emission_expected(order)
    except Exception:
        logger.debug("orders.fiscal_emission_expected_failed order=%s", order.ref, exc_info=True)
        return bool(((order.data or {}).get("fiscal") or {}).get("issue_document"))


def _latest_fiscal_directive_status(order_ref: str) -> str:
    try:
        from shopman.orderman.models import Directive

        from shopman.shop.directives import FISCAL_EMIT_NFCE
    except Exception:
        logger.debug("orders.fiscal_directive_import_failed order_ref=%s", order_ref, exc_info=True)
        return ""
    directive = (
        Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order_ref)
        .order_by("-created_at")
        .first()
    )
    return directive.status if directive else ""


def _format_customer_display(value: str) -> str:
    label = (value or "").strip()
    if not label:
        return ""

    digits = "".join(ch for ch in label if ch.isdigit())
    if not digits:
        return label

    looks_like_phone = label.startswith("+") or label.startswith("(") or len(digits) >= 10
    if not looks_like_phone:
        return label

    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]

    if digits.startswith("55") and len(digits) in (12, 13):
        ddd = digits[2:4]
        number = digits[4:]
        if len(number) == 9:
            return f"({ddd}) {number[:5]}-{number[5:]}"
        if len(number) == 8:
            return f"({ddd}) {number[:4]}-{number[4:]}"

    if label.startswith("+"):
        return "+" + digits

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"

    return label


def _timer_class(status: str, elapsed: float) -> str:
    if status == "new":
        if elapsed < 180:
            return "timer-ok"
        elif elapsed < 240:
            return "timer-warning"
        else:
            return "timer-urgent"
    return "timer-muted"


def _is_delivery(order: Order) -> bool:
    return get_fulfillment_type(order) == "delivery"


def _fulfillment_label(is_delivery: bool) -> str:
    """Rótulo do recebimento na tela do operador, em português.

    Estava escrito ``"Delivery" if is_delivery else "Retirada"``, inglês e
    português no mesmo ternário e em dois lugares — o operador lia "Delivery"
    no cartão. A convenção do projeto é URL em inglês, TEXTO de tela em
    português; centralizar aqui impede que as duas cópias voltem a divergir.
    """
    return "Entrega" if is_delivery else "Retirada"


def _delivery_address(order: Order) -> tuple[str, str]:
    """Endereço de entrega do pedido: ``(endereço, instruções)``.

    O Gestor é a tela de quem DESPACHA, e não tinha o endereço em lugar nenhum:
    a projection não trazia o campo e o app não tinha uma ocorrência de
    "address". O dado sempre existiu em ``Order.data`` (o PDV já o expunha), só
    não chegava a quem precisa mandar o pedido para algum lugar.

    Devolve ``("", "")`` na retirada, para a tela não ter que decidir nada: se
    veio vazio, não há endereço a mostrar.
    """
    if not _is_delivery(order):
        return "", ""

    data = order.data or {}
    structured = data.get("delivery_address_structured")
    structured = structured if isinstance(structured, dict) else {}

    address = str(data.get("delivery_address") or structured.get("formatted_address") or "").strip()
    complement = str(structured.get("complement") or "").strip()
    # O complemento é o que faz o entregador achar a porta (apto, bloco, fundos)
    # e nem sempre entra no texto formatado do Places. Só anexa quando ainda não
    # está lá, para não repetir "apto 42" duas vezes na mesma linha.
    if complement and complement.lower() not in address.lower():
        address = f"{address} - {complement}" if address else complement

    instructions = str(structured.get("delivery_instructions") or "").strip()
    return address, instructions


def _next_label(order: Order) -> str:
    if order.status == "ready" and _is_delivery(order):
        return READY_DELIVERY_LABEL
    return NEXT_ACTION_LABELS.get(order.status, "")


def _status_counts(orders: list[Order]) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ACTIVE_STATUSES, 0)
    for order in orders:
        if order.status in counts:
            counts[order.status] += 1
    counts["all"] = sum(counts.values())
    return counts


# O histórico é texto de tela, e texto de tela é em português. Sem um rótulo
# aqui o evento caía num `event.type.replace("_", " ").title()`, e o operador
# lia "Created" no histórico do pedido dele.
_EVENT_LABELS = {
    "operator_comment": "Comentário",
    "order_assigned": "Atendimento assumido",
    "order_unassigned": "Atendimento liberado",
    "created": "Pedido criado",
    "payment_collected": "Pagamento recebido",
    "equipment_returned": "Maquininha devolvida",
}

# Mudança de status, nas duas grafias que existem no banco: o model escreve
# `status_changed` e o histórico importado escreve `status_change`. Só a
# primeira era reconhecida, então a esmagadora maioria dos eventos virava
# "Status Change" no `.title()`.
_STATUS_EVENT_TYPES = {"status_changed", "status_change"}


def _build_timeline(order: Order) -> tuple[TimelineEventProjection, ...]:
    events = order.events.order_by("seq")
    result: list[TimelineEventProjection] = []
    for event in events:
        payload = event.payload or {}
        new_status = payload.get("new_status", "")
        if event.type in _STATUS_EVENT_TYPES and new_status:
            label = order_status_label(new_status)
        elif event.type in _EVENT_LABELS:
            label = _EVENT_LABELS[event.type]
        else:
            # Último recurso para um tipo que ninguém rotulou ainda. Continua
            # feio, mas é o caso raro; o que era comum agora tem nome.
            label = event.type.replace("_", " ").capitalize()

        result.append(
            TimelineEventProjection(
                label=label,
                event_type=event.type,
                timestamp_display=_format_datetime(event.created_at),
                actor=event.actor,
                detail=_event_detail(payload),
            )
        )
    return tuple(result)


def _event_detail(payload: dict) -> str:
    if not payload:
        return ""
    old_status = payload.get("old_status")
    new_status = payload.get("new_status")
    if old_status or new_status:
        old_label = order_status_label(old_status, old_status or "-")
        new_label = order_status_label(new_status, new_status or "-")
        return f"{old_label} -> {new_label}"
    for key in ("reason", "note", "error"):
        value = payload.get(key)
        if value:
            return str(value)
    # Sem detalhe legível, NENHUM detalhe. O fallback despejava o payload cru ao
    # lado do evento — `{"from_session": "SESS-V53LZVEYKF3Q"}` na tela de quem
    # atende o balcão. Chave interna não é informação para o operador.
    return ""


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")
