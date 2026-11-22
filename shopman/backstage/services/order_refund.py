"""Estornar UM pedido no Gestor: a exceção financeira do Gerente (#2727, item 5).

Regra do dono, 21/11/2026: *"gerente basicamente NÃO tem permissões financeiras.
Ponto. O que teremos são exceções, extremamente pontuais, com regra claríssima"* e
*"gerente pode ver valores, mas NUNCA somados, relatórios, etc. ... ver valores
específicos de uma transação não é o problema."*

A exceção é esta, e só esta: quem tem ``backstage.refund_single_order`` estorna
partindo de UM pedido, no detalhe do Gestor, e vê o valor pago naquela cobrança e o
que volta dela. Não ganha ``payman.view_paymentintent`` nem
``payman.refund_paymentintent``: o Admin de cobranças lista, e listar é proibido. A
trava é ``shopman/shop/tests/test_gerente_sem_permissao_financeira.py``.

Nada de estorno novo é inventado: quem fala com o gateway é
``payment.refund_intent_at_gateway``, a mesma função que o estorno do Dono no Admin
do Payman chama (``PAYMAN["REFUND_BACKEND"]`` →
``shop.adapters.payman_refund.GatewayRefundBackend``) e que o "Tentar o estorno de
novo" (``refund_retry``) usa. O disponível é a mesma conta do Admin: o capturado
menos o que já voltou (estorno e chargeback). Parcial vale, como no Admin.

Este módulo responde três perguntas e registra a tentativa:

- **pode?** O pedido tem UMA cobrança online com dinheiro guardado, e nada está
  em curso nela: nem o estorno automático (a directive ``payment.refund``), nem o
  estorno que falhou (esse tem o gesto próprio, ``refund_retry``), nem o dinheiro
  que saiu sem registro;
- **quanto?** O que a tela pediu, até o disponível; em branco, o disponível inteiro;
- **com que chave?** Uma por tentativa (a chave da intenção da tela). A tentativa
  que ficou SEM RESPOSTA do gateway faz a seguinte, com o mesmo valor, reapresentar
  a mesma chave: o gateway devolve a mesma devolução em vez de fazer outra.

Cada tentativa vira o evento ``payment.order_refund`` do pedido; a que sai também
grava o ``payment.refunded`` de todo estorno.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from django.db import transaction
from shopman.orderman.models import Directive, Order
from shopman.utils.monetary import format_money

from shopman.backstage.services import refund_retry
from shopman.shop.directives import PAYMENT_REFUND
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.remote_mutations import mutation_fingerprint

logger = logging.getLogger(__name__)

#: A exceção financeira do Gerente. Declarada em ``DayClosing.Meta.permissions``.
PERMISSION = "backstage.refund_single_order"
ACTION_REF = "refund"
ACTION_LABEL = "Estornar"
EVENT_TYPE = "payment.order_refund"

PERMISSION_REASON = "Só quem tem a permissão de estornar um pedido estorna daqui."
NOTHING_LEFT_REASON = "O valor desta cobrança já voltou inteiro ao cliente."
MANY_CHARGES_REASON = (
    "Este pedido tem mais de uma cobrança pelo meio de pagamento. O estorno dele é com o Dono."
)
RETRY_REASON = "Este pedido tem um estorno que não saiu. Use Tentar o estorno de novo, na faixa do pedido."
WAITING_REASON = "O estorno deste pedido foi pedido e não falhou: é só esperar a confirmação."
STALE_MESSAGE = "O valor desta cobrança mudou depois que você abriu a tela. Confira e tente de novo."
AMOUNT_REQUIRED = "Informe quanto estornar."
CONFIRM_REQUIRED = "Marque a confirmação para estornar."


class OrderRefundRefused(Exception):
    """O pedido não tem o que estornar daqui (ou o valor pedido não cabe)."""


class OrderRefundStale(Exception):
    """A tela leu uma cobrança que já não é a de agora."""


@dataclass(frozen=True)
class RefundPlan:
    """O que o estorno faria agora. ``block_reason`` vazio: pode estornar.

    Os valores são da cobrança deste pedido e de mais nenhuma: o que ela recebeu
    (``paid_q``), o que já voltou dela (``returned_q``) e o que ainda pode voltar
    (``available_q``).
    """

    block_reason: str = ""
    intent_ref: str = ""
    method: str = ""
    paid_q: int = 0
    returned_q: int = 0
    available_q: int = 0
    #: Quantas tentativas o pedido já teve: entra na base, e a tela velha é recusada.
    attempts: int = 0


def _gateway_charges(order: Order) -> list:
    """As cobranças online do pedido que receberam dinheiro (a rota do estorno é o gateway)."""
    from shopman.payman import PaymentService

    from shopman.shop.services.order_edit import ROUTE_GATEWAY, refund_route

    charges = []
    for intent in PaymentService.get_by_order(order.ref).filter(status__in=("captured", "refunded")).order_by("id"):
        if refund_route(intent) == ROUTE_GATEWAY and PaymentService.captured_total(intent.ref) > 0:
            charges.append(intent)
    return charges


def _totals(intent) -> tuple[int, int]:
    """``(pago, já devolvido)`` de UMA cobrança: a conta do Admin (``_available_q``)."""
    from shopman.payman import PaymentService

    returned_q = PaymentService.refunded_total(intent.ref) + PaymentService.chargeback_total(intent.ref)
    return PaymentService.captured_total(intent.ref), returned_q


def _attempts(order: Order) -> list[dict]:
    return [
        payload if isinstance(payload, dict) else {}
        for payload in order.events.filter(type=EVENT_TYPE).order_by("seq").values_list("payload", flat=True)
    ]


def plan(order: Order, *, retry_failed: bool | None = None) -> RefundPlan | None:
    """O que "Estornar" faria agora, sem gravar nem falar com o gateway.

    ``None``: o pedido não tem cobrança online paga, e o gesto não existe nele.
    ``retry_failed`` evita ler de novo o que o detalhe já leu (``refund_retry.plan``).
    """
    charges = _gateway_charges(order)
    if not charges:
        return None
    attempts = _attempts(order)
    held = [(intent, *_totals(intent)) for intent in charges]
    with_money = [(intent, paid_q, returned_q) for intent, paid_q, returned_q in held if paid_q - returned_q > 0]
    if len(with_money) > 1:
        return RefundPlan(block_reason=MANY_CHARGES_REASON, attempts=len(attempts))
    intent, paid_q, returned_q = with_money[0] if with_money else held[-1]
    base = {
        "intent_ref": intent.ref,
        "method": str(intent.method or ""),
        "paid_q": paid_q,
        "returned_q": returned_q,
        "available_q": max(paid_q - returned_q, 0),
        "attempts": len(attempts),
    }
    if not with_money:
        return RefundPlan(block_reason=NOTHING_LEFT_REASON, **base)
    if attempts and attempts[-1].get("outcome") == refund_retry.OUTCOME_UNRECORDED:
        return RefundPlan(block_reason=refund_retry.UNRECORDED_REASON, **base)
    if retry_failed is None:
        retry_failed = refund_retry.plan(order).failed
    if retry_failed:
        return RefundPlan(block_reason=RETRY_REASON, **base)
    in_flight = Directive.objects.filter(
        topic=PAYMENT_REFUND, payload__order_ref=order.ref, status__in=("queued", "running"),
    ).exists()
    if in_flight:
        return RefundPlan(block_reason=refund_retry.IN_FLIGHT_REASON, **base)
    money = payment_svc.cancelled_money(order)
    if money is not None and money.outcome == "refund_requested":
        # O cancelado digital já pediu a devolução sozinho: a resposta chega por ele.
        return RefundPlan(block_reason=WAITING_REASON, **base)
    return RefundPlan(**base)


def revision(order: Order, current: RefundPlan | None) -> str:
    """A base do gesto: a cobrança, o que ela ainda guarda e quantas tentativas a tela leu."""
    state = {
        "status": str(order.status),
        "intent_ref": getattr(current, "intent_ref", ""),
        "available_q": getattr(current, "available_q", 0),
        "attempts": getattr(current, "attempts", 0),
        "blocked": getattr(current, "block_reason", ""),
    }
    return mutation_fingerprint({"version": 1, "order": order.ref, "field": ACTION_REF, "state": state})


def can_refund(user) -> bool:
    return bool(
        user and user.is_active and user.is_staff
        and user.has_perm("shop.manage_orders") and user.has_perm(PERMISSION)
    )


def _money(value_q: int) -> str:
    return f"R$ {format_money(int(value_q or 0))}"


def detail_action(order: Order, user=None, *, retry_failed: bool | None = None):
    """A ação "Estornar" do detalhe, ou ``None`` (sem a permissão, ou sem cobrança online paga).

    Quem não tem a permissão nem vê a porta: o gesto é exceção, não menu de todos.
    """
    from shopman.shop.projections.types import Action

    if not can_refund(user):
        return None
    current = plan(order, retry_failed=retry_failed)
    if current is None:
        return None
    return Action(
        ref=ACTION_REF, kind="mutation", label=ACTION_LABEL, priority="danger",
        enabled=not current.block_reason, reason=current.block_reason, method="POST", idempotency="required",
        payload_schema={"base_revision": revision(order, current), "expected_actor_id": getattr(user, "pk", None)},
        confirmation={"required": True},
    )


def preview(order: Order, user=None) -> dict:
    """O que o diálogo mostra: o pago e o disponível DESTA cobrança, e a ação com a base.

    Nenhuma soma sobre outro pedido ou outra cobrança: os valores são de uma só.
    """
    from shopman.backstage.presentation.status import payment_method_label

    current = plan(order)
    action = detail_action(order, user)
    if current is None:
        return {
            "order_ref": order.ref,
            "blocked": True,
            "block_reason": "Este pedido não tem cobrança pelo meio de pagamento para estornar daqui.",
            "action": None,
        }
    return {
        "order_ref": order.ref,
        "method_label": payment_method_label(current.method) if current.method else "",
        "paid_q": current.paid_q,
        "paid_display": _money(current.paid_q),
        "returned_q": current.returned_q,
        "returned_display": _money(current.returned_q) if current.returned_q else "",
        "available_q": current.available_q,
        "available_display": _money(current.available_q),
        "partial_allowed": True,
        "blocked": bool(current.block_reason),
        "block_reason": current.block_reason,
        "action": _action_data(action),
    }


def _action_data(action) -> dict | None:
    if action is None:
        return None
    from dataclasses import asdict

    return asdict(action)


def fresh_gateway_key(order_ref: str, intent_ref: str, attempt_key: str) -> str:
    """A chave de uma tentativa nova: o pedido, a cobrança e o resumo da chave da intenção."""
    digest = hashlib.sha256(str(attempt_key).encode()).hexdigest()[:32]
    return f"order-refund-gestor:{order_ref}:{intent_ref}:{digest}"


def _gateway_key(order: Order, intent_ref: str, amount_q: int, attempt_key: str) -> str:
    """Uma chave por tentativa, menos depois da tentativa SEM resposta com o mesmo valor."""
    previous = (
        order.events.filter(type=EVENT_TYPE, payload__intent_ref=intent_ref)
        .order_by("-seq").values_list("payload", flat=True).first()
    )
    if (
        isinstance(previous, dict)
        and previous.get("outcome") == refund_retry.OUTCOME_UNCONFIRMED
        and previous.get("gateway_key")
        and previous.get("amount_q") == amount_q
    ):
        return str(previous["gateway_key"])
    return fresh_gateway_key(order.ref, intent_ref, attempt_key)


def parse_amount_q(raw) -> int | None:
    """``amount_q`` do corpo: inteiro em centavos, ou ``None`` (o disponível inteiro)."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise OrderRefundRefused(AMOUNT_REQUIRED)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise OrderRefundRefused(AMOUNT_REQUIRED) from exc
    if value <= 0 or str(value) != str(raw).strip():
        raise OrderRefundRefused(AMOUNT_REQUIRED)
    return value


