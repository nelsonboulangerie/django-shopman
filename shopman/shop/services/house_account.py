"""Conta do cliente: quem pode comprar "em conta", quanto deve, e o acerto (WP-10 do CASHMAN-PLAN).

O fenômeno: alguns clientes antigos acertam por período (semanal, mensal). Não
se divulga; é por cliente, desligado por padrão, e só o Admin liga.

Três perguntas, três donos, sem tabela de saldo:

- **Elegibilidade** é do cliente (guestman): ``Customer.metadata.house_account``
  (bool), escrito pelo Admin. Este módulo só lê.
- **Limite** (opcional) também é do cliente: ``Customer.metadata.house_account_limit_q``
  (centavos), escrito pelo Admin. Ausente = sem limite, e nada muda. Com limite,
  a venda em conta que levaria o saldo acima dele não é recusada: pede o PIN do
  gerente no PDV (``over_limit`` diz quanto passa; quem cobra é o ``pos``).
- **Quanto deve** é do Payman: Σ dos intents ``account`` autorizados e não
  capturados do cliente (``PaymentService.account_balance_q``). Derivado.
- **O acerto** é deste orquestrador: captura os intents mais antigos até o
  valor (FIFO, intents inteiros; o resto fica autorizado) e, quando o cliente
  pagou em dinheiro, grava ``account_settled`` no turno de quem recebeu, uma
  linha por intent (``order_ref`` + ``payment_ref``), na MESMA transação: o
  dinheiro consta nos dois livros ou em nenhum.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction

logger = logging.getLogger(__name__)

#: Com que o cliente pode acertar a conta. Dinheiro entra na gaveta (livro);
#: pix/cartão/external são atestados no balcão (o intent ``account`` não tem
#: gateway; o método fica em ``gateway_data.settled_with``).
SETTLE_METHODS = ("cash", "pix", "credit", "debit", "external")


class HouseAccountError(ValueError):
    """Recusa legível do acerto/elegibilidade (a API traduz para 400)."""


def is_eligible(customer_ref: str | None) -> bool:
    """O cliente pode comprar em conta? Só com ``Customer.metadata.house_account`` verdadeiro."""
    ref = str(customer_ref or "").strip()
    if not ref:
        return False
    try:
        from shopman.guestman.models import Customer
    except ImportError:
        return False
    customer = Customer.objects.filter(ref=ref).only("metadata").first()
    if customer is None:
        return False
    return bool((customer.metadata or {}).get("house_account"))


def require_eligible(customer_ref: str | None) -> None:
    if not str(customer_ref or "").strip():
        raise HouseAccountError("Venda em conta exige o cliente identificado.")
    if not is_eligible(customer_ref):
        raise HouseAccountError("Este cliente não tem conta na casa.")


def limit_q(customer_ref: str | None) -> int | None:
    """O limite da conta do cliente, em centavos, ou ``None`` (sem limite).

    Só vale o inteiro positivo de ``Customer.metadata.house_account_limit_q``;
    qualquer outra coisa é "sem limite", que é o comportamento de antes.
    """
    ref = str(customer_ref or "").strip()
    if not ref:
        return None
    try:
        from shopman.guestman.models import Customer
    except ImportError:
        return None
    customer = Customer.objects.filter(ref=ref).only("metadata").first()
    if customer is None:
        return None
    raw = (customer.metadata or {}).get("house_account_limit_q")
    if isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@dataclass(frozen=True)
class AccountLimitExcess:
    """A venda em conta passaria do limite: os números que a tela mostra ao gerente."""

    customer_ref: str
    balance_q: int  # o saldo devedor HOJE, antes desta venda
    limit_q: int
    charge_q: int  # o que esta venda põe na conta
    over_q: int  # quanto o saldo passaria do limite

    def as_dict(self) -> dict:
        return {
            "balance_q": self.balance_q,
            "limit_q": self.limit_q,
            "charge_q": self.charge_q,
            "over_q": self.over_q,
        }


def over_limit(customer_ref: str | None, charge_q: int) -> AccountLimitExcess | None:
    """Esta venda em conta levaria o saldo acima do limite? ``None`` quando não.

    Sem limite definido, ou sem nada indo para a conta, a resposta é ``None``:
    o limite é opcional e, ausente, nada muda. Exatamente no limite ainda cabe.
    """
    ref = str(customer_ref or "").strip()
    charge_q = int(charge_q or 0)
    if not ref or charge_q <= 0:
        return None
    limit = limit_q(ref)
    if limit is None:
        return None
    balance = balance_q(ref)
    over = balance + charge_q - limit
    if over <= 0:
        return None
    return AccountLimitExcess(customer_ref=ref, balance_q=balance, limit_q=limit, charge_q=charge_q, over_q=over)


def balance_q(customer_ref: str) -> int:
    from shopman.payman import PaymentService

    return PaymentService.account_balance_q(customer_ref)


@dataclass(frozen=True)
class AccountBalance:
    customer_ref: str
    customer_name: str
    balance_q: int
    intents: int
    oldest_at: str  # ISO; "" quando não há


def balances() -> list[AccountBalance]:
    """Todos os clientes com saldo em aberto, com nome resolvido no guestman."""
    from shopman.payman import PaymentService

    rows = PaymentService.account_balances()
    names: dict[str, str] = {}
    if rows:
        try:
            from shopman.guestman.models import Customer

            refs = [row["customer_ref"] for row in rows if row["customer_ref"]]
            names = {c.ref: c.name for c in Customer.objects.filter(ref__in=refs).only("ref", "first_name", "last_name")}
        except ImportError:
            names = {}
    return [
        AccountBalance(
            customer_ref=row["customer_ref"],
            customer_name=str(names.get(row["customer_ref"]) or row["customer_ref"]),
            balance_q=row["balance_q"],
            intents=row["intents"],
            oldest_at=row["oldest_at"].isoformat() if row.get("oldest_at") else "",
        )
        for row in rows
    ]


@dataclass(frozen=True)
class AccountSettlement:
    customer_ref: str
    method: str
    settled_q: int
    intent_refs: tuple[str, ...]
    remaining_q: int


def settle_account(
    customer_ref: str,
    amount_q: int,
    method: str,
    *,
    shift=None,
    actor,
) -> AccountSettlement:
    """O cliente acertou (parte d)a conta: captura FIFO e, em dinheiro, a gaveta recebe.

    ``amount_q`` é o que o cliente trouxe; capturam-se os intents mais antigos
    inteiros até esse valor (parcial = intents inteiros; o que não couber fica
    autorizado). Em dinheiro, ``shift`` é o turno ABERTO de quem recebeu e cada
    intent capturado vira uma linha ``account_settled`` (``order_ref``,
    ``payment_ref``) no livro, na mesma transação. Sem segunda assinatura:
    entrada não exige PIN (suprimento também não).
    """
    from shopman.cashman import services as cash_ledger
    from shopman.payman import PaymentService

    ref = str(customer_ref or "").strip()
    if not ref:
        raise HouseAccountError("Informe o cliente.")
    method = str(method or "").strip().lower()
    if method not in SETTLE_METHODS:
        raise HouseAccountError("Método de acerto inválido.")
    amount_q = int(amount_q or 0)
    if amount_q <= 0:
        raise HouseAccountError("Informe o valor recebido.")
    if method == "cash" and (shift is None or not getattr(shift, "is_open", False)):
        raise HouseAccountError("Abra um turno de caixa para receber o acerto em dinheiro.")

    actor_name = actor.get_username() if hasattr(actor, "get_username") else str(actor or "")
    with transaction.atomic():
        open_intents = list(PaymentService.account_open_intents(ref).select_for_update())
        if not open_intents:
            raise HouseAccountError("Este cliente não tem saldo em aberto.")
        remaining_q = amount_q
        captured: list = []
        for intent in open_intents:
            if intent.amount_q > remaining_q:
                break
            PaymentService.capture(
                intent.ref,
                gateway_data={"settled_with": method, "settled_by": actor_name},
            )
            captured.append(intent)
            remaining_q -= intent.amount_q
        if not captured:
            raise HouseAccountError(
                "O valor não cobre nem a venda mais antiga em aberto; o acerto é por venda inteira."
            )
        if method == "cash":
            for intent in captured:
                cash_ledger.record(
                    "account_settled",
                    shift=shift,
                    operator=actor if hasattr(actor, "get_username") else shift.opened_by,
                    amount_q=intent.amount_q,
                    order_ref=intent.order_ref,
                    payment_ref=intent.ref,
                    payload={"customer_ref": ref, "settled_by": actor_name},
                )
    settled_q = sum(i.amount_q for i in captured)
    logger.info(
        "house_account.settled customer=%s method=%s settled_q=%s intents=%s",
        ref, method, settled_q, [i.ref for i in captured],
    )
    return AccountSettlement(
        customer_ref=ref,
        method=method,
        settled_q=settled_q,
        intent_refs=tuple(i.ref for i in captured),
        remaining_q=PaymentService.account_balance_q(ref),
    )
