"""Cobrança digital pendente recebida no balcão — sem cobrança dupla.

Decisão do dono (26/09/2026): a encomenda que espera um Pix da Efí ou um link de
pagamento (Checkout do Stripe) pode ser recebida no balcão — dinheiro com troco,
débito ou crédito na maquininha — no mesmo gesto "Receber e entregar" do PDV.

O risco é um só: o cliente pagar DUAS vezes (a cobrança digital continua viva e
ele paga pelo celular enquanto entrega a nota no balcão). Por isso a ordem é
fixa, e cada passo só roda se o anterior deu certo:

1. **Perguntar ao provedor** (``payment.settle_from_gateway``): se o cliente
   acabou de pagar, o pagamento é registrado e o balcão NÃO recebe — só entrega.
2. **Matar a cobrança no provedor** (``adapter.cancel``: expira a Checkout
   Session / anula o PaymentIntent no Stripe; remove a cobrança Pix na Efí) e
   cancelar o intent no Payman. Falhou? Nada muda, e o operador lê o porquê.
3. **Calar os avisos de cobrança** que esperam na fila (``payment_requested``,
   ``payment_link_sent``, lembretes): skip com motivo, o mesmo carimbo do
   handler de notificação.
4. **Gravar ``payment.counter_takeover``** no pedido. Daí em diante ele é um
   pedido pago no balcão (``operator_orders.collects_at_handoff``) e o acerto
   canônico (``settle_delivery_cash``) registra o dinheiro/cartão no turno.

A rede de I/O com o provedor fica FORA da transação do acerto: um cancelamento
remoto não volta atrás com ``rollback``. Se o acerto falhar depois, o pedido já
está assumido pelo balcão e o operador simplesmente tenta de novo.

**A corrida tardia** — o provedor confirmar o pagamento DEPOIS de o balcão
receber (webhook atrasado, Pix pago no último segundo) — é fechada por
:func:`refund_late_payment` e :func:`handle_late_stripe_payment`: o dinheiro é
registrado num intent próprio (a cobrança cancelada não aceita captura), é
estornado no MESMO meio (política do dono) e o operador é avisado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

#: Métodos de cobrança digital que o balcão pode assumir: o Pix (Efí) e as
#: sessões hospedadas do Stripe (link do PDV e cartão da loja online).
TAKEOVER_METHODS = frozenset({"pix", "link", "card"})

#: Avisos de cobrança que perdem o sentido quando o balcão recebe.
PAYMENT_NOTICE_TEMPLATES = frozenset({"payment_requested", "payment_link_sent", "payment.reminder", "payment_reminder"})

#: O motivo do skip dos avisos e da recusa de reenvio.
SKIP_REASON = "payment_taken_over_at_counter"

CANCEL_FAILED_MESSAGE = (
    "Não consegui cancelar o link do cliente. Tente de novo ou peça para ele pagar pelo link."
)
GATEWAY_UNCERTAIN_MESSAGE = (
    "Não consegui confirmar com o banco se o cliente já pagou. Tente de novo em instantes."
)
PAID_ONLINE_MESSAGE = "O cliente acabou de pagar online. Não receba no balcão: só entregue a encomenda."


class TakeoverFailed(Exception):
    """A cobrança digital não pôde ser assumida pelo balcão. Nada mudou."""


class PaidOnline(Exception):
    """O cliente pagou pela cobrança digital antes de o balcão receber."""

    def __init__(self, message: str = PAID_ONLINE_MESSAGE):
        super().__init__(message)


@dataclass(frozen=True)
class Takeover:
    """O que o balcão assumiu (ou ``taken_over=False`` quando não havia o que assumir)."""

    taken_over: bool
    from_method: str = ""
    cancelled_intent_ref: str = ""


def _payment(order) -> dict:
    return dict((order.data or {}).get("payment") or {})


def pending_digital_method(order) -> str:
    """O método da cobrança digital que o balcão pode assumir — ou ``""``.

    Só Pix e sessão do Stripe, só pedido da casa (o iFood cobra pelo iFood), e
    só enquanto ainda não foi assumida. Não diz se há saldo: quem chama sabe.
    """
    if order.channel_ref == "ifood":
        return ""
    payment = _payment(order)
    if payment.get("counter_takeover"):
        return ""
    method = str(payment.get("method") or "").strip().lower()
    if method not in TAKEOVER_METHODS:
        return ""
    if str(payment.get("collection") or "").strip().lower() in {"on_delivery", "terminal"}:
        return ""
    if not str(payment.get("intent_ref") or "").strip():
        return ""
    return method


def notice_for(method: str) -> str:
    """A linha que o PDV mostra antes de confirmar: o que vai ser cancelado."""
    if method == "pix":
        return "O Pix enviado ao cliente será cancelado."
    return "O link de pagamento enviado ao cliente será cancelado."


def taken_over(order) -> bool:
    return bool(_payment(order).get("counter_takeover"))


def cancelled_by_takeover(order, intent_ref: str) -> bool:
    """Este intent é a cobrança digital que o balcão cancelou neste pedido?"""
    record = _payment(order).get("counter_takeover") or {}
    return bool(intent_ref) and str(record.get("cancelled_intent_ref") or "") == str(intent_ref)


def take_over_pending_digital_charge(order, *, actor: str) -> Takeover:
    """Assumir no balcão a cobrança digital pendente — ou recusar sem mudar nada.

    Levanta :class:`PaidOnline` quando o provedor diz que o cliente já pagou (o
    pagamento é registrado pelo caminho canônico) e :class:`TakeoverFailed`
    quando a cobrança não pôde ser cancelada no provedor ou o provedor não
    respondeu. Idempotente: pedido já assumido devolve ``taken_over=False``.
    """
    from shopman.shop.services import payment as payment_service

    method = pending_digital_method(order)
    if not method:
        return Takeover(taken_over=False)
    intent_ref = str(_payment(order).get("intent_ref") or "").strip()

    local_status = _local_status(intent_ref)
    if local_status in {"captured", "refunded"}:
        raise PaidOnline()
    if local_status == "authorized":
        # Cartão autorizado e não capturado: o dinheiro do cliente está preso a
        # esta cobrança. Receber de novo no balcão seria cobrar duas vezes.
        payment_service.capture(order)
        raise PaidOnline()

    # 1. O provedor tem pagamento? LEITURA; escreve só se houver captura.
    outcome = payment_service.settle_from_gateway(order)
    if outcome in {"paid", "authorized"}:
        if outcome == "authorized":
            payment_service.capture(order)
        raise PaidOnline()
    if outcome != "unpaid":
        raise TakeoverFailed(GATEWAY_UNCERTAIN_MESSAGE)

    # 2. Matar a cobrança no provedor, e só então no Payman.
    remote_expires_at = ""
    if local_status in {"pending", ""}:
        adapter = payment_service._adapter_for_persisted_intent(intent_ref, method=method)
        cancel_remote = getattr(adapter, "cancel", None) if adapter is not None else None
        if cancel_remote is None:
            # Provedor sem verbo de cancelamento: a cobrança remota morre sozinha
            # no vencimento. Sem vencimento conhecido, receber no balcão abriria a
            # porta da cobrança dupla.
            remote_expires_at = str(_payment(order).get("expires_at") or "")
            if not remote_expires_at:
                raise TakeoverFailed(CANCEL_FAILED_MESSAGE)
        else:
            try:
                result = cancel_remote(intent_ref, reason=SKIP_REASON)
                cancelled = bool(getattr(result, "success", False))
            except Exception:
                logger.warning("counter_takeover.cancel_failed order=%s intent=%s", order.ref, intent_ref, exc_info=True)
                cancelled = False
            if not cancelled:
                # A recusa pode ser justamente o pagamento que acabou de entrar
                # (sessão concluída, Pix CONCLUIDA): pergunta de novo.
                if payment_service.settle_from_gateway(order) in {"paid", "authorized"}:
                    raise PaidOnline()
                raise TakeoverFailed(CANCEL_FAILED_MESSAGE)
    _cancel_local_intent(intent_ref)

    # 3 e 4. Sob o lock do pedido: calar avisos e gravar o que aconteceu.
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment = _payment(locked)
        record = {
            "from_method": method,
            "cancelled_intent_ref": intent_ref,
            "at": timezone.now().isoformat(),
            "actor": actor,
        }
        if remote_expires_at:
            record["remote_expires_at"] = remote_expires_at
        payment["counter_takeover"] = record
        data = dict(locked.data or {})
        data["payment"] = payment
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])
        skipped = skip_pending_payment_notices(locked)
        locked.emit_event(
            event_type="payment.counter_takeover",
            actor=actor,
            payload={"from_method": method, "cancelled_intent_ref": intent_ref, "notices_skipped": skipped},
        )
    order.refresh_from_db()
    logger.info("counter_takeover order=%s method=%s intent=%s", order.ref, method, intent_ref)
    return Takeover(taken_over=True, from_method=method, cancelled_intent_ref=intent_ref)


def _local_status(intent_ref: str) -> str:
    from shopman.payman import PaymentError, PaymentService

    try:
        return str(PaymentService.get(intent_ref).status or "")
    except PaymentError:
        return ""


def _cancel_local_intent(intent_ref: str) -> None:
    """O intent do Payman acompanha o provedor (os adapters já o fazem; o resto aqui)."""
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return
    if intent.status in {"pending", "authorized"}:
        PaymentService.cancel(intent_ref, reason=SKIP_REASON)


def skip_pending_payment_notices(order) -> int:
    """Os avisos de cobrança deste pedido na fila são pulados, com motivo.

    Mesmo carimbo do ``NotificationSendHandler._record_skip``: o worker vê
    ``notification_delivery.status == "skipped"`` e encerra a Directive sem
    enviar. Devolve quantos foram pulados.
    """
    from shopman.orderman.models import Directive

    from shopman.shop.directives import NOTIFICATION_SEND

    count = 0
    pending = Directive.objects.select_for_update().filter(
        topic=NOTIFICATION_SEND,
        status=Directive.Status.QUEUED,
        payload__order_ref=order.ref,
        payload__template__in=sorted(PAYMENT_NOTICE_TEMPLATES),
    )
    for directive in pending:
        payload = dict(directive.payload or {})
        if (payload.get("notification_delivery") or {}).get("status") in {"accepted", "skipped"}:
            continue
        payload["notification_delivery"] = {
            "status": "skipped",
            "reason": SKIP_REASON,
            "recorded_at": timezone.now().isoformat(),
        }
        directive.payload = payload
        directive.save(update_fields=["payload", "updated_at"])
        count += 1
    return count


# ── A corrida tardia: o provedor confirma depois do balcão ────────────────


def refund_late_payment(order, *, booked_ref: str, adapter, method: str) -> bool:
    """Estorna, no MESMO meio, o pagamento digital que chegou depois do balcão.

    ``booked_ref`` é o intent capturado onde o dinheiro tardio foi registrado
    (a cobrança cancelada não aceita captura). Idempotente: o saldo reembolsável
    do Payman decide se ainda há o que devolver, e a chave de estorno é estável.
    Devolve ``True`` quando o estorno saiu (ou já tinha saído).
    """
    from shopman.utils.monetary import format_money

    from shopman.shop.services import payment as payment_service
    from shopman.shop.services.observability import create_operator_alert

    refundable_q = payment_service._payman_refundable_amount(booked_ref)
    if refundable_q is not None and refundable_q <= 0:
        return True
    label = "Pix" if method == "pix" else "cartão"
    if adapter is None or not hasattr(adapter, "refund"):
        payment_service.alert_refund_failed(order, booked_ref, refundable_q, "provedor sem estorno automático")
        return False
    try:
        result = adapter.refund(
            booked_ref,
            amount_q=refundable_q,
            reason=SKIP_REASON,
            idempotency_key=f"counter-takeover-refund:{booked_ref}",
        )
    except Exception as exc:
        # Falha transiente: o provedor reentrega o webhook e a chave estável
        # devolve o MESMO estorno. Grita agora mesmo assim.
        payment_service.alert_refund_failed(order, booked_ref, refundable_q, str(exc)[:200])
        raise
    if not getattr(result, "success", False):
        detail = getattr(result, "message", "") or getattr(result, "error_code", "") or "recusado pelo provedor"
        payment_service.alert_refund_failed(order, booked_ref, refundable_q, detail)
        return False
    amount = f"R$ {format_money(refundable_q)}" if refundable_q is not None else "o valor"
    create_operator_alert(
        type="payment_after_cancel",
        severity="warning",
        message=(
            f"Encomenda {order.ref}: o cliente pagou pelo {label} depois de pagar no balcão. "
            f"Devolvemos {amount} no mesmo {label}; se ele perguntar, o estorno já foi feito."
        ),
        order_ref=order.ref,
        dedupe_key=f"counter-takeover-late:{booked_ref}",
        intent_ref=booked_ref,
    )
    logger.warning("counter_takeover.late_payment_refunded order=%s intent=%s", order.ref, booked_ref)
    return True


def handle_late_stripe_payment(intent_ref: str, payment_intent_id: str) -> bool:
    """Webhook do Stripe para uma cobrança que o balcão já cancelou.

    Devolve ``True`` quando o evento era desse caso (e foi tratado aqui) e
    ``False`` quando não era — quem chama segue o caminho normal.

    - PaymentIntent em ``requires_capture``: anula a autorização; nada foi cobrado.
    - Dinheiro recebido: registra num intent próprio e estorna no cartão.
    """
    from shopman.payman import PaymentError, PaymentService

    from shopman.shop.adapters import payment_stripe
    from shopman.shop.services.observability import create_operator_alert

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return False
    if intent.status != "cancelled" or not intent.order_ref:
        return False
    order = Order.objects.filter(ref=intent.order_ref).first()
    if order is None or not cancelled_by_takeover(order, intent_ref):
        return False
    if not payment_intent_id:
        payment_intent_id = payment_stripe.gateway_payment_intent_id(intent_ref)
    if not payment_intent_id:
        return False

    stripe = payment_stripe._get_stripe()
    stripe_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    status = str(getattr(stripe_intent, "status", "") or "")
    if status == "requires_capture":
        stripe.PaymentIntent.cancel(payment_intent_id)
        create_operator_alert(
            type="payment_after_cancel",
            severity="warning",
            message=(
                f"Encomenda {order.ref}: o cliente autorizou o cartão depois de pagar no balcão. "
                "A autorização foi anulada no Stripe; nada foi cobrado."
            ),
            order_ref=order.ref,
            dedupe_key=f"counter-takeover-late:{payment_intent_id}",
            intent_ref=intent_ref,
        )
        return True
    amount_q = int(getattr(stripe_intent, "amount_received", 0) or 0)
    if status != "succeeded" and amount_q <= 0:
        # Ainda não há dinheiro: o próximo evento (succeeded) volta aqui.
        return True

    booked = PaymentService.create_intent(
        order.ref,
        amount_q or intent.amount_q,
        intent.method,
        gateway="",
        gateway_id=payment_intent_id,
        gateway_data={
            "booked_by": "counter_takeover",
            "reason": "pagamento_digital_depois_do_balcao",
            "superseded_intent_ref": intent_ref,
            "superseded_status": intent.status,
        },
        idempotency_key=f"counter-takeover-late:{payment_intent_id}"[:128],
    )
    if booked.status == "pending":
        PaymentService.authorize(booked.ref, gateway_id=payment_intent_id)
        booked.refresh_from_db()
    if booked.status == "authorized":
        PaymentService.capture(booked.ref, gateway_id=payment_intent_id)
    refund_late_payment(order, booked_ref=booked.ref, adapter=payment_stripe, method=str(intent.method or "card"))
    return True