def refund(order: Order, *, actor: str, amount_q: int | None, attempt_key: str, expected_revision: str) -> dict:
    """Pede ao gateway o estorno de ``amount_q`` (ou do disponível) da cobrança do pedido.

    Devolve ``{outcome, amount_q, refunded_q, available_q, message}``, todos da
    cobrança deste pedido. ``outcome`` é ``refunded`` quando o gateway confirmou;
    senão ``refused``, ``unconfirmed`` ou ``unrecorded`` (os de ``refund_retry``), e
    ``message`` é a frase do balcão. Levanta :class:`OrderRefundStale` (a tela leu
    outra cobrança) e :class:`OrderRefundRefused` (nada a estornar daqui, ou o valor
    não cabe).
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment_svc.lock_order_payment(locked)
        current = plan(locked)
        if revision(locked, current) != expected_revision:
            raise OrderRefundStale(STALE_MESSAGE)
        if current is None:
            raise OrderRefundRefused("Este pedido não tem cobrança pelo meio de pagamento para estornar daqui.")
        if current.block_reason:
            raise OrderRefundRefused(current.block_reason)
        asked_q = current.available_q if amount_q is None else amount_q
        if asked_q > current.available_q:
            raise OrderRefundRefused(f"Valor acima do disponível ({_money(current.available_q)}).")

        gateway_key = _gateway_key(locked, current.intent_ref, asked_q, attempt_key)
        result = payment_svc.refund_intent_at_gateway(
            current.intent_ref, amount_q=asked_q, idempotency_key=gateway_key, actor=actor, origin="Gestor",
        )
        error_code = "" if result.success else str(result.error_code or "refused")
        outcome = (
            refund_retry.OUTCOME_REFUNDED if result.success
            else refund_retry._OUTCOME_BY_ERROR.get(error_code, refund_retry.OUTCOME_REFUSED)
        )
        message = gateway_message = ""
        if not result.success:
            message = refund_retry.counter_message(outcome, error_code, current.method)
            gateway_message = str(result.message or "")
            logger.warning(
                "order_refund order=%s intent=%s outcome=%s code=%s gateway_said=%s",
                locked.ref, current.intent_ref, outcome, error_code, gateway_message,
            )
        locked.emit_event(
            EVENT_TYPE,
            actor=actor,
            payload={
                "intent_ref": current.intent_ref,
                "method": current.method,
                "amount_q": asked_q,
                "outcome": outcome,
                "error_code": error_code,
                "message": message,
                "gateway_message": gateway_message,
                "gateway_key": gateway_key,
            },
        )
        refunded_q = 0
        if result.success:
            refunded_q = int(result.amount_q or asked_q)
            locked.emit_event(
                "payment.refunded",
                actor=actor,
                payload={"method": current.method, "amount_q": refunded_q, "intent_ref": current.intent_ref},
            )
    logger.info(
        "order_refund order=%s actor=%s intent=%s amount_q=%s refunded_q=%s outcome=%s",
        order.ref, actor, current.intent_ref, asked_q, refunded_q, outcome,
    )
    return {
        "outcome": outcome,
        "amount_q": asked_q,
        "refunded_q": refunded_q,
        "available_q": max(current.available_q - refunded_q, 0),
        "message": message,
    }
