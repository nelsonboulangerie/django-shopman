"""Operator order mutation facade.

Backstage views use this module for order mutations. Projections may still read
orders directly, but mutation paths should not decide lifecycle transitions in
the HTTP layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from django.db import transaction
from shopman.orderman.models import Order

from shopman.shop.services.cancellation import cancel
from shopman.shop.services.order_helpers import get_fulfillment_type

logger = logging.getLogger(__name__)


class OrderStateConflict(ValueError):
    """O pedido mudou de status antes de a ação do operador ser aplicada.

    Levantada pelo guard reavaliado na linha travada (``select_for_update``):
    o aceite automático (directive ``confirmation.timeout``) corre em paralelo
    com o operador, então decidir sobre o status em memória permitiria, por
    exemplo, recusar um pedido que acabou de ser aceito (ACCEPTED →
    CANCELLED é transição válida). A camada HTTP mapeia para 409.
    """


class ChangeOutRequired(ValueError):
    """O pedido pede troco e ninguém disse quanto o entregador leva.

    A loja coleta "troco para quanto?" no checkout; o despacho é a hora em que
    esse dado vira dinheiro saindo da gaveta. Avançar para "saiu para entrega"
    sem dizer o valor (zero vale: "levou sem troco") deixaria a gaveta
    desfalcada sem linha no livro. A camada HTTP devolve 409 com a sugestão.
    """

    def __init__(self, suggested_q: int):
        self.suggested_q = int(suggested_q)
        super().__init__(
            "Informe o troco que o entregador leva da gaveta (pode ser zero). "
            f"Sugestão: {self.suggested_q} centavos."
        )


class AdvanceBlock(StrEnum):
    """Por que o avanço está barrado — o código, não a frase.

    Duas naturezas diferentes moram aqui, e a superfície precisa distingui-las:
    ``NO_NEXT_STEP`` é definitivo (pedido morto ou ainda sem aceite, não há o
    que avançar) e ``PAYMENT_NOT_CAPTURED`` é temporário (há próxima etapa, só
    falta o dinheiro entrar). Antes isso era deduzido casando pedaço de frase em
    português no rótulo, e um pedido cancelado ganhava botão "Ainda não dá para
    avançar".
    """

    NONE = ""
    NO_NEXT_STEP = "no_next_step"
    PAYMENT_NOT_CAPTURED = "payment_not_captured"
    # Encomenda para data futura: não dá pra iniciar o preparo antes do dia
    # (o pedido de sábado não vai pra cozinha na terça). Some sozinho na data.
    PREORDER_NOT_DUE = "preorder_not_due"


_ADVANCE_BLOCK_MESSAGES: dict[AdvanceBlock, str] = {
    AdvanceBlock.NO_NEXT_STEP: "Pedido não possui próxima etapa",
    AdvanceBlock.PAYMENT_NOT_CAPTURED: (
        "Pagamento ainda não foi confirmado. Aguarde antes de iniciar o preparo."
    ),
    AdvanceBlock.PREORDER_NOT_DUE: (
        "Encomenda para uma data futura. O preparo abre no dia combinado."
    ),
}

_NEXT_STATUS_MAP: dict[str, str] = {
    Order.Status.ACCEPTED: Order.Status.PREPARING,
    Order.Status.PREPARING: Order.Status.READY,
    Order.Status.READY: Order.Status.COMPLETED,
    Order.Status.DISPATCHED: Order.Status.DELIVERED,
    Order.Status.DELIVERED: Order.Status.COMPLETED,
}


def find_order(ref: str) -> Order | None:
    """Return an order by public reference, if it exists."""
    return Order.objects.filter(ref=ref).first()


def recent_history(*, limit: int = 20) -> list[Order]:
    """Return recent closed orders for the operator history view."""
    return list(
        Order.objects.filter(
            status__in=(
                Order.Status.COMPLETED,
                Order.Status.DELIVERED,
                Order.Status.CANCELLED,
            )
        )
        .prefetch_related("items")
        .order_by("-updated_at")[:limit]
    )


def confirm_order(order: Order, *, actor: str) -> None:
    """Confirm a manually accepted order.

    Guard + transição rodam na MESMA transação com lock: o guard reavalia o
    status na linha travada, nunca na instância em memória, para não decidir
    sobre estado velho enquanto a auto-confirmação corre em paralelo.
    """
    from shopman.shop.lifecycle import ensure_confirmable, ensure_payment_captured

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status != Order.Status.NEW:
            raise OrderStateConflict(
                "Pedido não está mais aguardando confirmação "
                f"(status atual: {locked.get_status_display()})."
            )
        ensure_payment_captured(locked)
        ensure_confirmable(locked)
        # transition_status re-lê a mesma linha já travada nesta transação,
        # então o lock cobre do guard até o save.
        order.transition_status(Order.Status.ACCEPTED, actor=actor)


def reject_order(
    order: Order,
    *,
    reason: str,
    actor: str,
    rejected_by: str,
    cancellation_code: str = "",
) -> None:
    """Reject an order and queue the customer notification directive.

    ``cancellation_code`` is the marketplace (iFood) cancellation code the
    operator picked; it rides ``order.data`` to the status-callback handler.

    Guard + cancelamento na MESMA transação com lock (ver ``OrderStateConflict``):
    ACCEPTED → CANCELLED é transição válida, então sem o guard na linha travada
    uma recusa atrasada cancelaria um pedido que o aceite automático acabou de
    aceitar.
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status != Order.Status.NEW:
            raise OrderStateConflict(
                "Pedido não está mais aguardando confirmação "
                f"(status atual: {locked.get_status_display()})."
            )

        extra_data = {"rejected_by": rejected_by}
        if cancellation_code:
            extra_data["ifood_cancellation_code"] = cancellation_code
        cancel(
            locked,
            reason=reason,
            actor=actor,
            extra_data=extra_data,
        )
        from shopman.shop.services import notification

        notification.send(locked, "order_rejected", reason=reason, rejected_by=rejected_by)
    logger.info("operator_reject order=%s reason=%s", order.ref, reason)


