"""A prévia do "Não retirado" no Gestor (WP-G11): o que volta à venda, o que se perde e o dinheiro.

Leitura pura. Quem grava é ``no_show.mark_not_picked_up`` (``shop/services/no_show``),
pela rota ``POST orders/<ref>/no-show/``; esta prévia responde, ANTES do gesto, as
perguntas do Gerente: o pedido já pode ser encerrado? o que acontece com cada linha?
quanto volta ao cliente, por onde, e quanto fica com a loja? o que o cliente vai ler?
A mesma régua decide a prévia e o comando: a tela nunca adivinha o que o servidor vai
recusar, e nesta versão não escolhe o destino de linha nenhuma.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.shop.services import no_show

ACTION_REF = "no-show"
PERMISSION_REASON = "Identifique uma pessoa com permissão para gerenciar pedidos."

_DESTINY_LABELS = {no_show.RESTOCK: "Volta à venda", no_show.LOSS: "Perda"}
_LOSS_REASON_LABELS = {
    no_show.WHY_MADE_TO_ORDER: "Feito na hora: não volta à venda.",
    no_show.WHY_NO_STOCK: "Sem estoque baixado: não há o que devolver ao balcão.",
    no_show.WHY_LOT_EXPIRED: "O lote já venceu.",
}


@dataclass(frozen=True)
class NoShowLineProjection:
    line_id: str
    sku: str
    name: str
    #: Quanto o pedido levou (texto decimal).
    qty: str
    #: ``restock`` (volta à venda, o cliente recebe o valor) ou ``loss`` (perda, a loja fica com o valor).
    destiny: str
    destiny_label: str
    #: Por que é perda (``made_to_order`` · ``no_stock`` · ``lot_expired``); vazio na linha que volta.
    reason: str
    reason_label: str
    #: O valor da linha: o preço pago por unidade (com o desconto rateado) vezes a quantidade.
    value_q: int
    value_display: str


def _money(value_q: int) -> str:
    return f"R$ {format_money(value_q)}"


def _authorized(user) -> bool:
    return bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))


def _action(order: Order, user, *, label: str, priority: str, reason: str, revision: str):
    from shopman.shop.projections.types import Action

    return Action(
        ref=ACTION_REF, kind="mutation", label=label, priority=priority,
        enabled=not reason, reason=reason, method="POST", idempotency="required",
        payload_schema={"base_revision": revision, "expected_actor_id": getattr(user, "pk", None)},
        confirmation={"required": True, "manager_approval": True},
    )


def detail_action(order: Order, user=None, *, now: datetime | None = None):
    """A ação "Não retirado" do detalhe do pedido, ou ``None`` quando o gesto não existe.

    Só é oferecida a pedido pronto, de retirada, fora do iFood e do balcão. Antes da
    hora (ou sem permissão) ela aparece desabilitada, com o motivo: quem está no
    balcão vê que o gesto existe e a partir de quando.
    """
    if not no_show.is_candidate(order):
        return None
    preview = no_show.preview(order, now=now)
    reason = preview["block_reason"] or ("" if _authorized(user) else PERMISSION_REASON)
    return _action(order, user, label="Não retirado", priority="menu", reason=reason, revision=preview["revision"])


def build_order_no_show(order: Order, *, user=None, now: datetime | None = None) -> dict:
    """A prévia inteira, pronta para o diálogo de "Não retirado"."""
    from shopman.backstage.projections.pos import _manager_cards

    preview = no_show.preview(order, now=now)
    reason = preview["block_reason"] or ("" if _authorized(user) else PERMISSION_REASON)
    lines = [
        NoShowLineProjection(
            line_id=line["line_id"],
            sku=line["sku"],
            name=line["name"],
            qty=line["qty"],
            destiny=line["destiny"],
            destiny_label=_DESTINY_LABELS[line["destiny"]],
            reason=line["reason"],
            reason_label=_LOSS_REASON_LABELS.get(line["reason"], ""),
            value_q=line["value_q"],
            value_display=_money(line["value_q"]),
        )
        for line in preview["lines"]
    ]
    action = _action(
        order, user, label="Encerrar como não retirado", priority="danger",
        reason=reason, revision=preview["revision"],
    )
    return {
        "ref": order.ref,
        "allowed": not reason,
        "block_reason": reason,
        "releases_at": preview["releases_at"],
        "lines": [asdict(line) for line in lines],
        "paid_q": preview["paid_q"],
        "paid_display": _money(preview["paid_q"]),
        "refund_q": preview["refund_q"],
        "refund_display": _money(preview["refund_q"]),
        "retained_q": preview["retained_q"],
        "retained_display": _money(preview["retained_q"]),
        "money_sentence": preview["money_sentence"],
        "customer_text": preview["customer_text"],
        "managers": list(_manager_cards(user)),
        "action": asdict(action),
    }


__all__ = ["ACTION_REF", "build_order_no_show", "detail_action"]
