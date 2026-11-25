"""Decide se um pedido pode nascer com a forma de pagamento que traz.

Pedido sem forma de pagamento não existe (decisão do dono, 06/11/2026, GES-03).
A forma mora em ``Session.data["payment"]`` / ``Order.data["payment"]``
(``docs/reference/data-schemas.md``). A única forma "sem receber agora" é **em
conta**, e só para o cliente identificado que tem a conta na casa
(``Customer.metadata.house_account``, lida por ``services.house_account``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shopman.shop.rules import BaseRule

#: As formas de pagamento que um pedido pode ter. ``mixed`` só com linhas
#: (``tenders``) que digam cada forma.
PAYMENT_METHODS = frozenset(
    {"cash", "pix", "card", "credit", "debit", "link", "external", "account", "mixed"}
)

MISSING_MESSAGE = "Escolha a forma de pagamento antes de fechar o pedido."


def conversation_payment_methods(channel_ref: str) -> list[str]:
    """As formas de pagamento que a conversa oferece: as do canal, sem dinheiro (D-003).

    D-003: dinheiro não entra no fluxo remoto; troco e dinheiro vivo moram na
    encomenda anotada pelo operador. Régua ÚNICA das portas da conversa: o
    orçamento e o pedido da Concierge (``concierge.tools``), o ``requirements``
    e as condições dos termos (``conversational.commerce_read``) e o fechamento
    de hoje (``concierge.order_closing``) leem as opções daqui.
    """
    from shopman.shop.config import ChannelConfig

    return [m for m in ChannelConfig.for_channel(channel_ref).payment.available_methods if m != "cash"]


def sole_payment_method(offered: Sequence[str]) -> str:
    """A forma que vale quando o cliente não escolheu: a única oferecida, ou nenhuma (``""``).

    Régua ÚNICA de "assumir a única forma": o orçamento da Concierge
    (``concierge.tools.review_order``) e as condições dos termos da conversa
    (``conversational.commerce_read._fulfillment_conditions``) decidem por ela.
    Cada porta passa a lista que ela oferece; com mais de uma, ou nenhuma, nada
    se assume e quem chama pergunta.
    """
    return offered[0] if len(offered) == 1 else ""


def payment_refusal(data: dict | None) -> tuple[str, str] | None:
    """``(código, frase)`` quando o pedido não pode nascer assim; ``None`` quando pode.

    ``payment_method_missing``: sem forma, forma desconhecida, ou mista sem
    linhas. ``house_account_not_allowed``: em conta (inteira ou numa linha da
    mista) para quem não tem a conta na casa.
    """
    data = data if isinstance(data, dict) else {}
    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    method = str(payment.get("method") or "").strip().lower()
    tenders = [t for t in (payment.get("tenders") or []) if isinstance(t, dict)]
    tender_methods = {str(t.get("method") or "").strip().lower() for t in tenders}

    if method not in PAYMENT_METHODS or (method == "mixed" and (not tenders or "" in tender_methods)):
        return "payment_method_missing", MISSING_MESSAGE
    if method == "account" or "account" in tender_methods:
        from shopman.shop.services import house_account

        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        customer_ref = str(customer.get("ref") or data.get("customer_ref") or "").strip()
        try:
            house_account.require_eligible(customer_ref)
        except house_account.HouseAccountError as exc:
            return "house_account_not_allowed", str(exc)
    return None


class PaymentMethodRule(BaseRule):
    """O porteiro do commit: recusa o pedido que ``payment_refusal`` recusa.

    Antes desta regra, um pedido podia nascer sem ``payment.method`` e o Gestor
    o mostrava como "Pagamento não informado": a sacola saía sem ninguém saber
    se era para cobrar. A forma mora em ``Session.data["payment"]`` (o
    ``CommitService`` a copia para o pedido), e toda porta que fecha pedido pelo
    commit passa por aqui: loja, PDV, Concierge do WhatsApp. O PDV já recusa o
    "em conta" antes (``pos._require_house_account_if_on_account``).

    Registrado sempre (``handlers._register_validators``), fora do
    ``RuleConfig``: não é política que o Admin desliga.
    """

    code = "shop.payment_method"
    label = "Forma de pagamento"
    rule_type = "validator"
    stage = "commit"
    default_params = {}

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.orderman.exceptions import ValidationError as OrderValidationError

        refused = payment_refusal(getattr(session, "data", None))
        if refused is None:
            return
        code, message = refused
        raise OrderValidationError(code=code, message=message, context={"field": "payment_method"})


def awaits_online_payment(order, *, payment_reads=None, channel_config=None) -> bool:
    """O pedido novo só espera o dinheiro online (Pix ou cartão que não caiu)?

    É a mesma régua do aceite (``lifecycle.ensure_payment_captured``): quem paga
    na entrega ou na loja, o PDV e o iFood nunca esperam aqui, e o cartão já
    autorizado também não. Lê, não grava. Usado para tirar da contagem do
    "para aceitar" o que ninguém consegue aceitar ainda (DEV-2026-091).
    """
    from shopman.orderman.exceptions import InvalidTransition

    from shopman.shop.lifecycle import ensure_payment_captured

    if str(getattr(order, "status", "")) != "new":
        return False
    try:
        ensure_payment_captured(order, payment_reads=payment_reads, channel_config=channel_config)
    except InvalidTransition as exc:
        return exc.code == "payment_not_captured"
    return False
