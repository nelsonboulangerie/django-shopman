"""
Cancellation service — single entry point for all cancellation paths.

Core: Order.transition_status()
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Order

logger = logging.getLogger(__name__)


def cancel(
    order,
    reason: str,
    actor: str = "system",
    *,
    extra_data: dict | None = None,
) -> bool:
    """
    Cancel an order. Single entry point for all cancellation paths:
    - Customer self-cancel
    - Operator reject / cancel
    - PIX / payment timeout

    Transitions the order to CANCELLED. The lifecycle on_cancelled handler
    releases stock via ``stock.release`` (``order.data[\"hold_ids\"]``).

    Args:
        order: The Order to cancel.
        reason: Reason for cancellation (stored in order.data).
        actor: Who initiated the cancellation.
        extra_data: Optional keys merged into ``order.data`` (e.g. ``rejected_by``).

    Returns:
        True if cancelled, False if order was already in a terminal state.

    SYNC — transitions status immediately.
    """
    # A máquina de estados é a autoridade única: no mapa DEFAULT, completed/
    # cancelled/returned não transicionam para cancelled — mesmo efeito do
    # conjunto fixo que morava aqui. A diferença é o canal que DECLARA
    # completed→cancelled no seu ``lifecycle.transitions`` (o pdv declara: a
    # venda de balcão fecha no commit, e o desfazer da janela precisa passar).
    # Um conjunto cravado por cima do mapa fazia a config do canal mentir.
    if not order.can_transition_to(Order.Status.CANCELLED):
        logger.info(
            "cancellation.cancel: order %s cannot transition from %s to cancelled, skipping",
            order.ref, order.status,
        )
        return False

    # Write cancellation context FIRST — transition_status fires the
    # order_changed signal via on_commit, and lifecycle handlers need
    # cancellation_reason and cancelled_by already in order.data.
    data = dict(order.data or {})
    data["cancellation_reason"] = reason
    data["cancelled_by"] = actor
    if extra_data:
        data.update(extra_data)
    order.data = data
    order.save(update_fields=["data", "updated_at"])

    order.transition_status(Order.Status.CANCELLED, actor=actor)

    logger.info("cancellation.cancel: order %s cancelled by %s — %s", order.ref, actor, reason)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Política de cancelamento do OPERADOR
# ─────────────────────────────────────────────────────────────────────────────
#
# O cliente já tem a dele: ``payment_service.can_cancel`` para em
# ``{new, accepted}`` e recusa quando o pagamento está capturado ou incerto.
# O operador não tinha nenhuma — ia direto na máquina de estados, que responde
# "esta transição é possível para este pedido?" e não sabe nada sobre dinheiro.
#
# São perguntas diferentes, e a separação é deliberada:
#
#   régua  (snapshot.lifecycle.transitions) → é estruturalmente possível?
#   política (aqui)                         → é permitido agora, olhando os
#                                             ciclos de pedido, pagamento e
#                                             fulfillment?
#   autorização (view + RBAC)               → este ator pode?
#
# Sem a do meio, cancelar um pedido PAGO passava batido: ninguém no caminho do
# operador perguntava pelo dinheiro. O PDV já tinha resolvido isso à mão no seu
# próprio endpoint ("cancelar venda fechada é exceção auditada: sempre sob PIN
# de gerente"); aqui a regra deixa de ser local e passa a valer para todo
# caminho de operador.


class OperatorCancelPolicy:
    """O que o operador pode fazer com este pedido, e sob que condição.

    ``allowed`` é a régua e o estado; ``requires_approval`` é o dinheiro. Um
    pedido pago não é *imcancelável* — é cancelável **sob segunda assinatura**,
    que é como a casa já trata exceção que mexe em dinheiro alheio.
    """

    __slots__ = ("allowed", "requires_approval", "reason")

    def __init__(self, *, allowed: bool, requires_approval: bool = False, reason: str = ""):
        self.allowed = allowed
        self.requires_approval = requires_approval
        self.reason = reason

    def __bool__(self) -> bool:
        return self.allowed


# Estados em que cancelar deixou de ser rotina: o pão já está pronto no balcão
# (``ready``) ou a venda já fechou (``completed``). Não são proibidos — são de
# gerente. O que vem depois do despacho não entra aqui de propósito: quando o
# motoboy saiu, o fato é DEVOLUÇÃO (``returned``), não cancelamento, e misturar
# os dois estragaria a leitura do B.I. depois.
ADVANCED_CANCEL_STATUSES = frozenset({"ready", "completed"})


def operator_cancel_policy(order) -> OperatorCancelPolicy:
    """Avalia se o operador pode cancelar ``order``, e sob que condição.

    Não consulta permissão: quem é o ator é pergunta da view. Aqui só se
    responde o que vale para *qualquer* operador diante *deste* pedido.
    """
    from shopman.shop.services import payment_status

    if order.status == Order.Status.CANCELLED:
        return OperatorCancelPolicy(allowed=False, reason="Este pedido já está cancelado.")

    if not order.can_transition_to(Order.Status.CANCELLED):
        return OperatorCancelPolicy(
            allowed=False,
            reason=f"Pedido em {order.get_status_display()} não pode ser cancelado.",
        )

    # Dinheiro capturado não impede — exige assinatura. E "incerto" recebe o
    # mesmo tratamento de propósito: se não dá para afirmar que o pedido NÃO
    # está pago, cancelar sem uma segunda pessoa olhando é o mesmo risco.
    # (Mesma régua do gate do cliente, que recusa `unknown` junto com `paid`.)
    try:
        paid = payment_status.has_sufficient_captured_payment(order)
        uncertain = (payment_status.get_payment_status(order) or "").lower() == "unknown"
    except Exception:
        # Falhar FECHADO: sem conseguir ler o pagamento, trate como se houvesse
        # dinheiro em jogo. O custo é uma assinatura a mais; o custo do inverso
        # é cancelar um pedido pago sem ninguém saber.
        logger.warning("operator_cancel_policy: leitura de pagamento falhou order=%s", order.ref, exc_info=True)
        paid, uncertain = True, True

    if paid or uncertain:
        return OperatorCancelPolicy(
            allowed=True,
            requires_approval=True,
            reason="Pedido pago: cancelar exige aprovação de gerente.",
        )

    return OperatorCancelPolicy(allowed=True)


def is_advanced_cancel(order) -> bool:
    """True quando cancelar este pedido exige a permissão elevada.

    Separado da política porque é pergunta de AUTORIZAÇÃO (quem), e a política
    responde a de POLÍTICA (o quê). A view cruza as duas.
    """
    return order.status in ADVANCED_CANCEL_STATUSES