def next_status_for(order: Order) -> str:
    """Return the canonical next operator-driven status, or empty string."""
    if order.status == Order.Status.READY and get_fulfillment_type(order) == "delivery":
        return Order.Status.DISPATCHED
    return _NEXT_STATUS_MAP.get(order.status, "")


def advance_block(order: Order) -> AdvanceBlock:
    """Why advancing is blocked right now, as a code.

    Single source for the operator-advance gate: ``advance_order`` raises with
    the matching message, and a fila do operador lê o código para decidir se
    oferece a ação — a previsão e a regra nunca divergem.
    """
    if not next_status_for(order):
        return AdvanceBlock.NO_NEXT_STEP
    if order.status == Order.Status.ACCEPTED and _requires_captured_payment_for_work(order):
        return AdvanceBlock.PAYMENT_NOT_CAPTURED
    if order.status == Order.Status.ACCEPTED and _preorder_not_due(order):
        return AdvanceBlock.PREORDER_NOT_DUE
    return AdvanceBlock.NONE


def advance_block_message(bloqueio: AdvanceBlock) -> str:
    """A frase que o operador lê para um código de bloqueio."""
    return _ADVANCE_BLOCK_MESSAGES.get(bloqueio, "")


def advance_block_reason(order: Order) -> str:
    """A frase que o operador lê, ou '' se ``advance_order`` rodaria agora."""
    return advance_block_message(advance_block(order))


