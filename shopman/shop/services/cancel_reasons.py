"""Os motivos de cancelar um pedido: a lista única, com o texto que o cliente lê.

Cada motivo tem uma chave estável em inglês (gravada em
``order.data["cancellation_reason_key"]``), o rótulo que o operador escolhe e o
texto revisado que o cliente lê na notificação ``order_cancelled`` e na página do
pedido. O texto livre do operador NÃO vai ao cliente: é a observação interna
(``order.data["cancellation_internal_note"]``).

A lista mora aqui e só aqui. As telas (Gestor, PDV) a recebem pela projeção do
pedido (``cancel_reasons``), nunca a duplicam.

Os cancelamentos automáticos (Pix vencido, cliente que cancela sozinho, desfazer
do balcão) gravam um código de máquina em ``cancellation_reason``;
:func:`reason_key_for` traduz esse código numa chave desta lista, para que o
cliente sempre leia um texto revisado e nunca o código.

Texto ao cliente: voz da concierge, frase inteira com ponto final (entra no
``{status_note}`` do template aprovado, entre "foi cancelado." e "Qualquer
dúvida…"), sem travessão, sem culpar o cliente.
"""

from __future__ import annotations

from dataclasses import dataclass

OTHER = "other"


@dataclass(frozen=True)
class CancelReason:
    key: str
    label: str
    customer_text: str


OPERATOR_CANCEL_REASONS: tuple[CancelReason, ...] = (
    CancelReason(
        key="out_of_stock",
        label="Acabou um item",
        customer_text="Um dos itens acabou e não conseguimos preparar o pedido completo.",
    ),
    CancelReason(
        key="cannot_deliver",
        label="Não dá para entregar",
        customer_text="Não conseguimos fazer a entrega no endereço e no horário do pedido.",
    ),
    CancelReason(
        key="customer_request",
        label="O cliente pediu",
        customer_text="Cancelamos conforme você nos pediu.",
    ),
    CancelReason(
        key="payment_not_confirmed",
        label="Pagamento não confirmado",
        customer_text="Não recebemos a confirmação do pagamento a tempo.",
    ),
    CancelReason(
        key="store_closing",
        label="A loja vai fechar",
        customer_text="Precisamos encerrar o atendimento antes do horário do seu pedido.",
    ),
    CancelReason(
        key=OTHER,
        label="Outro motivo",
        customer_text="Sentimos muito pelo imprevisto.",
    ),
)

#: Motivos que só o sistema grava: não aparecem na lista do operador, mas o
#: cliente lê o texto revisado deles como lê o de qualquer outro.
AUTOMATIC_CANCEL_REASONS: tuple[CancelReason, ...] = (
    # Loja online paga ao pedir (decisão do dono, 14/10/2026): o prazo de aceite
    # venceu sem ninguém aceitar. O dinheiro volta no aviso próprio do estorno.
    CancelReason(
        key="store_did_not_confirm",
        label="A loja não aceitou a tempo",
        customer_text="Não conseguimos confirmar seu pedido dentro do prazo.",
    ),
    # O prazo do pagamento digital venceu sem pagamento (``payment.timeout``). É o
    # ÚNICO aviso que o cliente recebe nesse caso (P1-9, 14/10/2026): diz o que
    # aconteceu com o dinheiro (nada foi cobrado) e o que fazer se ainda quiser.
    # O "nada foi cobrado" é sempre verdade aqui: o handler só cancela depois de o
    # gateway responder "não pago".
    CancelReason(
        key="pix_expired",
        label="O Pix venceu",
        customer_text=(
            "O Pix venceu e nada foi cobrado. "
            "Se ainda quiser, é só fazer um novo pedido."
        ),
    ),
    CancelReason(
        key="payment_deadline_passed",
        label="O prazo do pagamento acabou",
        customer_text=(
            "O prazo para pagar acabou e nada foi cobrado. "
            "Se ainda quiser, é só fazer um novo pedido."
        ),
    ),
)

_BY_KEY = {reason.key: reason for reason in (*OPERATOR_CANCEL_REASONS, *AUTOMATIC_CANCEL_REASONS)}
_OPERATOR_KEYS = frozenset(reason.key for reason in OPERATOR_CANCEL_REASONS)

# Códigos de máquina dos cancelamentos automáticos → chave da lista.
_MACHINE_REASON_KEYS = {
    "payment_timeout": "payment_deadline_passed",
    "pix_timeout": "pix_expired",
    "card_timeout": "payment_deadline_passed",
    "customer_requested": "customer_request",
    "confirmation_timeout": "store_did_not_confirm",
}

MISSING_REASON_MESSAGE = "Escolha o motivo do cancelamento."
UNKNOWN_REASON_MESSAGE = "Escolha um dos motivos da lista."


def cancel_reason(key: str) -> CancelReason | None:
    return _BY_KEY.get(str(key or "").strip())


def validation_message(key: str) -> str:
    """A frase de erro para uma chave inválida, ou vazio quando a chave é da lista."""
    key = str(key or "").strip()
    if not key:
        return MISSING_REASON_MESSAGE
    if key not in _OPERATOR_KEYS:
        return UNKNOWN_REASON_MESSAGE
    return ""


def reason_key_for(machine_reason: str) -> str:
    """A chave da lista para um código de máquina; o que não tem par vira ``other``."""
    return _MACHINE_REASON_KEYS.get(str(machine_reason or "").strip(), OTHER)


def reason_key_of(order_data: dict | None) -> str:
    """A chave do motivo do pedido: a gravada, ou a do código de máquina."""
    data = order_data or {}
    reason = cancel_reason(data.get("cancellation_reason_key"))
    return reason.key if reason else reason_key_for(data.get("cancellation_reason"))


def payment_deadline_reason_key(method: str) -> str:
    """A chave do prazo de pagamento vencido: o Pix tem frase própria."""
    return "pix_expired" if str(method or "").strip().lower() == "pix" else "payment_deadline_passed"


def customer_text(order_data: dict | None) -> str:
    """O texto que o cliente lê sobre o motivo do cancelamento deste pedido."""
    return _BY_KEY[reason_key_of(order_data)].customer_text


__all__ = [
    "AUTOMATIC_CANCEL_REASONS",
    "OPERATOR_CANCEL_REASONS",
    "OTHER",
    "CancelReason",
    "cancel_reason",
    "customer_text",
    "payment_deadline_reason_key",
    "reason_key_for",
    "reason_key_of",
    "validation_message",
]
