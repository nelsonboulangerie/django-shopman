"""Payment — storefront Presentation.

Consumes the data Projection (``shop.projections.payment_status``) plus the copy
catalog (``shop.projections.copy``) and produces the display shape the payment
templates and the storefront REST surface consume: resolved promise copy, money
formatted ``R$``, the polling/terminal flags. **No policy** is decided here —
every decision (promise state, terminal flags, actions, redirect) already
arrived sealed in the data projection.

The canonical copy lives in the orchestrator (``OMOTENASHI_DEFAULTS``); the
strings passed to ``catalog.title``/``catalog.message`` are last-resort
fallbacks (per the copy.py contract: fallback PT-BR lives in Presentation).
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.utils.monetary import format_money

from shopman.shop.projections.copy import CopyCatalog, build_copy
from shopman.shop.projections.payment_status import (
    PaymentData,
    PaymentPromiseData,
    PaymentStatusData,
    promise_has_pending_payment_action,  # noqa: F401 — re-exported for the payment view
)
from shopman.shop.projections.payment_status import (
    build_payment as build_payment_data,
)
from shopman.shop.projections.payment_status import (
    build_payment_status as build_payment_status_data,
)
from shopman.shop.projections.types import Action

# A tela de pagamento segue a mesma regra do acompanhamento: uma frase por
# estado, que já diz o que fazer e o que acontece se não for feito. Não há campo
# separado de "próxima ação" nem alerta de "como resolver" — rótulo em cima de
# frase curta é o que dava ao pós-checkout cara de formulário.
#
# state → (title_key, title_fb, message_key, message_fb)
_PROMISE_COPY: dict[str, tuple[str, str, str, str]] = {
    "paid": (
        "PAYMENT_PROMISE_PAID_TITLE", "Pagamento confirmado",
        "PAYMENT_PROMISE_PAID_MESSAGE", "Tudo certo. Levando você para o acompanhamento.",
    ),
    "cancelled": (
        "PAYMENT_PROMISE_CANCELLED_TITLE", "Pedido cancelado",
        "PAYMENT_PROMISE_CANCELLED_MESSAGE", "Este pedido não aceita mais pagamento.",
    ),
    "expired": (
        "PAYMENT_PROMISE_EXPIRED_TITLE", "Pagamento expirado",
        "PAYMENT_PROMISE_EXPIRED_MESSAGE",
        "O prazo acabou e cancelamos o pedido. Você pode pedir de novo quando quiser.",
    ),
    "card_authorized": (
        "PAYMENT_PROMISE_CARD_AUTHORIZED_TITLE", "Pagamento autorizado",
        "PAYMENT_PROMISE_CARD_AUTHORIZED_MESSAGE", "Não precisa fazer mais nada.",
    ),
    "intent_error": (
        "PAYMENT_PROMISE_ERROR_TITLE", "Não conseguimos preparar o pagamento",
        "PAYMENT_PROMISE_ERROR_MESSAGE",
        "Seu pedido está registrado. Tente gerar o pagamento de novo e, se não der, fale conosco.",
    ),
    "card_authorization_requested": (
        "PAYMENT_PROMISE_CARD_PRECONFIRMATION_TITLE", "Autorizar cartão",
        "PAYMENT_PROMISE_CARD_PRECONFIRMATION_MESSAGE",
        "Autorize no ambiente seguro. Depois conferimos a disponibilidade.",
    ),
    "card_checkout_requested": (
        "PAYMENT_PROMISE_CARD_TITLE", "Pagamento com cartão",
        "PAYMENT_PROMISE_CARD_MESSAGE",
        "Disponibilidade confirmada. Finalize no ambiente seguro e começamos a preparar.",
    ),
    "card_checkout_pending": (
        "PAYMENT_PROMISE_CARD_PENDING_TITLE", "Preparando pagamento",
        "PAYMENT_PROMISE_CARD_PENDING_MESSAGE", "O botão aparece em instantes.",
    ),
    "pix_waiting_confirmation": (
        "PAYMENT_PROMISE_PIX_WAITING_TITLE", "Aguardando a loja",
        "PAYMENT_PROMISE_PIX_WAITING_MESSAGE",
        "Estamos conferindo a disponibilidade. O código Pix aparece aqui em seguida. "
        "Se não conseguirmos confirmar, cancelamos e avisamos você.",
    ),
    "pix_payment_before_confirmation": (
        "PAYMENT_PROMISE_PIX_PRECONFIRMATION_TITLE", "Pague com Pix",
        "PAYMENT_PROMISE_PIX_PRECONFIRMATION_MESSAGE",
        "Use o código abaixo. Ainda estamos conferindo a disponibilidade, "
        "e cancelamos o pedido se o prazo acabar.",
    ),
    "pix_payment_requested": (
        "PAYMENT_PROMISE_PIX_TITLE", "Pague com Pix",
        "PAYMENT_PROMISE_PIX_MESSAGE",
        "Disponibilidade confirmada. Use o código abaixo e começamos a preparar. "
        "Se o prazo acabar, cancelamos o pedido.",
    ),
}


# ──────────────────────────────────────────────────────────────────────
# Presentation DTOs (appearance) — what templates / serializers consume
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaymentPromiseProjection:
    """Customer-facing payment promise contract, rendered."""

    state: str
    title: str
    message: str
    tone: str
    actions: tuple[Action, ...]
    deadline_at: str | None
    deadline_kind: str | None
    deadline_action: str
    requires_active_notification: bool
    stale_after_seconds: int | None = None


@dataclass(frozen=True)
class PaymentProjection:
    """Canonical full payment page projection, rendered."""

    order_ref: str
    method: str
    order_status: str
    payment_status: str | None
    total_display: str
    promise: PaymentPromiseProjection
    pix_qr_code: str | None
    pix_copy_paste: str | None
    pix_expires_at: str | None
    checkout_url: str | None
    status_url: str
    server_now_iso: str
    actions: tuple[Action, ...]
    error_message: str | None
    is_debug: bool
    # Habilita o botão "Simular pagamento" (PIX e cartão): DEBUG OU adapters de
    # pagamento mock (staging). Em produção real (gateway de verdade) fica False.
    mock_enabled: bool = False


@dataclass(frozen=True)
class PaymentStatusProjection:
    """Canonical payment status polling projection, rendered."""

    order_ref: str
    promise: PaymentPromiseProjection
    is_paid: bool
    is_cancelled: bool
    is_expired: bool
    is_terminal: bool
    redirect_url: str
    should_redirect: bool


# ──────────────────────────────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────────────────────────────


def mock_payment_enabled() -> bool:
    """Mock payment ('Simular pagamento') liberado em DEBUG ou com adapters mock (staging)."""
    from django.conf import settings

    return bool(settings.DEBUG or getattr(settings, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False))


def build_payment(order) -> PaymentProjection:
    """Build the full payment page projection for an Order."""
    from django.conf import settings

    return present_payment(
        build_payment_data(order, is_debug=settings.DEBUG),
        mock_enabled=mock_payment_enabled(),
    )


def build_payment_status(order) -> PaymentStatusProjection:
    """Build the polling partial projection for an Order."""
    return present_payment_status(build_payment_status_data(order))


def present_payment(data: PaymentData, *, mock_enabled: bool = False) -> PaymentProjection:
    copy = build_copy("PAYMENT")
    return PaymentProjection(
        order_ref=data.order_ref,
        method=data.method,
        order_status=data.order_status,
        payment_status=data.payment_status,
        total_display=f"R$ {format_money(data.total_q)}",
        promise=_present_promise(data.promise, order_status=data.order_status, copy=copy),
        pix_qr_code=data.pix_qr_code,
        pix_copy_paste=data.pix_copy_paste,
        pix_expires_at=data.pix_expires_at,
        checkout_url=data.checkout_url,
        status_url=data.status_url,
        server_now_iso=data.server_now_iso,
        actions=data.actions,
        error_message=data.error_message,
        is_debug=data.is_debug,
        mock_enabled=mock_enabled,
    )


def present_payment_status(data: PaymentStatusData) -> PaymentStatusProjection:
    copy = build_copy("PAYMENT")
    return PaymentStatusProjection(
        order_ref=data.order_ref,
        promise=_present_promise(data.promise, order_status=data.order_status, copy=copy),
        is_paid=data.is_paid,
        is_cancelled=data.is_cancelled,
        is_expired=data.is_expired,
        is_terminal=data.is_terminal,
        redirect_url=data.redirect_url,
        should_redirect=data.should_redirect,
    )


# ──────────────────────────────────────────────────────────────────────
# Promise copy
# ──────────────────────────────────────────────────────────────────────


def _present_promise(
    data: PaymentPromiseData,
    *,
    order_status: str,
    copy: CopyCatalog,
) -> PaymentPromiseProjection:
    title, message = _promise_copy(
        data,
        order_status=order_status,
        copy=copy,
    )
    return PaymentPromiseProjection(
        state=data.state,
        title=title,
        message=message,
        tone=data.tone,
        actions=data.actions,
        deadline_at=data.deadline_at,
        deadline_kind=data.deadline_kind,
        deadline_action=data.deadline_action,
        requires_active_notification=data.requires_active_notification,
        stale_after_seconds=data.stale_after_seconds,
    )


def _promise_copy(
    data: PaymentPromiseData,
    *,
    order_status: str,
    copy: CopyCatalog,
) -> tuple[str, str]:
    """Título e mensagem do estado — uma frase, sem slots."""
    spec = _PROMISE_COPY.get(data.state)
    if spec is None:
        return "", ""
    title_key, title_fb, message_key, message_fb = spec
    title = copy.title(title_key, title_fb) if title_key else title_fb
    if data.state == "card_authorized":
        message = _card_authorized_message(order_status, copy)
    else:
        message = copy.message(message_key, message_fb) if message_key else message_fb
    return title, message


def _card_authorized_message(order_status: str, copy: CopyCatalog) -> str:
    """O cartão foi autorizado: o que muda é só o que a loja faz em seguida."""
    if order_status == "new":
        return copy.message(
            "PAYMENT_PROMISE_CARD_AUTHORIZED_MESSAGE_NEW",
            "Não precisa fazer mais nada. Agora conferimos a disponibilidade.",
        )
    return copy.message(
        "PAYMENT_PROMISE_CARD_AUTHORIZED_MESSAGE_CONFIRMED",
        "Não precisa fazer mais nada. Estamos finalizando o pagamento.",
    )


__all__ = [
    "PaymentProjection",
    "PaymentPromiseProjection",
    "PaymentStatusProjection",
    "build_payment",
    "build_payment_status",
    "present_payment",
    "present_payment_status",
    "promise_has_pending_payment_action",
]
