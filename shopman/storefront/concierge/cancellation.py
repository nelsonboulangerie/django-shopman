"""Cancelamento pela Concierge, conforme a etapa (dono, 03/10/2026).

"Depende da etapa: se nada foi feito ainda, ela poderia confirmar sim. E isso
deve ser transparente para todos: algo como 'Concierge cancelou conforme
solicitado pelo cliente'."

A regra é a do site, não uma nova:

- **Quando**: exatamente quando o próprio cliente poderia cancelar pela conta
  (``customer_orders.can_cancel``: pedido em ``new``/``accepted`` e pagamento
  comprovadamente não capturado). Fora disso, a regra R4 manda para a equipe.
- **Como**: pelo mesmo serviço (``customer_orders.cancel``), com o ator
  ``concierge``. Estorno, liberação de estoque, nota e o aviso de cancelamento
  seguem o lifecycle de qualquer cancelamento.
- **De quem**: só pedido do próprio cliente, achado pela identidade da conversa
  (``customer_identity_filter``), nunca pelo número que alguém digitou.
- **Com confirmação**: antes de cancelar, uma pergunta de uma linha ("Cancelo o
  pedido X, com 2 croissants? Responda sim ou não."), guardada em
  ``Conversation.flags["pending_cancel"]``; só o "sim" do turno seguinte cancela.
- **Transparente**: o histórico do pedido ganha o evento ``concierge_cancelled``
  ("Cancelado pela Concierge a pedido do cliente", com a mensagem dele), e a
  conversa ganha uma nota para quem a lê no Admin.
- **Verdade sobre o dinheiro** (R6): a resposta diz o que o sistema de fato fez
  com o pagamento, lido depois do cancelamento.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

PENDING_FLAG = "pending_cancel"
#: A pergunta vale por este tempo; depois, o "sim" não cancela nada.
PENDING_TTL = timedelta(minutes=30)
#: O ator gravado no pedido (``cancelled_by``, eventos).
ACTOR = "concierge"

CONFIRM_COPY_KEY = "CONCIERGE_CANCEL_CONFIRM"
DONE_COPY_KEY = "CONCIERGE_CANCEL_DONE"
KEPT_COPY_KEY = "CONCIERGE_CANCEL_KEPT"

_YES = {"sim", "s", "pode", "pode cancelar", "sim pode", "sim, pode", "sim, cancela", "sim cancela",
        "cancela", "pode sim", "confirmo", "isso", "sim por favor", "sim, por favor"}
_NO = {"nao", "n", "nao cancela", "nao precisa", "deixa", "deixa assim", "nao, deixa", "melhor nao",
       "esquece", "nao obrigado", "nao, obrigado", "nao obrigada", "nao, obrigada"}
#: Um ref de pedido citado na fala: inteiro ("NB-261003-M63") ou só o código do fim ("M63").
_ORDER_REF = re.compile(r"\b[a-z]{2,12}-\d{6}-[a-z0-9]{2,8}\b", re.I)
_ORDER_CODE = re.compile(r"\b[a-z]\d{2,3}\b", re.I)


@dataclass(frozen=True)
class Outcome:
    #: ``asked`` · ``cancelled`` · ``kept`` · ``refused`` (não dá mais: equipe)
    code: str
    text: str = ""
    order_ref: str = ""


def _fold(text: str) -> str:
    from .house_rules import fold

    return " ".join(fold(text).replace("!", " ").replace(".", " ").split())


def _copy(key: str, **values) -> str:
    from .service import copy_message

    text = copy_message(key)
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text.strip()


def asks_to_cancel(text: str) -> bool:
    from .handoff import classify_handoff_request

    return classify_handoff_request(text) == "order_cancel"


# ── O pedido ──────────────────────────────────────────────────────────


def _own_open_orders(conversation):
    """Os pedidos em andamento DESTE cliente, pela identidade da conversa."""
    from shopman.orderman.models import Order

    from shopman.shop.services.customer_orders import customer_identity_filter

    identity = customer_identity_filter(
        customer_ref=conversation.customer_ref or None, phone=conversation.phone or None
    )
    if identity is None:
        return Order.objects.none()
    return (
        Order.objects.filter(identity)
        .exclude(status__in=Order.TERMINAL_STATUSES)
        .distinct()
        .order_by("-created_at")
    )


def target_order(conversation, text: str = "", *, order_ref: str = ""):
    """O pedido que o cliente quer cancelar, se for um só e for dele; senão ``None``."""
    orders = list(_own_open_orders(conversation)[:10])
    if order_ref:
        orders = [order for order in orders if order.ref == order_ref]
    else:
        refs = {ref.upper() for ref in _ORDER_REF.findall(text or "")}
        codes = {code.upper() for code in _ORDER_CODE.findall(text or "")}
        if refs or codes:
            # Citou um número: só vale se for de um pedido dele. Número de outra
            # pessoa não acha nada aqui, e a conversa vai para a equipe (R4).
            orders = [
                order for order in orders
                if order.ref.upper() in refs or order.ref.upper().rsplit("-", 1)[-1] in codes
            ]
    if len(orders) != 1:
        return None
    return orders[0]


def self_cancellable(conversation, text: str = "", *, order_ref: str = ""):
    """O pedido que a Concierge pode cancelar sozinha, pela régua do site; senão ``None``."""
    if not getattr(conversation, "_commercial_authority", False):
        return None
    order = target_order(conversation, text, order_ref=order_ref)
    if order is None:
        return None
    from shopman.shop.services import customer_orders, ifood_cancellation

    try:
        from shopman.storefront.services.orders import resolve_timeouts_if_due

        resolve_timeouts_if_due(order)
        order.refresh_from_db()
    except Exception:
        logger.warning("concierge.cancel: timeout resolution failed order=%s", order.ref, exc_info=True)
        return None
    if ifood_cancellation.requires_remote_decision(order) or not customer_orders.can_cancel(order):
        return None
    return order


def _items_summary(order) -> str:
    parts = []
    for item in order.items.all()[:4]:
        qty = Decimal(str(item.qty))
        qty_text = str(int(qty)) if qty == qty.to_integral_value() else str(qty.normalize()).replace(".", ",")
        parts.append(f"{qty_text} {item.name or item.sku}")
    if order.items.count() > 4:
        parts.append("e mais itens")
    return ", ".join(parts)


# ── A conversa ────────────────────────────────────────────────────────


def pending(conversation) -> dict | None:
    value = (conversation.flags or {}).get(PENDING_FLAG)
    return value if isinstance(value, dict) and value.get("order_ref") else None


def _set_pending(conversation, value: dict | None) -> None:
    flags = dict(conversation.flags or {})
    if value is None:
        flags.pop(PENDING_FLAG, None)
    else:
        flags[PENDING_FLAG] = value
    conversation.flags = flags
    conversation.save(update_fields=["flags", "updated_at"])


def ask(conversation, order, customer_text: str) -> Outcome:
    """A pergunta de uma linha antes de cancelar."""
    _set_pending(
        conversation,
        {
            "order_ref": order.ref,
            "asked_at": timezone.now().isoformat(),
            # A fala do cliente vai para o histórico do pedido se ele disser "sim".
            "request": " ".join(str(customer_text or "").split())[:300],
        },
    )
    return Outcome("asked", _copy(CONFIRM_COPY_KEY, order_ref=order.ref, items=_items_summary(order)), order.ref)


def answer_kind(text: str) -> str:
    """``yes``, ``no`` ou ``""`` (outra coisa)."""
    folded = _fold(text)
    if folded in _YES:
        return "yes"
    if folded in _NO:
        return "no"
    return ""


def is_pending_answer(conversation, text: str) -> bool:
    """A fala responde à pergunta de cancelamento ainda válida."""
    state = pending(conversation)
    return bool(state and not _expired(state) and answer_kind(text))


def _expired(state: dict) -> bool:
    asked_at = parse_datetime(str(state.get("asked_at") or ""))
    return asked_at is None or timezone.now() - asked_at > PENDING_TTL


def resolve_pending(conversation, customer_text: str) -> Outcome | None:
    """A resposta à pergunta pendente; ``None`` quando a fala é outra coisa.

    Qualquer outra fala desfaz a pergunta: um "sim" de daqui a pouco, sobre outro
    assunto, nunca cancela pedido.
    """
    state = pending(conversation)
    if state is None:
        return None
    kind = answer_kind(customer_text)
    if _expired(state) or not kind:
        _set_pending(conversation, None)
        return None
    _set_pending(conversation, None)
    if kind == "no":
        return Outcome("kept", _copy(KEPT_COPY_KEY, order_ref=state["order_ref"]), state["order_ref"])
    return _execute(conversation, state)


def _execute(conversation, state: dict) -> Outcome:
    from shopman.shop.models import ConversationMessage
    from shopman.shop.services import customer_orders
    from shopman.shop.services import payment as payment_service

    from .service import assert_turn_authority

    assert_turn_authority(conversation, for_mutation=True)
    order = self_cancellable(conversation, order_ref=state["order_ref"])
    if order is None:
        # Mudou de etapa entre a pergunta e o "sim" (aceito e em preparo, pago):
        # agora é com a equipe (R4).
        return Outcome("refused", order_ref=state["order_ref"])

    had_intent = bool(((order.data or {}).get("payment") or {}).get("intent_ref"))
    status_before = (payment_service.get_payment_status(order) or "").lower()
    captured_before = int(payment_service.captured_balance_q(order) or 0)

    request = str(state.get("request") or "").strip()
    note = "Cancelado pela Concierge a pedido do cliente"
    # O cancelamento e o registro dele são um gesto só: sem o registro, não cancela.
    # O lifecycle (estorno, estoque, nota, aviso) roda no commit deste bloco.
    with transaction.atomic():
        if not customer_orders.cancel(order, actor=ACTOR):
            return Outcome("refused", order_ref=order.ref)
        order.emit_event(
            event_type="concierge_cancelled",
            actor=ACTOR,
            payload={
                "note": f"{note}: \"{request}\"" if request else note,
                "conversation_id": conversation.pk,
            },
        )
        ConversationMessage.objects.create(
            conversation=conversation,
            role=ConversationMessage.Role.ASSISTANT,
            kind=ConversationMessage.Kind.NOTE,
            text=f"{note} (pedido {order.ref}).",
            envelope={"version": 3, "order_ref": order.ref, "turn_fence": conversation.turn_fence},
        )
    order.refresh_from_db()
    payment_line = _payment_line(
        order,
        had_intent=had_intent,
        status_before=status_before,
        captured_before=captured_before,
        status_after=(payment_service.get_payment_status(order) or "").lower(),
    )
    text = _copy(DONE_COPY_KEY, order_ref=order.ref)
    if payment_line:
        text = f"{text} {payment_line}"
    return Outcome("cancelled", text, order.ref)


def _payment_line(order, *, had_intent: bool, status_before: str, captured_before: int, status_after: str) -> str:
    """O que aconteceu com o pagamento, lido do sistema (R6: só o que foi feito)."""
    from shopman.utils.monetary import format_money

    if captured_before > 0:
        amount = f"R$ {format_money(captured_before)}"
        if status_after == "refunded":
            return f"O valor pago, {amount}, foi estornado pelo mesmo meio de pagamento."
        return f"O estorno do valor pago, {amount}, foi pedido ao meio de pagamento."
    if not had_intent:
        return ""
    method = str(((order.data or {}).get("payment") or {}).get("method") or "")
    if method == "card" and status_before == "authorized" and status_after == "cancelled":
        return "A reserva no cartão foi desfeita, e nada foi cobrado."
    if status_after == "cancelled":
        return "O pagamento pendente foi cancelado, e nada foi cobrado."
    return "Nada foi cobrado."
