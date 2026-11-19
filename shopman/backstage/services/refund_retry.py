"""Tentar o estorno de novo (WP-G13): o Gerente resolve o estorno que falhou.

O estorno que o gateway recusou (ou que o sistema desistiu de tentar) ficava em
"Estorno não saiu" esperando o suporte: o único reenvio era o Admin do Payman, com
permissão só do Dono (EXCELENCIA-GESTOR P1-15, F-10). Aqui o gesto vai para o
Gestor, com a assinatura de um Gerente (decisão 3 do dono, 17/11/2026). Vale para
o cancelado e, desde a #2727, para o que falhou fora dele: a devolução registrada
(WP-G12), a encomenda editada que ficou mais barata e o pagamento digital que
chegou depois de o balcão receber.

Nada de estorno novo é inventado: quem fala com o gateway é o mesmo
``payment.refund_intent_at_gateway`` do Admin, cobrança por cobrança. Este módulo só
responde três perguntas e registra a tentativa:

- **pode?** Só o pedido em "Estorno não saiu": o aviso ``payment_refund_failed``
  aberto e dinheiro que ainda falta voltar (no cancelado, a mesma régua da faixa:
  devolução pedida e não fechada);
- **quanto e de onde?** O que ``payment.gateway_refund_owed_q`` diz que falta
  voltar pelo meio online (no cancelado, o ``cancelled_money`` com o teto do "não
  retirado"; fora dele, o ``overpaid_q`` e o pagamento que chegou depois do balcão,
  já descontado o que a gaveta e a maquininha devolvem), repartido pelas
  cobranças online que ainda guardam dinheiro (``payment.gateway_refund_legs``);
- **com que chave?** Uma por tentativa (a chave da intenção da tela). A exceção é a
  tentativa que ficou SEM RESPOSTA do gateway: a seguinte reapresenta a mesma
  chave, para o gateway devolver a mesma devolução em vez de fazer outra. Vale
  também para o estorno automático que pode ter saído sem resposta (a directive
  que esgotou as tentativas, o estorno do pagamento que chegou depois do balcão):
  a primeira tentativa daqui reapresenta a chave DELE.

Cada tentativa vira o evento ``payment.refund_retry`` do pedido (quem tentou, quem
autorizou, o que o gateway respondeu); a que sai também grava o ``payment.refunded``
de todo estorno.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from django.db import transaction
from shopman.orderman.models import Directive, Order
from shopman.utils.monetary import format_money

from shopman.shop.directives import PAYMENT_REFUND
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.remote_mutations import mutation_fingerprint

logger = logging.getLogger(__name__)

ACTION_REF = "refund-retry"
ACTION_LABEL = "Tentar o estorno de novo"
EVENT_TYPE = "payment.refund_retry"
ALERT_TYPE = "payment_refund_failed"
PERMISSION_REASON = "Identifique uma pessoa com permissão para gerenciar pedidos."

OUTCOME_REFUNDED = "refunded"
#: O gateway respondeu que não: nada saiu, e outra tentativa leva outra chave.
OUTCOME_REFUSED = "refused"
#: O gateway não respondeu: o estorno pode ter saído, e a próxima tentativa repete a chave.
OUTCOME_UNCONFIRMED = "unconfirmed"
#: O dinheiro saiu e o registro daqui falhou: ninguém tenta de novo, o suporte acerta o livro.
OUTCOME_UNRECORDED = "unrecorded"

_OUTCOME_BY_ERROR = {"gateway_unreachable": OUTCOME_UNCONFIRMED, "ledger_drift": OUTCOME_UNRECORDED}

NOT_FAILED_REASON = "Este pedido não tem estorno que falhou para tentar de novo."
_STATE_REASONS = {
    "refunded": "O estorno deste pedido já saiu.",
    "refund_requested": "O estorno deste pedido foi pedido e não falhou: é só esperar a confirmação.",
    "card_hold_released": "A reserva do cartão foi desfeita: não há o que estornar.",
    "nothing_charged": "Nada foi cobrado neste pedido: não há o que estornar.",
}
IN_FLIGHT_REASON = "O sistema ainda está tentando este estorno sozinho. Espere ele terminar para tentar de novo."
NO_ROUTE_REASON = "Esta cobrança não volta pelo meio de pagamento a partir daqui. O suporte conclui o estorno."
UNRECORDED_REASON = (
    "O dinheiro saiu na última tentativa, mas o registro aqui falhou. O suporte acerta o registro: não tente de novo."
)
STALE_MESSAGE = "O estorno deste pedido mudou depois que você abriu a tela. Confira e tente de novo."
_UNCONFIRMED_MESSAGE = (
    "O meio de pagamento não respondeu, e não dá para saber se o estorno saiu. Tente de novo em alguns minutos."
)


#: Como a Caixa chama o meio de pagamento na frase da recusa.
_METHOD_SUBJECT = {"pix": "O Pix", "card": "O cartão"}
_NO_PAYMENT_CODES = frozenset({"not_paid", "no_payment"})
_NO_WAY_CODES = frozenset({"no_gateway_route", "intent_not_found"})
_NOTHING_RETURNED = "Nada foi devolvido ao cliente. Chame o suporte."


def counter_message(outcome: str, error_code: str, method: str) -> str:
    """A frase da tentativa que não saiu, para quem está no balcão.

    A resposta do gateway (``PaymentResult.message``) foi escrita para o Admin:
    fala de gateway, de ambiente e de painel. Na faixa e na linha do tempo do
    Gestor vai o que a Caixa precisa saber: se o dinheiro voltou e o que fazer.
    A resposta técnica fica no evento (``gateway_message``) e no log.
    """
    if outcome == OUTCOME_UNCONFIRMED:
        return _UNCONFIRMED_MESSAGE
    if outcome == OUTCOME_UNRECORDED:
        return UNRECORDED_REASON
    subject = _METHOD_SUBJECT.get(str(method or "").lower(), "O meio de pagamento")
    if error_code in _NO_WAY_CODES or error_code.startswith("refund_route_"):
        return f"Não foi possível pedir o estorno desta cobrança daqui. {_NOTHING_RETURNED}"
    if error_code in _NO_PAYMENT_CODES:
        return f"{subject} diz que não há pagamento para devolver nesta cobrança. {_NOTHING_RETURNED}"
    return f"{subject} não aceitou o estorno. {_NOTHING_RETURNED}"


class RefundRetryRefused(Exception):
    """O pedido não está em "Estorno não saiu" (ou não há por onde estornar daqui)."""


class RefundRetryStale(Exception):
    """A tela leu um estorno que já não é o de agora."""


@dataclass(frozen=True)
class RetryLeg:
    """Uma cobrança de gateway que ainda guarda dinheiro, e quanto dela volta."""

    intent_ref: str
    method: str
    amount_q: int


@dataclass(frozen=True)
class RetryPlan:
    """O que a tentativa faria agora. ``block_reason`` vazio: pode tentar."""

    block_reason: str = ""
    #: O pedido está em "Estorno não saiu" (com ou sem por onde tentar daqui): a
    #: faixa mostra a linha do gesto. ``False``: não há estorno que falhou.
    failed: bool = False
    amount_q: int = 0
    #: ``pix`` ou ``card``: por onde o dinheiro volta (``payment.CancelledMoney.method``,
    #: ou a primeira cobrança online fora do cancelado).
    method: str = ""
    legs: tuple[RetryLeg, ...] = ()
    #: Quantas tentativas o pedido já teve: entra na base, e a tela velha é recusada.
    attempts: int = 0


@dataclass(frozen=True)
class RetryAttempt:
    """A última tentativa registrada no pedido, para a faixa do detalhe dizer o que houve."""

    outcome: str
    message: str
    at: object


def _attempt_payloads(order: Order) -> list[tuple[dict, object]]:
    return [
        (payload if isinstance(payload, dict) else {}, created_at)
        for payload, created_at in order.events.filter(type=EVENT_TYPE).order_by("seq").values_list("payload", "created_at")
    ]


def last_attempt(order: Order) -> RetryAttempt | None:
    """A tentativa mais recente que NÃO saiu, ou ``None`` (nunca tentaram, ou a última saiu)."""
    attempts = _attempt_payloads(order)
    if not attempts:
        return None
    payload, created_at = attempts[-1]
    if payload.get("outcome") == OUTCOME_REFUNDED:
        return None
    return RetryAttempt(
        outcome=str(payload.get("outcome") or ""), message=str(payload.get("message") or ""), at=created_at,
    )


def _failed_money(order: Order) -> tuple[bool, str, str]:
    """``(falhou, meio, motivo)``: o pedido está em "Estorno não saiu", ou por que não está.

    No cancelado digital, a régua é a da faixa (``order_pending.cancelled_money``):
    a devolução foi pedida, não fechou, e o aviso ``payment_refund_failed`` do
    pedido está aberto. Fora dele não há estado de devolução para ler: o que
    falhou é o aviso aberto, e o valor vem de ``payment.gateway_refund_owed_q``.
    """
    from shopman.backstage.projections import order_pending

    money = payment_svc.cancelled_money(order)
    if money is not None:
        if money.outcome != order_pending.MONEY_REFUND_REQUESTED:
            return False, "", _STATE_REASONS.get(money.outcome, NOT_FAILED_REASON)
        if order_pending.ALERT_REFUND_FAILED not in order_pending.open_alert_types(order):
            return False, "", _STATE_REASONS["refund_requested"]
        return True, str(money.method or ""), ""
    if order_pending.ALERT_REFUND_FAILED not in order_pending.open_alert_types(order):
        return False, "", NOT_FAILED_REASON
    return True, "", ""


def _leg_method(method: str) -> str:
    """Como a faixa nomeia o meio de uma cobrança online: ``pix`` ou ``card``."""
    return "pix" if str(method or "").lower() == "pix" else "card"


def _gateway_legs(order: Order, owed_q: int) -> tuple[RetryLeg, ...]:
    """Reparte ``owed_q`` pelas cobranças online do pedido que ainda guardam dinheiro."""
    return tuple(
        RetryLeg(intent_ref=intent_ref, method=method, amount_q=amount_q)
        for intent_ref, method, amount_q in payment_svc.gateway_refund_legs(order, owed_q)
    )


def plan(order: Order) -> RetryPlan:
    """O que "Tentar o estorno de novo" faria agora, sem gravar nem falar com o gateway."""
    failed, method, reason = _failed_money(order)
    if not failed:
        return RetryPlan(block_reason=reason)
    attempts = _attempt_payloads(order)
    count = len(attempts)
    # No cancelado, nunca mais do que o teto do "não retirado" (o capturado menos o
    # que fica com a loja); fora dele, nunca o que a gaveta ou a maquininha devolvem.
    owed_q = payment_svc.gateway_refund_owed_q(order)
    if owed_q <= 0:
        return RetryPlan(block_reason=NOT_FAILED_REASON, method=method, attempts=count)
    legs = _gateway_legs(order, owed_q)
    method = method or (_leg_method(legs[0].method) if legs else "")
    if attempts and attempts[-1][0].get("outcome") == OUTCOME_UNRECORDED:
        return RetryPlan(block_reason=UNRECORDED_REASON, failed=True, amount_q=owed_q, method=method, attempts=count)
    in_flight = Directive.objects.filter(
        topic=PAYMENT_REFUND, payload__order_ref=order.ref, status__in=("queued", "running"),
    ).exists()
    if in_flight:
        return RetryPlan(block_reason=IN_FLIGHT_REASON, failed=True, amount_q=owed_q, method=method, attempts=count)
    if not legs:
        return RetryPlan(block_reason=NO_ROUTE_REASON, failed=True, amount_q=owed_q, method=method, attempts=count)
    return RetryPlan(failed=True, amount_q=sum(leg.amount_q for leg in legs), method=method, legs=legs, attempts=count)


def revision(order: Order, current: RetryPlan | None = None) -> str:
    """A base do gesto: o valor, as cobranças e quantas tentativas a tela leu."""
    current = current if current is not None else plan(order)
    state = {
        "status": str(order.status),
        "amount_q": current.amount_q,
        "legs": [[leg.intent_ref, leg.amount_q] for leg in current.legs],
        "attempts": current.attempts,
        "blocked": current.block_reason,
    }
    return mutation_fingerprint({"version": 1, "order": order.ref, "field": ACTION_REF, "state": state})


def _authorized(user) -> bool:
    return bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))


def detail_action(order: Order, user=None, *, current: RetryPlan | None = None):
    """A ação "Tentar o estorno de novo" do detalhe, com a base que o comando confere."""
    from shopman.shop.projections.types import Action

    current = current if current is not None else plan(order)
    reason = current.block_reason or ("" if _authorized(user) else PERMISSION_REASON)
    confirmation = {"required": True, "manager_approval": True}
    if current.amount_q > 0:
        # O que o gerente lê antes de assinar. No cancelado a tela já o tira do
        # ``cancelled_money``; fora dele (devolução, encomenda editada) só daqui.
        confirmation["description"] = (
            f"Estorno de R$ {format_money(current.amount_q)}, pedido de novo ao meio de pagamento."
        )
    return Action(
        ref=ACTION_REF, kind="mutation", label=ACTION_LABEL, priority="secondary",
        enabled=not reason, reason=reason, method="POST", idempotency="required",
        payload_schema={"base_revision": revision(order, current), "expected_actor_id": getattr(user, "pk", None)},
        confirmation=confirmation,
    )


def fresh_gateway_key(order_ref: str, intent_ref: str, attempt_key: str) -> str:
    """A chave de uma tentativa nova: o pedido, a cobrança e o resumo da chave da intenção.

    O resumo mantém a chave curta (ela vira id de devolução no gateway e no
    livro) sem perder a regra: mesma tentativa, mesma chave; outra tentativa, outra.
    """
    digest = hashlib.sha256(str(attempt_key).encode()).hexdigest()[:32]
    return f"order-refund-retry:{order_ref}:{intent_ref}:{digest}"


def _gateway_key(order: Order, leg: RetryLeg, attempt_key: str) -> str:
    """A chave que vai ao gateway: uma por tentativa.

    Menos quando a tentativa anterior DESTA cobrança ficou sem resposta: o
    estorno pode ter saído, e só a mesma chave (com o mesmo valor) faz o gateway
    devolver aquela devolução em vez de abrir outra.
    """
    previous = (
        order.events.filter(type=EVENT_TYPE, payload__intent_ref=leg.intent_ref)
        .order_by("-seq").values_list("payload", flat=True).first()
    )
    if (
        isinstance(previous, dict)
        and previous.get("outcome") == OUTCOME_UNCONFIRMED
        and previous.get("gateway_key")
        and previous.get("amount_q") == leg.amount_q
    ):
        return str(previous["gateway_key"])
    if previous is None:
        inherited = _exhausted_automatic_key(order, leg) or _late_payment_key(order, leg)
        if inherited:
            return inherited
    return fresh_gateway_key(order.ref, leg.intent_ref, attempt_key)


def _late_payment_key(order: Order, leg: RetryLeg) -> str:
    """A chave do estorno automático do pagamento que chegou depois de o balcão receber.

    Aquele estorno (``counter_takeover.refund_late_payment``) abre o aviso tanto
    na recusa quanto na falta de resposta do gateway, e o aviso não diz qual das
    duas foi. Na dúvida, a primeira tentativa daqui reapresenta a chave DELE, com
    o mesmo valor (o saldo inteiro da cobrança): se ele saiu, o gateway devolve a
    mesma devolução; se foi recusado, a resposta volta igual e a tentativa
    seguinte leva chave nova. Valor diferente, a chave é nova: não é o mesmo estorno.
    """
    from shopman.payman import PaymentError, PaymentService

    from shopman.shop.services import counter_takeover

    try:
        intent = PaymentService.get(leg.intent_ref)
    except PaymentError:
        return ""
    if not counter_takeover.late_payment_of_takeover(order, intent):
        return ""
    if PaymentService.refunded_total(intent.ref) > 0:
        return ""
    if PaymentService.captured_total(intent.ref) != leg.amount_q:
        return ""
    return counter_takeover.late_refund_key(intent.ref)


def _exhausted_automatic_key(order: Order, leg: RetryLeg) -> str:
    """A chave do estorno automático que esgotou as tentativas SEM resposta do gateway.

    A directive ``payment.refund`` só termina em ``failed`` quando toda tentativa
    caiu em falha transiente (gateway fora, timeout): a recusa de verdade encerra
    a directive e abre o aviso na hora. Sem resposta, o estorno pode ter saído.
    A primeira tentativa do Gestor reapresenta a chave DAQUELE estorno, com o
    mesmo valor: se ele saiu, o gateway devolve a mesma devolução em vez de
    fazer outra (o que importa no "não retirado", em que sobra saldo na
    cobrança). Valor diferente, a chave é nova: não é o mesmo estorno.
    """
    payload = (
        Directive.objects.filter(topic=PAYMENT_REFUND, payload__order_ref=order.ref, status=Directive.Status.FAILED)
        .order_by("-id").values_list("payload", flat=True).first()
    )
    if not isinstance(payload, dict):
        return ""
    asked_q = payload.get("amount_q")
    if asked_q is not None and int(asked_q) != leg.amount_q:
        return ""
    return payment_svc.order_refund_gateway_key(
        order, leg.intent_ref, idempotency_key=str(payload.get("idempotency_key") or "") or None,
    )


def retry(order: Order, *, actor: str, approved_by: str, attempt_key: str, expected_revision: str) -> dict:
    """Pede de novo ao gateway o estorno que falhou, e registra a tentativa no pedido.

    Devolve ``{outcome, amount_q, refunded_q, message}``: ``outcome`` é
    ``refunded`` só quando o gateway confirmou TUDO o que faltava; senão é o da
    cobrança que não saiu, e ``message`` é a frase do balcão para ela. Levanta
    :class:`RefundRetryStale` (a tela leu outro estorno) e
    :class:`RefundRetryRefused` (o pedido não está em "Estorno não saiu").
    """
    from shopman.backstage.services.alerts import resolve_alerts

    signer = actor if actor == approved_by else f"{actor}, autorizado por {approved_by}"
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment_svc.lock_order_payment(locked)
        current = plan(locked)
        if revision(locked, current) != expected_revision:
            raise RefundRetryStale(STALE_MESSAGE)
        if current.block_reason:
            raise RefundRetryRefused(current.block_reason)

        refunded_q = 0
        failures: list[tuple[str, str]] = []
        for leg in current.legs:
            gateway_key = _gateway_key(locked, leg, attempt_key)
            result = payment_svc.refund_intent_at_gateway(
                leg.intent_ref, amount_q=leg.amount_q, idempotency_key=gateway_key, actor=signer, origin="Gestor",
            )
            error_code = "" if result.success else str(result.error_code or "refused")
            outcome = OUTCOME_REFUNDED if result.success else _OUTCOME_BY_ERROR.get(error_code, OUTCOME_REFUSED)
            message = gateway_message = ""
            if not result.success:
                # A frase do balcão vai para a tela; a do gateway, para o evento e o log.
                message = counter_message(outcome, error_code, leg.method)
                gateway_message = str(result.message or "")
                failures.append((outcome, message))
                logger.warning(
                    "refund_retry order=%s intent=%s outcome=%s code=%s gateway_said=%s",
                    locked.ref, leg.intent_ref, outcome, error_code, gateway_message,
                )
            locked.emit_event(
                EVENT_TYPE,
                actor=actor,
                payload={
                    "intent_ref": leg.intent_ref,
                    "method": leg.method,
                    "amount_q": leg.amount_q,
                    "approved_by": approved_by,
                    "outcome": outcome,
                    "error_code": error_code,
                    "message": message,
                    "gateway_message": gateway_message,
                    "gateway_key": gateway_key,
                },
            )
            if result.success:
                done_q = int(result.amount_q or leg.amount_q)
                refunded_q += done_q
                locked.emit_event(
                    "payment.refunded",
                    actor=actor,
                    payload={"method": leg.method, "amount_q": done_q, "intent_ref": leg.intent_ref},
                )
        if refunded_q > 0 and payment_svc.gateway_refund_owed_q(locked) <= 0:
            # O Payman já diz que nada mais volta pelo meio online: o aviso do sino
            # deixa de ser verdade.
            resolve_alerts(ALERT_TYPE, order_ref=locked.ref, actor=f"refund-retry:{actor}")
    logger.info(
        "refund_retry order=%s actor=%s approved_by=%s amount_q=%s refunded_q=%s failures=%s",
        order.ref, actor, approved_by, current.amount_q, refunded_q, [outcome for outcome, _ in failures],
    )
    return {
        "outcome": failures[0][0] if failures else OUTCOME_REFUNDED,
        "amount_q": current.amount_q,
        "refunded_q": refunded_q,
        "message": " ".join(dict.fromkeys(message for _, message in failures if message)),
    }
