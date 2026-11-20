"""O saldo da encomenda cobrado em Pix no balcão (#2897), sem cobrança dupla.

Gesto de dinheiro tem UMA tela (dono, 16/11/2026): o "Receber e entregar" do PDV
abre a tela de Pagamento da venda, e o Pix entra nela do jeito que a venda de
balcão já recebe Pix: um intent Pix do pedido (``payment.initiate``), o QR na
tela e na Tela do cliente, e a confirmação pelo caminho canônico (webhook da Efí,
``pix_confirmation.confirm_pix``; no simulador, ``mock_pix.confirm``). Pago, o
saldo vira zero e a entrega é o "Entregar" de sempre
(``operator_orders.hand_over_at_counter``).

A regra que manda é a do :mod:`counter_takeover`: o cliente nunca tem duas
cobranças vivas para o mesmo pedido.

- **O Pix online do cliente ainda vivo, do mesmo valor**: o balcão o aproveita
  (``adopted``), mostra o QR dele e não cria outro.
- **Outra cobrança digital viva** (link, cartão hospedado, Pix vencido ou de outro
  valor): o :mod:`counter_takeover` pergunta ao provedor, cancela lá e só então o
  Pix novo nasce. Pagou enquanto isso? ``PaidOnline``: só entregar.
- **O Pix do balcão que não chega**: receber em dinheiro ou cartão passa pelo mesmo
  ``counter_takeover`` (o "Receber e entregar" de sempre), que cancela este Pix
  antes de o dinheiro entrar. Pix pago depois disso cai em cobrança cancelada e é
  estornado no mesmo meio (``counter_takeover.refund_late_payment``).
- **Vencido, o Pix do balcão NÃO cancela a encomenda** (``governs`` no
  ``PaymentTimeoutHandler``): o cliente está na frente do balcão, e o caminho é
  gerar outro ou receber de outra forma.

Fora daqui, e dito no PR: o Pix misto (Pix + dinheiro no mesmo saldo) e o saldo
de encomenda com parte já paga (o ``initiate`` cobra o total efetivo do pedido).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

#: A marca do Pix do balcão em ``Order.data.payment`` (docs/reference/data-schemas.md).
MARKER_KEY = "counter_pix"
#: Os ``counter_takeover`` das rodadas anteriores (ver ``counter_takeover.cancelled_by_takeover``).
TAKEOVER_HISTORY_KEY = "counter_takeover_history"

PARTIAL_BALANCE_MESSAGE = (
    "Esta encomenda já tem parte paga: o Pix do balcão ainda não cobra só o saldo. "
    "Receba em dinheiro ou cartão."
)
NOT_CREATED_MESSAGE = "Não deu para gerar o Pix agora. Receba em dinheiro ou cartão, ou tente de novo."


class CounterPixRefused(ValueError):
    """O Pix do balcão não pode nascer agora. A frase é a que o operador lê."""


def _payment(order) -> dict:
    return dict((order.data or {}).get("payment") or {})


def governs(order) -> bool:
    """Este pedido está com o Pix do balcão (nascendo ou vivo)?

    A marca vale enquanto o intent dela for o do pedido, ou enquanto o Pix ainda
    nasce (sem ``intent_ref``, dentro do ``initiate``).
    """
    payment = _payment(order)
    marker = payment.get(MARKER_KEY) or {}
    if not isinstance(marker, dict) or not marker:
        return False
    if str(payment.get("method") or "").strip().lower() != "pix":
        return False
    marked = str(marker.get("intent_ref") or "")
    return not marked or marked == str(payment.get("intent_ref") or "")


def live_proof(order) -> dict | None:
    """O QR do Pix do balcão ainda pagável, no formato da venda (``_pos_payment_response``).

    ``None`` quando não há Pix do balcão, ou quando ele não pode mais ser pago
    (vencido, cancelado, pago).
    """
    if not governs(order):
        return None
    payment = _payment(order)
    intent_ref = str(payment.get("intent_ref") or "")
    if not intent_ref or _intent_status(intent_ref) != "pending" or _expired(payment):
        return None
    from shopman.shop.services.pos import _pos_payment_response

    return _pos_payment_response(order)


def start(order, *, actor: str, terminal_ref: str, attempt_id: str = "") -> dict:
    """Cobrar o saldo da encomenda em Pix no balcão. Devolve o QR (formato da venda).

    Levanta :class:`CounterPixRefused` com a frase do operador,
    ``counter_takeover.PaidOnline`` (o cliente acabou de pagar online: só
    entregar) e ``counter_takeover.TakeoverFailed`` (a cobrança viva não pôde ser
    cancelada: nada mudou). Idempotente: o Pix do balcão ainda pagável é
    devolvido como está.
    """
    from shopman.shop.services import counter_takeover, operator_orders, order_composition
    from shopman.shop.services import payment as payment_service

    order.refresh_from_db()
    proof = live_proof(order)
    if proof is not None:
        return proof

    due = payment_service.balance_due_q(order)
    blocked = operator_orders.counter_hand_over_block(order, balance_q=due)
    if blocked:
        raise CounterPixRefused(blocked)
    if not due:
        raise CounterPixRefused("Esta encomenda já está paga: só entregue.")
    if due != order_composition.effective_total_q(order):
        raise CounterPixRefused(PARTIAL_BALANCE_MESSAGE)
    _enforce_pix_policy(due)

    digital = counter_takeover.pending_digital_method(order)
    payment = _payment(order)
    if digital == "pix" and _adoptable(payment, due):
        # O Pix online do cliente ainda vivo e do mesmo valor: é ESTE que o
        # cliente paga no balcão. Criar outro abriria a cobrança dupla.
        _mark(order, actor=actor, terminal_ref=terminal_ref, due=due, adopted=True)
        order.refresh_from_db()
        from shopman.shop.services.pos import _pos_payment_response

        return _pos_payment_response(order)
    if digital:
        # Link, cartão hospedado, Pix vencido ou de outro valor: cancela no
        # provedor primeiro (pergunta antes se o cliente já pagou).
        counter_takeover.take_over_pending_digital_charge(order, actor=actor, attempt_id=attempt_id)
        order.refresh_from_db()

    previous = _switch_to_pix(order, actor=actor, terminal_ref=terminal_ref, due=due)
    try:
        payment_service.initiate(order)
    except Exception:
        logger.warning("counter_pix.initiate_failed order=%s", order.ref, exc_info=True)
    order.refresh_from_db()
    payment = _payment(order)
    intent_ref = str(payment.get("intent_ref") or "")
    if not intent_ref or not (payment.get("copy_paste") or payment.get("qr_code")):
        error = str(payment.get("error") or "").strip()
        _revert(order, previous=previous)
        raise CounterPixRefused(f"{error} {NOT_CREATED_MESSAGE}".strip() if error else NOT_CREATED_MESSAGE)
    _stamp_intent(order, intent_ref=intent_ref)
    order.refresh_from_db()
    order.emit_event(
        event_type="payment.counter_pix",
        actor=actor,
        payload={"intent_ref": intent_ref, "amount_q": due, "terminal_ref": terminal_ref},
    )
    logger.info("counter_pix.started order=%s intent=%s amount_q=%s", order.ref, intent_ref, due)
    from shopman.shop.services.pos import _pos_payment_response

    return _pos_payment_response(order)


# ── Peças ─────────────────────────────────────────────────────────────────────


def _enforce_pix_policy(amount_q: int) -> None:
    """O teto do Pix de homologação da Efí (o mesmo da venda)."""
    from shopman.shop.services import pix_policy

    try:
        pix_policy.enforce_pix_test_amount_limit(amount_q)
    except pix_policy.PixPaymentPolicyError as exc:
        raise CounterPixRefused(exc.message) from exc


def _intent_status(intent_ref: str) -> str:
    from shopman.payman import PaymentError, PaymentService

    try:
        return str(PaymentService.get(intent_ref).status or "")
    except PaymentError:
        return ""


def _expired(payment: dict) -> bool:
    from django.utils.dateparse import parse_datetime

    expires_at = parse_datetime(str(payment.get("expires_at") or ""))
    return expires_at is not None and expires_at <= timezone.now()


def _adoptable(payment: dict, due: int) -> bool:
    """O Pix online vivo pode ser o do balcão: pendente, no prazo, do valor do saldo."""
    intent_ref = str(payment.get("intent_ref") or "")
    if not intent_ref or _intent_status(intent_ref) != "pending" or _expired(payment):
        return False
    if not (payment.get("copy_paste") or payment.get("qr_code")):
        return False
    return int(payment.get("amount_q") or 0) == int(due)


def _mark(order, *, actor: str, terminal_ref: str, due: int, adopted: bool) -> None:
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment = _payment(locked)
        payment[MARKER_KEY] = {
            "at": timezone.now().isoformat(),
            "actor": actor,
            "terminal_ref": terminal_ref,
            "amount_q": int(due),
            "intent_ref": str(payment.get("intent_ref") or ""),
            "adopted": adopted,
            "from": {},
        }
        data = dict(locked.data or {})
        data["payment"] = payment
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])
        locked.emit_event(
            event_type="payment.counter_pix",
            actor=actor,
            payload={"intent_ref": payment[MARKER_KEY]["intent_ref"], "amount_q": int(due), "adopted": adopted},
        )


def _switch_to_pix(order, *, actor: str, terminal_ref: str, due: int) -> dict:
    """O pedido passa a ser cobrado em Pix, com a marca do balcão. Devolve o que era."""
    from shopman.shop.services.payment import _INTENT_PRESENTATION_KEYS

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment = _payment(locked)
        previous = dict(payment)
        # A cobrança assumida antes (o link cancelado agora, ou o Pix do balcão de
        # uma rodada anterior) vai para o histórico: o registro vivo passa a ser o
        # deste Pix, e o pagamento que cair depois na cobrança antiga continua
        # sendo estornado (``cancelled_by_takeover`` lê o histórico).
        if payment.get("counter_takeover"):
            history = list(payment.get(TAKEOVER_HISTORY_KEY) or [])
            history.append(payment.pop("counter_takeover"))
            payment[TAKEOVER_HISTORY_KEY] = history
        origin = {key: previous.get(key) for key in ("method", "collection", "tenders") if key in previous}
        for key in (*_INTENT_PRESENTATION_KEYS, "error", "collection"):
            payment.pop(key, None)
        payment["method"] = "pix"
        payment["amount_q"] = int(due)
        payment["tenders"] = [{
            "method": "pix",
            "amount_q": int(due),
            "collection": "terminal",
            "status": "pending",
            "terminal_ref": terminal_ref,
        }]
        payment[MARKER_KEY] = {
            "at": timezone.now().isoformat(),
            "actor": actor,
            "terminal_ref": terminal_ref,
            "amount_q": int(due),
            "intent_ref": "",
            "adopted": False,
            "from": origin,
        }
        data = dict(locked.data or {})
        data["payment"] = payment
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])
    order.refresh_from_db()
    return previous


def _stamp_intent(order, *, intent_ref: str) -> None:
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment = _payment(locked)
        marker = dict(payment.get(MARKER_KEY) or {})
        marker["intent_ref"] = intent_ref
        payment[MARKER_KEY] = marker
        data = dict(locked.data or {})
        data["payment"] = payment
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])


def _revert(order, *, previous: dict) -> None:
    """O Pix não nasceu: o pagamento volta ao que era (com a cobrança assumida, se houve)."""
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment = _payment(locked)
        if payment.get("intent_ref") and _intent_status(str(payment.get("intent_ref"))) in {"pending", "authorized"}:
            # Um intent chegou a nascer sem QR: não fica vivo sem tela que o mostre.
            from shopman.payman import PaymentError, PaymentService

            try:
                PaymentService.cancel(str(payment["intent_ref"]), reason="counter_pix_not_created")
            except PaymentError:
                logger.warning("counter_pix.revert_cancel_failed order=%s", locked.ref, exc_info=True)
        restored = dict(previous)
        data = dict(locked.data or {})
        data["payment"] = restored
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])
    order.refresh_from_db()
