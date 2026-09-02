"""Order tracking — storefront Presentation.

Consumes the data Projection (``shop.projections.order_tracking``) plus the copy
catalog (``shop.projections.copy``) and produces the display shape the tracking
templates and the storefront REST surface consume: resolved copy, money
formatted ``R$``, ETA phrase, status label + colour token, timeline labels,
progress labels, pickup hours. **No policy** is decided here — every decision
(status semantics, promise state, progress path) already arrived sealed in the
data projection.

This module owns the *appearance* DTOs (``OrderTrackingProjection`` &c). The
canonical copy lives in the orchestrator (``OMOTENASHI_DEFAULTS``); the strings
passed to ``catalog.title``/``catalog.message`` are last-resort fallbacks (per
the approved copy.py contract: fallback PT-BR lives in Presentation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.utils.monetary import format_money

from shopman.shop.projections.copy import CopyCatalog, build_copy
from shopman.shop.projections.order_tracking import (
    TrackingData,
    TrackingFulfillmentData,
    TrackingPickupData,
    TrackingPromiseData,
    TrackingStatusData,
    build_tracking,
    build_tracking_status,
)
from shopman.shop.projections.types import (
    Action,
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.storefront.presentation.status import order_status_label, status_color
from shopman.storefront.presentation.types import (
    FulfillmentProjection,
    OrderProgressStepProjection,
)

logger = logging.getLogger(__name__)

# Surface display labels for timeline events that are not status changes.
EVENT_LABELS: dict[str, str | None] = {
    # "Criado" é o que o nosso banco fez; "recebido" é o que importa para quem
    # mandou o pedido. A linha do tempo é a loja narrando a jornada do cliente.
    "created": "Pedido recebido",
    "status_changed": None,
    "payment.captured": "Pagamento confirmado",
    "payment.refunded": "Pagamento estornado",
    "return_initiated": "Devolução solicitada",
    "refund_processed": "Reembolso processado",
    "fiscal_cancelled": "Nota fiscal cancelada",
    "fulfillment.dispatched": "Saiu para entrega",
    "fulfillment.delivered": "Pedido entregue",
}

FULFILLMENT_STATUS_LABELS: dict[str, str] = {
    "pending": "Aguardando",
    "in_progress": "Em separação",
    "dispatched": "Saiu para entrega",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

# display_status_key → (copy key, fallback). Keys absent here fall back to the
# canonical order status labels.
STATUS_LABEL_COPY: dict[str, tuple[str, str]] = {
    "payment_expired": ("TRACKING_STATUS_PAYMENT_EXPIRED", "Pagamento expirado"),
    "waiting_store_confirmation": ("TRACKING_STATUS_WAITING_STORE_CONFIRMATION", "Aguardando a loja"),
    "payment_pending": ("TRACKING_STATUS_PAYMENT_PENDING", "Aguardando pagamento"),
    "card_authorized": ("TRACKING_STATUS_CARD_AUTHORIZED", "Pagamento autorizado"),
    "ready_delivery": ("TRACKING_STATUS_READY_DELIVERY", "Aguardando entregador"),
    "ready_pickup": ("TRACKING_STATUS_READY_PICKUP", "Pronto para retirada"),
    "preorder_scheduled": ("TRACKING_STATUS_PREORDER_SCHEDULED", "Encomenda confirmada"),
}

# Semantic payment status descriptor → customer-facing label.
PAYMENT_STATUS_LABELS: dict[str, str] = {
    "payment_expired": "Pagamento expirado",
    "payment_confirmed": "Pagamento confirmado",
    "card_authorized": "Pagamento autorizado",
    "payment_pending": "Aguardando pagamento",
}

# Progress step key → (copy key, fallback). Shared by the timeline AND the
# status-panel title, so each is a short status name — the panel message carries
# the detail. Warm "nós" voice; no trailing periods (these are headings).
# Marcos da jornada do PEDIDO — terceira pessoa, particípio, sem repetir
# "Pedido" a cada linha (a lista inteira já é sobre ele). O painel de status usa
# títulos próprios (TRACKING_PROMISE_*_TITLE): manchete e marco são trabalhos
# diferentes, e compartilhar a mesma chave era o que impedia as duas superfícies
# de ficarem coerentes cada uma no seu registro.
STEP_LABEL_COPY: dict[str, tuple[str, str]] = {
    "received": ("TRACKING_STEP_RECEIVED", "Recebido"),
    "availability": ("TRACKING_STEP_AVAILABILITY_CONFIRMED", "Aceito"),
    "payment": ("TRACKING_STEP_PAYMENT_CONFIRMED", "Pago"),
    "preparing": ("TRACKING_STEP_PREPARING", "Em preparo"),
    "ready_delivery": ("TRACKING_STEP_READY_DELIVERY", "Pronto"),
    "dispatched": ("TRACKING_STEP_DISPATCHED", "Saiu para entrega"),
    "delivered": ("TRACKING_STEP_DELIVERED", "Entregue"),
    "completed": ("TRACKING_STEP_COMPLETED", "Concluído"),
    "cancelled": ("TRACKING_STEP_CANCELLED", "Cancelado"),
}

DAY_NAMES_PT = {
    "monday": "Segunda",
    "tuesday": "Terça",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sábado",
    "sunday": "Domingo",
}
DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ──────────────────────────────────────────────────────────────────────
# Presentation DTOs (appearance) — what templates / serializers consume
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PickupInfoProjection:
    """Store address and hours shown when the fulfillment type is pickup."""

    heading: str
    address: str
    opening_hours: str
    directions_label: str
    directions_url: str | None


@dataclass(frozen=True)
class OrderTrackingCopyProjection:
    """Surface chrome copy for the tracking page."""

    page_kicker: str
    order_ref_label: str
    menu_label: str
    support_label: str
    progress_heading: str
    live_badge: str
    polling_badge: str
    finished_badge: str
    items_heading: str
    total_label: str
    delivery_fee_label: str
    promise_fallback_message: str
    retry_label: str
    not_found_title: str
    not_found_description: str
    rate_limit_title: str
    cancel_success_title: str
    cancel_success_message: str
    cancel_failed_message: str
    cancel_cta: str
    cancel_dialog_title: str
    cancel_dialog_message: str
    cancel_dialog_confirm: str
    cancel_dialog_back: str
    cancelled_reason_title: str
    refund_title: str
    mock_payment_success_title: str
    mock_payment_success_message: str
    mock_payment_failed_title: str
    mock_payment_failed_message: str
    rating_success_title: str
    rating_failed_message: str
    rating_comment_placeholder: str
    rating_comment_aria_label: str
    rating_submit_label: str
    rating_thanks: str
    rating_thanks_title: str
    rating_thanks_celebrate: str
    page_meta_description: str
    delivery_heading: str
    stale_cta: str
    # Copy estática do bloco de pagamento inline (Pix/cartão), que antes vivia na
    # tela de pagamento (PAYMENT-TRACKING-MERGE).
    pix_instruction: str
    pix_copy_label: str
    pix_copy_btn: str
    pix_copied: str
    pix_expires_label: str
    pix_pending_note: str
    pix_auto_update_note: str
    card_intro: str
    card_security_note: str
    # Fila de espera (WP-P2E): o chamado tem prazo, e a tela tem que dizer isso
    # mesmo quando a notificação não chegou — ela é a superfície que sempre existe.
    waitlist_waiting_title: str
    waitlist_waiting_message: str
    waitlist_confirm_title: str
    waitlist_confirm_message: str
    waitlist_confirm_cta: str
    waitlist_confirmed_title: str
    waitlist_released_title: str
    waitlist_released_message: str


@dataclass(frozen=True)
class OrderTrackingPromiseProjection:
    """Current operational promise as rendered for the customer."""

    state: str
    title: str
    message: str
    tone: str
    deadline_at: str | None
    deadline_kind: str | None
    timer_mode: str
    deadline_action: str
    requires_active_notification: bool
    notification_topic: str | None
    actions: tuple[Action, ...] = ()
    # Nota de rodapé: complemento OPCIONAL, sem rótulo, em tom secundário. Não é
    # slot — a maioria dos estados deixa vazio. Serve para tirar da frase
    # principal a consequência que o cliente não precisa ler primeiro ("se o
    # prazo acabar…"), sem escondê-la. Quem tem nota é quem declara CONSEQUENCE.
    footnote: str = ""
    # ── Bloco de pagamento (só nos degraus com o que pagar) ──────────
    # O acompanhamento renderiza Pix/cartão inline; a antiga tela de pagamento
    # deixou de existir. Vazio na esmagadora maioria dos estados.
    payment_method: str = ""
    pix_qr_code: str | None = None
    pix_copy_paste: str | None = None
    pix_expires_at: str | None = None
    checkout_url: str | None = None
    fulfillment_wait_kind: str = ""
    fulfillment_wait_until: str | None = None


@dataclass(frozen=True)
class OrderTrackingProjection:
    """Canonical full tracking projection, rendered."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    # Encomenda (WP-D): quando o pedido tem data futura, ``when_display`` traz
    # o combinado como o cliente escolheu no checkout ("sábado, 19/07 · A
    # partir das 09h") para o cabeçalho/resumo da página.
    is_preorder: bool
    when_display: str | None
    copy: OrderTrackingCopyProjection
    promise: OrderTrackingPromiseProjection
    promise_deadline_label: str
    progress_steps: tuple[OrderProgressStepProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    items: tuple[OrderItemProjection, ...]
    total_display: str
    delivery_fee_display: str | None
    delivery_distance_display: str | None
    is_delivery: bool
    delivery_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_info: PickupInfoProjection | None
    actions: tuple[Action, ...]
    is_active: bool
    server_now_iso: str
    payment_pending: bool
    payment_expired: bool
    payment_confirmed: bool
    payment_status_label: str | None
    payment_expires_at: str | None
    confirmation_countdown: bool
    confirmation_expires_at: str | None
    eta_display: str | None
    whatsapp_url: str
    support_url: str
    share_text: str
    is_debug: bool
    last_updated_iso: str
    last_updated_display: str
    stale_after_seconds: int
    waitlist_state: str
    waitlist_deadline: str | None
    waitlist_planned_for_display: str | None
    # Captura simulada (DEBUG/staging). Vem PRONTA da projection do orquestrador,
    # que é o único dono da pergunta: ambiente + método + estado do pedido. A API
    # já a sobrescreveu com a resposta só-de-ambiente, e o resultado era o botão
    # "Simular pagamento" na tela de um pedido de cartão no Stripe real.
    mock_payment_enabled: bool
    # Cancelamento pelo estabelecimento: motivo + estorno visíveis ao cliente
    # (Pix/cartão) — a página não depende da notificação.
    cancellation_note: str = ""
    refund_status_label: str | None = None


@dataclass(frozen=True)
class OrderTrackingStatusProjection:
    """Polling projection for tracking status partials, rendered."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    progress_steps: tuple[OrderProgressStepProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    is_terminal: bool


# ──────────────────────────────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────────────────────────────


def build_order_tracking(order) -> OrderTrackingProjection:
    """Build the full tracking page projection for an Order."""
    from django.conf import settings

    return present_tracking(build_tracking(order, is_debug=settings.DEBUG))


def build_order_tracking_status(order) -> OrderTrackingStatusProjection:
    """Build the polling partial projection for an Order."""
    return present_tracking_status(build_tracking_status(order))


def present_tracking(data: TrackingData) -> OrderTrackingProjection:
    copy = build_copy("TRACKING")
    last_updated_display = copy.title("TRACKING_PROMISE_UPDATED_NOW", "Atualizado agora")
    when_display = _when_display(data.commitment_date, data.commitment_slot_ref)
    promise = _present_promise(
        data.promise,
        status=data.status,
        is_delivery=data.is_delivery,
        copy=copy,
        when_display=when_display,
        payment_confirmed=data.payment_confirmed,
    )
    return OrderTrackingProjection(
        order_ref=data.order_ref,
        status=data.status,
        status_label=_status_label(data.display_status_key, data.status, copy),
        status_color=status_color(data.display_status_key, data.status),
        is_preorder=data.is_preorder,
        when_display=when_display if data.is_preorder else None,
        copy=_tracking_copy(copy),
        promise=promise,
        promise_deadline_label=_deadline_label(promise, copy),
        progress_steps=_present_progress_steps(data, copy=copy),
        timeline=_present_timeline(data),
        items=_present_items(data),
        total_display=f"R$ {format_money(data.total_q)}",
        delivery_fee_display=_delivery_fee_display(data.delivery_fee_q),
        delivery_distance_display=_delivery_distance_display(data.delivery_distance_km),
        is_delivery=data.is_delivery,
        delivery_fulfillments=_present_fulfillments(data.delivery_fulfillments, copy=copy),
        pickup_fulfillments=_present_fulfillments(data.pickup_fulfillments, copy=copy, is_pickup=True),
        pickup_info=_present_pickup(data.pickup, copy=copy),
        actions=data.actions,
        is_active=data.is_active,
        server_now_iso=data.server_now_iso,
        payment_pending=data.payment_pending,
        payment_expired=data.payment_expired,
        payment_confirmed=data.payment_confirmed,
        payment_status_label=_payment_status_label(data.payment_status_key),
        cancellation_note=data.cancellation_note,
        refund_status_label=_refund_status_label(data.refund_status_key, copy),
        payment_expires_at=data.payment_expires_at,
        confirmation_countdown=data.confirmation_countdown,
        confirmation_expires_at=data.confirmation_expires_at,
        eta_display=_eta_display(data.eta_at),
        whatsapp_url=data.whatsapp_url,
        support_url=_support_url(data.support_url, data.order_ref, copy=copy),
        share_text=f"Meu pedido {data.order_ref} na {data.shop_name}",
        is_debug=data.is_debug,
        last_updated_iso=data.last_updated_iso,
        last_updated_display=last_updated_display,
        stale_after_seconds=data.stale_after_seconds,
        waitlist_state=data.waitlist_state,
        waitlist_deadline=data.waitlist_deadline,
        waitlist_planned_for_display=_waitlist_planned_for_display(data.waitlist_planned_for),
        mock_payment_enabled=data.can_mock_confirm_payment,
    )


def _waitlist_planned_for_display(planned_iso: str | None) -> str | None:
    """"hoje" / "amanhã" / dia da semana — o mesmo vocabulário da sacola."""
    from shopman.storefront.presentation.cart import _planned_for_display

    return _planned_for_display(planned_iso)


def present_tracking_status(data: TrackingStatusData) -> OrderTrackingStatusProjection:
    copy = build_copy("TRACKING")
    return OrderTrackingStatusProjection(
        order_ref=data.order_ref,
        status=data.status,
        status_label=_status_label(data.display_status_key, data.status, copy),
        status_color=status_color(data.display_status_key, data.status),
        progress_steps=_present_progress_steps_from(data.progress_steps, is_pickup=False, copy=copy),
        timeline=_present_timeline(data),
        is_terminal=data.is_terminal,
    )


# ──────────────────────────────────────────────────────────────────────
# Status, payment, money, ETA
# ──────────────────────────────────────────────────────────────────────


def _status_label(display_status_key: str, status: str, copy: CopyCatalog) -> str:
    spec = STATUS_LABEL_COPY.get(display_status_key)
    if spec:
        return copy.title(spec[0], spec[1])
    return order_status_label(display_status_key, "") or order_status_label(status, "") or status


def _refund_status_label(key: str | None, copy: CopyCatalog) -> str | None:
    if not key:
        return None
    return copy.title(f"TRACKING_REFUND_STATUS_{key.upper()}", "Reembolso")

def _payment_status_label(payment_status_key: str | None) -> str | None:
    if not payment_status_key:
        return None
    return PAYMENT_STATUS_LABELS.get(payment_status_key)


def _delivery_distance_display(delivery_distance_km: float | None) -> str | None:
    km = delivery_distance_km
    if km is None:
        return None
    if km == int(km):
        return f"{int(km)} km"
    return f"{km:.1f}".replace(".", ",") + " km"


def _delivery_fee_display(delivery_fee_q: int | None) -> str | None:
    if delivery_fee_q is None:
        return None
    return "Grátis" if delivery_fee_q == 0 else f"R$ {format_money(delivery_fee_q)}"


def _eta_display(eta_at: str | None) -> str | None:
    if not eta_at:
        return None
    dt = parse_datetime(eta_at)
    if dt is None:
        return None
    try:
        return timezone.localtime(dt).strftime("%H:%M")
    except Exception:
        logger.debug("order_tracking._eta_display degraded", exc_info=True)
        return None


def _when_display(commitment_date_iso: str | None, slot_ref: str | None) -> str | None:
    """"sábado, 19/07 · A partir das 09h" — a data e o slot como o cliente
    escolheu no checkout (mesma composição do ``whenSummary`` da loja)."""
    date_part = _commitment_date_display(commitment_date_iso)
    if not date_part:
        return None
    if slot_ref:
        from shopman.storefront.services.pickup_slots import slot_label

        label = slot_label(slot_ref)
        if label:
            return f"{date_part} · {label}"
    return date_part


def _commitment_date_display(commitment_date_iso: str | None) -> str | None:
    if not commitment_date_iso:
        return None
    try:
        from datetime import date, timedelta

        from django.utils import formats

        commitment = date.fromisoformat(commitment_date_iso)
        today = timezone.localdate()
        if commitment == today:
            return "hoje"
        if commitment == today + timedelta(days=1):
            return "amanhã"
        return f"{formats.date_format(commitment, 'l')}, {formats.date_format(commitment, 'd/m')}"
    except Exception:
        logger.debug("order_tracking._commitment_date_display degraded", exc_info=True)
        return None


def _fmt_timestamp(iso: str | None) -> str:
    if not iso:
        return ""
    dt = parse_datetime(iso)
    if dt is None:
        return str(iso)
    try:
        return timezone.localtime(dt).strftime("%d/%m às %H:%M")
    except Exception:
        logger.debug("order_tracking._fmt_timestamp degraded", exc_info=True)
        return str(iso)


def _clean_label(value: str) -> str:
    return str(value or "").strip().rstrip(":").strip()


def _deadline_label(promise: OrderTrackingPromiseProjection, copy: CopyCatalog) -> str:
    """Rótulo do countdown por tipo de prazo — um relógio único "Prazo" era ambíguo
    (loja confirmando vs. cliente pagando são momentos diferentes)."""
    if promise.deadline_kind == "payment":
        return _clean_label(copy.message("TRACKING_PAYMENT_TIME_LEFT", "Prazo para pagar:"))
    if promise.deadline_kind == "availability":
        # A mensagem acima já diz que estamos conferindo; aqui basta dizer o que
        # o relógio mede.
        return _clean_label(copy.message("TRACKING_AUTO_CONFIRM_LABEL", "Resposta em:"))
    return _clean_label(copy.title("TRACKING_PROMISE_LABEL_DEADLINE", "Prazo:"))


def _support_url(base: str, order_ref: str, *, copy: CopyCatalog) -> str:
    if not base:
        return base
    support_message = copy.message(
        "TRACKING_SUPPORT_WHATSAPP_MESSAGE",
        "Oi! Posso ajudar com o pedido {order_ref}?",
    ).format(order_ref=order_ref)
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'text': support_message})}"


# ──────────────────────────────────────────────────────────────────────
# Promise
# ──────────────────────────────────────────────────────────────────────


# Aviso ativo por estado ("também avisamos você por um canal ativo"). Reduz a
# ansiedade de ficar olhando a tela. Só entram estados que o data projection
_TERMINAL_STATES = {"delivered", "completed", "cancelled", "returned", "payment_expired"}


# ── Obrigações da promessa: conceito, não slot ────────────────────────
#
# A projeção de dados já declara a semântica de cada estado (``actions``,
# ``deadline_action``, ``requires_active_notification``). O que o cliente
# precisa saber NÃO vira campo de texto separado com rótulo ("Próximo passo:",
# "Se expirar:"): vira UMA frase natural que já diz tudo. Rótulo em cima de
# frase curta é o que deixava o acompanhamento com cara de formulário.
#
# ``_PROMISE_COVERS`` é a declaração de que a copy daquele estado cobre cada
# obrigação. O teste de cobertura compara com as obrigações derivadas do dado —
# então a copy pode ser reescrita à vontade sem quebrar teste, mas um estado
# novo que ganhe prazo e esqueça de dizer a consequência quebra na hora.
#
# É declaração, não prova: serve para obrigar quem escreve a encarar a
# obrigação e para aparecer no diff da revisão.
NEXT_STEP = "next_step"        # o pedido espera uma ação do cliente
CONSEQUENCE = "consequence"    # algo acontece sozinho quando o prazo estoura
NOTIFICATION = "notification"  # o sistema avisa, e a copy promete isso

_PROMISE_COVERS: dict[str, frozenset[str]] = {
    "received": frozenset(),
    # Bola da loja: conferindo (com relógio de auto-confirmação ou aguardando o
    # código Pix nascer) e loja fechada.
    "store_checking": frozenset({CONSEQUENCE, NOTIFICATION}),
    "store_closed": frozenset(),
    "preorder_scheduled": frozenset(),
    # Bola do cliente: o código/link existe e ele precisa pagar.
    "payment_pix_ready": frozenset({NEXT_STEP, CONSEQUENCE, NOTIFICATION}),
    # O link do balcão tem prazo com consequência (a reserva é liberada); o
    # cartão da loja online não tem prazo e a nota fica vazia para ele.
    "payment_card_ready": frozenset({NEXT_STEP, CONSEQUENCE, NOTIFICATION}),
    "payment_retry": frozenset({NEXT_STEP}),
    "payment_preparing": frozenset({NOTIFICATION}),
    # Bola do gateway: cartão autorizado, capturando.
    "payment_authorized": frozenset(),
    "payment_confirmed": frozenset(),
    "payment_expired": frozenset({CONSEQUENCE}),
    "preparing": frozenset({NOTIFICATION}),
    "ready_pickup": frozenset({NEXT_STEP}),
    "ready_delivery": frozenset(),
    # O aviso que este estado promete é o próprio "saiu para entrega" que trouxe
    # o cliente até aqui. Não prometemos aviso de chegada: sem rastreio de
    # courier o sistema não detecta a entrega — quem fecha o loop é o botão.
    "dispatched": frozenset({NEXT_STEP, NOTIFICATION}),
    "delivered": frozenset(),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "returned": frozenset(),
}


def promise_obligations(data: TrackingPromiseData) -> frozenset[str]:
    """Obrigações que o estado declara no dado — a copy tem que dar conta delas."""
    needs: set[str] = set()
    if data.actions:
        needs.add(NEXT_STEP)
    if data.deadline_action not in {"", "none"}:
        needs.add(CONSEQUENCE)
    if data.requires_active_notification and data.state not in _TERMINAL_STATES:
        needs.add(NOTIFICATION)
    return frozenset(needs)


def _present_promise(
    data: TrackingPromiseData,
    *,
    status: str,
    is_delivery: bool,
    copy: CopyCatalog,
    when_display: str | None = None,
    payment_confirmed: bool = False,
) -> OrderTrackingPromiseProjection:
    title, message = _promise_copy(
        data,
        status=status,
        is_delivery=is_delivery,
        copy=copy,
        when_display=when_display,
        payment_confirmed=payment_confirmed,
    )
    footnote = _promise_footnote(data, copy=copy)
    return OrderTrackingPromiseProjection(
        state=data.state,
        title=title,
        message=message,
        tone=data.tone,
        deadline_at=data.deadline_at,
        deadline_kind=data.deadline_kind,
        timer_mode=data.timer_mode,
        deadline_action=data.deadline_action,
        requires_active_notification=data.requires_active_notification,
        notification_topic=data.notification_topic,
        actions=data.actions,
        footnote=footnote,
        payment_method=data.payment_method,
        pix_qr_code=data.pix_qr_code,
        pix_copy_paste=data.pix_copy_paste,
        pix_expires_at=data.pix_expires_at,
        checkout_url=data.checkout_url,
        fulfillment_wait_kind=data.fulfillment_wait_kind,
        fulfillment_wait_until=data.fulfillment_wait_until,
    )


_PROMISE_FOOTNOTE: dict[str, tuple[str, str]] = {
    "payment_pix_ready": (
        "TRACKING_PROMISE_PAYMENT_FOOTNOTE",
        "Se o prazo acabar, o pedido cancela automaticamente e avisamos você.",
    ),
    "payment_card_ready": (
        "TRACKING_PROMISE_LINK_FOOTNOTE",
        "Se o prazo passar, liberamos a reserva e avisamos você.",
    ),
    "payment_expired": (
        "TRACKING_PROMISE_EXPIRED_FOOTNOTE",
        "Você pode pedir de novo quando quiser.",
    ),
}


def _promise_footnote(data: TrackingPromiseData, *, copy: CopyCatalog) -> str:
    """Complemento opcional do estado — vazio na maioria deles, de propósito."""
    spec = _PROMISE_FOOTNOTE.get(data.state)
    if not spec:
        return ""
    if data.state == "payment_card_ready" and data.deadline_action in {"", "none"}:
        # A nota é do LINK (tem prazo); o cartão da loja online não tem, e
        # prometer consequência sem prazo seria informação solta.
        return ""
    key, fallback = spec
    return copy.message(key, fallback)


def _promise_copy(
    data: TrackingPromiseData,
    *,
    status: str,
    is_delivery: bool,
    copy: CopyCatalog,
    when_display: str | None = None,
    payment_confirmed: bool = False,
) -> tuple[str, str]:
    """Título e mensagem do estado — UMA frase que já cobre as obrigações.

    Nada de campo separado para "próximo passo" e "como resolver": o que o
    cliente precisa saber entra na própria mensagem, na ordem em que ele pensa
    (o que está acontecendo → o que fazer → o que acontece se não fizer).
    ``_PROMISE_COVERS`` declara o que cada estado cobre; o teste de cobertura
    confere contra as obrigações do dado.
    """
    state = data.state
    wait_display = when_display or _commitment_date_display(data.fulfillment_wait_until)

    if state == "preorder_scheduled":
        title = copy.title("TRACKING_PROMISE_PREORDER_TITLE", "Encomenda confirmada")
        if when_display:
            message = copy.message(
                "TRACKING_PROMISE_PREORDER_MESSAGE",
                "Pedido garantido para {when}. Preparamos tudo fresco no dia.",
            ).replace("{when}", when_display)
        else:
            message = copy.message(
                "TRACKING_PROMISE_PREORDER_MESSAGE_NO_DATE",
                "Pedido garantido. Preparamos tudo fresco no dia combinado.",
            )
        return title, message

    if state == "payment_expired":
        return _pair(copy, "TRACKING_PAYMENT_EXPIRED",
                     "Pagamento expirado",
                     "O prazo acabou e cancelamos o pedido.")

    if state == "payment_pix_ready":
        # Um estado, uma frase: o cliente copia o código e paga. Pix existe em
        # dois contratos: em post_commit a loja já aceitou antes do QR; em
        # at_commit o pedido ainda pode estar new. A copy não inventa resposta
        # de loja nem repete confirmação operacional que já aconteceu.
        if _is_preorder_wait(data):
            message = _payment_wait_message(
                data,
                copy=copy,
                wait_display=wait_display,
                method="pix",
            )
            return copy.title("TRACKING_PAYMENT_REQUESTED", "Pague com Pix"), message
        message = (
            copy.message(
                "TRACKING_PAYMENT_PIX_READY_MESSAGE_NEW",
                "Pague com o Pix abaixo. A confirmação do Pix é automática; acompanhe os próximos passos por aqui.",
            )
            if status == "new"
            else copy.message(
                "TRACKING_PAYMENT_PIX_READY_MESSAGE_ACCEPTED",
                "Pedido aceito. Pague com o Pix abaixo. A confirmação do Pix é automática; acompanhe os próximos passos por aqui.",
            )
        )
        return copy.title("TRACKING_PAYMENT_REQUESTED", "Pague com Pix"), message

    if state == "payment_card_ready":
        if data.payment_method == "link":
            # O link é o pedido REMOTO anotado no balcão: a casa anotou, o
            # cliente paga do celular, e a encomenda só é liberada contra o
            # pagamento. A frase diz até quando — o mesmo prazo do aviso e da
            # tela do PDV — e a nota de rodapé diz a consequência.
            title = copy.title("TRACKING_PROMISE_LINK_TITLE", "Pague pelo link")
            deadline = data.payment_deadline_phrase
            if deadline:
                message = copy.message(
                    "TRACKING_PROMISE_LINK_MESSAGE_DEADLINE",
                    "Anotamos seu pedido. Pague até {deadline} para garantir.",
                ).replace("{deadline}", deadline)
            else:
                message = copy.message(
                    "TRACKING_PROMISE_LINK_MESSAGE",
                    "Anotamos seu pedido. Finalize o pagamento no ambiente seguro para garantir.",
                )
            return title, message
        if _is_preorder_wait(data):
            message = _payment_wait_message(
                data,
                copy=copy,
                wait_display=wait_display,
                method="card",
            )
            return copy.title("TRACKING_PROMISE_CARD_TITLE", "Pague com cartão"), message
        if status == "new":
            card_message = copy.message(
                "TRACKING_PROMISE_CARD_MESSAGE_NEW",
                "Finalize no ambiente seguro para autorizar o cartão e acompanhar o pedido por aqui.",
            )
        else:
            card_message = copy.message(
                "TRACKING_PROMISE_CARD_MESSAGE_ACCEPTED",
                "Finalize no ambiente seguro para seguir com o pedido aceito.",
            )
        return (
            copy.title("TRACKING_PROMISE_CARD_TITLE", "Pague com cartão"),
            card_message,
        )

    if state == "payment_retry":
        return (
            copy.title("TRACKING_PROMISE_RETRY_TITLE", "Não conseguimos preparar o pagamento"),
            copy.message("TRACKING_PROMISE_RETRY_MESSAGE",
                         "Seu pedido está registrado. Tente gerar o pagamento de novo e, se não der, fale conosco."),
        )

    if state == "payment_preparing":
        if data.fulfillment_wait_kind == "preorder":
            return (
                copy.title("TRACKING_PROMISE_PIX_PREPARING_TITLE", "Gerando seu Pix"),
                copy.message(
                    "TRACKING_PROMISE_PIX_PREPARING_PREORDER_MESSAGE",
                    "Estamos gerando o Pix da sua encomenda. O código aparece aqui em instantes.",
                ),
            )
        if _is_fulfillment_wait(data):
            return (
                copy.title("TRACKING_PROMISE_PIX_PREPARING_TITLE", "Gerando seu Pix"),
                copy.message(
                    "TRACKING_PROMISE_PIX_PREPARING_WAITLIST_MESSAGE",
                    "Estamos gerando o Pix da sua reserva. O código aparece aqui em instantes.",
                ),
            )
        return (
            copy.title("TRACKING_PROMISE_PIX_PREPARING_TITLE", "Gerando seu Pix"),
            copy.message("TRACKING_PROMISE_PIX_PREPARING_MESSAGE",
                         "Pedido aceito. O código Pix aparece aqui em instantes."),
        )

    if state == "store_closed":
        if data.next_opening_phrase:
            message = copy.message(
                "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE_NEXT",
                "Estamos fechados agora. Conferimos seu pedido quando abrirmos, {next}.",
            ).replace("{next}", data.next_opening_phrase)
        else:
            message = copy.message(
                "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE",
                "Estamos fechados agora. Conferimos seu pedido assim que abrirmos.",
            )
        return copy.title("TRACKING_PROMISE_RECEIVED_TITLE", "Pedido recebido"), message

    if state == "payment_authorized":
        if _is_fulfillment_wait(data):
            if wait_display:
                if status == "new":
                    message = copy.message(
                        "TRACKING_CARD_AUTHORIZED_WAITLIST_MESSAGE",
                        "Sua reserva está na fila de espera.",
                    )
                else:
                    message = copy.message(
                        "TRACKING_CARD_AUTHORIZED_WAITLIST_MESSAGE_ACCEPTED",
                        "Sua reserva está na fila de espera. Avisamos quando estiver pronto.",
                    )
                message = message.replace("{when}", wait_display)
            else:
                if status == "new":
                    message = copy.message(
                        "TRACKING_CARD_AUTHORIZED_WAITLIST_MESSAGE_NO_DATE",
                        "Sua reserva está na fila de espera.",
                    )
                else:
                    message = copy.message(
                        "TRACKING_CARD_AUTHORIZED_WAITLIST_MESSAGE_ACCEPTED_NO_DATE",
                        "Sua reserva está na fila de espera. Avisamos quando estiver pronto.",
                    )
            return copy.title("TRACKING_CARD_AUTHORIZED", "Pagamento autorizado"), message
        message = (
            copy.message("TRACKING_CARD_AUTHORIZED_MESSAGE_NEW",
                         "Cartão autorizado. Acompanhe o pedido por aqui.")
            if status == "new"
            else copy.message("TRACKING_CARD_AUTHORIZED_MESSAGE_CONFIRMED",
                              "Cartão autorizado. Pedido aceito; acompanhe o andamento por aqui.")
        )
        return copy.title("TRACKING_CARD_AUTHORIZED", "Pagamento autorizado"), message

    if state == "store_checking":
        # Pago e conferindo é UM momento, não dois recados. O aviso separado
        # "Pagamento confirmado." empilhava uma terceira linha dizendo o que a
        # frase já podia dizer — e o histórico registra o passo de qualquer jeito.
        # Chaves literais: o scanner do usage_map lê a chamada, não a variável.
        title = copy.title("TRACKING_PROMISE_RECEIVED_TITLE", "Pedido recebido")
        if _is_fulfillment_wait(data):
            message = (
                _paid_fulfillment_wait_message(data, copy=copy, wait_display=wait_display)
                if payment_confirmed
                else _waitlist_message(data, copy=copy, wait_display=wait_display)
            )
            return title, message
        if payment_confirmed:
            return title, copy.message(
                "TRACKING_PROMISE_AVAILABILITY_MESSAGE_PAID",
                "Pagamento confirmado. Estamos conferindo a disponibilidade.",
            )
        return title, copy.message(
            "TRACKING_PROMISE_AVAILABILITY_MESSAGE",
            "Estamos conferindo a disponibilidade. Avisamos em seguida.",
        )

    if state == "received":
        # `received` é o fallback da máquina de estados, e na prática quem chega
        # aqui é o pedido JÁ confirmado esperando a cozinha (balcão, dinheiro,
        # iFood). Prometer conferência de disponibilidade ali seria mentira: ela
        # já aconteceu. Com o pedido ainda `new` (canal sem auto-confirmação), a
        # conferência de fato é o que falta.
        if status == "accepted":
            if _is_fulfillment_wait(data):
                return (
                    copy.title("TRACKING_PROMISE_CONFIRMED_WAITING", "Pedido aceito"),
                    _waitlist_message(data, copy=copy, wait_display=wait_display),
                )
            return _pair(copy, "TRACKING_PROMISE_CONFIRMED_WAITING",
                         "Pedido aceito",
                         "Acompanhe o andamento por aqui.")
        if _is_fulfillment_wait(data):
            return (
                copy.title("TRACKING_PROMISE_RECEIVED_TITLE", "Pedido recebido"),
                _waitlist_message(data, copy=copy, wait_display=wait_display),
            )
        return (
            copy.title("TRACKING_PROMISE_RECEIVED_TITLE", "Pedido recebido"),
            copy.message("TRACKING_PROMISE_AVAILABILITY_MESSAGE",
                         "Estamos conferindo a disponibilidade. Avisamos em seguida."),
        )

    if state == "payment_confirmed":
        if _is_fulfillment_wait(data):
            message = _waitlist_message(data, copy=copy, wait_display=wait_display)
            return copy.title("TRACKING_PROMISE_PAYMENT_TITLE", "Pagamento confirmado"), message
        message = (
            copy.message("TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE_NEW",
                         "Estamos conferindo a disponibilidade.")
            if status == "new"
            else copy.message("TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE_CONFIRMED",
                              "Pedido aceito. Acompanhe o andamento por aqui.")
        )
        return copy.title("TRACKING_PROMISE_PAYMENT_TITLE", "Pagamento confirmado"), message

    if state == "preparing":
        eta_display = _eta_display(data.eta_at)
        if is_delivery:
            message = (
                copy.message("TRACKING_PROMISE_PREPARING_MESSAGE_DELIVERY_ETA",
                             "Deve sair para entrega às {eta}. Avisamos quando sair.")
                .replace("{eta}", eta_display)
                if eta_display
                else copy.message("TRACKING_PROMISE_PREPARING_MESSAGE_DELIVERY",
                                  "Avisamos quando sair para entrega.")
            )
        else:
            message = (
                copy.message("TRACKING_PROMISE_PREPARING_MESSAGE_PICKUP_ETA",
                             "Deve ficar pronto às {eta}. Avisamos quando estiver.")
                .replace("{eta}", eta_display)
                if eta_display
                else copy.message("TRACKING_PROMISE_PREPARING_MESSAGE_PICKUP",
                                  "Avisamos assim que estiver pronto.")
            )
        return copy.title("TRACKING_PROMISE_PREPARING_TITLE", "Preparando…"), message

    if state == "ready_delivery":
        return _pair(copy, "TRACKING_DELIVERY_WAITING_COURIER",
                     "Pronto para coleta",
                     "Estamos aguardando um entregador.")

    if state == "ready_pickup":
        return (
            copy.title("TRACKING_PROMISE_READY_PICKUP_TITLE", "Pronto para retirada"),
            copy.message("TRACKING_PROMISE_READY_PICKUP_MESSAGE",
                         "Está esperando por você no balcão."),
        )

    if state == "dispatched":
        eta_display = _eta_display(data.eta_at)
        message = (
            copy.message("TRACKING_PROMISE_DISPATCHED_MESSAGE_ETA",
                         "Chega por volta de {eta}. Confirme aqui quando receber.")
            .replace("{eta}", eta_display)
            if eta_display
            else copy.message("TRACKING_PROMISE_DISPATCHED_MESSAGE",
                              "Está a caminho. Confirme aqui quando receber.")
        )
        return copy.title("TRACKING_PROMISE_DISPATCHED_TITLE", "Saiu para entrega"), message

    terminal = _TERMINAL_PROMISE_COPY.get(state)
    if terminal:
        title_key, title_fb, message_key, message_fb = terminal
        return (
            copy.title(title_key, title_fb),
            copy.message(message_key, message_fb) if message_key else message_fb,
        )

    # Estado inesperado (ex.: um terminal novo ainda sem copy dedicada): nunca
    # afirmar "Recebemos seu pedido" — seria um sinal errado num pedido que já
    # saiu daquele momento. Mensagem neutra e honesta, sem próximo passo inventado.
    return (
        copy.title("TRACKING_PROMISE_FALLBACK_TITLE", "Acompanhando seu pedido"),
        copy.message("TRACKING_PROMISE_FALLBACK_MESSAGE", "Acompanhando atualizações do pedido."),
    )


# state → (title_key, title_fb, message_key, message_fb)
_TERMINAL_PROMISE_COPY: dict[str, tuple[str, str, str, str]] = {
    "delivered": (
        "TRACKING_STEP_DELIVERED", "Entregue",
        "TRACKING_DELIVERED_YOIN", "Bom apetite!",
    ),
    "completed": (
        "TRACKING_STEP_COMPLETED", "Concluído",
        "TRACKING_PROMISE_COMPLETED_MESSAGE", "Obrigado pela preferência!",
    ),
    "cancelled": (
        "TRACKING_STEP_CANCELLED", "Cancelado",
        "TRACKING_PROMISE_CANCELLED_MESSAGE", "Pedido cancelado.",
    ),
    "returned": (
        "TRACKING_STEP_RETURNED", "Devolvido",
        "TRACKING_PROMISE_RETURNED_MESSAGE", "Pedido devolvido.",
    ),
}


def _pair(copy: CopyCatalog, key: str, fallback_title: str, fallback_message: str) -> tuple[str, str]:
    return copy.title(key, fallback_title), copy.message(key, fallback_message)


def _is_fulfillment_wait(data: TrackingPromiseData) -> bool:
    return data.fulfillment_wait_kind in {"planned_batch", "preorder"}


def _is_preorder_wait(data: TrackingPromiseData) -> bool:
    """Só a ENCOMENDA cobra para garantir a vaga.

    Encomenda e fornada do dia são necessidades diferentes, e o risco também é.
    Na encomenda a casa produz para uma pessoa nomeada numa data futura: se ela
    não vem, a perda é total, e por isso o pagamento antecipado se justifica.
    Na fornada de HOJE o pão vai ser assado de qualquer jeito — quem não aparece
    devolve o pão para a gôndola, que o vende. Cobrar adiantado ali é pedir
    garantia contra um prejuízo que não existe.

    A espera pelo lote do dia é do WP-P2E (``waitlist_state``), que promete de
    graça e cobra quando o lote sai.
    """
    return data.fulfillment_wait_kind == "preorder"


def _waitlist_message(
    data: TrackingPromiseData,
    *,
    copy: CopyCatalog,
    wait_display: str | None,
) -> str:
    if wait_display:
        if data.fulfillment_wait_kind == "preorder":
            return copy.message(
                "TRACKING_PROMISE_PREORDER_WAIT_MESSAGE",
                "Sua encomenda está reservada para {when}. Preparamos tudo fresco no dia.",
            ).replace("{when}", wait_display)
        return copy.message(
            "TRACKING_PROMISE_WAITLIST_MESSAGE",
            "Sua reserva está na fila de espera. Avisamos quando estiver pronto.",
        ).replace("{when}", wait_display)
    if data.fulfillment_wait_kind == "preorder":
        return copy.message(
            "TRACKING_PROMISE_PREORDER_WAIT_MESSAGE_NO_DATE",
            "Sua encomenda está reservada. Preparamos tudo fresco no dia combinado.",
        )
    return copy.message(
        "TRACKING_PROMISE_WAITLIST_MESSAGE_NO_DATE",
        "Sua reserva está na fila de espera. Avisamos quando estiver pronto.",
    )


def _payment_wait_message(
    data: TrackingPromiseData,
    *,
    copy: CopyCatalog,
    wait_display: str | None,
    method: str,
) -> str:
    if data.fulfillment_wait_kind == "preorder":
        if method == "card":
            if wait_display:
                return copy.message(
                    "TRACKING_PROMISE_CARD_PREORDER_MESSAGE",
                    "Finalize no ambiente seguro para garantir sua encomenda para {when}.",
                ).replace("{when}", wait_display)
            return copy.message(
                "TRACKING_PROMISE_CARD_PREORDER_MESSAGE_NO_DATE",
                "Finalize no ambiente seguro para garantir sua encomenda.",
            )
        if wait_display:
            return copy.message(
                "TRACKING_PAYMENT_PIX_PREORDER_MESSAGE",
                "Pague com o Pix abaixo para confirmar sua encomenda para {when}.",
            ).replace("{when}", wait_display)
        return copy.message(
            "TRACKING_PAYMENT_PIX_PREORDER_MESSAGE_NO_DATE",
            "Pague com o Pix abaixo para confirmar sua encomenda.",
        )

    # Só encomenda chega aqui (ver _is_preorder_wait): a fornada do dia não pede
    # pagamento para garantir vaga. Se algum caminho novo cair aqui, a tela
    # devolve a frase honesta de pagamento — degradar com graça, nunca colapsar.
    if method == "card":
        return copy.message(
            "TRACKING_PROMISE_CARD_MESSAGE_NEW",
            "Finalize no ambiente seguro para autorizar o cartão e acompanhar o pedido por aqui.",
        )
    return copy.message(
        "TRACKING_PAYMENT_PIX_READY_MESSAGE_NEW",
        "Pague com o Pix abaixo. A confirmação do Pix é automática; acompanhe os próximos passos por aqui.",
    )


def _paid_fulfillment_wait_message(
    data: TrackingPromiseData,
    *,
    copy: CopyCatalog,
    wait_display: str | None,
) -> str:
    if data.fulfillment_wait_kind == "preorder":
        if wait_display:
            return copy.message(
                "TRACKING_PROMISE_PREORDER_WAIT_MESSAGE_PAID",
                "Pagamento confirmado. Sua encomenda está reservada para {when}. Preparamos tudo fresco no dia.",
            ).replace("{when}", wait_display)
        return copy.message(
            "TRACKING_PROMISE_PREORDER_WAIT_MESSAGE_PAID_NO_DATE",
            "Pagamento confirmado. Sua encomenda está reservada. Preparamos tudo fresco no dia combinado.",
        )

    if wait_display:
        return copy.message(
            "TRACKING_PROMISE_WAITLIST_MESSAGE_PAID",
            "Pagamento confirmado. Sua reserva está na fila de espera. Avisamos quando estiver pronto.",
        ).replace("{when}", wait_display)
    return copy.message(
        "TRACKING_PROMISE_WAITLIST_MESSAGE_PAID_NO_DATE",
        "Pagamento confirmado. Sua reserva está na fila de espera. Avisamos quando estiver pronto.",
    )


def _first_visible_action(actions: tuple[Action, ...]) -> Action | None:
    for action in actions:
        if action.enabled:
            return action
    return actions[0] if actions else None


# ──────────────────────────────────────────────────────────────────────
# Items, timeline, progress, fulfillments, pickup
# ──────────────────────────────────────────────────────────────────────


def _present_items(data: TrackingData) -> tuple[OrderItemProjection, ...]:
    return tuple(
        OrderItemProjection(
            sku=item.sku,
            name=item.name,
            qty=item.qty,
            unit_price_display=f"R$ {format_money(item.unit_price_q)}",
            total_display=f"R$ {format_money(item.line_total_q)}",
        )
        for item in data.items
    )


def _timeline_label(event_type: str, label_key: str) -> str:
    if event_type == "status_changed" and label_key:
        return order_status_label(label_key)
    if label_key == "shipment_dispatched":
        return "Enviado"
    if label_key == "shipment_delivered":
        return "Entregue"
    label = EVENT_LABELS.get(event_type)
    if label is None:
        label = event_type.replace(".", " ").replace("_", " ").title()
    return label


def _present_timeline(data: TrackingData | TrackingStatusData) -> tuple[TimelineEventProjection, ...]:
    return tuple(
        TimelineEventProjection(
            label=_timeline_label(event.event_type, event.label_key),
            event_type=event.event_type,
            timestamp_display=_fmt_timestamp(event.at),
        )
        for event in data.timeline
    )


def _step_label(key: str, *, is_pickup: bool, copy: CopyCatalog) -> str:
    if key == "ready":
        if is_pickup:
            return copy.title("TRACKING_STEP_READY_PICKUP", "Pronto")
        return copy.title("TRACKING_STEP_READY_GENERIC", "Pronto")
    spec = STEP_LABEL_COPY.get(key)
    if spec:
        return copy.title(spec[0], spec[1])
    return key


def _present_progress_steps(data: TrackingData, *, copy: CopyCatalog) -> tuple[OrderProgressStepProjection, ...]:
    return _present_progress_steps_from(data.progress_steps, is_pickup=data.is_pickup, copy=copy)


def _present_progress_steps_from(steps, *, is_pickup: bool, copy: CopyCatalog) -> tuple[OrderProgressStepProjection, ...]:
    return tuple(
        OrderProgressStepProjection(
            label=_step_label(step.key, is_pickup=is_pickup, copy=copy),
            key=step.key,
            state=step.state,
            timestamp_display=_fmt_timestamp(step.at) if step.at else None,
        )
        for step in steps
    )


def _fulfillment_tracking_label(carrier: str | None, copy: CopyCatalog) -> str:
    if carrier:
        template = copy.title("TRACKING_TRACK_SHIPMENT_WITH_CARRIER", "Acompanhar via {carrier}")
        return template.format(carrier=carrier)
    return copy.title("TRACKING_TRACK_SHIPMENT", "Rastrear envio")


def _present_fulfillments(
    fulfillments: tuple[TrackingFulfillmentData, ...],
    *,
    copy: CopyCatalog,
    is_pickup: bool = False,
) -> tuple[FulfillmentProjection, ...]:
    # Retirada não tem envio a acompanhar: a linha sobrava com um "Em preparo"
    # solto, sem código, sem link e sem nada que o painel já não dissesse.
    if is_pickup:
        return ()
    labels = FULFILLMENT_STATUS_LABELS
    return tuple(
        FulfillmentProjection(
            status=ful.status,
            status_label=labels.get(ful.status, ful.status),
            # Retirada não tem envio a rastrear — só entrega ganha o rótulo/link.
            tracking_label="" if is_pickup else _fulfillment_tracking_label(ful.carrier, copy),
            tracking_code=ful.tracking_code,
            tracking_url=ful.tracking_url,
            carrier=ful.carrier,
            dispatched_at_display=_fmt_timestamp(ful.dispatched_at) if ful.dispatched_at else None,
            delivered_at_display=_fmt_timestamp(ful.delivered_at) if ful.delivered_at else None,
        )
        for ful in fulfillments
    )


def _present_pickup(pickup: TrackingPickupData | None, *, copy: CopyCatalog) -> PickupInfoProjection | None:
    if pickup is None:
        return None
    return PickupInfoProjection(
        heading=copy.title("TRACKING_PICKUP_HEADING", "Retirada"),
        address=pickup.address,
        opening_hours=_format_opening_hours(pickup.opening_hours),
        directions_label=copy.title("TRACKING_PICKUP_DIRECTIONS_CTA", "Como chegar"),
        directions_url=pickup.directions_url,
    )


def _format_opening_hours(opening_hours: dict) -> str:
    if not opening_hours:
        return ""

    def _fmt_time(value: str) -> str:
        parts = value.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if minute:
            return f"{hour}h{minute:02d}"
        return f"{hour}h"

    day_hours: list[tuple[str, str]] = []
    for day in DAY_ORDER:
        info = opening_hours.get(day)
        if info and info.get("open") and info.get("close"):
            day_hours.append((day, f"{_fmt_time(info['open'])} às {_fmt_time(info['close'])}"))
        else:
            day_hours.append((day, "Fechado"))

    groups: list[tuple[list[str], str]] = []
    for day, hours in day_hours:
        if groups and groups[-1][1] == hours:
            groups[-1][0].append(day)
        else:
            groups.append(([day], hours))

    result = []
    for days, hours in groups:
        if len(days) == 1:
            label = DAY_NAMES_PT[days[0]]
        elif len(days) == 2:
            label = f"{DAY_NAMES_PT[days[0]]} e {DAY_NAMES_PT[days[1]]}"
        else:
            label = f"{DAY_NAMES_PT[days[0]]} a {DAY_NAMES_PT[days[-1]]}"
        result.append({"label": label, "hours": hours})
    return "; ".join(f"{hour['label']}: {hour['hours']}" for hour in result)


def _tracking_copy(copy: CopyCatalog) -> OrderTrackingCopyProjection:
    return OrderTrackingCopyProjection(
        page_kicker=copy.title("TRACKING_PAGE_KICKER", "Acompanhamento"),
        order_ref_label=copy.title("TRACKING_ORDER_REF_LABEL", "Pedido"),
        menu_label=copy.title("TRACKING_MENU_CTA", "Ver cardápio"),
        support_label=copy.title("TRACKING_SUPPORT_CTA", "Ajuda"),
        progress_heading=copy.title("TRACKING_PROGRESS_HEADING", "Etapas do pedido"),
        live_badge=copy.title("TRACKING_LIVE_BADGE", "Ao vivo"),
        polling_badge=copy.title("TRACKING_POLLING_BADGE", "Atualização periódica"),
        finished_badge=copy.title("TRACKING_FINISHED_BADGE", "Finalizado"),
        items_heading=copy.title("TRACKING_ITEMS_HEADING", "Itens do pedido"),
        total_label=copy.title("TRACKING_TOTAL_LABEL", "Total"),
        delivery_fee_label=copy.title("TRACKING_DELIVERY_FEE_LABEL", "Entrega"),
        promise_fallback_message=copy.message(
            "TRACKING_PROMISE_FALLBACK_MESSAGE",
            "Acompanhando atualizações do pedido.",
        ),
        retry_label=copy.title("TRACKING_RETRY_CTA", "Tentar novamente"),
        not_found_title=copy.title("TRACKING_NOT_FOUND_TITLE", "Pedido não encontrado"),
        not_found_description=copy.message(
            "TRACKING_NOT_FOUND_MESSAGE",
            "Confira o link do pedido ou fale com a equipe.",
        ),
        rate_limit_title=copy.title("TRACKING_RATE_LIMIT_TITLE", "Atualização pausada por um instante"),
        cancelled_reason_title=copy.title("TRACKING_CANCELLED_REASON_TITLE", "Motivo do cancelamento"),
        refund_title=copy.title("TRACKING_REFUND_TITLE", "Reembolso"),
        cancel_success_title=copy.title("TRACKING_CANCEL_SUCCESS_TITLE", "Pedido cancelado"),
        cancel_success_message=copy.message(
            "TRACKING_CANCEL_SUCCESS_MESSAGE",
            "Recebemos o cancelamento. Acompanhe o status nesta página.",
        ),
        cancel_failed_message=copy.message(
            "TRACKING_CANCEL_FAILED_MESSAGE",
            "Não foi possível cancelar este pedido agora.",
        ),
        cancel_cta=copy.title("TRACKING_CANCEL_CTA", "Cancelar pedido"),
        cancel_dialog_title=copy.title("TRACKING_CANCEL_HEADING", "Cancelar pedido?"),
        cancel_dialog_message=copy.message(
            "TRACKING_CANCEL_CONFIRM",
            "Vamos avisar a loja e atualizar o acompanhamento.",
        ),
        cancel_dialog_confirm=copy.title("TRACKING_CANCEL_YES", "Sim, cancelar"),
        cancel_dialog_back=copy.title("TRACKING_CANCEL_BACK", "Voltar"),
        mock_payment_success_title=copy.title("TRACKING_MOCK_PAYMENT_SUCCESS_TITLE", "Pagamento teste capturado"),
        mock_payment_success_message=copy.message(
            "TRACKING_MOCK_PAYMENT_SUCCESS_MESSAGE",
            "Atualizamos o pedido com o estado financeiro simulado.",
        ),
        mock_payment_failed_title=copy.title(
            "TRACKING_MOCK_PAYMENT_FAILED_TITLE",
            "Não foi possível capturar o pagamento teste",
        ),
        mock_payment_failed_message=copy.message(
            "TRACKING_MOCK_PAYMENT_FAILED_MESSAGE",
            "Atualize o pedido e tente novamente.",
        ),
        rating_success_title=copy.title("TRACKING_RATING_SUCCESS_TITLE", "Avaliação registrada"),
        rating_failed_message=copy.message(
            "TRACKING_RATING_FAILED_MESSAGE",
            "Não foi possível registrar a avaliação agora.",
        ),
        rating_comment_placeholder=copy.title("TRACKING_RATING_COMMENT_PLACEHOLDER", "Comentário opcional"),
        rating_comment_aria_label=copy.title("TRACKING_RATING_COMMENT_ARIA_LABEL", "Comentário da avaliação"),
        rating_submit_label=copy.title("TRACKING_RATING_SUBMIT_CTA", "Enviar avaliação"),
        rating_thanks=copy.message("TRACKING_RATE_THANKS", "Valorizamos muito seu retorno."),
        rating_thanks_title=copy.title("TRACKING_RATE_THANKS", "Obrigado!"),
        rating_thanks_celebrate=copy.message(
            "TRACKING_RATING_THANKS_CELEBRATE",
            "Ficamos muito felizes que você gostou. Esperamos você de novo em breve.",
        ),
        page_meta_description=copy.message("TRACKING_PAGE_META_DESCRIPTION", "Acompanhe seu pedido"),
        delivery_heading=copy.title("TRACKING_DELIVERY_HEADING", "Entrega"),
        stale_cta=copy.message("TRACKING_PROMISE_STALE", "Atualizar"),
        pix_instruction=copy.message(
            "TRACKING_PAYMENT_PIX_INSTRUCTION",
            "Escaneie o QR Code no app do banco ou copie o código Pix.",
        ),
        pix_copy_label=copy.title("TRACKING_PAYMENT_PIX_COPY_LABEL", "Pix Copia e Cola"),
        pix_copy_btn=copy.title("TRACKING_PAYMENT_PIX_COPY_BTN", "Copiar código"),
        pix_copied=copy.title("TRACKING_PAYMENT_PIX_COPIED", "Código Pix copiado."),
        pix_expires_label=copy.message("TRACKING_PAYMENT_PIX_EXPIRES_LABEL", "Tempo para pagar"),
        pix_pending_note=copy.message(
            "TRACKING_PAYMENT_PIX_PENDING_NOTE",
            "O prazo para pagar começa quando o código aparecer.",
        ),
        pix_auto_update_note=copy.message(
            "TRACKING_PAYMENT_PIX_AUTO_UPDATE_NOTE",
            "Quando o Pix for confirmado, atualizamos esta tela automaticamente.",
        ),
        card_intro=copy.message(
            "TRACKING_PAYMENT_CARD_INTRO",
            "Conclua o pagamento no nosso ambiente seguro. Assim que a confirmação chegar, atualizamos esta tela.",
        ),
        card_security_note=copy.message("TRACKING_PAYMENT_CARD_SECURITY_NOTE", "Pagamento processado por provedor seguro. Nós não recebemos os dados do seu cartão."),
        waitlist_waiting_title=copy.title("TRACKING_WAITLIST_WAITING_TITLE", "Você está na fila"),
        waitlist_waiting_message=copy.message(
            "TRACKING_WAITLIST_WAITING_MESSAGE",
            "Assim que a fornada sair, a gente te avisa para confirmar. Nada foi cobrado ainda.",
        ),
        waitlist_confirm_title=copy.title("TRACKING_WAITLIST_CONFIRM_TITLE", "Sua fornada saiu!"),
        waitlist_confirm_message=copy.message(
            "TRACKING_WAITLIST_CONFIRM_MESSAGE",
            "Confirme para garantir o seu. Se não der, a vaga vai para a próxima pessoa da fila.",
        ),
        waitlist_confirm_cta=copy.title("TRACKING_WAITLIST_CONFIRM_CTA", "Confirmar meu pedido"),
        waitlist_confirmed_title=copy.title("TRACKING_WAITLIST_CONFIRMED_TITLE", "Confirmado, já vamos separar"),
        waitlist_released_title=copy.title("TRACKING_WAITLIST_RELEASED_TITLE", "A vaga passou a vez"),
        waitlist_released_message=copy.message(
            "TRACKING_WAITLIST_RELEASED_MESSAGE",
            "O prazo de confirmação passou e liberamos a sua vaga. Nada foi cobrado, e você pode entrar na fila da próxima fornada.",
        ),
    )


__all__ = [
    "OrderTrackingCopyProjection",
    "OrderTrackingProjection",
    "OrderTrackingPromiseProjection",
    "OrderTrackingStatusProjection",
    "PickupInfoProjection",
    "build_order_tracking",
    "build_order_tracking_status",
    "present_tracking",
    "present_tracking_status",
]
