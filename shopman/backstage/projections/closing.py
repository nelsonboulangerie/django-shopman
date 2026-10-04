"""DayClosingProjection — read models for the day closing page (Fase 4).

Translates saleable stock, product classifications, and closing history into
immutable projections. Replaces the inline ``_build_items``
logic now consumed by ``shopman.backstage.admin_console.closing``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Sum
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import Quant

from shopman.backstage.models import DayClosing

logger = logging.getLogger(__name__)


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClosingItemProjection:
    """A single SKU row in the day closing form.

    A pele (badge/rótulo) é derivada de ``classification`` por cada superfície
    consumidora — a projection não carrega presentation.
    """

    sku: str
    name: str
    qty_available: int
    classification: str  # "keep" | "expired" | "mixed" — o LOTE decide (C4)
    qty_expiring: int  # em lotes vencendo hoje/vencidos (+ produto do dia sem lote)
    qty_nonconforming: int  # em lotes marcados — não vão para o dia seguinte


@dataclass(frozen=True)
class ClosingSnapshotItemProjection:
    """A single SKU row from a completed closing snapshot."""

    sku: str
    qty_remaining: int
    qty_kept: int
    qty_expired: int
    qty_nonconforming: int


@dataclass(frozen=True)
class ReconciliationError:
    """A discrepancy between what was sold and what was available on closing.

    Recorded in `DayClosing.data["reconciliation_errors"]` as a list of dicts
    matching this shape. The deficit is the qty sold beyond what stock +
    production could supply for that SKU.
    """

    sku: str
    sold_qty: int
    available_qty: int
    deficit_qty: int

    @classmethod
    def from_dict(cls, raw: dict) -> ReconciliationError:
        return cls(
            sku=str(raw.get("sku", "")),
            sold_qty=int(raw.get("sold", 0)),
            available_qty=int(raw.get("available", 0)),
            deficit_qty=int(raw.get("deficit", 0)),
        )


@dataclass(frozen=True)
class PendingProductionProjection:
    """An open WorkOrder surfaced at day closing (planned or started)."""

    ref: str
    output_sku: str
    recipe_name: str
    status: str  # "planned" | "started"
    status_label: str  # "Planejada" | "Em produção"
    quantity: str  # display (planned qty ou started qty)
    target_date: str  # ISO "2026-04-16" — a data que o link para a Produção precisa
    target_date_display: str  # "16/04"
    is_overdue: bool  # target_date < hoje


@dataclass(frozen=True)
class UpcomingPreorderRowProjection:
    """Encomendas confirmadas para uma data futura (WP-D).

    Informativo no fechamento: sai do estoque na data combinada — por isso NÃO
    entra na reconciliação do dia. Só a CONTAGEM de pedidos: o fechamento é
    cego para dinheiro (vendas, esperado, diferença), e o total em R$ das
    encomendas é venda. Quem audita valores é o relatório de caixa do Dono.
    """

    date: str  # ISO
    date_display: str  # "amanhã", "sáb, 19/07"
    orders_count: int


@dataclass(frozen=True)
class EpisodeOptionProjection:
    """Uma opção de resposta — o operador escolhe, não digita."""

    ref: str
    label: str
    hint: str


@dataclass(frozen=True)
class PendingEpisodeProjection:
    """Algo estranho que o sistema notou e ainda ninguém explicou.

    O texto do sinal é o que o sistema MEDIU; o motivo vem das opções. A
    pergunta só aparece quando há sinal — nada de formulário em branco todo dia.
    """

    id: int
    signal: str          # "nenhuma venda entre 14h e 16h"
    window_display: str  # "14:05 → 16:20"


@dataclass(frozen=True)
class DayClosingProjection:
    """Top-level read model for the day closing page."""

    today: str  # ISO date
    today_display: str  # "16/04/2026"
    items: tuple[ClosingItemProjection, ...]
    has_items: bool
    already_closed: bool
    existing_closing_display: str  # "" if not closed, "Fechado por X às HH:MM"
    total_available: int
    production_summary: dict
    reconciliation_errors: tuple[ReconciliationError, ...]
    pending_production: tuple[PendingProductionProjection, ...]
    has_pending_production: bool
    upcoming_preorders: tuple[UpcomingPreorderRowProjection, ...] = ()
    has_upcoming_preorders: bool = False
    pending_episodes: tuple[PendingEpisodeProjection, ...] = ()
    episode_options: tuple[EpisodeOptionProjection, ...] = ()
    has_pending_episodes: bool = False
    # A forma do movimento por hora, hoje × o mesmo dia da semana típico (v4
    # "Explicar o dia estranho"): só a FORMA, valores relativos de 0 a 1, nunca
    # reais nem contagem. ``{hours, today, typical, typical_label, drop_after}``;
    # vazio quando não há histórico para comparar.
    hourly_shape: dict | None = None
    # Quem está fechando ("Admin · gerência"), para o chip do cabeçalho do corredor.
    operator_display: str = ""


# ── Builder ────────────────────────────────────────────────────────────


def build_day_closing() -> DayClosingProjection:
    """Build the day closing projection for today."""
    today = timezone.localdate()
    existing = DayClosing.objects.filter(date=today).first()

    items = _build_items()
    total_available = sum(it.qty_available for it in items)

    closing_display = ""
    production_summary = _today_production_summary(today)
    reconciliation_errors: tuple[ReconciliationError, ...] = ()
    if existing:
        by = existing.closed_by.get_username() if existing.closed_by else "?"
        at = existing.closed_at.strftime("%H:%M") if existing.closed_at else ""
        closing_display = f"Fechado por {by} às {at}"
        production_summary = _closing_data(existing).get("production_summary") or production_summary
        raw_errors = _closing_data(existing).get("reconciliation_errors") or ()
        reconciliation_errors = tuple(
            ReconciliationError.from_dict(raw) if isinstance(raw, dict) else raw
            for raw in raw_errors
        )

    pending_production = _pending_production(today)
    upcoming_preorders = _upcoming_preorders(today)

    pending_episodes = _pending_episodes(today)

    return DayClosingProjection(
        today=today.isoformat(),
        today_display=today.strftime("%d/%m/%Y"),
        items=tuple(items),
        has_items=bool(items),
        already_closed=existing is not None,
        existing_closing_display=closing_display,
        total_available=total_available,
        production_summary=production_summary,
        reconciliation_errors=reconciliation_errors,
        pending_production=pending_production,
        has_pending_production=bool(pending_production),
        upcoming_preorders=upcoming_preorders,
        has_upcoming_preorders=bool(upcoming_preorders),
        pending_episodes=pending_episodes,
        episode_options=_episode_options() if pending_episodes else (),
        has_pending_episodes=bool(pending_episodes),
        hourly_shape=_hourly_shape(today),
    )


SHAPE_HOURS = tuple(range(7, 20))
_WEEKDAY_TYPICAL = (
    "segunda típica", "terça típica", "quarta típica", "quinta típica",
    "sexta típica", "sábado típico", "domingo típico",
)


def _orders_by_hour(day) -> dict[int, int]:
    from django.db.models import Count
    from django.db.models.functions import ExtractHour
    from shopman.orderman.models import Order

    rows = (
        Order.objects.filter(created_at__date=day)
        .exclude(status="cancelled")
        .annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(n=Count("id"))
    )
    return {int(row["hour"]): int(row["n"]) for row in rows if row["hour"] is not None}


def _hourly_shape(today) -> dict | None:
    """Hoje × o mesmo dia da semana nas últimas 4 semanas, por hora, só a forma.

    Às cegas (fim do dia não mostra dinheiro): as duas séries saem divididas pelo
    maior valor do dia típico, então o que se lê é "a curva de hoje desceu
    antes", nunca quanto. ``drop_after`` é a primeira hora a partir da qual hoje
    fica abaixo de metade do típico até o fim (o "caiu depois das 14h").
    """
    from datetime import timedelta

    try:
        today_counts = _orders_by_hour(today)
        past = [_orders_by_hour(today - timedelta(days=7 * week)) for week in range(1, 5)]
    except Exception:
        logger.debug("closing_hourly_shape_failed", exc_info=True)
        return None
    past = [counts for counts in past if counts]
    if not past:
        return None
    typical = [sum(c.get(h, 0) for c in past) / len(past) for h in SHAPE_HOURS]
    peak = max(typical) or 0
    if peak <= 0:
        return None
    now_hour = timezone.localtime().hour if today == timezone.localdate() else 24
    today_series = [round(today_counts.get(h, 0) / peak, 3) if h <= now_hour else None for h in SHAPE_HOURS]
    typical_series = [round(v / peak, 3) for v in typical]
    drop_after = ""
    for index, hour in enumerate(SHAPE_HOURS):
        tail = [
            (t, ty) for t, ty in zip(today_series[index:], typical_series[index:], strict=False)
            if t is not None and ty >= 0.15
        ]
        if len(tail) >= 2 and all(t < ty * 0.5 for t, ty in tail) and index > 0:
            drop_after = f"{hour}h"
            break
    return {
        "hours": [f"{h}h" for h in SHAPE_HOURS],
        "today": today_series,
        "typical": typical_series,
        "typical_label": _WEEKDAY_TYPICAL[today.weekday()],
        "drop_after": drop_after,
    }


# ── Internals ──────────────────────────────────────────────────────────


def _pending_episodes(day) -> tuple:
    """O que o sistema notou e ainda ninguém explicou.

    Vazio na esmagadora maioria dos dias — a pergunta só aparece quando houve
    sinal, e é isso que a mantém respondível.
    """
    from shopman.backstage.services.episodes import pending_for_day

    rows = []
    for episode in pending_for_day(day):
        start = timezone.localtime(episode.started_at)
        end = timezone.localtime(episode.ended_at) if episode.ended_at else None
        rows.append(
            PendingEpisodeProjection(
                id=episode.pk,
                signal=episode.detected_signal,
                window_display=(
                    f"{start:%H:%M} → {end:%H:%M}" if end else f"desde {start:%H:%M}"
                ),
            )
        )
    return tuple(rows)


def _episode_options() -> tuple:
    """As opções de resposta, do catálogo — escolher, nunca digitar."""
    from shopman.backstage.models import OperationEpisodeKind

    return tuple(
        EpisodeOptionProjection(ref=kind.ref, label=kind.label, hint=kind.hint)
        for kind in OperationEpisodeKind.objects.filter(is_active=True)
    )


def _build_items() -> list[ClosingItemProjection]:
    """SKUs PRODUZIDOS NA CASA com estoque vendável — o que se conta no fechamento.

    ⚠️ Só entra o que tem ficha ativa (``sku_roles_map(...).produced``). A
    revenda (o pote de geleia, o chá em lata, a água) não se conta todo dia:
    não vence de um dia para o outro, o estoque dela anda pela venda e pelo
    recebimento, e contá-la toda noite era a lista que o operador pulava
    digitando qualquer coisa — contagem cega que ninguém faz de verdade é
    pior que contagem nenhuma. Decisão do dono, 25/09/2026.
    """
    from shopman.shop.services.sku_records import sku_roles_map

    quants = list(
        Quant.objects.filter(
            position__is_saleable=True,
            _quantity__gt=0,
        )
        .values("sku")
        .annotate(total_qty=Sum("_quantity"))
        .order_by("sku")
    )
    roles = sku_roles_map(row["sku"] for row in quants)
    quants = [row for row in quants if roles.get(row["sku"]) and roles[row["sku"]].produced]

    from shopman.backstage.services.closing import (
        day_product_expires_on_close,
        expired_lot_refs,
        nonconforming_lot_refs,
    )

    today = timezone.localdate()
    items: list[ClosingItemProjection] = []
    for row in quants:
        sku = row["sku"]
        qty = row["total_qty"]

        try:
            product = Product.objects.get(sku=sku)
        except Product.DoesNotExist:
            product = None

        name = product.name if product else sku

        # O LOTE decide o destino da sobra (C4): mesma lei do
        # perform_day_closing, importada de lá — uma pergunta, um dono.
        bad_lots = nonconforming_lot_refs(sku)
        dying_lots = expired_lot_refs(sku, today)
        batchless_dies = day_product_expires_on_close(sku)
        qty_nonconforming = 0
        qty_expiring = 0
        for quant in Quant.objects.filter(
            sku=sku, position__is_saleable=True, _quantity__gt=0,
        ):
            amount = int(quant._quantity)
            if quant.batch and quant.batch in bad_lots:
                qty_nonconforming += amount
            elif (quant.batch and quant.batch in dying_lots) or (
                not quant.batch and batchless_dies
            ):
                qty_expiring += amount

        dying_total = qty_expiring + qty_nonconforming
        if dying_total == 0:
            classification = "keep"
        elif dying_total >= int(qty):
            classification = "expired"
        else:
            classification = "mixed"

        items.append(
            ClosingItemProjection(
                sku=sku,
                name=name,
                qty_available=int(qty),
                classification=classification,
                qty_expiring=qty_expiring,
                qty_nonconforming=qty_nonconforming,
            )
        )

    return items



def _closing_data(closing: DayClosing) -> dict:
    if isinstance(closing.data, dict):
        return closing.data
    return {"items": closing.data or [], "production_summary": {}, "reconciliation_errors": []}


def _pending_production(today: date) -> tuple[PendingProductionProjection, ...]:
    """WOs abertas (planned/started) até hoje — o fechamento acusa, não bloqueia."""
    try:
        from shopman.craftsman.models import WorkOrder

        status_labels = {
            WorkOrder.Status.PLANNED: "Planejada",
            WorkOrder.Status.STARTED: "Em produção",
        }
        rows = []
        qs = (
            WorkOrder.objects.filter(
                status__in=(WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED),
                target_date__lte=today,
            )
            .select_related("recipe")
            .order_by("status", "target_date", "ref")
        )
        for wo in qs:
            qty = wo.started_qty if wo.status == WorkOrder.Status.STARTED else wo.quantity
            rows.append(
                PendingProductionProjection(
                    ref=wo.ref,
                    output_sku=wo.output_sku,
                    recipe_name=wo.recipe.name or wo.recipe.ref,
                    status=str(wo.status),
                    status_label=status_labels.get(wo.status, str(wo.status)),
                    quantity=str(qty or wo.quantity),
                    target_date=wo.target_date.isoformat() if wo.target_date else "",
                    target_date_display=wo.target_date.strftime("%d/%m") if wo.target_date else "",
                    is_overdue=bool(wo.target_date and wo.target_date < today),
                )
            )
        return tuple(rows)
    except Exception:
        logger.debug("closing.pending_production_failed", exc_info=True)
        return ()


def _upcoming_preorders(today: date) -> tuple[UpcomingPreorderRowProjection, ...]:
    """Encomendas vivas para datas futuras, agregadas por data combinada.

    ⚠️ Conta TODA encomenda a confirmar ou confirmada (``new``/``accepted``) com
    data combinada depois de hoje, qualquer que seja o dia em que foi feita — e
    não "as vendidas hoje", como a tela chegou a dizer. O fechamento informa
    para o operador saber o que já está comprometido nos próximos dias.
    """
    try:
        from shopman.orderman.models import Order

        from shopman.shop.services.order_helpers import get_commitment_date

        by_date: dict[date, int] = {}
        orders = (
            Order.objects.filter(
                status__in=("new", "accepted"),
                data__delivery_date__gt=today.isoformat(),
            )
        )
        for order in orders:
            commitment = get_commitment_date(order)
            if commitment is None or commitment <= today:
                continue
            by_date[commitment] = by_date.get(commitment, 0) + 1

        return tuple(
            UpcomingPreorderRowProjection(
                date=commitment.isoformat(),
                date_display=_upcoming_date_display(commitment, today),
                orders_count=by_date[commitment],
            )
            for commitment in sorted(by_date)
        )
    except Exception:
        logger.debug("closing.upcoming_preorders_failed", exc_info=True)
        return ()


def _upcoming_date_display(commitment: date, today: date) -> str:
    from django.utils import formats

    if commitment == today + timedelta(days=1):
        return "amanhã"
    return f"{formats.date_format(commitment, 'D')}, {formats.date_format(commitment, 'd/m')}"


def _today_production_summary(selected_date: date) -> dict:
    """Prévia do resumo que o fechamento vai persistir — a MESMA conta.

    Era uma cópia divergente (sem qualidade, truncando fracionários); a fonte
    única é ``services.closing.production_summary``.
    """
    try:
        from shopman.backstage.services.closing import production_summary

        return production_summary(selected_date)
    except Exception:
        logger.debug("closing.production_summary_failed", exc_info=True)
        return {}
