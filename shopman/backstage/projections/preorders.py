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


def build_preorder_detail(ref: str) -> PreorderDetailProjection | None:
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
    balance_q = _balance_q(order, total_q, reads)
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


def _balance_q(order, total_q: int, reads) -> int | None:
    """O que falta receber: total efetivo menos o que entrou, nunca negativo.

    - **iFood**: a prova é o payload do iFood (``payments``), não o Payman — a
      casa não cobra o pedido do marketplace. Pré-pago é saldo zero; pendente é
      o ``pending_q`` que ainda se cobra na porta; sem evidência, ``None``.
    - **Demais canais**: soma de TODOS os intents do pedido (venda mista tem um
      por método) pelo Payman. Tender "na conta da casa" já é obrigação
      reconhecida do cliente — cobrá-lo de novo no balcão seria cobrar duas
      vezes —, então ele abate o saldo como se tivesse entrado.
    """
    from shopman.shop.services import payment as payment_svc

    data = order.data or {}
    if order.channel_ref == "ifood":
        from shopman.shop.services.ifood_ingest import payment_status_from_payload

        payments = (data.get("ifood") or {}).get("payments") or {}
        status = payment_status_from_payload(payments, int(order.total_q or 0))
        if status == "paid":
            return 0
        if status == "pending":
            pending_q = int(payments.get("pending_q") or 0)
            return max(0, min(total_q, pending_q) if pending_q > 0 else total_q)
        return None

    captured = payment_svc.captured_balance_from_reads(order, reads)
    if captured is None:
        return None
    return max(0, total_q - captured - _on_account_q(order, total_q))


def _on_account_q(order, total_q: int) -> int:
    payment_data = (order.data or {}).get("payment") or {}
    tenders = [t for t in payment_data.get("tenders") or [] if isinstance(t, dict)]
    if tenders:
        return sum(int(t.get("amount_q") or 0) for t in tenders if t.get("method") == "account")
    return total_q if payment_data.get("method") == "account" else 0


def _payment_state(order, balance_q: int | None, total_q: int) -> str:
    """O estado do dinheiro, independente da mercadoria (:data:`PAYMENT_STATES`)."""
    if balance_q is None:
        return "check"
    if balance_q > 0:
        return "to_receive"
    if total_q > 0 and _on_account_q(order, total_q) > 0:
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