def advance_order(
    order: Order,
    *,
    actor: str,
    change_out_q: int | None = None,
    cash_shift=None,
    equipment: list[str] | None = None,
) -> str:
    """Advance an order through the operator lifecycle.

    No despacho de uma entrega paga em dinheiro, o troco que o entregador leva
    sai da gaveta AQUI (``courier_out`` no turno de quem despacha, mesma
    transação da transição). Quando o pedido pede troco (``change_for_q`` acima
    do total) o valor é obrigatório, zero incluído: é o servidor que exige, não
    a tela, porque uma gaveta desfalcada sem linha é exatamente o buraco.
    """
    blocked = advance_block_reason(order)
    if blocked:
        raise ValueError(blocked)
    next_status = next_status_for(order)

    dispatching = next_status == Order.Status.DISPATCHED and get_fulfillment_type(order) == "delivery"
    change_out = 0
    if dispatching:
        suggested_q = change_out_suggested_q(order)
        if change_out_q is None and suggested_q > 0:
            raise ChangeOutRequired(suggested_q)
        change_out = int(change_out_q or 0)
        if change_out < 0:
            raise ValueError("O troco levado não pode ser negativo.")
        if change_out > 0 and (cash_shift is None or not getattr(cash_shift, "is_open", False)):
            raise ValueError("Abra um turno de caixa para o entregador levar troco da gaveta.")
        taken = _clean_equipment(order, equipment)
    else:
        taken = []

    with transaction.atomic():
        _sync_delivery_fulfillment(order, next_status)
        if taken:
            # Custódia do aparelho (maquininha): o despacho registra o que saiu;
            # "onde está agora" é derivado (saiu e ainda não voltou). Não é
            # dinheiro, então não vai ao livro do caixa.
            data = dict(order.data or {})
            data["dispatch"] = {
                **dict(data.get("dispatch") or {}),
                "equipment": taken,
                "equipment_out_at": timezone_now_iso(),
                "equipment_out_by": actor,
            }
            order.data = data
            order.save(update_fields=["data", "updated_at"])
        order.transition_status(next_status, actor=actor)
        if change_out > 0:
            from shopman.cashman import services as cash_ledger

            cash_ledger.record(
                "courier_out",
                shift=cash_shift,
                operator=_user_for_actor(actor) or cash_shift.operator,
                amount_q=-change_out,
                order_ref=order.ref,
                payload={
                    "change_for_q": _change_for_q(order),
                    "suggested_q": change_out_suggested_q(order),
                    "dispatched_by": actor,
                },
            )
    if dispatching:
        schedule_delivery_auto_complete(order)
    return next_status


# ── Troco da entrega: o que a loja coletou e o que o livro diz ─────────────


@dataclass(frozen=True)
class CourierChange:
    """O troco de uma entrega, visto do livro: saiu quanto, voltou quanto.

    ``suggested_q`` é o que a loja coletou (``change_for_q − total``), enquanto
    o dinheiro da entrega não foi acertado; ``out_q`` é o que de fato saiu com o
    entregador (``courier_out``); ``back_q`` é o que voltou (``courier_in``),
    ``None`` enquanto o acerto não fechou o ciclo.
    """

    suggested_q: int = 0
    out_q: int = 0
    back_q: int | None = None

    @property
    def pending(self) -> bool:
        """Saiu e ainda não voltou (nem "voltou zero")."""
        return self.out_q > 0 and self.back_q is None


# ── Aparelho que sai com o entregador (maquininha) ─────────────────────────


def equipment_options(channel_ref: str) -> list[str]:
    """Os aparelhos que o canal permite levar no despacho (``fulfillment.equipment``)."""
    from shopman.shop.config import ChannelConfig

    try:
        return [str(ref) for ref in (ChannelConfig.for_channel(channel_ref).fulfillment.equipment or [])]
    except Exception:
        logger.debug("operator_orders.equipment_options: config indisponível channel=%s", channel_ref, exc_info=True)
        return []


def _clean_equipment(order: Order, equipment) -> list[str]:
    wanted = [str(ref).strip() for ref in (equipment or []) if str(ref).strip()]
    if not wanted:
        return []
    allowed = equipment_options(order.channel_ref or "")
    unknown = [ref for ref in wanted if ref not in allowed]
    if unknown:
        raise ValueError(f"Aparelho não previsto para este canal: {', '.join(unknown)}.")
    return list(dict.fromkeys(wanted))


@dataclass(frozen=True)
class EquipmentCustody:
    """O que saiu com o entregador e se já voltou."""

    equipment: tuple[str, ...] = ()
    out_at: str = ""
    out_by: str = ""
    back_at: str = ""
    back_by: str = ""

    @property
    def pending(self) -> bool:
        return bool(self.equipment) and not self.back_at


def equipment_custody(order: Order) -> EquipmentCustody:
    dispatch = (order.data or {}).get("dispatch") or {}
    return EquipmentCustody(
        equipment=tuple(str(ref) for ref in (dispatch.get("equipment") or [])),
        out_at=str(dispatch.get("equipment_out_at") or ""),
        out_by=str(dispatch.get("equipment_out_by") or ""),
        back_at=str(dispatch.get("equipment_back_at") or ""),
        back_by=str(dispatch.get("equipment_back_by") or ""),
    )


