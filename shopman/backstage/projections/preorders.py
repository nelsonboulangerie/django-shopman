"""Encomendas do PDV — a leitura que o balcão faz do que a casa prometeu.

A seção "Encomendas" do PDV (``docs/plans/ENCOMENDAS-PDV-PLAN.md``) responde
três perguntas do balcão: *vim buscar a encomenda da Ana*, *o que sai hoje?* e
*quanto temos para sábado?*. As três são a mesma leitura com recortes
diferentes, e ela mora aqui.

**O corte (decisão do dono, 26/09/2026):** encomenda é todo pedido com
recebimento — retirada ou entrega — de QUALQUER canal (PDV, loja online, iFood),
hoje ou depois, pela DATA COMBINADA. Diverge de propósito do *Agendados* do
Gestor (só data futura); a tela diz o seu corte, o lifecycle não muda.

**Nada aqui é montagem nova.** O conjunto de pedidos é o MESMO do lote da Via
Pedido (:func:`order_ticket.orders_for_period` — data combinada, sem Balcão,
sem cancelado/devolvido, na ordem do painel), e cada campo do card sai de um
helper do Gestor (``order_queue``): o resumo dos itens efetivos, o nome de
chamada com a máscara do iFood, o rótulo do recebimento, o número do canal, o
contato do detalhe. O que só existe aqui é o **saldo** — o total efetivo menos
o que o Payman diz que entrou — e a **situação** que ele ajuda a derivar.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import formats, timezone
from shopman.utils.monetary import format_money

from shopman.backstage.projections import order_queue

logger = logging.getLogger(__name__)

#: Teto do intervalo de uma leitura. A grade é de uma semana e a busca olha um
#: mês; passar disto é intervalo digitado errado, e a resposta é o teto, não
#: uma leitura que arrasta o ano inteiro para o balcão.
MAX_SPAN_DAYS = 62

#: Busca por telefone só a partir de quatro dígitos: com menos, "12" casa com
#: metade da agenda e a lista vira ruído.
MIN_PHONE_DIGITS = 4

#: O rótulo do canal quando o cadastro do canal não tem nome. O mesmo
#: vocabulário do Gestor (``orders-nuxt/presentation/board.channelLabel``).
_CHANNEL_FALLBACK_LABELS = {
    "web": "Loja online",
    "whatsapp": "WhatsApp",
    "ifood": "iFood",
    "pos": "PDV",
    "pdv": "PDV",
}

#: A situação que o balcão lê. A ordem de precedência está em
#: :func:`_situation`: o que aconteceu com a MERCADORIA vence o que aconteceu
#: com o dinheiro, porque o saldo tem campo próprio no card e a mercadoria não.
SITUATION_LABELS = {
    "to_pay": "A pagar",
    "paid": "Pago",
    "on_account": "Na conta da casa",
    "check_payment": "Conferir pagamento",
    "ready": "Pronto",
    "out_for_delivery": "Saiu para entrega",
    "delivered": "Entregue",
}

_DELIVERED_STATUSES = frozenset({"delivered", "completed"})

#: O estado do DINHEIRO, separado da situação (que é da mercadoria primeiro): uma
#: encomenda "Pronto" ainda pode ter saldo, e é o saldo que os filtros do balcão
#: (Todas · A receber · Pagas) leem.
#:
#:   to_receive → saldo > 0: o balcão cobra na retirada.
#:   paid       → nada a receber (inclui pré-pago do iFood e total zero).
#:   on_account → saldo zero porque parte (ou tudo) foi para a conta da casa. É
#:                obrigação do cliente reconhecida, NUNCA "a receber" no balcão —
#:                cobrar de novo seria cobrar duas vezes —, e também não é "paga".
#:   check      → o Payman não respondeu: "não sei" nunca entra calado em "a
#:                receber" nem em "pagas"; a tela dá a ele um aviso próprio.
PAYMENT_STATES = ("to_receive", "paid", "on_account", "check")


# ── Projeções ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreorderItemProjection:
    name: str
    qty_display: str
    line_total_display: str


@dataclass(frozen=True)
class PreorderCardProjection:
    """Uma encomenda na lista, na grade ou no resultado da busca."""

    ref: str
    # Número do canal (``displayId`` do iFood) SÓ quando o ref não o carrega —
    # a mesma régua do card do Gestor, para não dizer o número duas vezes.
    channel_display_id: str
    customer_name: str
    channel_ref: str
    channel_label: str
    fulfillment_type: str  # "pickup" | "delivery"
    fulfillment_label: str  # "Retirada" | "Entrega"
    commitment_date: str  # ISO
    commitment_date_display: str  # "hoje" · "amanhã" · "sáb, 27/09"
    window_label: str  # "" quando não houve janela combinada
    window_start: str  # "HH:MM" ou ""
    status: str
    situation: str
    situation_label: str
    # O dinheiro, à parte da mercadoria — ver :data:`PAYMENT_STATES`.
    payment_state: str
    total_q: int
    total_display: str
    # ``None`` = o Payman não respondeu por algum intent do pedido. "Não sei"
    # nunca vira "zero": a situação diz "Conferir pagamento".
    balance_q: int | None
    balance_display: str
    items_summary: str
    items_count: int


@dataclass(frozen=True)
class PreorderDayProjection:
    """Um dia da grade: as encomendas dele e a conta do dia no topo da coluna."""

    date: str
    date_display: str  # "hoje" · "amanhã" · "sáb, 27/09"
    weekday_display: str  # "sáb"
    day_display: str  # "27/09"
    is_today: bool
    orders_count: int
    total_q: int
    total_display: str
    # A soma dos saldos das encomendas "a receber" do dia (conta da casa e
    # pagamento a conferir ficam de fora — ver :data:`PAYMENT_STATES`).
    to_receive_q: int
    to_receive_display: str
    orders: tuple[PreorderCardProjection, ...]


@dataclass(frozen=True)
class PreorderListProjection:
    date_from: str
    date_to: str
    today: str
    query: str
    count: int
    total_q: int
    total_display: str
    to_receive_q: int
    to_receive_display: str
    # TODOS os dias do intervalo, inclusive os vazios: a grade semanal tem sete
    # colunas mesmo quando terça não tem nada, e a coluna vazia é informação.
    days: tuple[PreorderDayProjection, ...]


@dataclass(frozen=True)
class PreorderHandOverProjection:
    """Entregar no balcão: "Entregar" (pago) ou "Receber e entregar" (com saldo).

    A régua é do orquestrador (``operator_orders.counter_hand_over_block``); a
    tela só lê ``allowed`` e, quando não pode, a frase de ``block_reason``.
    """

    allowed: bool
    # Há saldo: o gesto é receber (dinheiro com troco, ou cartão na maquininha)
    # e entregar, num toque só.
    needs_payment: bool
    amount_q: int
    amount_display: str
    # A forma que o cliente combinou, quando é de balcão ("cash"/"debit"/
    # "credit"); vazio quando não disse ou combinou outra coisa.
    suggested_method: str
    block_reason: str
    # Pix ou link pendente que o balcão vai cancelar ao receber: a linha que a
    # tela mostra antes de confirmar. Vazio quando não há cobrança digital viva.
    digital_charge_notice: str = ""


@dataclass(frozen=True)
class PreorderCancelProjection:
    """Cancelar pelo PDV: a mesma régua, política e permissão do Gestor."""

    allowed: bool
    # Pedido pago (ou pagamento incerto) exige o PIN de um gerente.
    requires_approval: bool
    block_reason: str


@dataclass(frozen=True)
class PreorderRescheduleProjection:
    """Reagendar pelo PDV: a régua do orquestrador (``reschedule.state_refusal``)."""

    allowed: bool
    block_reason: str
    # O combinado de hoje, para o diálogo partir dele.
    date: str
    slot: str
    # Os itens: a janela oferecível depende deles (``/pos/schedule/?skus=``).
    skus: tuple[str, ...]


@dataclass(frozen=True)
class PreorderDetailProjection:
    card: PreorderCardProjection
    items: tuple[PreorderItemProjection, ...]
    payment_method_label: str
    delivery_address: str
    delivery_instructions: str
    # A observação do CLIENTE no checkout (``order_notes``). A nota do operador
    # (``kitchen_note``) é da cozinha e mora no Gestor/KDS.
    customer_note: str
    customer_phone: str
    customer_phone_uri: str
    customer_relay_phone: str
    customer_relay_code: str
    ticket_printed: bool
    # A base das mutações (entregar, cancelar): a revisão operacional do pedido
    # e quem está identificado. O servidor recusa se qualquer um mudou.
    revision: str
    actor_id: int | None
    hand_over: PreorderHandOverProjection
    cancel: PreorderCancelProjection
    reschedule: PreorderRescheduleProjection
    # Quem pode assinar o cancelamento de pedido pago (a lista do PDV).
    managers: tuple[dict, ...]


# ── Leitura ───────────────────────────────────────────────────────────────


def parse_range(raw_from, raw_to, *, today: date | None = None) -> tuple[date, date]:
    """``date_from``/``date_to`` na régua da casa, com o teto de :data:`MAX_SPAN_DAYS`.

    A régua é a do lote da Via Pedido (``order_ticket.parse_period``): data
    ilegível cai no padrão, intervalo invertido é trocado. O teto corta o FIM
    do intervalo, nunca o começo — quem pediu "a partir de hoje" continua
    vendo hoje.
    """
    from shopman.backstage.services import order_ticket

    date_from, date_to = order_ticket.parse_period(raw_from, raw_to, today=today)
    if (date_to - date_from).days + 1 > MAX_SPAN_DAYS:
        date_to = date_from + timedelta(days=MAX_SPAN_DAYS - 1)
    return date_from, date_to


def build_preorder_list(*, date_from: date, date_to: date, query: str = "") -> PreorderListProjection:
    """As encomendas do intervalo, agrupadas por dia, filtradas pela busca."""
    from shopman.backstage.services import order_ticket

    orders = order_ticket.orders_for_period(date_from, date_to)
    needle = str(query or "").strip()
    if needle:
        orders = [order for order in orders if _matches(order, needle)]

    cards = _cards_for(orders)
    by_day: dict[date, list[PreorderCardProjection]] = {}
    for card in cards:
        by_day.setdefault(date.fromisoformat(card.commitment_date), []).append(card)

    today = timezone.localdate()
    days = []
    cursor = date_from
    while cursor <= date_to:
        day_cards = by_day.get(cursor, [])
        day_total = sum(card.total_q for card in day_cards)
        day_to_receive = _to_receive_q(day_cards)
        days.append(
            PreorderDayProjection(
                date=cursor.isoformat(),
                date_display=_date_display(cursor, today),
                weekday_display=str(formats.date_format(cursor, "D")).lower(),
                day_display=formats.date_format(cursor, "d/m"),
                is_today=cursor == today,
                orders_count=len(day_cards),
                total_q=day_total,
                total_display=_money(day_total),
                to_receive_q=day_to_receive,
                to_receive_display=_money(day_to_receive),
                orders=tuple(day_cards),
            )
        )
        cursor += timedelta(days=1)

    total = sum(card.total_q for card in cards)
    to_receive = _to_receive_q(cards)
    return PreorderListProjection(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        today=today.isoformat(),
        query=needle,
        count=len(cards),
        total_q=total,
        total_display=_money(total),
        to_receive_q=to_receive,
        to_receive_display=_money(to_receive),
        days=tuple(days),
    )


def build_preorder_detail(ref: str, *, user=None) -> PreorderDetailProjection | None:
    """Uma encomenda, com o que o balcão precisa para entregar.

    ``None`` quando o pedido não existe OU não está no corte (venda de Balcão,
    cancelado, devolvido): o detalhe da seção não é uma porta lateral para ler
    qualquer pedido da casa.
    """
    from shopman.orderman.models import Order

    from shopman.backstage.services import order_ticket
    from shopman.shop.services import order_composition
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    order = Order.objects.filter(ref=ref).prefetch_related("items").first()
    if order is None or order.status in order_ticket.EXCLUDED_STATUSES or is_pos_counter_order(order):
        return None

    card = _cards_for([order])[0]
    data = order.data or {}
    payment_data = data.get("payment") or {}
    address, instructions = order_queue._delivery_address(order)
    contact = order_queue._customer_contact(order, data.get("customer") if isinstance(data.get("customer"), dict) else {})
    items = tuple(
        PreorderItemProjection(
            name=item.name or item.sku,
            qty_display=format(item.qty.normalize(), "f"),
            line_total_display=_money(item.line_total_q),
        )
        for item in order_composition.effective_items(order)
    )
    method = str(payment_data.get("method") or "")
    from shopman.shop.services import operator_orders

    return PreorderDetailProjection(
        card=card,
        items=items,
        payment_method_label=(
            "iFood" if order.channel_ref == "ifood"
            else order_queue._payment_method_label(method, payment_data, order=order)
        ),
        delivery_address=address,
        delivery_instructions=instructions,
        customer_note=str(data.get("order_notes") or "").strip(),
        customer_phone=contact.get("customer_phone", ""),
        customer_phone_uri=contact.get("customer_phone_uri", ""),
        customer_relay_phone=contact.get("customer_relay_phone", ""),
        customer_relay_code=contact.get("customer_relay_code", ""),
        ticket_printed=bool(data.get("ticket_printed_at")),
        revision=operator_orders.operational_revision(order),
        actor_id=getattr(user, "pk", None),
        hand_over=_hand_over(order, card, method),
        cancel=_cancel(order, user),
        reschedule=_reschedule(order, card),
        managers=tuple(order_queue._approver_options(user)) if user is not None else (),
    )


def _hand_over(order, card: PreorderCardProjection, method: str) -> PreorderHandOverProjection:
    from shopman.shop.services import counter_takeover, operator_orders

    reason = operator_orders.counter_hand_over_block(order, balance_q=card.balance_q)
    amount = int(card.balance_q or 0)
    digital = counter_takeover.pending_digital_method(order) if amount > 0 and not reason else ""
    return PreorderHandOverProjection(
        allowed=not reason,
        needs_payment=amount > 0,
        amount_q=amount,
        amount_display=_money(amount),
        suggested_method=method if method in {"cash", "debit", "credit"} else "",
        block_reason=reason,
        digital_charge_notice=counter_takeover.notice_for(digital) if digital else "",
    )


def _reschedule(order, card: PreorderCardProjection) -> PreorderRescheduleProjection:
    from shopman.shop.services import order_composition, reschedule

    data = order.data or {}
    reason = reschedule.state_refusal(order)
    return PreorderRescheduleProjection(
        allowed=not reason,
        block_reason=reason,
        date=str(data.get("delivery_date") or card.commitment_date),
        slot=str(data.get("delivery_time_slot") or ""),
        skus=tuple(dict.fromkeys(item.sku for item in order_composition.effective_items(order) if item.sku)),
    )


def _cancel(order, user) -> PreorderCancelProjection:
    """A capacidade do Gestor (régua + política + permissão), e uma porta a menos.

    O iFood fica no Gestor: cancelar ali exige um motivo da lista do iFood, lido
    na hora, e o balcão não precisa de uma segunda tela para isso.
    """
    if order.channel_ref == "ifood":
        return PreorderCancelProjection(
            allowed=False, requires_approval=False,
            block_reason="Pedido do iFood: cancele pelo Gestor de pedidos, que consulta os motivos do iFood.",
        )
    capability = order_queue._cancel_capability(order, user)
    return PreorderCancelProjection(
        allowed=bool(capability["can_cancel"]),
        requires_approval=bool(capability["cancel_requires_approval"]),
        block_reason=str(capability["cancel_block_label"] or ""),
    )


# ── Internos ──────────────────────────────────────────────────────────────


def _cards_for(orders: list) -> list[PreorderCardProjection]:
    """Os cards, com as leituras em LOTE: um read do Payman, um dos canais."""
    from shopman.shop.services import payment as payment_svc

    reads = payment_svc.read_payments_for(orders) if orders else {}
    labels = _channel_labels({order.channel_ref for order in orders})
    return [_card(order, reads=reads, channel_labels=labels) for order in orders]


def _card(order, *, reads, channel_labels: dict[str, str]) -> PreorderCardProjection:
    from shopman.backstage.services import order_ticket
    from shopman.shop.services import order_composition
    from shopman.shop.services.fulfillment_window import window_label, window_start_time

    data = order.data or {}
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    # A MESMA cadeia do card do Gestor: nome, senão telefone, senão o handle.
    customer_name = order_queue._format_customer_display(
        customer.get("name", "")
        or customer.get("phone", "")
        or data.get("customer_phone", "")
        or order.handle_ref
        or ""
    )
    items = order_composition.effective_items(order)
    total_q = order_composition.effective_total_q(order)
    balance_q = _balance_q(order, reads)
    payment_state = _payment_state(order, balance_q, total_q)
    situation = _situation(order, payment_state)
    is_delivery = order_queue._is_delivery(order)
    commitment = order_ticket.commitment_of(order)
    slot = data.get("delivery_time_slot")
    start = window_start_time(slot)
    return PreorderCardProjection(
        ref=order.ref,
        channel_display_id=order_queue._channel_display_id(order),
        customer_name=customer_name,
        channel_ref=order.channel_ref or "",
        channel_label=channel_labels.get(order.channel_ref or "", "") or _fallback_channel_label(order.channel_ref),
        fulfillment_type="delivery" if is_delivery else "pickup",
        fulfillment_label=order_queue._fulfillment_label(is_delivery),
        commitment_date=commitment.isoformat(),
        commitment_date_display=_date_display(commitment, timezone.localdate()),
        window_label=window_label(slot),
        window_start=start.strftime("%H:%M") if start else "",
        status=order.status,
        situation=situation,
        situation_label=SITUATION_LABELS[situation],
        payment_state=payment_state,
        total_q=total_q,
        total_display=_money(total_q),
        balance_q=balance_q,
        balance_display=_money(balance_q) if balance_q is not None else "",
        items_summary=order_queue.items_summary(items),
        items_count=len(items),
    )


def _balance_q(order, reads) -> int | None:
    """O que falta receber — a régua do orquestrador (:func:`payment.balance_due_q`).

    A mesma que o balcão usa para receber: total efetivo menos TODOS os intents do
    pedido (venda mista tem um por método) e menos o que foi para a conta da casa
    (já é obrigação reconhecida do cliente; cobrá-la no balcão seria cobrar duas
    vezes). No iFood, a prova é o payload do iFood, não o Payman.
    """
    from shopman.shop.services import payment as payment_svc

    return payment_svc.balance_due_q(order, payment_reads=reads)


def _payment_state(order, balance_q: int | None, total_q: int) -> str:
    """O estado do dinheiro, independente da mercadoria (:data:`PAYMENT_STATES`)."""
    if balance_q is None:
        return "check"
    if balance_q > 0:
        return "to_receive"
    from shopman.shop.services import payment as payment_svc

    if total_q > 0 and payment_svc.on_account_q(order) > 0:
        return "on_account"
    return "paid"


_SITUATION_BY_PAYMENT_STATE = {
    "check": "check_payment",
    "to_receive": "to_pay",
    "on_account": "on_account",
    "paid": "paid",
}


def _situation(order, payment_state: str) -> str:
    """A situação que o balcão lê — a mercadoria primeiro, depois o dinheiro."""
    if order.status in _DELIVERED_STATUSES:
        return "delivered"
    if order.status == "dispatched":
        return "out_for_delivery"
    if order.status == "ready":
        return "ready"
    return _SITUATION_BY_PAYMENT_STATE[payment_state]


def _to_receive_q(cards) -> int:
    """O que falta receber no balcão: só o saldo das encomendas "a receber"."""
    return sum(int(card.balance_q or 0) for card in cards if card.payment_state == "to_receive")


def _matches(order, needle: str) -> bool:
    """Busca por número do pedido, nome, telefone ou número do iFood.

    Nome sem acento e sem caixa ("jose" acha "José"). Telefone por dígitos, a
    partir de :data:`MIN_PHONE_DIGITS` — e nunca contra o relé do iFood (o 0800
    da central não é o telefone de ninguém, e casar com ele devolveria todo
    pedido do iFood do dia).
    """
    data = order.data or {}
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    folded = _fold(needle)
    if folded in _fold(order.ref):
        return True
    display_id = str(((data.get("ifood") or {}).get("display_id")) or "").strip()
    if display_id and folded in _fold(display_id):
        return True
    if folded in _fold(str(customer.get("name") or "")):
        return True

    digits = "".join(ch for ch in needle if ch.isdigit())
    if len(digits) >= MIN_PHONE_DIGITS:
        from shopman.shop.services.notification import customer_phone_is_platform_relay

        phone = str(customer.get("phone") or data.get("customer_phone") or "")
        phone_digits = "".join(ch for ch in phone if ch.isdigit())
        if phone_digits and digits in phone_digits and not customer_phone_is_platform_relay(order):
            return True
    return False


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def _channel_labels(refs: set[str]) -> dict[str, str]:
    """O nome de cada canal como o cadastro o chama — uma consulta só."""
    try:
        from shopman.shop.models import Channel

        return {
            ref: str(name or "").strip()
            for ref, name in Channel.objects.filter(ref__in=[r for r in refs if r]).values_list("ref", "name")
        }
    except Exception:
        logger.warning("preorders.channel_labels_failed", exc_info=True)
        return {}


def _fallback_channel_label(ref: str | None) -> str:
    ref = str(ref or "")
    return _CHANNEL_FALLBACK_LABELS.get(ref, ref.capitalize())


def _date_display(day: date, today: date) -> str:
    if day == today:
        return "hoje"
    if day == today + timedelta(days=1):
        return "amanhã"
    if day == today - timedelta(days=1):
        return "ontem"
    return f"{str(formats.date_format(day, 'D')).lower()}, {formats.date_format(day, 'd/m')}"


def _money(value_q: int) -> str:
    return f"R$ {format_money(int(value_q or 0))}"
