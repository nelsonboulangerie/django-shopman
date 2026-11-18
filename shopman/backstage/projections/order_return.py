"""A prévia da devolução no Gestor (WP-G12): o que pode voltar e para onde vai o dinheiro.

Leitura pura. Quem grava é ``ReturnService.initiate_return`` (``shop/handlers/returns``),
pela rota ``POST orders/<ref>/return/``; esta prévia responde, ANTES do gesto, as três
perguntas do Gerente: o pedido aceita devolução? quanto de cada item ainda pode voltar?
para onde o dinheiro volta? A mesma régua decide a prévia e o comando: a tela nunca
adivinha o que o servidor vai recusar.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.shop.handlers.returns import returned_qty_by_line
from shopman.shop.services import order_composition
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.order_edit import DELIVERY_FEE_SKU

#: Os estados em que a devolução existe (a mesma régua de ``initiate_return``).
RETURNABLE_STATUSES = frozenset({Order.Status.DELIVERED, Order.Status.COMPLETED})

#: Os meios que o próprio sistema estorna no gateway, e por onde o dinheiro volta.
_GATEWAY_REFUND_DESTINATION = {"pix": "ao Pix do cliente", "card": "no cartão do cliente", "link": "no cartão do cliente"}


@dataclass(frozen=True)
class ReturnLineProjection:
    line_id: str
    sku: str
    name: str
    #: O que o pedido levou, o que já voltou e o que ainda pode voltar (texto decimal).
    qty: str
    returned_qty: str
    returnable_qty: str
    #: O preço pago por unidade (já com o desconto rateado): é o que volta.
    unit_refund_q: int
    unit_refund_display: str
    #: Vendido por peso: a quantidade é em kg e aceita fração.
    by_weight: bool


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized if normalized != 0 else Decimal("0"), "f")


def return_revision(order: Order) -> str:
    """A base da devolução: o estado, o total e as devoluções já registradas."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    data = order.data or {}
    state = {"status": order.status, "total_q": order.total_q, "returns": data.get("returns") or [], "adjustment": data.get("adjustment")}
    return mutation_fingerprint({"version": 1, "order": order.ref, "field": "return", "state": state})


def return_block_reason(order: Order) -> str:
    """Por que este pedido não aceita devolução agora ("" quando aceita)."""
    if order.channel_ref == "ifood":
        return "Pedido do iFood: a devolução e o reembolso são feitos no portal do iFood."
    if order.status == Order.Status.RETURNED:
        return "Este pedido já foi devolvido."
    if order.status not in RETURNABLE_STATUSES:
        return "A devolução é para pedido entregue ou concluído."
    payment = (order.data or {}).get("payment") or {}
    if payment_svc._pays_on_account(payment):
        return "Venda na conta da casa: a devolução ainda não passa pelo Gestor."
    return ""


def money_destination(order: Order) -> tuple[bool, str]:
    """``(volta_dinheiro, para_onde)``: o fim da frase "R$ 12,00 serão estornados ao Pix do cliente."

    A mesma régua do estorno (``ReturnService.process_refund`` → ``payment.refund``):
    o gateway estorna sozinho; dinheiro e maquininha ficam pendentes no PDV, onde o
    gesto de devolver dinheiro mora (``pending_cash_refunds``, ``pending_card_machine_refunds``).
    """
    from shopman.shop.services.order_edit import CARD_MACHINE_METHODS

    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "")
    captured_q = payment_svc.captured_balance_q(order)
    if captured_q == 0:
        return False, ""
    if method in _GATEWAY_REFUND_DESTINATION:
        return True, f"serão estornados {_GATEWAY_REFUND_DESTINATION[method]}."
    if method == "cash":
        return True, "em dinheiro ficam a devolver no caixa do PDV."
    if method in CARD_MACHINE_METHODS:
        return True, "ficam a estornar na maquininha, pelo PDV."
    return True, "ficam a devolver ao cliente."


def build_order_return(order: Order, *, user=None) -> dict:
    """A prévia inteira, pronta para o diálogo de devolução."""
    from shopman.shop.projections.types import Action

    reason = return_block_reason(order)
    returned = returned_qty_by_line(order)
    lines: list[ReturnLineProjection] = []
    for item in order_composition.effective_items(order):
        meta = item.meta if isinstance(item.meta, dict) else {}
        if meta.get("type") == "delivery_fee" or item.sku == DELIVERY_FEE_SKU:
            continue
        qty = Decimal(str(item.qty))
        already = returned.get(item.line_id, Decimal("0"))
        returnable = max(Decimal("0"), qty - already)
        unit_q = int(item.unit_price_q or 0)
        lines.append(ReturnLineProjection(
            line_id=item.line_id,
            sku=item.sku,
            name=item.name or item.sku,
            qty=_decimal_text(qty),
            returned_qty=_decimal_text(already),
            returnable_qty=_decimal_text(returnable),
            unit_refund_q=unit_q,
            unit_refund_display=f"R$ {format_money(unit_q)}",
            by_weight=bool(meta.get("weighed")) or qty != qty.to_integral_value(),
        ))
    if not reason and not any(Decimal(line.returnable_qty) > 0 for line in lines):
        reason = "Tudo deste pedido já foi devolvido."

    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))
    if not authorized:
        reason = reason or "Identifique uma pessoa com permissão para gerenciar pedidos."
    money_returns, destination = money_destination(order) if not reason else (False, "")
    action = Action(
        ref="return", kind="mutation", label="Registrar devolução", priority="danger",
        enabled=not reason, reason=reason, method="POST", idempotency="required",
        payload_schema={"base_revision": return_revision(order), "expected_actor_id": getattr(user, "pk", None)},
        confirmation={"required": True, "manager_approval": True},
    )
    from shopman.backstage.projections.pos import _manager_cards

    return {
        "ref": order.ref,
        "allowed": not reason,
        "block_reason": reason,
        "lines": [asdict(line) for line in lines],
        "money_returns": money_returns,
        "money_destination": destination,
        "managers": list(_manager_cards(user)),
        "action": asdict(action),
    }


__all__ = ["RETURNABLE_STATUSES", "build_order_return", "money_destination", "return_block_reason", "return_revision"]
