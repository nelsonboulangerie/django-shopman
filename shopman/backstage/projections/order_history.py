"""Histórico do Gestor — pedidos que saíram do quadro (concluídos, cancelados, devolvidos).

Por que existe: o quadro do Gestor só mostra o que ainda pede gesto. Pedido
concluído ou cancelado sumia da tela, e achar "o pedido da Maria de terça, pago
no Pix" era Admin ou memória. Esta leitura é a lista paginada desses pedidos,
filtrada NO SERVIDOR (a casa tem milhares de pedidos; o cliente nunca recebe tudo).

Três regras moldam o formato:

1. **O momento do histórico é o de quando o pedido FECHOU** (concluído,
   cancelado ou devolvido), não o de quando entrou. É o que o gestor procura:
   "o que fechou ontem". Sem carimbo de fechamento, vale a última atualização.
2. **Venda de balcão do PDV fica de fora**, pela mesma régua do quadro
   (``is_pos_counter_order``): ela é do PDV e do caixa, e inundaria a lista.
3. **Cada recorte traz as opções com contagem** (``facets``), contadas com os
   OUTROS recortes aplicados e o próprio solto: marcar "Pix" não zera a
   contagem de "Cartão", que é justamente a próxima pergunta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q, TextField, Value
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.backstage.presentation.status import order_status_label, payment_method_label
from shopman.backstage.projections.order_queue import _format_customer_display

PAGE_SIZE = 30

#: Os estados finais que o histórico mostra, na ordem da tela.
HISTORY_STATUSES = ("completed", "cancelled", "returned")

#: Formas de pagamento conhecidas (chaves do ``Order.data.payment.method``).
#: As que não aparecem no período somem das opções; uma forma nova que apareça no
#: dado entra com o próprio rótulo do omotenashi.
KNOWN_PAYMENT_METHODS = ("pix", "card", "credit", "debit", "cash", "link", "mixed", "external", "account")

FULFILLMENT_LABELS = {"pickup": "Retirada", "delivery": "Entrega"}

#: Rótulo de valor vazio por recorte: o vazio é um valor filtrável ("sem forma").
NO_PAYMENT_VALUE = "none"
NO_PAYMENT_LABEL = "Não informado"

_STATUS_TONES = {"completed": "success", "cancelled": "danger", "returned": "warning"}


# ── Contrato ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HistoryFacetOption:
    value: str
    label: str
    count: int


@dataclass(frozen=True)
class HistoryFacet:
    # Chave do recorte na querystring: status, channel, payment, fulfillment.
    id: str
    label: str
    options: tuple[HistoryFacetOption, ...]


@dataclass(frozen=True)
class OrderHistoryRowProjection:
    ref: str
    status: str
    status_label: str
    # success | danger | warning — o app traduz em cor.
    status_tone: str
    channel_ref: str
    channel_label: str
    customer_label: str
    fulfillment: str
    fulfillment_label: str
    payment_method: str
    payment_label: str
    total_q: int
    total_display: str
    # ISO do fechamento, e o rótulo local curto ("03/10 14:32").
    closed_at: str
    closed_display: str


@dataclass(frozen=True)
class OrderHistoryProjection:
    date_from: str
    date_to: str
    query: str
    facets: tuple[HistoryFacet, ...]
    items: tuple[OrderHistoryRowProjection, ...]
    page: int
    page_size: int
    total: int
    has_next: bool
    # "48 pedidos" / "Nenhum pedido com esses filtros".
    total_label: str


@dataclass(frozen=True)
class HistoryFilters:
    date_from: date
    date_to: date
    statuses: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()
    payments: tuple[str, ...] = ()
    fulfillments: tuple[str, ...] = ()
    query: str = ""
    page: int = 1


# ── Leitura ───────────────────────────────────────────────────────────


def _day_start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def _base_queryset(filters: HistoryFilters):
    """Período + estados finais + fora o balcão. Os recortes vêm por cima."""
    qs = (
        Order.objects.filter(status__in=HISTORY_STATUSES)
        .annotate(
            # Coalesce: chave ausente vira "" e não NULL, senão o exclude abaixo
            # descartaria (NOT NULL = NULL) todo pedido que não veio do PDV.
            origin=Coalesce(KT("data__origin_channel"), Value(""), output_field=TextField()),
            pos_sales_mode=Coalesce(KT("data__pos__sales_mode"), Value(""), output_field=TextField()),
            closed_at=Coalesce("completed_at", "cancelled_at", "returned_at", "updated_at"),
            payment_method=Coalesce(KT("data__payment__method"), Value(""), output_field=TextField()),
            fulfillment=Coalesce(KT("data__fulfillment_type"), KT("data__delivery_method"), Value(""), output_field=TextField()),
        )
        .exclude(origin="pos", pos_sales_mode="counter")
        .filter(
            closed_at__gte=_day_start(filters.date_from),
            closed_at__lt=_day_start(filters.date_to + timedelta(days=1)),
        )
    )
    if filters.query:
        q = filters.query
        qs = qs.filter(
            Q(ref__icontains=q)
            | Q(external_ref__icontains=q)
            | Q(handle_ref__icontains=q)
            | Q(data__customer__name__icontains=q)
            | Q(data__customer__phone__icontains=q)
        )
    return qs


def _payment_q(values: tuple[str, ...]) -> Q:
    known = [value for value in values if value != NO_PAYMENT_VALUE]
    q = Q(payment_method__in=known) if known else Q(pk__in=[])
    if NO_PAYMENT_VALUE in values:
        q |= Q(payment_method="")
    return q


def _facet_filters(filters: HistoryFilters) -> dict[str, Q]:
    """Um ``Q`` por recorte ativo, para contar cada recorte com os outros aplicados."""
    out: dict[str, Q] = {}
    if filters.statuses:
        out["status"] = Q(status__in=filters.statuses)
    if filters.channels:
        out["channel"] = Q(channel_ref__in=filters.channels)
    if filters.payments:
        out["payment"] = _payment_q(filters.payments)
    if filters.fulfillments:
        out["fulfillment"] = Q(fulfillment__in=filters.fulfillments)
    return out


def _apply(qs, facet_qs: dict[str, Q], *, skip: str = ""):
    for key, q in facet_qs.items():
        if key != skip:
            qs = qs.filter(q)
    return qs


def _counts(qs, field: str) -> dict[str, int]:
    return {row[field] or "": row["n"] for row in qs.order_by().values(field).annotate(n=Count("pk"))}


def _channel_labels(refs) -> dict[str, str]:
    from shopman.shop.models import Channel

    names = dict(Channel.objects.filter(ref__in=list(refs)).values_list("ref", "name"))
    return {ref: (names.get(ref) or ref or "Sem canal") for ref in refs}


def _facets(base, facet_qs: dict[str, Q], filters: HistoryFilters) -> tuple[HistoryFacet, ...]:
    status_counts = _counts(_apply(base, facet_qs, skip="status"), "status")
    channel_counts = _counts(_apply(base, facet_qs, skip="channel"), "channel_ref")
    payment_counts = _counts(_apply(base, facet_qs, skip="payment"), "payment_method")
    fulfillment_counts = _counts(_apply(base, facet_qs, skip="fulfillment"), "fulfillment")

    status_options = tuple(
        HistoryFacetOption(value=status, label=order_status_label(status), count=status_counts.get(status, 0))
        for status in HISTORY_STATUSES
        if status != "returned" or status_counts.get(status) or status in filters.statuses
    )

    channel_refs = set(channel_counts) | set(filters.channels)
    channel_labels = _channel_labels(channel_refs)
    channel_options = tuple(
        sorted(
            (HistoryFacetOption(value=ref, label=channel_labels[ref], count=channel_counts.get(ref, 0)) for ref in channel_refs),
            key=lambda option: (-option.count, option.label.casefold()),
        )
    )

    payment_values = [method for method in KNOWN_PAYMENT_METHODS if payment_counts.get(method)]
    payment_values += sorted(m for m in payment_counts if m and m not in KNOWN_PAYMENT_METHODS)
    payment_values += [m for m in filters.payments if m not in payment_values and m != NO_PAYMENT_VALUE]
    payment_options = [
        HistoryFacetOption(value=method, label=payment_method_label(method), count=payment_counts.get(method, 0))
        for method in payment_values
    ]
    if payment_counts.get("") or NO_PAYMENT_VALUE in filters.payments:
        payment_options.append(
            HistoryFacetOption(value=NO_PAYMENT_VALUE, label=NO_PAYMENT_LABEL, count=payment_counts.get("", 0))
        )

    fulfillment_options = tuple(
        HistoryFacetOption(value=key, label=label, count=fulfillment_counts.get(key, 0))
        for key, label in FULFILLMENT_LABELS.items()
    )

    return (
        HistoryFacet(id="status", label="Situação", options=status_options),
        HistoryFacet(id="channel", label="Canal", options=channel_options),
        HistoryFacet(id="payment", label="Pagamento", options=tuple(payment_options)),
        HistoryFacet(id="fulfillment", label="Recebimento", options=fulfillment_options),
    )


def _row(order, channel_labels: dict[str, str]) -> OrderHistoryRowProjection:
    data = order.data or {}
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    customer_label = _format_customer_display(
        customer.get("name", "") or customer.get("phone", "") or data.get("customer_phone", "") or order.handle_ref or ""
    )
    method = order.payment_method or ""
    closed_local = timezone.localtime(order.closed_at)
    return OrderHistoryRowProjection(
        ref=order.ref,
        status=order.status,
        status_label=order_status_label(order.status),
        status_tone=_STATUS_TONES.get(order.status, "neutral"),
        channel_ref=order.channel_ref,
        channel_label=channel_labels.get(order.channel_ref, order.channel_ref),
        customer_label=customer_label,
        fulfillment=order.fulfillment or "",
        fulfillment_label=FULFILLMENT_LABELS.get(order.fulfillment or "", ""),
        payment_method=method,
        payment_label=payment_method_label(method) if method else NO_PAYMENT_LABEL,
        total_q=int(order.total_q or 0),
        total_display=f"R$ {format_money(int(order.total_q or 0))}",
        closed_at=closed_local.isoformat(),
        closed_display=closed_local.strftime("%d/%m %H:%M"),
    )


def build_order_history(filters: HistoryFilters) -> OrderHistoryProjection:
    page = max(int(filters.page or 1), 1)
    base = _base_queryset(filters)
    facet_qs = _facet_filters(filters)
    qs = _apply(base, facet_qs)

    total = qs.count()
    start = (page - 1) * PAGE_SIZE
    orders = list(qs.order_by("-closed_at", "-pk")[start:start + PAGE_SIZE])
    facets = _facets(base, facet_qs, filters)
    channel_labels = {option.value: option.label for option in facets[1].options}
    channel_labels.update(_channel_labels({order.channel_ref for order in orders} - set(channel_labels)))

    if total:
        total_label = "1 pedido" if total == 1 else f"{total} pedidos"
    elif facet_qs or filters.query:
        total_label = "Nenhum pedido com esses filtros"
    else:
        total_label = "Nenhum pedido fechado neste período"

    return OrderHistoryProjection(
        date_from=filters.date_from.isoformat(),
        date_to=filters.date_to.isoformat(),
        query=filters.query,
        facets=facets,
        items=tuple(_row(order, channel_labels) for order in orders),
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        has_next=start + PAGE_SIZE < total,
        total_label=total_label,
    )