def mark_equipment_returned(order: Order, *, actor: str) -> EquipmentCustody:
    """O entregador devolveu o aparelho: fecha a custódia no pedido que o levou."""
    custody = equipment_custody(order)
    if not custody.equipment:
        raise ValueError("Este pedido não levou aparelho.")
    if custody.back_at:
        raise ValueError("O aparelho deste pedido já voltou.")
    data = dict(order.data or {})
    data["dispatch"] = {
        **dict(data.get("dispatch") or {}),
        "equipment_back_at": timezone_now_iso(),
        "equipment_back_by": actor,
    }
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    order.emit_event(event_type="equipment_returned", actor=actor, payload={"equipment": list(custody.equipment)})
    return equipment_custody(order)


def equipment_out(*, channel_ref: str | None = None) -> list[tuple[str, Order]]:
    """Onde está cada aparelho agora: ``(ref, pedido)`` dos pedidos que o levaram e ainda não devolveram."""
    qs = Order.objects.filter(data__dispatch__has_key="equipment").exclude(data__dispatch__has_key="equipment_back_at")
    if channel_ref:
        qs = qs.filter(channel_ref=channel_ref)
    out: list[tuple[str, Order]] = []
    for order in qs.order_by("-created_at"):
        for ref in equipment_custody(order).equipment:
            out.append((ref, order))
    return out


def _change_for_q(order: Order) -> int:
    payment = (order.data or {}).get("payment") or {}
    try:
        return max(0, int(payment.get("change_for_q") or 0))
    except (TypeError, ValueError):
        return 0


def change_out_suggested_q(order: Order) -> int:
    """Quanto de troco a loja sugere que o entregador leve: ``change_for_q − total``.

    Só enquanto é entrega em dinheiro na porta ainda não acertada; zero quando o
    cliente não pediu troco, pediu abaixo do total (erro de digitação) ou o
    dinheiro já entrou.
    """
    payment = (order.data or {}).get("payment") or {}
    if get_fulfillment_type(order) != "delivery":
        return 0
    if payment.get("method") != "cash" or payment.get("collection") != "on_delivery":
        return 0
    if payment.get("cod_settled_at"):
        return 0
    return max(0, _change_for_q(order) - int(order.total_q or 0))


def courier_change_by_order(order_refs) -> dict[str, tuple[int, int | None]]:
    """``{order_ref: (out_q, back_q | None)}`` numa consulta, para projections com muitos cards."""
    from shopman.cashman.models import Entry

    refs = [str(ref) for ref in order_refs if ref]
    if not refs:
        return {}
    out: dict[str, int] = {}
    back: dict[str, int] = {}
    rows = Entry.objects.filter(
        kind__in=[Entry.Kind.COURIER_OUT, Entry.Kind.COURIER_IN], order_ref__in=refs
    ).values_list("order_ref", "kind", "amount_q")
    for ref, kind, amount_q in rows:
        if kind == Entry.Kind.COURIER_OUT:
            out[ref] = out.get(ref, 0) - int(amount_q)
        else:
            back[ref] = back.get(ref, 0) + int(amount_q)
    return {ref: (out.get(ref, 0), back.get(ref)) for ref in set(out) | set(back)}


def courier_change(order: Order) -> CourierChange:
    out_q, back_q = courier_change_by_order([order.ref]).get(order.ref, (0, None))
    return CourierChange(suggested_q=change_out_suggested_q(order), out_q=out_q, back_q=back_q)


def _user_for_actor(actor: str):
    """O usuário por trás do ``actor`` ("pos:ana", "gestor:pablo", "ana"), ou ``None``."""
    from django.contrib.auth import get_user_model

    username = str(actor or "")
    if ":" in username:
        username = username.split(":", 1)[1]
    return get_user_model().objects.filter(username=username).first() if username else None


