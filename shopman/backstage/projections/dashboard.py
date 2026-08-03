"""DashboardProjection — read models for the admin dashboard.

O dashboard do Admin é uma landing de configuração e auditoria: a operação ao
vivo (pedidos, produção) mora nos apps Nuxt (Gestor/PDV/KDS/Produção). Aqui
ficam apenas os dados de atenção/auditoria: alertas de estoque, alertas do
operador e o estoque D-1 pendente de fechamento.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

logger = logging.getLogger(__name__)


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StockAlertRowProjection:
    """A stock alert row."""

    sku: str
    current: str
    minimum: str
    deficit: str
    position: str


@dataclass(frozen=True)
class D1StockRowProjection:
    """A D-1 stock row."""

    sku: str
    name: str
    qty: str
    entry_date_display: str


@dataclass(frozen=True)
class OperatorAlertProjection:
    """An unacknowledged operator alert."""

    pk: int
    type: str
    severity: str
    message: str
    order_ref: str
    created_at_display: str


@dataclass(frozen=True)
class RatingRowProjection:
    """One recent customer rating — stars + comment for the dashboard."""

    rating: int
    stars: str
    comment: str
    order_ref: str
    submitted_at_display: str
    is_low: bool


@dataclass(frozen=True)
class DashboardProjection:
    """Top-level read model for the admin dashboard (config + auditoria)."""

    stock_alerts: tuple[StockAlertRowProjection, ...]
    kpi_stock_alerts: int
    kpi_operator_alerts: int
    d1_stock: tuple[D1StockRowProjection, ...]
    operator_alerts: tuple[OperatorAlertProjection, ...]
    # Avaliações do cliente: agregado (média móvel + contagens) e os últimos
    # comentários. Fecha o loop — a nota escrita no storefront finalmente é lida.
    rating_average: str
    rating_count: int
    rating_low_count: int
    recent_ratings: tuple[RatingRowProjection, ...]


# ── Builder ────────────────────────────────────────────────────────────


def build_dashboard() -> DashboardProjection:
    """Build the admin dashboard projection."""
    stock_alerts = _stock_alerts()
    d1_stock = _d1_stock()
    operator_alerts = _operator_alerts()
    rating_average, rating_count, rating_low_count, recent_ratings = _customer_ratings()

    return DashboardProjection(
        stock_alerts=tuple(stock_alerts),
        kpi_stock_alerts=len(stock_alerts),
        kpi_operator_alerts=len(operator_alerts),
        d1_stock=tuple(d1_stock),
        operator_alerts=tuple(operator_alerts),
        rating_average=rating_average,
        rating_count=rating_count,
        rating_low_count=rating_low_count,
        recent_ratings=tuple(recent_ratings),
    )


# ── Row builders ───────────────────────────────────────────────────────


def _stock_alerts() -> list[StockAlertRowProjection]:
    try:
        from shopman.stockman.models import Quant, StockAlert
    except ImportError:
        return []

    alerts = StockAlert.objects.filter(is_active=True)
    rows: list[StockAlertRowProjection] = []
    for alert in alerts[:10]:
        quant_qs = Quant.objects.filter(sku=alert.sku)
        if alert.position_id:
            quant_qs = quant_qs.filter(position=alert.position)

        total_qty = quant_qs.aggregate(total=Sum("_quantity"))["total"] or Decimal("0")

        if total_qty < alert.min_quantity:
            rows.append(StockAlertRowProjection(
                sku=alert.sku,
                current=str(total_qty),
                minimum=str(alert.min_quantity),
                deficit=str(alert.min_quantity - total_qty),
                position=str(alert.position) if alert.position else "Todas",
            ))

    return rows


def _d1_stock() -> list[D1StockRowProjection]:
    try:
        from shopman.stockman import Move, Position, Quant
    except ImportError:
        return []

    from django.utils.formats import date_format

    ontem_pos = Position.objects.filter(ref="ontem").first()
    if not ontem_pos:
        return []

    quants = Quant.objects.filter(position=ontem_pos, _quantity__gt=0)
    if not quants.exists():
        return []

    rows: list[D1StockRowProjection] = []
    for quant in quants:
        last_move = (
            Move.objects.filter(quant=quant, reason__startswith="d1:")
            .order_by("-timestamp")
            .first()
        )
        entry_date = last_move.timestamp.date() if last_move else None

        try:
            from shopman.offerman.models import Product
            product = Product.objects.get(sku=quant.sku)
            name = product.name
        except Exception:
            logger.debug("d1_stock_product_lookup_failed sku=%s", quant.sku, exc_info=True)
            name = quant.sku

        rows.append(D1StockRowProjection(
            sku=quant.sku,
            name=name,
            qty=str(quant._quantity),
            entry_date_display=date_format(entry_date, "d/m") if entry_date else "—",
        ))

    return rows


def _customer_ratings() -> tuple[str, int, int, list[RatingRowProjection]]:
    """Aggregate customer ratings for the dashboard.

    Média móvel + últimos comentários sobre uma janela recente (as últimas
    avaliações), lendo direto de ``Order.data["customer_rating"]`` — a nota
    escrita pelo storefront finalmente vira leitura para a loja.
    """
    try:
        from django.utils.dateparse import parse_datetime
        from django.utils.formats import date_format
        from shopman.orderman.models import Order
    except ImportError:
        return "—", 0, 0, []

    # Janela recente: as avaliações são raras, mas varrer todo o histórico não
    # escala. As últimas 200 (por criação do pedido) dão uma média móvel honesta
    # e barata. A nota int mora em data.customer_rating.rating (>=1 filtra os
    # pedidos que têm nota, robusto em SQLite e Postgres).
    rated = (
        Order.objects.filter(data__customer_rating__rating__gte=1)
        .order_by("-created_at")[:200]
    )

    scores: list[int] = []
    rows: list[RatingRowProjection] = []
    for order in rated:
        rating_data = (order.data or {}).get("customer_rating") or {}
        score = rating_data.get("rating")
        if not isinstance(score, int) or score < 1 or score > 5:
            continue
        scores.append(score)
        submitted_at = parse_datetime(str(rating_data.get("submitted_at") or "")) or None
        rows.append(RatingRowProjection(
            rating=score,
            stars="★" * score + "☆" * (5 - score),
            comment=str(rating_data.get("comment") or "").strip(),
            order_ref=order.ref,
            submitted_at_display=date_format(submitted_at, "d/m H:i") if submitted_at else "—",
            is_low=score <= 2,
        ))

    if not scores:
        return "—", 0, 0, []

    average = sum(scores) / len(scores)
    low_count = sum(1 for s in scores if s <= 2)
    # ``rows`` já vem em ordem decrescente de criação do pedido (a query ordena
    # por -created_at), então os primeiros são os mais recentes — os "últimos
    # comentários". Sem re-sort pela string "d/m H:i", que não ordena no tempo.
    return f"{average:.1f}", len(scores), low_count, rows[:8]


def _operator_alerts() -> list[OperatorAlertProjection]:
    try:
        from django.utils.formats import date_format

        from shopman.backstage.models import OperatorAlert

        qs = OperatorAlert.objects.filter(acknowledged=False).order_by("-created_at")[:20]
        return [
            OperatorAlertProjection(
                pk=a.id,
                type=a.type,
                severity=a.severity,
                message=a.message,
                order_ref=a.order_ref or "",
                created_at_display=date_format(a.created_at, "d/m H:i") if a.created_at else "—",
            )
            for a in qs
        ]
    except Exception:
        logger.debug("operator_alerts_load_failed", exc_info=True)
        return []
