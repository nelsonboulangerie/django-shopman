"""Decide se um pedido pode nascer com a forma de pagamento que traz.

Pedido sem forma de pagamento não existe (decisão do dono, 06/11/2026, GES-03).
A forma mora em ``Session.data["payment"]`` / ``Order.data["payment"]``
(``docs/reference/data-schemas.md``). A única forma "sem receber agora" é **em
conta**, e só para o cliente identificado que tem a conta na casa
(``Customer.metadata.house_account``, lida por ``services.house_account``).
"""

from __future__ import annotations

from typing import Any

from shopman.shop.rules import BaseRule

#: As formas de pagamento que um pedido pode ter. ``mixed`` só com linhas
#: (``tenders``) que digam cada forma.
PAYMENT_METHODS = frozenset(
    {"cash", "pix", "card", "credit", "debit", "link", "external", "account", "mixed"}
)

MISSING_MESSAGE = "Escolha a forma de pagamento antes de fechar o pedido."


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