def schedule_delivery_auto_complete(order: Order) -> None:
    """Agenda a auto-conclusão de um pedido em entrega: ETA + folga após a saída.

    Rede de segurança para o trecho sem rastreio — se nem o cliente ("Recebi")
    nem o operador ("Marcar entregue") fecharem, o pedido não fica preso em
    "saiu para entrega". Idempotente (reusa o directive enfileirado); respeita o
    desligamento (folga <= 0). O handler revalida o status, então um pedido já
    fechado quando o directive vence é um no-op.
    """
    from datetime import timedelta

    from django.utils import timezone
    from shopman.orderman.models import Directive

    from shopman.shop.directives import DELIVERY_AUTO_COMPLETE
    from shopman.shop.models import Shop
    from shopman.shop.services.order_helpers import (
        delivery_auto_complete_grace_minutes,
        delivery_eta_minutes,
    )

    shop = Shop.load()
    grace = delivery_auto_complete_grace_minutes(shop)
    if grace <= 0:
        return  # auto-conclusão desligada via config
    minutes = delivery_eta_minutes(shop, order.data or {}) + grace
    available_at = timezone.now() + timedelta(minutes=minutes)

    existing = (
        Directive.objects.filter(
            topic=DELIVERY_AUTO_COMPLETE,
            payload__order_ref=order.ref,
            status=Directive.Status.QUEUED,
        )
        .order_by("available_at", "id")
        .first()
    )
    if existing:
        existing.available_at = available_at
        existing.save(update_fields=["available_at", "updated_at"])
        return
    Directive.objects.create(
        topic=DELIVERY_AUTO_COMPLETE,
        payload={"order_ref": order.ref},
        available_at=available_at,
    )


def confirm_received(order: Order, *, actor: str = "customer") -> bool:
    """Customer confirms a dispatched delivery arrived → mark delivered.

    Same machinery as the operator "Marcar como Entregue" (fulfillment sync +
    transition), so handlers/notifications fire exactly once. Only valid while
    the order is out for delivery; idempotent (returns False) otherwise — couriers
    são terceirizados, então o cliente fechando o loop é uma das vias legítimas
    para o pedido virar "entregue" (junto do operador e da auto-conclusão).
    """
    if order.status != Order.Status.DISPATCHED or get_fulfillment_type(order) != "delivery":
        return False
    _sync_delivery_fulfillment(order, Order.Status.DELIVERED)
    order.transition_status(Order.Status.DELIVERED, actor=actor)
    return True


def cancel_order(
    order: Order,
    *,
    reason: str,
    actor: str,
    cancellation_code: str = "",
    customer_note: str = "",
) -> None:
    """Cancel an order through the canonical cancellation service.

    ``cancellation_code`` (iFood) rides ``order.data`` to the status-callback handler.

    ``customer_note`` is the operator-authored, customer-facing justification. It is
    stored under ``order.data["cancellation_note"]`` and surfaced to the customer in
    the ``order_cancelled`` notification. Kept separate from ``cancellation_reason``,
    which also carries machine codes (``pix_timeout``, ``customer_requested``) that
    must never reach the customer. Empty when the operator gave no reason → the
    customer gets the plain cancellation message.
    """
    extra_data: dict[str, str] = {}
    if cancellation_code:
        extra_data["ifood_cancellation_code"] = cancellation_code
    if customer_note.strip():
        extra_data["cancellation_note"] = customer_note.strip()
    cancel(order, reason=reason, actor=actor, extra_data=extra_data or None)


