"""Acrescentar item a um pedido já feito, pela Concierge (dono, 03/10/2026).

"Se é possível fazer dentro dos guardrails do sistema, via PDV, por que a
Concierge não poderia fazer?"

A Concierge NÃO oferece: só faz quando o cliente pede (inclusive escolhendo "1"
na pergunta "acrescentar ao pedido aberto ou pedido novo?" da memória). E faz
pelo MESMO serviço do balcão, ``shop.services.order_edit``, com as travas dele:

- a porta: até "em preparo", sem NFC-e autorizada, fora do iFood
  (``order_edit.state_refusal``);
- o preço: o do catálogo no canal do pedido; desconto não é recalculado;
- o dinheiro: a diferença a mais vira saldo a receber (``payment.balance_due_q``),
  e cobrança digital aberta com o valor antigo trava a mudança;
- o estoque: conferido na pergunta e exigido no "sim" (``require_stock``);
- o aviso ``order_updated`` ao cliente, como em toda edição;
- o histórico: o evento ``order_edited`` com ``source = concierge:add``, que o
  Gestor mostra como "Itens acrescentados pela Concierge a pedido do cliente".

Nesta fatia só AUMENTO de itens. Tirar item, trocar recebimento ou data seguem
com a equipe.

Antes de aplicar, uma pergunta de uma linha com os dados do sistema; só o "sim"
aplica (a pergunta pendente mora na memória da conversa, ``dialogue``, com o
mesmo vencimento das outras). Pedido só do próprio cliente, achado pela
identidade da conversa, nunca pelo número que alguém digitou.

Se o serviço recusa, a Concierge diz o motivo verdadeiro e oferece o caminho que
existe: pedido do dia → um pedido novo; encomenda → a equipe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

ACTOR = "concierge"
MAX_QTY = 99

CONFIRM_COPY_KEY = "CONCIERGE_ADD_CONFIRM"
DONE_COPY_KEY = "CONCIERGE_ADD_DONE"
REFUSED_NEW_COPY_KEY = "CONCIERGE_ADD_REFUSED_NEW"
REFUSED_TEAM_COPY_KEY = "CONCIERGE_ADD_REFUSED_TEAM"
COPY_KEYS = (CONFIRM_COPY_KEY, DONE_COPY_KEY, REFUSED_NEW_COPY_KEY, REFUSED_TEAM_COPY_KEY)

HISTORY_NOTE = "Itens acrescentados pela Concierge a pedido do cliente"

#: O motivo, na voz da casa, para cada recusa do serviço. O que não está aqui
#: cai em :data:`_GENERIC_REASON`: a Concierge não inventa motivo.
_REASONS = {
    "marketplace_order": "Esse pedido é do iFood, e item novo nele se pede pelo próprio iFood.",
    "test_order": "Esse pedido é de teste e não recebe itens.",
    "fiscal_authorized": "A nota fiscal desse pedido já foi emitida, e aí não dá mais para acrescentar itens nele.",
    "open_digital_charge": (
        "Esse pedido tem um pagamento (Pix ou link) esperando com o valor de agora, "
        "e aí não dá para mudar o valor dele por aqui."
    ),
    "on_account_total_locked": "Esse pedido está na conta da casa, e o valor dele não muda por aqui.",
    "weight_entry_required": "Esse item é vendido por peso, e só a equipe acrescenta com a etiqueta.",
    "price_missing": "Esse item está sem preço no cadastro agora.",
    "unknown_sku": "Esse item não está no cardápio.",
}
_STATUS_REASONS = {
    "ready": "O pedido {ref} já está pronto, e aí não dá mais para acrescentar itens nele.",
    "dispatched": "O pedido {ref} já saiu para entrega, e aí não dá mais para acrescentar itens nele.",
    "delivered": "O pedido {ref} já foi entregue.",
    "completed": "O pedido {ref} já foi concluído.",
    "cancelled": "O pedido {ref} foi cancelado.",
    "returned": "O pedido {ref} foi devolvido.",
}
_GENERIC_REASON = "Não consigo acrescentar isso ao pedido {ref} por aqui."
_NOT_FOUND_REASON = "Não achei esse pedido entre os seus pedidos."
_STOCK_REASON = "{items} está indisponível para esse pedido."


@dataclass(frozen=True)
class Outcome:
    #: ``asked`` (a pergunta de uma linha) · ``added`` · ``refused`` (motivo e o caminho que existe)
    code: str
    text: str
    order_ref: str = ""
    #: A próxima pergunta pendente da conversa (``dialogue``): a confirmação, a
    #: oferta de pedido novo. ``None`` quando nada fica no ar.
    pending: dict | None = None
    #: A equipe foi chamada: ``text`` é o aviso do handoff (motivo + "já chamei a
    #: equipe"), e ``handoff_reason`` é o que a equipe lê.
    handoff: bool = False
    handoff_reason: str = ""

    @property
    def memo(self) -> dict:
        """O que a memória da conversa grava (``dialogue.next_state``)."""
        return {"pending": self.pending}


def _copy(key: str, **values) -> str:
    from .service import copy_message

    text = copy_message(key)
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text.strip()


def _brl(value_q: int) -> str:
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(int(value_q))}"


def _today_iso() -> str:
    return timezone.localdate().isoformat()


# ── O pedido ──────────────────────────────────────────────────────────


def own_order(conversation, order_ref: str):
    """O pedido ``order_ref`` se for DESTE cliente (identidade da conversa); senão ``None``.

    Aceita o ref inteiro ou só o código do fim ("M63"). Pedido de outra pessoa
    não acha nada aqui.
    """
    from shopman.orderman.models import Order

    from shopman.shop.services.customer_orders import customer_identity_filter

    ref = str(order_ref or "").strip().upper()
    if not ref:
        return None
    identity = customer_identity_filter(
        customer_ref=conversation.customer_ref or None, phone=conversation.phone or None
    )
    if identity is None:
        return None
    candidates = list(Order.objects.filter(identity).distinct().order_by("-created_at")[:20])
    matches = [o for o in candidates if o.ref.upper() == ref] or [
        o for o in candidates if o.ref.upper().rsplit("-", 1)[-1] == ref
    ]
    return matches[0] if len(matches) == 1 else None


def _is_preorder(order) -> bool:
    """Encomenda = combinada para um dia depois de hoje."""
    from shopman.shop.services.order_helpers import get_commitment_date

    day = get_commitment_date(order)
    return bool(day and day > timezone.localdate())


def _normalize(additions) -> list[dict]:
    """``[{sku, qty, name}]`` com SKU do catálogo, quantidade inteira de 1 a 99, um por SKU."""
    from shopman.offerman.models import Product

    merged: dict[str, dict] = {}
    for raw in additions or []:
        sku = str((raw or {}).get("sku") or "").strip()
        try:
            qty = Decimal(str((raw or {}).get("qty")))
        except Exception:
            return []
        if not sku or not qty.is_finite() or qty <= 0 or qty != qty.to_integral_value():
            return []
        product = Product.objects.filter(sku__iexact=sku).first()
        if product is None:
            return []
        entry = merged.setdefault(product.sku, {"sku": product.sku, "qty": 0, "name": product.name or product.sku})
        entry["qty"] += int(qty)
    out = list(merged.values())
    if not out or any(entry["qty"] > MAX_QTY for entry in out):
        return []
    return out


def items_text(additions: list[dict]) -> str:
    parts = [f"{entry['qty']} {entry['name']}" for entry in additions]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]


def _lines(order, additions: list[dict]) -> list[dict]:
    """A lista FINAL para o ``order_edit``: o que já estava, pelo ``line_id``, mais o que entra."""
    from shopman.shop.services import order_composition
    from shopman.shop.services.order_edit import _is_fixed_line

    kept = [
        {"line_id": item.line_id, "sku": item.sku, "qty": str(item.qty)}
        for item in order_composition.effective_items(order)
        if not _is_fixed_line(item)
    ]
    return kept + [{"sku": entry["sku"], "qty": entry["qty"]} for entry in additions]


def _out_of_stock(order, additions: list[dict]) -> list[dict]:
    """O que não tem saldo para o dia do pedido (leitura; o "sim" exige de novo)."""
    from shopman.shop.services import availability
    from shopman.shop.services.order_helpers import get_commitment_date

    day = get_commitment_date(order)
    missing = []
    for entry in additions:
        try:
            reading = availability.check(
                entry["sku"], Decimal(entry["qty"]), channel_ref=order.channel_ref or None, target_date=day,
            )
        except Exception:
            logger.warning("concierge.add: availability degraded order=%s sku=%s", order.ref, entry["sku"], exc_info=True)
            continue
        if not reading.get("ok"):
            missing.append(entry)
    return missing


# ── Recusa ────────────────────────────────────────────────────────────


def _refused(order, additions: list[dict], reason: str, *, order_ref: str = "") -> Outcome:
    """O motivo verdadeiro e o caminho que existe: pedido novo (do dia) ou a equipe (encomenda)."""
    ref = order.ref if order is not None else order_ref
    items = items_text(additions) if additions else ""
    if (order is not None and _is_preorder(order)) or not items:
        # Encomenda: o motivo e a equipe já chamada, na mesma mensagem (o handoff
        # é criado de fato pelo turno; a R6 só deixa a frase sair com o recibo).
        what = f"acrescentar {items}" if items else "acrescentar itens"
        return Outcome(
            "refused",
            _copy(REFUSED_TEAM_COPY_KEY, reason=reason),
            ref,
            handoff=True,
            handoff_reason=f"Cliente pediu para {what} ao pedido {ref}: {reason}"[:200],
        )
    return Outcome(
        "refused",
        _copy(REFUSED_NEW_COPY_KEY, reason=reason, items=items),
        ref,
        pending={"kind": "confirm_new", "order_ref": ref, "item": items},
    )


def _reason_for(order, code: str) -> str:
    if code == "order_not_editable":
        template = _STATUS_REASONS.get(str(order.status))
        if template:
            return template.format(ref=order.ref)
    return _REASONS.get(code, _GENERIC_REASON).format(ref=order.ref)


# ── A pergunta e o "sim" ──────────────────────────────────────────────


def propose(conversation, *, order_ref: str, additions) -> Outcome:
    """A pergunta de uma linha, com os dados do sistema; ou a recusa com o motivo.

    Nada é gravado no pedido aqui: ``order_edit.plan`` só calcula.
    """
    from shopman.shop.services import order_edit

    entries = _normalize(additions)
    if not getattr(conversation, "_commercial_authority", False):
        # Sem a identidade confirmada do turno, nenhum pedido muda por aqui.
        return _refused(None, [], "Não consigo mexer em pedido já feito por aqui agora.", order_ref=order_ref)
    order = own_order(conversation, order_ref)
    if order is None:
        return _refused(None, entries, _NOT_FOUND_REASON, order_ref=order_ref)
    if not entries:
        return _refused(order, [], _GENERIC_REASON.format(ref=order.ref))
    try:
        from shopman.storefront.services.orders import resolve_timeouts_if_due

        resolve_timeouts_if_due(order)
        order.refresh_from_db()
    except Exception:
        logger.warning("concierge.add: timeout resolution failed order=%s", order.ref, exc_info=True)
    try:
        plan = order_edit.plan(order, lines=_lines(order, entries), source=order_edit.CONCIERGE_SOURCE)
    except order_edit.EditRefused as exc:
        return _refused(order, entries, _reason_for(order, exc.code))
    if not _only_adds(plan) or plan.settlement.kind not in {order_edit.SETTLE_COLLECT, order_edit.SETTLE_NONE}:
        return _refused(order, entries, _GENERIC_REASON.format(ref=order.ref))
    missing = _out_of_stock(order, entries)
    if missing:
        return _refused(order, entries, _STOCK_REASON.format(items=items_text(missing)))

    from .dialogue import order_label

    pending = {
        "kind": "confirm_add",
        "order_ref": order.ref,
        "add": entries,
        "total_q": plan.total_q,
        "item": items_text(entries),
        "day": _today_iso(),
    }
    text = _copy(
        CONFIRM_COPY_KEY,
        items=items_text(entries),
        order=order_label(order, now=timezone.now()),
        total=_brl(plan.total_q),
        balance=_brl(plan.balance_after_q),
    )
    return Outcome("asked", text, order.ref, pending=pending)


def _only_adds(plan) -> bool:
    """Nesta fatia, só aumento: nada sai, nada diminui, o total sobe."""
    diff = plan.diff or {}
    if diff.get("removed"):
        return False
    for entry in diff.get("changed") or []:
        if Decimal(str(entry.get("qty"))) < Decimal(str(entry.get("previous_qty"))):
            return False
    return plan.items_changed and plan.total_q > plan.previous_total_q and not (
        plan.notes_changed or plan.fulfillment_changed or plan.schedule_changed
    )


def apply(conversation, pending: dict) -> Outcome:
    """O "sim": aplica pelo ``order_edit.edit`` e registra. Recusa diz o motivo."""
    from shopman.shop.models import ConversationMessage
    from shopman.shop.services import order_edit

    from .service import assert_turn_authority

    order_ref = str(pending.get("order_ref") or "")
    entries = _normalize(pending.get("add"))
    if not getattr(conversation, "_commercial_authority", False):
        return _refused(None, [], "Não consigo mexer em pedido já feito por aqui agora.", order_ref=order_ref)
    assert_turn_authority(conversation, for_mutation=True)
    order = own_order(conversation, order_ref)
    if order is None or not entries:
        return _refused(order, entries, _NOT_FOUND_REASON, order_ref=order_ref)

    # O pedido mudou entre a pergunta e o "sim" (outra edição, outro preço): o
    # cliente confirma o valor de AGORA, nunca um valor velho.
    fresh = propose(conversation, order_ref=order.ref, additions=entries)
    if fresh.code != "asked":
        return fresh
    if fresh.pending["total_q"] != int(pending.get("total_q") or 0):
        return fresh

    try:
        with transaction.atomic():
            # Uma mensagem só: a resposta da Concierge leva o que o aviso
            # ``order_updated`` diria (total novo, saldo e destino da diferença).
            result = order_edit.edit(
                order, lines=_lines(order, entries), actor=ACTOR, source=order_edit.CONCIERGE_SOURCE,
                notify_customer=False,
            )
            ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.Role.ASSISTANT,
                kind=ConversationMessage.Kind.NOTE,
                text=f"{HISTORY_NOTE}: {items_text(entries)} (pedido {order.ref}).",
                envelope={"version": 3, "order_ref": order.ref, "turn_fence": conversation.turn_fence},
            )
    except order_edit.EditRefused as exc:
        if exc.code == "insufficient_stock":
            return _refused(order, entries, _STOCK_REASON.format(items=items_text(entries)))
        order.refresh_from_db()
        return _refused(order, entries, _reason_for(order, exc.code))
    plan = result.plan
    text = _copy(
        DONE_COPY_KEY,
        items=items_text(entries),
        order_ref=order.ref,
        money=order_edit.money_for_customer(plan),
    )
    return Outcome("added", text, order.ref, pending=None)
