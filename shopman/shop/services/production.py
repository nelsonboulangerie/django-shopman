"""
Production service — coordenação em torno do WorkOrder (WP-S5).

Movimentação física de estoque (consumo de insumos + entrada do acabado) é
integrada ao Core via `production_changed` → contrib/stockman (caminho de escrita
único e canônico).

Este módulo é o gancho explícito do orquestrador: logging estruturado e pontos
únicos para evoluir (alertas ao operador, integrações externas).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)


def suggest_for(target_date: date, output_skus: list[str] | None = None):
    """Sugestões de produção com a config da loja aplicada.

    Ponto único de resolução: estação (mês da data-alvo), multiplicador de alta
    demanda e margem de segurança vêm de ``ProductionConfig`` — CLI, projections
    e matriz enxergam exatamente a mesma sugestão.

    O calendário também entra aqui: quem sabe quando a loja abre é o
    orquestrador, então é ele que tira da amostra os dias fechados. Sem isso um
    domingo de portas fechadas entra na média como um domingo fraco e puxa a
    sugestão da semana inteira para baixo.
    """
    from shopman.craftsman import suggest as formula_suggest
    from shopman.craftsman.conf import get_setting

    from shopman.shop.production_config import ProductionConfig

    suggestion = ProductionConfig.load().suggestion
    window_days = int(get_setting("HISTORICAL_DAYS") or 28)
    return formula_suggest(
        target_date,
        output_skus=output_skus,
        season_months=suggestion.season_months_for(target_date.month),
        high_demand_multiplier=suggestion.high_demand_multiplier_decimal,
        safety_pct=suggestion.safety_stock_percent_decimal,
        exclude_dates=untrustworthy_days(days=window_days),
        selling_window=selling_window_for(target_date),
    )


def selling_window_for(day: date):
    """O par (abre, fecha) do dia, do horário declarado da loja.

    É com ele que a fórmula extrapola a demanda dos dias que esgotaram: o pão
    que acabou às 10h vendeu numa fração do expediente, e a fração só é
    calculável sabendo quando o expediente começa. Sem horário configurado
    devolve None, e a fórmula prefere contar o que vendeu a inventar o resto.
    """
    from shopman.shop.services.business_calendar import selling_hours_for

    return selling_hours_for(day)


def untrustworthy_days(*, days: int, until: date | None = None) -> frozenset[date]:
    """Dias que não devem ensinar demanda, por qualquer motivo.

    Duas famílias, mesmo efeito: dia em que a casa **não abriu** (calendário) e
    dia **atrapalhado** por um episódio (faltou luz, equipamento parado). O
    segundo é tão enganoso quanto o primeiro — vender pouco porque a loja
    estava sem energia não é sinal de que a procura caiu.
    """
    from shopman.shop.adapters.episodes import disrupted_days

    until = until or timezone.localdate()
    closed = closed_days_within(days=days, until=until)
    disrupted = disrupted_days(since=until - timedelta(days=days), until=until)
    return closed | disrupted


def closed_days_within(*, days: int, until: date | None = None) -> frozenset[date]:
    """Dias sem expediente na janela ``[until - days, until)``.

    Degrada para vazio se o calendário não estiver configurado — nunca esconde
    dias por engano (a sugestão prefere amostra a mais do que amostra fantasma).
    """
    from shopman.shop.services.business_calendar import is_open_on

    until = until or timezone.localdate()
    return frozenset(
        day
        for offset in range(1, days + 1)
        if not is_open_on(day := until - timedelta(days=offset))
    )


def reserve_materials(work_order) -> None:
    """Ponto de coordenação ao planejar produção.

    O Stockman reage ao signal `production_changed` (action=planned/started).
    Aqui registramos o evento de domínio para auditoria e extensões futuras.
    """
    logger.info(
        "production.reserve_materials: wo=%s qty=%s ref=%s",
        work_order.ref,
        work_order.quantity,
        work_order.output_sku,
    )


def emit_goods(work_order) -> None:
    """Ponto de coordenação ao encerrar produção com saída real.

    Consumo de insumos e entrada do acabado ocorrem via signal
    `production_changed` → contrib/stockman (caminho de escrita único).
    """
    logger.info(
        "production.emit_goods: wo=%s finished=%s ref=%s",
        work_order.ref,
        work_order.finished,
        work_order.output_sku,
    )


def notify(work_order, event: str) -> None:
    """Registro de lifecycle de produção (log estruturado).

    Eventos felizes (planned/started/finished/voided) ficam no ledger + log —
    sinal, não ruído. Notificação ativa ao operador acontece nos ALERTAS
    (production_alerts._notify_operator, opt-in via
    ``production.notifications``): atraso, yield baixo, esquecimento, falta
    de insumo.
    """
    logger.info(
        "production.notify: wo=%s event=%s",
        work_order.ref,
        event,
    )


def void_work_order(
    work_order_id,
    *,
    actor: str,
    reason: str = "Estornado via produção rápida",
) -> str:
    """Void a work order and return its reference."""
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution

    work_order = WorkOrder.objects.get(pk=work_order_id)
    CraftExecution.void(order=work_order, reason=reason, actor=actor)
    return work_order.ref


def quick_plan(
    *,
    recipe_id,
    quantity,
    position_id,
):
    """Plan a same-day ad-hoc work order (fornada avulsa).

    Nasce sem previsto herdado de plano nenhum — o previsto É o que o operador
    declarou. Quem fecha decide o caminho: escalar (``quick_finish``) ou
    particionado (``apply_finish`` do quiosque de QC).
    """
    from shopman.craftsman.services.scheduling import CraftPlanning

    recipe = _get_active_recipe(recipe_id)
    qty = _positive_decimal(quantity, error="Quantidade inválida.")
    position_ref = _position_ref(position_id)

    return CraftPlanning.plan(
        recipe,
        qty,
        date=timezone.localdate(),
        position_ref=position_ref,
        source_ref="quick_production",
    )


def quick_finish(
    *,
    recipe_id,
    quantity,
    position_id,
    actor: str,
) -> tuple[str, str, Decimal]:
    """Plan and immediately finish a production work order."""
    from shopman.craftsman.services.execution import CraftExecution

    work_order = quick_plan(recipe_id=recipe_id, quantity=quantity, position_id=position_id)
    CraftExecution.finish(order=work_order, finished=work_order.quantity, actor=actor)
    return work_order.output_sku, work_order.ref, work_order.quantity


def set_planned_quantity(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str = "",
    operator_ref: str = "",
    reason: str = "",
    actor: str,
    source_ref: str = "production_matrix",
) -> tuple[str, str, Decimal, str]:
    """Create, adjust, or consolidate the planned WorkOrder behind a matrix cell."""
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution
    from shopman.craftsman.services.scheduling import CraftPlanning

    recipe = _get_active_recipe(recipe_id)
    qty = _non_negative_decimal(quantity, error="Quantidade planejada inválida.")
    target_date = _target_date_or_today(target_date_value)
    position = str(position_ref or "").strip() or _default_position_ref()
    operator = str(operator_ref or "").strip()
    extra_meta = _formula_meta(
        recipe=recipe,
        target_date=target_date,
        quantity=qty,
        source_ref=source_ref,
    )

    planned_orders = list(
        WorkOrder.objects.filter(
            recipe=recipe,
            target_date=target_date,
            position_ref=position,
            status=WorkOrder.Status.PLANNED,
        ).order_by("created_at")
    )

    if qty == 0:
        for work_order in planned_orders:
            CraftExecution.void(
                order=work_order,
                reason="Planejamento zerado na matriz",
                actor=actor,
            )
        return recipe.output_sku, "", qty, "cleared"

    if not planned_orders:
        work_order = CraftPlanning.plan(
            recipe,
            qty,
            date=target_date,
            position_ref=position,
            operator_ref=operator,
            source_ref=source_ref,
            actor=actor,
            meta=extra_meta,
        )
        return recipe.output_sku, work_order.ref, qty, "created"

    work_order = planned_orders[0]
    duplicate_orders = planned_orders[1:]
    if duplicate_orders:
        _merge_committed_order_links(work_order, duplicate_orders)
        if extra_meta:
            work_order.meta = {**(work_order.meta or {}), **extra_meta}
        work_order.save(update_fields=["meta", "updated_at"])
    elif extra_meta:
        work_order.meta = {**(work_order.meta or {}), **extra_meta}
        work_order.save(update_fields=["meta", "updated_at"])

    adjusted = False
    if work_order.quantity != qty:
        CraftPlanning.adjust(
            work_order,
            quantity=qty,
            reason=reason or "Planejamento informado na matriz",
            actor=actor,
        )
        adjusted = True

    for duplicate in duplicate_orders:
        CraftExecution.void(
            order=duplicate,
            reason=f"Planejamento consolidado em {work_order.ref}",
            actor=actor,
        )

    if duplicate_orders:
        return recipe.output_sku, work_order.ref, qty, "consolidated"
    return recipe.output_sku, work_order.ref, qty, "adjusted" if adjusted else "unchanged"


def start_work_order(
    *,
    work_order_id,
    quantity,
    position_id="",
    operator_ref: str = "",
    note: str = "",
    actor: str,
) -> tuple[str, Decimal]:
    """Mark a planned WorkOrder as started."""
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.scheduling import CraftPlanning

    qty = _positive_decimal(quantity, error="Quantidade iniciada inválida.")
    work_order = WorkOrder.objects.get(pk=work_order_id)
    position_ref = _position_ref(position_id) if position_id else work_order.position_ref
    operator = str(operator_ref or "").strip() or work_order.operator_ref
    CraftPlanning.start(
        work_order,
        quantity=qty,
        position_ref=position_ref,
        operator_ref=operator,
        note=str(note or "").strip(),
        actor=actor,
    )
    return work_order.ref, qty


def finish_work_order(
    *,
    work_order_id,
    quantity=None,
    actor: str,
    finished_items: list[dict] | None = None,
    wasted_items: list[dict] | None = None,
) -> tuple[str, Decimal]:
    """Finish an existing WorkOrder — escalar ou particionado (ADR-017).

    O escalar (``quantity``) continua válido e grava uma linha sem grau. Com
    ``finished_items``, cada grupo vira uma linha de OUTPUT carregando
    ``quality_grade_ref``/``quality_defect_ref``/``batch_ref`` — a fornada de
    40 que produz 32+8+3 em vez de "38". ``wasted_items`` leva as unidades
    vetadas com o defeito que as vetou.
    """
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution

    work_order = WorkOrder.objects.get(pk=work_order_id)
    if finished_items:
        CraftExecution.finish(
            order=work_order,
            finished=finished_items,
            wasted=wasted_items or None,
            actor=actor,
        )
        total = sum(Decimal(str(item["quantity"])) for item in finished_items)
        return work_order.ref, total

    qty = _positive_decimal(quantity, error="Quantidade concluída inválida.")
    CraftExecution.finish(order=work_order, finished=qty, actor=actor)
    return work_order.ref, qty


def _merge_committed_order_links(primary, duplicates: list) -> None:
    """Preserve order links when duplicate planned WOs are consolidated."""
    try:
        from shopman.orderman.models import Order

        from shopman.shop.handlers.production_order_sync import (
            ORDER_AWAITING_WO_REFS_KEY,
            WORK_ORDER_COMMITTED_ORDER_REFS_KEY,
        )
    except Exception:
        logger.debug("production.consolidate_links_unavailable", exc_info=True)
        return

    refs = list((primary.meta or {}).get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or [])
    for duplicate in duplicates:
        refs.extend((duplicate.meta or {}).get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or [])
    refs = list(dict.fromkeys(ref for ref in refs if ref))
    primary.meta = {
        **(primary.meta or {}),
        "consolidated_work_order_refs": list(
            dict.fromkeys([
                *list((primary.meta or {}).get("consolidated_work_order_refs") or []),
                *[duplicate.ref for duplicate in duplicates],
            ])
        ),
    }
    if refs:
        primary.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] = refs

    for order in Order.objects.filter(ref__in=refs):
        awaiting_refs = list((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or [])
        if primary.ref not in awaiting_refs:
            order.data = {
                **(order.data or {}),
                ORDER_AWAITING_WO_REFS_KEY: [*awaiting_refs, primary.ref],
            }
            order.save(update_fields=["data", "updated_at"])


def _get_active_recipe(recipe_id):
    from shopman.craftsman.models import Recipe

    try:
        return Recipe.objects.get(pk=recipe_id, is_active=True)
    except (Recipe.DoesNotExist, ValueError, TypeError) as exc:
        raise ValueError("Receita inválida.") from exc


def _positive_decimal(value, *, error: str = "quantidade inválida") -> Decimal:
    try:
        qty = Decimal(str(value).strip())
        if qty <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(error) from exc
    return qty


def _non_negative_decimal(value, *, error: str = "quantidade inválida") -> Decimal:
    try:
        qty = Decimal(str(value).strip())
        if qty < 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(error) from exc
    return qty


def _position_ref(position_id) -> str:
    if position_id:
        from shopman.stockman import Position

        try:
            return Position.objects.get(pk=position_id).ref
        except Position.DoesNotExist:
            pass
    return _default_position_ref()


def _default_position_ref() -> str:
    from shopman.stockman import Position

    default_pos = Position.objects.filter(is_default=True).first()
    return default_pos.ref if default_pos else ""


def _target_date_or_today(value) -> date:
    try:
        return date.fromisoformat(value) if value else timezone.localdate()
    except (ValueError, TypeError):
        return timezone.localdate()


def _formula_meta(*, recipe, target_date: date, quantity: Decimal, source_ref: str) -> dict:
    if source_ref != "formula:suggestion":
        return {}
    try:
        lines = suggest_for(target_date, output_skus=[recipe.output_sku])
        basis = {}
        for line in lines:
            if line.recipe.pk == recipe.pk:
                basis = dict(line.basis or {})
                break
        if not basis:
            basis = {
                "date": target_date.isoformat(),
                "output_sku": recipe.output_sku,
                "recipe_ref": recipe.ref,
            }
        basis["accepted_quantity"] = str(quantity)
        return {"formula_basis": basis}
    except Exception:
        logger.debug("production.formula_basis_unavailable recipe=%s", recipe.ref, exc_info=True)
        return {}