def settle_delivery_cash(
    order: Order,
    *,
    cash_shift,
    actor: str,
    amount_q: int | None = None,
    change_back_q: int | None = None,
    equipment_back: bool = False,
) -> int:
    """O dinheiro da entrega chega ao balcão: acerto no turno de quem RECEBEU.

    Três registros, na mesma transação, cada um na sua casa:
    - o pedido diz que foi acertado (``cod_settled_at/by``, tender recebido);
    - o Payman recebe o intent de dinheiro capturado (``settle``): é o livro de
      pagamentos de todos os métodos, e a entrega paga na porta só liquida aqui;
    - o livro-caixa do turno recebe ``cod_settled`` (efeito = valor): é o turno
      que COLETOU, independente de quem criou a venda, o que antes era regra
      escondida num algoritmo de fechamento e hoje é a linha em si.

    Quando o entregador levou troco da gaveta (``courier_out`` no despacho), o
    acerto fecha o ciclo: ``change_back_q`` é obrigatório (zero vale: usou tudo)
    e vira ``courier_in`` na mesma transação, apontando para a saída quando é o
    mesmo turno. Nada de etiqueta de turno no pedido: a atribuição É o lançamento.
    """
    from django.db import transaction
    from shopman.cashman import services as cash_ledger

    if get_fulfillment_type(order) != "delivery":
        raise ValueError("Acerto de entrega só se aplica a pedidos delivery.")
    if order.status not in {Order.Status.DISPATCHED, Order.Status.DELIVERED, Order.Status.COMPLETED}:
        raise ValueError("Acerto de entrega só é permitido depois da saída para entrega.")
    if cash_shift is None or not getattr(cash_shift, "is_open", False):
        raise ValueError("Abra um turno de caixa para registrar o acerto.")

    data = dict(order.data or {})
    payment = dict(data.get("payment") or {})
    if payment.get("collection") != "on_delivery" or payment.get("method") != "cash":
        raise ValueError("Pedido não está marcado como dinheiro na entrega.")
    if payment.get("cod_settled_at"):
        raise ValueError("Dinheiro da entrega já foi acertado.")

    amount = int(amount_q if amount_q is not None else order.total_q or 0)
    if amount <= 0:
        raise ValueError("Valor de acerto inválido.")
    if amount != int(order.total_q or 0):
        raise ValueError("Valor de acerto deve bater com o total do pedido.")

    change = courier_change(order)
    change_back: int | None = None
    if change.pending:
        if change_back_q is None:
            raise ValueError("Informe quanto de troco voltou com o entregador (pode ser zero).")
        change_back = int(change_back_q)
        if change_back < 0 or change_back > change.out_q:
            raise ValueError("O troco que voltou não pode ser negativo nem maior do que saiu.")
    elif change_back_q:
        raise ValueError("Este pedido não levou troco da gaveta.")

    from shopman.payman import PaymentService

    receiver = _user_for_actor(actor) or cash_shift.operator

    with transaction.atomic():
        intent = PaymentService.settle(
            order.ref,
            amount,
            "cash",
            currency="BRL",
            idempotency_key=f"order-payment:{order.ref}:cash:{amount}:on_delivery",
            gateway_data={"collection": "on_delivery", "terminal_ref": cash_shift.terminal.ref},
        )
        tenders = list(payment.get("tenders") or [])
        updated = False
        for tender in tenders:
            if tender.get("method") == "cash" and tender.get("collection") == "on_delivery":
                tender["collection"] = "terminal"
                tender["status"] = "received"
                tender["terminal_ref"] = cash_shift.terminal.ref
                tender["received_at"] = timezone_now_iso()
                tender["intent_ref"] = intent.ref
                updated = True
                break
        if not updated:
            tenders.append({
                "method": "cash",
                "amount_q": amount,
                "collection": "terminal",
                "status": "received",
                "terminal_ref": cash_shift.terminal.ref,
                "received_at": timezone_now_iso(),
                "intent_ref": intent.ref,
            })

        payment["tenders"] = tenders
        payment["cash_received_q"] = amount
        payment["intent_ref"] = intent.ref
        payment["cod_settled_at"] = timezone_now_iso()
        payment["cod_settled_by"] = actor
        data["payment"] = payment
        order.data = data
        order.save(update_fields=["data", "updated_at"])
        cash_ledger.record(
            "cod_settled",
            shift=cash_shift,
            operator=receiver,
            amount_q=amount,
            order_ref=order.ref,
            payment_ref=intent.ref,
            payload={"settled_by": actor},
        )
        if change_back is not None:
            from shopman.cashman.models import Entry

            courier_out = (
                Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref).order_by("-id").first()
            )
            cash_ledger.record(
                "courier_in",
                shift=cash_shift,
                operator=receiver,
                amount_q=change_back,
                order_ref=order.ref,
                parent=courier_out if courier_out is not None and courier_out.shift_id == cash_shift.pk else None,
                payload={"courier_out_id": courier_out.pk if courier_out else None, "settled_by": actor},
            )
        order.emit_event(
            event_type="payment_collected",
            actor=actor,
            payload={"method": "cash", "amount_q": amount, "terminal_ref": cash_shift.terminal.ref},
        )
        if equipment_back and equipment_custody(order).pending:
            mark_equipment_returned(order, actor=actor)
    logger.info("operator_settle_delivery_cash order=%s shift=%s amount=%s", order.ref, cash_shift.pk, amount)
    return amount


