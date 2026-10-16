"""Cartão autorizado esperando aceite: o prazo que o Stripe dá e quem o vigia.

O cartão da loja online nasce com ``capture_method="manual"``: o cliente
autoriza no checkout, o dinheiro fica reservado no cartão dele e a loja só
cobra quando aceita (``lifecycle._on_accepted``). Enquanto ninguém aceita, o
pedido fica em ``new`` e o ``payment.timeout`` não o cancela (o cliente pagou;
cancelar seria devolver "não deu certo" a quem fez a parte dele).

O furo era o outro lado: a reserva NÃO dura para sempre. O Stripe mantém uma
autorização de cartão online por **7 dias** e depois a cancela sozinho; a
cobrança morre e o pedido continuava em ``new``, parado, com o dinheiro que já
não existia. Aqui mora:

- o prazo (:func:`expires_at`): o ``capture_before`` que o Stripe devolve na
  cobrança, quando gravado no intent; senão ``authorized_at`` + 7 dias;
- o vigia (:func:`watch`): uma Directive por autorização que avisa o Gestor
  quando o pedido fica parado (logo depois do aviso normal de pedido parado),
  avisa de novo nas últimas 24 h com o prazo, e no vencimento põe o pedido num
  estado coerente: cancelado, com nada cobrado, cliente avisado e alerta crítico.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

#: Quanto o Stripe segura uma autorização de cartão online sem captura. É a
#: janela padrão da rede (Visa/Mastercard em compra não presencial); o Stripe
#: cancela o PaymentIntent quando ela passa. Quando o intent traz o
#: ``capture_before`` da própria cobrança, é ele que vale.
AUTHORIZATION_WINDOW = timedelta(days=7)

#: O último aviso antes do vencimento: um dia inteiro para alguém aceitar.
LAST_CALL_BEFORE = timedelta(hours=24)

#: O primeiro aviso do cartão vem DEPOIS do aviso normal de pedido parado
#: (``stale_new_order``, 10 min na loja online): se nem ele resolveu em uma hora,
#: o Gestor passa a ver o prazo da autorização e o que se perde com ele.
STUCK_AFTER = timedelta(hours=1)

#: Folga para perguntar de novo ao Stripe quando o prazo calculado passou e ele
#: ainda segura a autorização (o relógio dele manda).
GATEWAY_GRACE = timedelta(hours=1)

ALERT_EXPIRING = "card_authorization_expiring"
ALERT_EXPIRED = "card_authorization_expired"
ALERT_RELEASE_FAILED = "card_authorization_release_failed"

#: Motivo gravado no pedido e no intent quando a autorização vence.
EXPIRED_REASON = "card_authorization_expired"

#: O motivo que o cliente lê no aviso de cancelamento, como ``Motivo: <motivo>.``
#: (sem ponto final, a moldura do aviso já fecha a frase).
EXPIRED_CUSTOMER_NOTE = (
    "A reserva no seu cartão venceu antes de confirmarmos o pedido, e nada foi cobrado"
)


def _parse(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.get_current_timezone())
    else:
        text = str(value)
        if text.isdigit():
            dt = datetime.fromtimestamp(int(text), tz=timezone.get_current_timezone())
        else:
            dt = parse_datetime(text)
            if dt is None:
                return None
    if not timezone.is_aware(dt):
        dt = timezone.make_aware(dt)
    return dt


def _authorized_card_intent(order):
    """O intent do pedido, se for cartão de checkout hospedado ainda autorizado."""
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    intent_ref = str(payment.get("intent_ref") or "")
    if method != "card" or not intent_ref:
        return None
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        # Intent inexistente: não há autorização de pé para vigiar.
        logger.info("card_authorization.intent_not_found order=%s intent=%s", order.ref, intent_ref)
        return None
    if str(intent.status or "").lower() != "authorized":
        return None
    return intent


def intent_expires_at(intent) -> datetime | None:
    """O vencimento da autorização deste intent (``None`` sem autorização)."""
    gateway_data = getattr(intent, "gateway_data", None) or {}
    from_gateway = _parse(gateway_data.get("capture_before"))
    if from_gateway:
        return from_gateway
    authorized_at = getattr(intent, "authorized_at", None)
    if authorized_at is None:
        return None
    return authorized_at + AUTHORIZATION_WINDOW


def expires_at(order) -> datetime | None:
    """Quando a autorização do cartão deste pedido vence; ``None`` se não há uma de pé."""
    intent = _authorized_card_intent(order)
    return intent_expires_at(intent) if intent is not None else None


def deadline_label(when: datetime) -> str:
    """"20/10 às 14h30", no fuso da loja."""
    local = timezone.localtime(when)
    return local.strftime("%d/%m às %Hh%M")


def watch(order) -> None:
    """Agenda o vigia da autorização de um pedido novo. Idempotente por intent.

    Chamado onde a autorização entra no sistema (webhook do Stripe e a
    conciliação que pergunta ao gateway). Pedido fora de ``new`` não precisa:
    aceito, a captura é do lifecycle; cancelado, a autorização é anulada.
    """
    from shopman.orderman.models import Directive, Order

    from shopman.shop.directives import CARD_AUTHORIZATION_WATCH

    if order.status != Order.Status.NEW:
        return
    intent = _authorized_card_intent(order)
    if intent is None:
        return
    # Canal com prazo de aceite (loja online, ADR-036): a autorização é o
    # pagamento chegando, e o prazo da loja começa aqui.
    from shopman.shop.lifecycle import start_acceptance_deadline

    start_acceptance_deadline(order)
    deadline = intent_expires_at(intent)
    if deadline is None:
        return

    now = timezone.now()
    first_at = max(now, (intent.authorized_at or now) + STUCK_AFTER)
    first_at = min(first_at, deadline)
    dedupe_key = f"card-authorization:{order.ref}:{intent.ref}"
    if Directive.objects.filter(
        topic=CARD_AUTHORIZATION_WATCH,
        dedupe_key=dedupe_key,
    ).exists():
        return
    try:
        with transaction.atomic():
            Directive.objects.create(
                topic=CARD_AUTHORIZATION_WATCH,
                dedupe_key=dedupe_key,
                payload={
                    "order_ref": order.ref,
                    "intent_ref": intent.ref,
                    "expires_at": deadline.isoformat(),
                    "stage": "stuck",
                },
                available_at=first_at,
            )
    except IntegrityError:
        # A constraint de dedupe fecha a corrida de dois webhooks simultâneos.
        logger.info("card_authorization.watch_dedupe order=%s", order.ref, exc_info=True)


def alert_expiring(order, deadline: datetime, *, stage: str) -> None:
    """Avisa o Gestor, com o prazo, que o cartão autorizado espera aceite."""
    from shopman.shop.services.observability import create_operator_alert

    label = deadline_label(deadline)
    if stage == "last_call":
        message = (
            f"A autorização do cartão do pedido {order.ref} vence em {label}. "
            "Aceite para cobrar ou recuse para liberar o valor; depois disso o pagamento se perde."
        )
        severity = "error"
        respond_by = deadline
    else:
        message = (
            f"O pedido {order.ref} tem o cartão autorizado e espera aceite. "
            f"A autorização do cartão vence em {label}: aceite para cobrar ou recuse para liberar o valor."
        )
        severity = "warning"
        respond_by = None
    create_operator_alert(
        type=ALERT_EXPIRING,
        severity=severity,
        message=message,
        order_ref=order.ref,
        dedupe_key=f"card-authorization:{order.ref}:{stage}",
        respond_by=respond_by,
    )


def expire(order, *, intent_ref: str) -> str:
    """O prazo passou. Pergunta ao Stripe e põe o pedido num estado coerente.

    Retorna ``"cancelled"`` (venceu: pedido cancelado, nada cobrado, alerta
    crítico), ``"still_authorized"`` (o Stripe ainda segura: pergunte de novo),
    ``"paid"`` (alguém cobrou por fora: o caminho de pago já cuidou) ou
    ``"indeterminate"`` (sem resposta confiável: tentar de novo).
    """
    from shopman.payman import PaymentError, PaymentService

    from shopman.shop.services import payment as payment_service
    from shopman.shop.services.cancellation import cancel
    from shopman.shop.services.observability import create_operator_alert

    adapter = payment_service._adapter_for_persisted_intent(intent_ref, method="card")
    check = getattr(adapter, "check_gateway_status", None) if adapter else None
    if check is None:
        return "indeterminate"
    try:
        state = str(check(intent_ref) or "")
    except Exception:
        logger.warning("card_authorization.gateway_check_failed order=%s", order.ref, exc_info=True)
        return "indeterminate"

    if state == "authorized":
        return "still_authorized"
    if state == "captured":
        payment_service.settle_from_gateway(order)
        return "paid"
    if state not in {"cancelled", "not_found"}:
        return "indeterminate"

    # O Stripe já cancelou a cobrança: a baixa local vem antes do cancelamento
    # do pedido, para o ``on_cancelled`` não tentar anular de novo o que morreu.
    try:
        PaymentService.cancel(intent_ref, reason=EXPIRED_REASON)
    except PaymentError:
        logger.info("card_authorization.local_cancel_skipped intent=%s", intent_ref, exc_info=True)

    cancelled = cancel(
        order,
        reason=EXPIRED_REASON,
        actor="payment.card_authorization",
        extra_data={
            "card_authorization_expired_at": timezone.now().isoformat(),
            "cancellation_note": EXPIRED_CUSTOMER_NOTE,
        },
        expected_unpaid_intent_ref=intent_ref,
    )
    if cancelled:
        create_operator_alert(
            type=ALERT_EXPIRED,
            severity="critical",
            message=(
                f"A autorização do cartão do pedido {order.ref} venceu sem aceite. "
                "O pedido foi cancelado e nada foi cobrado; o cliente recebeu o aviso. "
                "Se ainda quiser atender, fale com ele e faça um pedido novo."
            ),
            order_ref=order.ref,
            dedupe_key=f"card-authorization:{order.ref}:expired",
        )
    return "cancelled"


def alert_release_failed(order, *, intent_ref: str, error: str = "") -> None:
    """Recusar não liberou a autorização no Stripe: o valor segue retido."""
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type=ALERT_RELEASE_FAILED,
        severity="critical",
        message=(
            f"O pedido {order.ref} foi recusado, mas o Stripe não liberou a autorização do cartão "
            f"(pagamento {intent_ref}). O valor segue reservado no cartão do cliente: "
            "cancele o pagamento no painel do Stripe."
        ),
        order_ref=order.ref,
        dedupe_key=f"card-authorization:{order.ref}:release-failed",
        error=error,
    )


__all__ = [
    "ALERT_EXPIRED",
    "ALERT_EXPIRING",
    "ALERT_RELEASE_FAILED",
    "AUTHORIZATION_WINDOW",
    "LAST_CALL_BEFORE",
    "STUCK_AFTER",
    "alert_expiring",
    "alert_release_failed",
    "deadline_label",
    "expire",
    "expires_at",
    "intent_expires_at",
    "watch",
]
