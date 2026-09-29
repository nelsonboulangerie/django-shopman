"""B.I. de clientes — leitura analítica (ADR-021, BI-PLAN §5/F4).

Distribuição RFM e agregados do ``CustomerInsight`` (o agregado materializado
que o guestman JÁ mantém — o B.I. só lê, nunca recalcula) e novos clientes
por semana a partir de ``Customer.created_at``.

Só cliente ATIVO entra em qualquer número daqui. A unificação de cadastros
(``MergeService.merge``) não apaga o doador: desativa (``is_active=False``) e
deixa o ``CustomerInsight`` dele parado no retrato de antes. Contá-lo é contar a
mesma pessoa duas vezes — no segmento RFM, no ticket médio, no "em risco" e no
total. O undo reativa o doador, e aí ele volta a contar sozinho.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class BICustomerSegmentRow:
    segment: str
    customers: int


@dataclass(frozen=True)
class BICustomersWeekRow:
    week_start: str  # segunda-feira, ISO
    new_customers: int


@dataclass(frozen=True)
class BICustomersReport:
    date_from: str
    date_to: str
    segments: tuple[BICustomerSegmentRow, ...]
    new_by_week: tuple[BICustomersWeekRow, ...]
    customers_total: int
    with_insight: int
    at_risk: int
    average_ticket_q: int


def build_bi_customers(
    *, date_from: date | None = None, date_to: date | None = None
) -> BICustomersReport:
    from shopman.guestman.contrib.insights.models import RFM_SEGMENTS, CustomerInsight
    from shopman.guestman.models import Customer

    from .bi_production import _normalize_window

    date_from, date_to = _normalize_window(date_from, date_to)

    insights = list(
        CustomerInsight.objects.filter(customer__is_active=True).values_list(
            "rfm_segment", "average_ticket_q", "total_orders", "churn_risk"
        )
    )
    segment_counts: dict[str, int] = defaultdict(int)
    tickets = []
    at_risk = 0
    for segment, average_ticket_q, total_orders, churn_risk in insights:
        if segment:
            segment_counts[segment] += 1
        if total_orders:
            tickets.append(average_ticket_q)
        # Mesmo limiar de CustomerInsight.is_at_risk — uma pergunta, um dono.
        if churn_risk is not None and churn_risk > Decimal("0.7"):
            at_risk += 1

    known_segments = tuple(ref for ref, _label in RFM_SEGMENTS)
    segments = tuple(
        BICustomerSegmentRow(segment=segment, customers=segment_counts[segment])
        for segment in (*known_segments, *sorted(set(segment_counts) - set(known_segments)))
        if segment_counts.get(segment)
    )

    week_counts: dict[date, int] = defaultdict(int)
    active_customers = Customer.objects.filter(is_active=True)
    # Novos por semana também só contam ativos. O cadastro absorvido nasceu de
    # verdade naquela semana, mas a unificação disse que ele era a mesma pessoa
    # de outro cadastro — que já é contado na semana em que ELE nasceu. Contar
    # os dois é inventar um cliente novo. (Consequência aceita: unificar hoje
    # pode baixar a contagem de uma semana passada; é a correção, não deriva.)
    created = active_customers.filter(
        created_at__date__range=(date_from, date_to)
    ).values_list("created_at", flat=True)
    for created_at in created:
        day = created_at.date()
        week_counts[day - timedelta(days=day.weekday())] += 1

    return BICustomersReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        segments=segments,
        new_by_week=tuple(
            BICustomersWeekRow(week_start=week.isoformat(), new_customers=week_counts[week])
            for week in sorted(week_counts)
        ),
        customers_total=active_customers.count(),
        with_insight=len(insights),
        at_risk=at_risk,
        average_ticket_q=sum(tickets) // len(tickets) if tickets else 0,
    )