def save_kitchen_note(order: Order, *, notes: str) -> None:
    """Persist the operator's kitchen note on the order data payload.

    The note (preset tags + free text) is written by the operator in the gestor
    and surfaced on the KDS ticket for the kitchen. Distinct from the customer's
    ``order_notes`` (from checkout) and from timeline ``operator_comment`` entries.
    """
    data = dict(order.data or {})
    data["kitchen_note"] = notes
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def assign_order(order: Order, *, operator_id: int, operator_name: str, actor: str) -> None:
    """Claim an order for an operator ("estou atendendo"), stored in Order.data.

    Contextual, not structural → lives in the JSONField (no migration), per the
    Core extensibility contract. Idempotent: re-claiming refreshes the holder.
    """
    from django.utils import timezone

    data = dict(order.data or {})
    data["assignment"] = {
        "operator_id": operator_id,
        "operator_name": operator_name,
        "at": timezone.now().isoformat(),
    }
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    order.emit_event(
        event_type="order_assigned",
        actor=actor,
        payload={"operator_id": operator_id, "operator_name": operator_name},
    )


def unassign_order(order: Order, *, actor: str) -> None:
    """Release an order's operator claim. No-op if it was not claimed."""
    data = dict(order.data or {})
    if data.pop("assignment", None) is None:
        return
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    order.emit_event(event_type="order_unassigned", actor=actor)


def add_comment(order: Order, *, note: str, actor: str) -> None:
    """Append a timestamped operator comment to the order timeline (OrderEvent).

    Distinct from ``kitchen_note`` (a single editable blob): a comment is an
    immutable, attributed entry that shows up in the timeline like any other
    event — useful for a running operator log/handover.
    """
    text = (note or "").strip()
    if not text:
        raise ValueError("Comentário vazio")
    order.emit_event(event_type="operator_comment", actor=actor, payload={"note": text})


def _requires_captured_payment_for_work(order: Order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False
    from shopman.shop.services import payment as payment_service

    return payment_service.has_sufficient_captured_payment(order) is not True


def _preorder_not_due(order: Order) -> bool:
    """True quando a encomenda é para uma data FUTURA — preparo abre só no dia."""
    from django.utils import timezone

    from shopman.shop.services.order_helpers import get_commitment_date

    target = get_commitment_date(order)
    return target is not None and target > timezone.localdate()


def timezone_now_iso() -> str:
    from django.utils import timezone

    return timezone.now().isoformat()


def _sync_delivery_fulfillment(order: Order, next_status: str) -> None:
    """Keep the delivery fulfillment lifecycle aligned with operator actions."""
    if get_fulfillment_type(order) != "delivery":
        return
    if next_status not in {Order.Status.DISPATCHED, Order.Status.DELIVERED}:
        return

    from shopman.orderman.models import Fulfillment

    from shopman.shop.services import fulfillment as fulfillment_service

    fulfillment = order.fulfillments.order_by("pk").first()
    if fulfillment is None:
        fulfillment = fulfillment_service.create(order) or order.fulfillments.order_by("pk").first()
    if fulfillment is None:
        return

    if next_status == Order.Status.DISPATCHED:
        _advance_fulfillment_to(
            fulfillment,
            Fulfillment.Status.DISPATCHED,
            fulfillment_service,
        )
    elif next_status == Order.Status.DELIVERED:
        _advance_fulfillment_to(
            fulfillment,
            Fulfillment.Status.DELIVERED,
            fulfillment_service,
        )


def _advance_fulfillment_to(fulfillment, target_status: str, fulfillment_service) -> None:
    from shopman.orderman.models import Fulfillment

    if fulfillment.status == target_status:
        return
    if fulfillment.status == Fulfillment.Status.DELIVERED:
        return

    if target_status == Fulfillment.Status.DISPATCHED:
        if fulfillment.status == Fulfillment.Status.PENDING:
            fulfillment_service.update(fulfillment, Fulfillment.Status.IN_PROGRESS)
            fulfillment.refresh_from_db()
        if fulfillment.status == Fulfillment.Status.IN_PROGRESS:
            fulfillment_service.update(fulfillment, Fulfillment.Status.DISPATCHED)
        return

    if target_status == Fulfillment.Status.DELIVERED:
        if fulfillment.status in {Fulfillment.Status.PENDING, Fulfillment.Status.IN_PROGRESS}:
            _advance_fulfillment_to(
                fulfillment,
                Fulfillment.Status.DISPATCHED,
                fulfillment_service,
            )
            fulfillment.refresh_from_db()
        if fulfillment.status == Fulfillment.Status.DISPATCHED:
            fulfillment_service.update(fulfillment, Fulfillment.Status.DELIVERED)
