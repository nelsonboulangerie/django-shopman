"""
Query service — suggest, needs, expected.

Read-only operations. All @classmethod (mixin pattern).
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum

logger = logging.getLogger(__name__)


@dataclass
class Need:
    """Material need from BOM explosion."""
    item_ref: str
    quantity: Decimal
    unit: str
    has_recipe: bool
    #: Margem de segurança do rendimento, quando pedida e aplicável — já SOMADA
    #: em ``quantity``. Fica aqui separada porque a tela precisa dizer POR QUE
    #: aqueles gramas a mais existem; número que cresce sozinho é o que esta
    #: casa não aceita. ``None`` = a linha não recebeu margem.
    margin: object | None = None


@dataclass
class Suggestion:
    """Production suggestion for a date."""
    recipe: object  # Recipe instance
    quantity: Decimal
    basis: dict = field(default_factory=dict)


@dataclass
class CraftQueueItem:
    """Operational queue row for the production floor."""

    ref: str
    recipe_ref: str
    output_sku: str
    status: str
    target_date: object
    position_ref: str
    operator_ref: str
    planned_qty: Decimal
    started_qty: Decimal | None
    finished_qty: Decimal | None
    loss_qty: Decimal | None
    yield_rate: Decimal | None


@dataclass
class CraftSummary:
    """Operational summary for a floor/date slice."""

    total_orders: int = 0
    planned_orders: int = 0
    started_orders: int = 0
    finished_orders: int = 0
    void_orders: int = 0
    planned_qty: Decimal = Decimal("0")
    started_qty: Decimal = Decimal("0")
    finished_qty: Decimal = Decimal("0")
    loss_qty: Decimal = Decimal("0")


class CraftQueries:
    """Read-only query methods."""

    @classmethod
    def expected(cls, output_sku, date):
        """
        Sum of active WorkOrder quantities for output_sku on date.

        Used by the availability system (spec 016).

        Returns:
            Decimal — total planned quantity.
        """
        from shopman.craftsman.models import WorkOrder

        result = WorkOrder.objects.filter(
            output_sku=output_sku,
            status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED],
            target_date=date,
        ).aggregate(total=Sum("quantity"))
        return result["total"] or Decimal("0")

    @classmethod
    def needs(cls, date, expand=False, *, yield_margin=False):
        """
        BOM explosion for a date. Returns material needs.

        Args:
            date: production date
            expand: if True, recursively expand sub-recipes to raw materials
            yield_margin: se ``True``, soma a margem de segurança do rendimento
                das massas (ver ``services.yield_margin``). **Opt-in de
                propósito** — ver a nota abaixo.

        Returns:
            list[Need] — aggregated material needs.

        **Onde a margem entra, e por quê aqui.** A margem é decisão de
        PRODUÇÃO — "quanto de massa fazer hoje" —, não da ficha: a ficha diz a
        proporção (300 g de farinha para cada quilo de massa) e essa proporção
        não muda porque a balança tem divisão de 2 g. Por isso ela **não** toca
        ``Recipe``/``RecipeItem``, e entra aqui, na consulta de planejamento
        que já faz a caminhada do BOM e já é o que a lista de separação lê.

        E, principalmente, **ela não entra no consumo do ledger**. O consumo é
        FATO, e nasce em outro lugar: ``CraftExecution.finish`` congela os
        ``WorkOrderItem`` de consumo a partir do snapshot da ficha, e
        ``contrib.stockman.handlers._consume_materials`` baixa exatamente essas
        linhas. Nenhum dos dois passa por ``needs()``. Se a margem escorresse
        para lá, o sistema debitaria todo dia mais insumo do que o padeiro usou
        e a sugestão de compra nasceria inflada — erro silencioso, que só
        apareceria no inventário meses depois.

        A margem é orçada **por preparo, na fornada** (não por peça e não por
        work order): duas ordens que dividem a mesma Massa Tradição são UMA
        mistura na masseira, então a perda da masseira entra uma vez e o
        colchão de variância é o da soma das peças.

        Com ``expand=True`` a margem é aplicada ANTES da explosão, então ela
        cascateia para a matéria-prima: fazer 3% mais massa de fato pede 3%
        mais farinha. Nesse modo a linha do preparo deixa de existir (foi
        explodida), então o motivo não tem onde aparecer por linha — quem
        mostra a explicação é a projection, no cabeçalho.
        """
        from shopman.craftsman.models import WorkOrder

        orders = WorkOrder.objects.filter(
            status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED],
            target_date=date,
        ).select_related("recipe").prefetch_related("recipe__items")

        # Necessidade IMEDIATA (um nível de BOM), agregada por (insumo, unidade).
        # Agregar antes de explodir é o que permite orçar a margem na fornada
        # inteira do preparo, em vez de uma margem por work order.
        immediate: dict[tuple[str, str], Decimal] = {}
        pieces: dict[tuple[str, str], Decimal] = {}

        for wo in orders:
            recipe = wo.recipe
            coefficient = wo.quantity / recipe.batch_size
            counted_output = _is_counted_output(recipe)
            for ri in recipe.items.filter(is_optional=False).order_by("sort_order"):
                key = (ri.input_sku, ri.unit)
                immediate[key] = immediate.get(key, Decimal("0")) + ri.quantity * coefficient
                if yield_margin and counted_output and _margin_applies(ri):
                    pieces[key] = pieces.get(key, Decimal("0")) + Decimal(str(wo.quantity))

        margins = _yield_margins(pieces) if yield_margin else {}
        for key, margin in margins.items():
            immediate[key] += margin.total

        aggregated = {}
        for (item_ref, unit), quantity in immediate.items():
            if expand:
                for sub_ref, sub_qty, sub_unit in _expand_bom(item_ref, quantity, unit):
                    _aggregate(aggregated, sub_ref, sub_qty, sub_unit)
            else:
                _aggregate(aggregated, item_ref, quantity, unit, margin=margins.get((item_ref, unit)))

        return list(aggregated.values())

    @classmethod
    def suggest(
        cls,
        date,
        output_skus=None,
        *,
        season_months: list | None = None,
        high_demand_multiplier: Decimal | None = None,
        safety_pct: Decimal | None = None,
        exclude_dates: frozenset | None = None,
        selling_window=None,
    ):
        """
        Suggest production quantities for a date.

        Args:
            date: production date. Também é a âncora do recorte por
                  dia-da-semana no histórico: planejar sábado olha sábados.
            output_skus: optional list of output_sku strings to filter recipes.
                         If None, all active recipes are considered.
            season_months: optional list of month ints to filter history by season.
                           e.g. [10, 11, 12, 1, 2, 3] for hot season.
                           If None, all history months are used.
            high_demand_multiplier: if provided and the date falls on Friday (4) or
                                    Saturday (5), multiply suggested qty by this factor.
            safety_pct: optional safety-margin override applied over
                        (avg_demand + committed). If None, the
                        SAFETY_STOCK_PERCENT setting is used.
            exclude_dates: dias que não entram na amostra (loja fechada,
                           feriado). Quem conhece o calendário é o
                           orquestrador; o core só recebe a lista.
            selling_window: par (abre, fecha) usado para extrapolar a demanda
                           dos dias que esgotaram. Sem ele, dia esgotado conta
                           o que vendeu e nada é inventado.

        Algorithm:
            For each active Recipe (optionally filtered by output_skus):
            1. Get historical demand via DemandProtocol.history()
            2. Filter by season_months if provided
            3. Estimate true demand (extrapolate if soldout_at set)
            4. confidence = "high" / "medium" / "low" based on sample_size
            5. avg_demand = average of estimates
            6. Apply waste adjustment if waste_rate > 15%
            7. committed = DemandProtocol.committed(output_sku, date)
            8. quantity = (avg_demand + committed) * (1 + SAFETY_STOCK_PERCENT)
            9. Apply high_demand_multiplier on Fri/Sat if provided

        Returns [] if DEMAND_BACKEND is not configured.
        """
        from shopman.craftsman.conf import get_setting
        from shopman.craftsman.models import Recipe

        backend_path = get_setting("DEMAND_BACKEND")
        if not backend_path:
            return []

        try:
            from django.utils.module_loading import import_string

            backend = import_string(backend_path)()
        except Exception:
            logger.warning("Failed to load DEMAND_BACKEND: %s", backend_path)
            return []

        if safety_pct is None:
            safety_pct = get_setting("SAFETY_STOCK_PERCENT")
        historical_days = get_setting("HISTORICAL_DAYS")
        same_weekday = get_setting("SAME_WEEKDAY_ONLY")
        exclude_dates = frozenset(exclude_dates or ())

        suggestions = []
        recipes = Recipe.objects.filter(is_active=True)
        if output_skus:
            recipes = recipes.filter(output_sku__in=output_skus)
        for recipe in recipes:
            history = backend.history(
                recipe.output_sku,
                days=historical_days,
                same_weekday=same_weekday,
                target_date=date,
                exclude_dates=exclude_dates,
            )

            if not history:
                continue

            # Filter by season if provided
            if season_months:
                history = [dd for dd in history if dd.date.month in season_months]

            # Estimate true demand for each historical day
            estimates = [_estimate_demand(dd, selling_window) for dd in history]

            # Confidence based on sample size
            confidence = _calc_confidence(len(estimates))
            if confidence is None:
                # Not enough data — skip this recipe
                continue

            avg_demand = sum(estimates) / len(estimates)

            # Waste adjustment: if waste_rate > 15%, reduce proportionally
            total_sold = sum(dd.sold for dd in history)
            total_wasted = sum(dd.wasted for dd in history)
            waste_rate: Decimal | None = None
            if total_sold > 0 and total_wasted > 0:
                waste_rate = total_wasted / total_sold
                if waste_rate > Decimal("0.15"):
                    avg_demand = avg_demand * (1 - waste_rate)

            committed = backend.committed(recipe.output_sku, date)

            raw_qty = (avg_demand + committed) * (1 + safety_pct)

            # High demand multiplier: Fri(4) or Sat(5)
            high_demand_applied = False
            if high_demand_multiplier and date.weekday() in (4, 5):
                raw_qty = raw_qty * high_demand_multiplier
                high_demand_applied = True

            quantity = raw_qty.quantize(Decimal("1"))  # round to whole units

            # Determine season label
            season_label: str | None = None
            if season_months:
                season_label = _season_label(season_months)

            suggestions.append(
                Suggestion(
                    recipe=recipe,
                    quantity=quantity,
                    basis={
                        "avg_demand": avg_demand,
                        "committed": committed,
                        "safety_pct": safety_pct,
                        "historical_days": historical_days,
                        "same_weekday": same_weekday,
                        "sample_size": len(estimates),
                        "confidence": confidence,
                        "season": season_label,
                        "waste_rate": waste_rate,
                        "high_demand_applied": high_demand_applied,
                        "excluded_days": len(exclude_dates),
                        "soldout_days": sum(
                            1 for dd in history if dd.soldout_at is not None
                        ),
                    },
                )
            )

        return suggestions

    @classmethod
    def queue(
        cls,
        *,
        date=None,
        position_ref: str | None = None,
        operator_ref: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[CraftQueueItem]:
        """
        Operational queue for the floor.

        Defaults to active work (`planned` + `started`) because this is the
        practical queue the floor needs to act on.
        """
        from shopman.craftsman.models import WorkOrder

        statuses = statuses or [WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED]
        orders = cls._queue_queryset(
            date=date,
            position_ref=position_ref,
            operator_ref=operator_ref,
            statuses=statuses,
        )

        items = []
        for order in orders:
            started_qty = _started_qty(order)
            finished_qty = order.finished
            loss_qty = None
            yield_rate = None
            if finished_qty is not None:
                base_qty = started_qty or order.quantity
                loss_qty = max(base_qty - finished_qty, Decimal("0"))
                yield_rate = (finished_qty / base_qty) if base_qty else None

            items.append(
                CraftQueueItem(
                    ref=order.ref,
                    recipe_ref=order.recipe.ref,
                    output_sku=order.output_sku,
                    status=order.status,
                    target_date=order.target_date,
                    position_ref=order.position_ref or "",
                    operator_ref=order.operator_ref or "",
                    planned_qty=order.quantity,
                    started_qty=started_qty,
                    finished_qty=finished_qty,
                    loss_qty=loss_qty,
                    yield_rate=yield_rate,
                )
            )
        return items

    @classmethod
    def summary(
        cls,
        *,
        date=None,
        position_ref: str | None = None,
        operator_ref: str | None = None,
    ) -> CraftSummary:
        """
        Aggregate operational summary for a floor/date slice.

        This is a projection for dashboards and floor coordination, not a new
        domain state machine.
        """
        from shopman.craftsman.models import WorkOrder

        orders = cls._queue_queryset(
            date=date,
            position_ref=position_ref,
            operator_ref=operator_ref,
            statuses=[
                WorkOrder.Status.PLANNED,
                WorkOrder.Status.STARTED,
                WorkOrder.Status.FINISHED,
                WorkOrder.Status.VOID,
            ],
        )

        summary = CraftSummary()
        for order in orders:
            summary.total_orders += 1
            summary.planned_qty += order.quantity or Decimal("0")

            if order.status == WorkOrder.Status.PLANNED:
                summary.planned_orders += 1
            elif order.status == WorkOrder.Status.STARTED:
                summary.started_orders += 1
            elif order.status == WorkOrder.Status.FINISHED:
                summary.finished_orders += 1
            elif order.status == WorkOrder.Status.VOID:
                summary.void_orders += 1

            started_qty = _started_qty(order)
            if started_qty is not None:
                summary.started_qty += started_qty

            if order.finished is not None:
                summary.finished_qty += order.finished
                base_qty = started_qty or order.quantity
                summary.loss_qty += max(base_qty - order.finished, Decimal("0"))

        return summary

    @classmethod
    def _queue_queryset(
        cls,
        *,
        date=None,
        position_ref: str | None = None,
        operator_ref: str | None = None,
        statuses: list[str] | None = None,
    ):
        from shopman.craftsman.models import WorkOrder

        qs = (
            WorkOrder.objects.filter(status__in=statuses or [])
            .select_related("recipe")
            .prefetch_related("events")
            .order_by("target_date", "position_ref", "status", "created_at")
        )
        if date is not None:
            qs = qs.filter(target_date=date)
        if position_ref:
            qs = qs.filter(position_ref=position_ref)
        if operator_ref:
            qs = qs.filter(operator_ref=operator_ref)
        return qs


def _aggregate(agg, item_ref, quantity, unit, margin=None):
    """Aggregate material need by (item_ref, unit)."""
    from shopman.craftsman.services.recipes import has_active_recipe_for_output_sku

    key = (item_ref, unit)
    if key in agg:
        agg[key].quantity += quantity
        if margin is not None:
            agg[key].margin = margin
    else:
        has_recipe = has_active_recipe_for_output_sku(item_ref)
        agg[key] = Need(
            item_ref=item_ref,
            quantity=quantity,
            unit=unit,
            has_recipe=has_recipe,
            margin=margin,
        )


def _is_counted_output(recipe) -> bool:
    """A saída desta ficha é CONTADA (peças), e não pesada?

    A margem de rendimento só faz sentido quando existe "peça": é o
    arredondamento da balança ao dividir a massa que ela orça. Ficha que rende
    massa (a fórmula) não porciona nada — quem porciona é a ficha da peça.

    A unidade da saída é a DECLARADA (catálogo, ou ``meta["output_unit"]``),
    nunca deduzida: ADR-024 §R4 manda recusar em vez de adivinhar, e aqui
    recusar significa simplesmente não orçar margem nenhuma.
    """
    from shopman.utils import units

    return units.dimension(recipe._declared_output_unit()) == units.COUNT


def _margin_applies(recipe_item) -> bool:
    """Esta linha da ficha recebe margem de rendimento?

    Duas condições, e as duas são de propósito estreitas:

    * a linha é medida em MASSA — margem de rendimento é conversa de massa;
    * o insumo é PRODUZIDO na casa (tem ficha ativa própria) — a margem
      responde "quanto fazer", e só se decide fazer o que se faz. Farinha,
      sal e fermento ficam de fora: não se "produz" sal, e inflar a linha de
      matéria-prima na lista de separação inflaria a sugestão de compra todo
      dia por um excesso que não é consumo.

    O excesso de matéria-prima que de fato acontece continua sendo capturado
    onde ele é fato: no ledger, quando a massa que a leva é feita a mais.
    """
    from shopman.craftsman.services.recipes import has_active_recipe_for_output_sku
    from shopman.utils import units

    if units.dimension(recipe_item.unit) != units.MASS:
        return False
    return has_active_recipe_for_output_sku(recipe_item.input_sku)


def _yield_margins(pieces: dict) -> dict:
    """Orça uma margem por preparo, a partir do total de peças que ele rende."""
    from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    from shopman.craftsman.services.yield_margin import compute_yield_margin, mixer_loss_g_for

    margins = {}
    for (item_ref, unit), total_pieces in pieces.items():
        prep_recipe = get_active_recipe_for_output_sku(item_ref)
        margin = compute_yield_margin(
            pieces=total_pieces,
            unit=unit,
            mixer_loss_g=mixer_loss_g_for(prep_recipe),
        )
        if margin is not None:
            margins[(item_ref, unit)] = margin
    return margins


def _started_qty(order) -> Decimal | None:
    """Resolve latest started quantity from prefetched events when available."""
    events = list(getattr(order, "_prefetched_objects_cache", {}).get("events", []))
    if not events:
        event = order.events.filter(kind="started").order_by("-seq").only("payload").first()
        if not event:
            return None
        return Decimal(str(event.payload.get("quantity", "0")))

    started_events = [event for event in events if event.kind == "started"]
    if not started_events:
        return None
    latest = max(started_events, key=lambda ev: ev.seq)
    return Decimal(str(latest.payload.get("quantity", "0")))


def _expand_bom(item_ref, quantity, unit, depth=0):
    """
    Recursively expand BOM to raw materials.

    If item_ref has an active Recipe, expand its items.
    Otherwise, yield as-is (terminal ingredient).

    Max depth 5 for cycle protection.
    """
    from shopman.craftsman.exceptions import CraftError
    from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku

    if depth > 5:
        raise CraftError("BOM_CYCLE", item_ref=item_ref, depth=depth)

    sub_recipe = get_active_recipe_for_output_sku(item_ref)
    if sub_recipe:
        sub_coefficient = quantity / sub_recipe.batch_size
        for ri in sub_recipe.items.filter(is_optional=False).order_by("sort_order"):
            yield from _expand_bom(ri.input_sku, ri.quantity * sub_coefficient, ri.unit, depth + 1)
    else:
        yield (item_ref, quantity, unit)


def _calc_confidence(sample_size: int) -> str | None:
    """Return confidence label or None (skip) based on sample size."""
    if sample_size >= 8:
        return "high"
    if sample_size >= 3:
        return "medium"
    if sample_size >= 1:
        return "low"
    return None


_HOT_MONTHS = frozenset([10, 11, 12, 1, 2, 3])
_COLD_MONTHS = frozenset([6, 7, 8])
_MILD_MONTHS = frozenset([4, 5, 9])


def _season_label(months: list[int]) -> str | None:
    """Infer season label from a list of month ints."""
    m = frozenset(months)
    if m == _HOT_MONTHS:
        return "hot"
    if m == _COLD_MONTHS:
        return "cold"
    if m == _MILD_MONTHS:
        return "mild"
    return None


def _estimate_demand(dd, selling_window=None):
    """
    Estimate true demand from a DailyDemand record.

    Um dia que ESGOTOU não mostra a demanda: mostra o estoque que havia. Sem
    corrigir isso, o produto que acaba toda quinta às 10h ensina que quinta
    vende pouco, a sugestão manda produzir pouco, e a falta se perpetua.

    If soldout_at is None → demand = sold (full day of selling).
    If soldout_at is set → extrapolate based on selling rate, capped at 2x.
        rate = sold / minutes_selling
        estimated = min(rate * full_day_minutes, 2 * sold)

    ``selling_window`` é o par (abre, fecha) do dia — quem sabe o horário da
    loja é o orquestrador. **Sem janela, não extrapola**: chutar um expediente
    padrão inventaria demanda que ninguém observou (a casa não finge dado).
    """
    if dd.soldout_at is None or selling_window is None:
        return dd.sold

    from datetime import date as date_type
    from datetime import datetime

    open_time, close_time = selling_window
    dummy = date_type(2000, 1, 1)

    open_dt = datetime.combine(dummy, open_time)
    soldout_dt = datetime.combine(dummy, dd.soldout_at)
    close_dt = datetime.combine(dummy, close_time)

    minutes_selling = (soldout_dt - open_dt).total_seconds() / 60
    if minutes_selling <= 0:
        return dd.sold

    full_day_minutes = (close_dt - open_dt).total_seconds() / 60
    if full_day_minutes <= 0:
        return dd.sold

    rate = dd.sold / Decimal(str(minutes_selling))
    estimated = rate * Decimal(str(full_day_minutes))

    # Cap at 2x actual sold to avoid wild overestimation
    cap = dd.sold * 2
    return min(estimated, cap)
