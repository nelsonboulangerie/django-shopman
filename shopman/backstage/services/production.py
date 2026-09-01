"""Production operator mutation facade.

Backstage views call this module for production mutations. Domain invariants
remain in ``shopman.shop.services.production`` and Craftsman; this layer is the
operator-surface boundary for form-oriented actions.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.utils import timezone
from shopman.utils.spreadsheet import escape_cell

from shopman.backstage.services.exceptions import ProductionConflict, ProductionError
from shopman.shop.services import production as production_core
from shopman.shop.services import quality as quality_service

logger = logging.getLogger(__name__)


def _operator_error(exc: Exception) -> Exception:
    """Traduz um ``CraftError`` do kernel para a borda do operador.

    Sem isto, dois quiosques fechando a MESMA fornada davam 500 cru com
    mensagem em inglês (o ``CraftError`` não é DRF nem ``ProductionError``,
    então nenhuma view o capturava). Conflito de estado (fechada/estornada/
    alterada em outra tela) vira ``ProductionConflict`` → 409; o resto vira
    ``ProductionError`` → 400. Exceção que não é ``CraftError`` volta como
    veio (o chamador decide).

    ``StockError`` entra na mesma tradução: desde que a perna de output parou
    de engolir a falha, ela sobe até aqui, e sem isso o operador levava 500 cru
    numa fornada que JÁ está fechada.
    """
    from shopman.craftsman.exceptions import CraftError
    from shopman.stockman.exceptions import StockError

    if isinstance(exc, StockError):
        return ProductionError(
            f"A fornada foi fechada, mas não entrou no estoque: {exc}. "
            "Confira a posição de venda antes de repetir."
        )
    if not isinstance(exc, CraftError):
        return exc
    code = getattr(exc, "code", "")
    data = getattr(exc, "data", {}) or {}
    if code in ("TERMINAL_STATUS", "VOID_FROM_DONE"):
        if str(data.get("status") or "") == "void":
            return ProductionConflict("Esta fornada foi estornada. Atualize o painel.")
        if code == "VOID_FROM_DONE":
            return ProductionConflict("Fornada concluída não pode ser estornada.")
        return ProductionConflict("Esta fornada já foi fechada em outra tela. Atualize o painel.")
    if code in ("INVALID_STATUS", "STALE_REVISION", "IDEMPOTENCY_CONFLICT"):
        return ProductionConflict(
            "A fornada mudou em outra tela. Atualize o painel e tente de novo."
        )
    if code == "INVALID_QUANTITY":
        return ProductionError("Quantidade inválida.")
    return ProductionError(str(exc) or "Falha na produção.")


@dataclass(frozen=True)
class MissingMaterial:
    sku: str
    needed: Decimal
    available: Decimal

    @property
    def shortage(self) -> Decimal:
        return max(Decimal("0"), self.needed - self.available)


class ProductionStockShortError(ProductionError):
    """Raised when pre-finish material validation detects a shortage."""

    def __init__(self, *, work_order_ref: str, missing: list[MissingMaterial]):
        self.work_order_ref = work_order_ref
        self.missing = missing
        summary = ", ".join(
            f"{item.sku}: faltam {_qty(item.shortage)}" for item in missing
        )
        super().__init__(f"Insumos insuficientes para {work_order_ref}: {summary}")


class ProductionOrderShortError(ProductionError):
    """Raised when a planned quantity no longer covers linked orders."""

    def __init__(self, *, work_order_ref: str, required: Decimal, requested: Decimal, order_refs: tuple[str, ...]):
        self.work_order_ref = work_order_ref
        self.required = required
        self.requested = requested
        self.order_refs = order_refs
        short = max(Decimal("0"), required - requested)
        super().__init__(
            f"{work_order_ref} tem {_qty(required)} un. comprometidas; "
            f"a nova quantidade deixa {_qty(short)} un. descobertas."
        )


def apply_void(
    work_order_id,
    *,
    actor: str,
    reason: str = "Estornado via produção rápida",
    expected_rev: int | None = None,
) -> str:
    """Void a work order from the operator surface.

    ⚠️ `expected_rev` é a revisão que a TELA leu. Sem ela, duas bancadas ajustando a
    mesma fornada sobre um quadro de sessenta segundos de idade fazem o último POST
    vencer — sem 409 e sem aviso. O core já sabia fazer o compare-and-swap e a tradução
    para 409 já existia (`STALE_REVISION`); faltava o número atravessar a borda.
    """
    try:
        return production_core.void_work_order(
            work_order_id,
            actor=actor,
            reason=reason,
            expected_rev=expected_rev,
        )
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def apply_quick_finish(
    *,
    recipe_id,
    quantity,
    position_id,
    actor: str,
    partition=None,
    force: bool = False,
):
    """Plan and immediately finish a work order from the operator surface.

    O fechamento passa pelo MESMO caminho do finish normal, COM ou SEM
    ``partition``: guardrail de insumo (``check_finish_materials``), veto
    resolvido na borda, N lotes com percentual congelado, alerta quando a
    rastreabilidade falha.

    Sem partição isto ia direto ao ``quick_finish`` do core, pulando o
    ``apply_finish`` — e a fornada avulsa era o único fechamento da casa que
    fechava sem farinha no estoque, calado. A mesma ação era barrada no
    quiosque de QC (que manda partição) e livre no grid do gestor.
    """
    try:
        work_order = production_core.quick_plan(
            recipe_id=recipe_id, quantity=quantity, position_id=position_id
        )
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)
    wo_ref, total = apply_finish(
        work_order_id=work_order.pk,
        quantity=quantity,
        actor=actor,
        force=force,
        partition=partition,
    )
    return work_order.output_sku, wo_ref, total


def apply_planned(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str = "",
    operator_ref: str = "",
    reason: str = "",
    actor: str,
    force: bool = False,
    source_ref: str = "production_matrix",
    expected_rev: int | None = None,
):
    """Create or adjust the planned work order represented by a matrix cell.

    ``expected_rev``: ver ``apply_void``. Alcança só o AJUSTE — criar não tem revisão
    anterior para comparar.
    """
    _check_linked_order_coverage(
        recipe_id=recipe_id,
        quantity=quantity,
        target_date_value=target_date_value,
        position_ref=position_ref,
        operator_ref=operator_ref,
        force=force,
    )
    try:
        return production_core.set_planned_quantity(
            recipe_id=recipe_id,
            quantity=quantity,
            target_date_value=target_date_value,
            position_ref=position_ref,
            operator_ref=operator_ref,
            reason=reason,
            actor=actor,
            source_ref=source_ref,
            expected_rev=expected_rev,
        )
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def apply_start(
    *,
    work_order_id,
    quantity,
    position_id="",
    operator_ref: str = "",
    note: str = "",
    actor: str,
    expected_rev: int | None = None,
):
    """Start a planned work order from the operator surface.

    ``expected_rev``: ver ``apply_void``.
    """
    try:
        return production_core.start_work_order(
            work_order_id=work_order_id,
            quantity=quantity,
            expected_rev=expected_rev,
            position_id=position_id,
            operator_ref=operator_ref,
            note=note,
            actor=actor,
        )
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


# Teto de sanidade da duração armada: um timer de forno não passa de 24h.
OVEN_MAX_PLANNED_SECONDS = 86_400


def apply_oven_arm(*, work_order_id, planned_seconds, operator_ref: str = "", actor: str = ""):
    """Registra a declaração "enfornou" (ADR-021 §4, BI-PLAN §4).

    O servidor carimba ``armed_at`` no recebimento — mesmo tratamento de
    ``started_at``/``finished_at`` da WorkOrder; sem relógio de cliente.
    Re-armar com run aberto = nova enfornada: o run anterior vira
    ``abandoned`` (nunca mede) e um novo abre.
    """
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder

    from shopman.backstage.models import OvenRun

    try:
        seconds = int(planned_seconds)
    except (TypeError, ValueError):
        raise ProductionError("Duração do timer inválida.") from None
    if not 0 < seconds <= OVEN_MAX_PLANNED_SECONDS:
        raise ProductionError("Duração do timer inválida.")

    try:
        work_order = _get_work_order(work_order_id)
    except WorkOrder.DoesNotExist:
        raise ProductionError("Ordem de produção não encontrada.") from None
    if work_order.status in (WorkOrder.Status.FINISHED, WorkOrder.Status.VOID):
        raise ProductionError("Ordem já encerrada; não há o que enfornar.")

    with transaction.atomic():
        superseded = OvenRun.objects.filter(
            work_order_ref=work_order.ref, status="open"
        ).update(status="abandoned")
        run = OvenRun.objects.create(
            work_order_ref=work_order.ref,
            oven_ref=work_order.position_ref or "",
            operator_ref=operator_ref or actor,
            planned_seconds=seconds,
            metadata={"superseded_open_runs": superseded} if superseded else {},
        )
    return run


def apply_oven_conclude(*, work_order_id, actor: str = ""):
    """Registra a declaração "retirou" (o Concluir do timer).

    Sem run aberto não há o que medir — retorna ``None`` (o cliente é
    best-effort; a honestidade fica na cobertura do relatório). Expiração do
    timer e o Confirmar do QC nunca chegam aqui: só o Concluir declarado.
    """
    from shopman.craftsman.models import WorkOrder

    from shopman.backstage.models import OvenRun

    try:
        work_order = _get_work_order(work_order_id)
    except WorkOrder.DoesNotExist:
        raise ProductionError("Ordem de produção não encontrada.") from None
    run = (
        OvenRun.objects.filter(work_order_ref=work_order.ref, status="open")
        .order_by("-armed_at")
        .first()
    )
    if run is None:
        return None
    run.status = "concluded"
    run.concluded_at = timezone.now()
    run.save(update_fields=["status", "concluded_at"])
    return run


def resolve_partition(work_order, *, quantity, quality: str = "", partition=None):
    """Normaliza a entrada do operador na partição da fornada (ADR-017 §4).

    Três formas de entrada, uma saída — ``(finished_items, wasted_items)``:

    - ``partition`` explícita (``[{quantity, quality_grade_ref,
      quality_defect_ref, loss}]``): cada grupo vira linha de OUTPUT; grupo com
      ``loss=True`` é perda declarada pelo operador (o que não saiu do forno) e
      vira WASTE com o motivo, sem grau e sem lote; grupo cujo defeito tem
      ``forces_discard`` também vira WASTE (o veto é resolvido AQUI, antes do
      craft.finish — o core nunca interpreta o defeito).
    - ``quality`` sozinho (a superfície de hoje): partição de um grupo só.
    - nada: um grupo no grau padrão do catálogo.

    Grau desconhecido cai no padrão; defeito desconhecido é descartado com
    aviso (o catálogo é a fronteira de validação — ADR-004).
    """
    from shopman.shop.models import QualityDefect, QualityGrade

    grades = dict(QualityGrade.objects.values_list("ref", "markdown_percent"))
    default_ref = quality_service.default_grade_ref()
    vetoes = set(
        QualityDefect.objects.filter(forces_discard=True).values_list("ref", flat=True)
    )
    known_defects = set(QualityDefect.objects.values_list("ref", flat=True))

    if not partition:
        grade = (quality or "").strip().lower() or default_ref
        if grade not in grades:
            grade = default_ref
        partition = [{"quantity": quantity, "quality_grade_ref": grade}]

    production_date = work_order.target_date or timezone.localdate()
    base_batch_ref = f"{work_order.output_sku}-{production_date:%Y%m%d}-{work_order.pk}"

    finished_items: list[dict] = []
    wasted_items: list[dict] = []
    for group in partition:
        grade = str(group.get("quality_grade_ref") or "").strip().lower() or default_ref
        if grade not in grades:
            logger.warning(
                "production.partition: grau desconhecido %r vira o padrão (wo=%s)",
                grade, work_order.ref,
            )
            grade = default_ref
        defect = str(group.get("quality_defect_ref") or "").strip().lower()
        if defect and defect not in known_defects:
            logger.warning(
                "production.partition: defeito desconhecido %r descartado (wo=%s)",
                defect, work_order.ref,
            )
            defect = ""

        if group.get("loss"):
            # Perda declarada: abaixo do piso não existe grau, existe descarte
            # (QC-FORNADA §2). Carrega o motivo, nunca grau nem lote.
            wasted_items.append({
                "item_ref": work_order.output_sku,
                "quantity": group.get("quantity"),
                "quality_defect_ref": defect,
            })
            continue

        if defect in vetoes:
            # Veto é segurança alimentar: as unidades nunca viram lote com
            # desconto — viram perda, carregando o motivo.
            wasted_items.append({
                "item_ref": work_order.output_sku,
                "quantity": group.get("quantity"),
                "quality_defect_ref": defect,
            })
            continue

        finished_items.append({
            "item_ref": work_order.output_sku,
            "quantity": group.get("quantity"),
            "quality_grade_ref": grade,
            "quality_defect_ref": defect,
            # N grupos = N lotes: o ref base preserva a fórmula histórica; os
            # grupos seguintes ganham sufixo ordinal.
            "batch_ref": base_batch_ref if not finished_items else f"{base_batch_ref}-{len(finished_items) + 1}",
        })

    if not finished_items:
        raise ProductionError(
            "Nenhum grupo da fornada é vendável (só perda ou veto) — registre como perda "
            "(void/waste), não como conclusão."
        )
    return finished_items, wasted_items


def apply_finish(
    *,
    work_order_id,
    quantity,
    actor: str,
    force: bool = False,
    quality: str = "",
    partition=None,
    expected_rev: int | None = None,
):
    """Finish a work order from the operator surface — escalar ou particionado.

    ``expected_rev``: ver ``apply_void``. Convive com a chave de idempotência sem
    conflito — uma responde "é o MESMO gesto de novo?", a outra "o quadro que você leu
    ainda vale?". A primeira devolve o resultado anterior; a segunda recusa.

    ``set_quality``/``meta["quality"]`` morreram (ADR-017 §3): a qualidade
    agora viaja nas LINHAS de OUTPUT e é derivada de lá por quem precisa
    (broadcast, fomo, relatório). O grau único da superfície de hoje é só uma
    partição de um grupo.
    """
    work_order = _get_work_order(work_order_id)
    finished_items, wasted_items = resolve_partition(
        work_order, quantity=quantity, quality=quality, partition=partition
    )
    missing = check_finish_materials(work_order)
    if missing and not force:
        raise ProductionStockShortError(work_order_ref=work_order.ref, missing=missing)
    if missing:
        _create_stock_short_alert(
            work_order_id=work_order.pk,
            error=_missing_summary(missing),
        )

    try:
        result = production_core.finish_work_order(
            work_order_id=work_order_id,
            quantity=quantity,
            actor=actor,
            finished_items=finished_items,
            wasted_items=wasted_items,
            idempotency_key=_finish_idempotency_key(
                work_order, finished_items, wasted_items
            ),
            expected_rev=expected_rev,
        )
    except Exception as exc:
        if _looks_like_stock_error(exc):
            _create_stock_short_alert(work_order_id=work_order_id, error=str(exc))
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)
    _record_batch_traceability(work_order_id=work_order_id)
    return result


def _finish_idempotency_key(work_order, finished_items, wasted_items) -> str:
    """Chave estável do fechamento: mesma fornada, mesmo resultado, mesma chave.

    O core devolve a WO existente quando a chave se repete, então o retry do
    operador depois de um erro que veio DEPOIS do commit para de morrer em
    ``TERMINAL_STATUS`` — o hazard em que um receiver posterior estoura e a
    fornada fica correta no banco e impossível de fechar na tela.

    A chave sai do RESULTADO (as linhas resolvidas), não do que o operador
    digitou: é o que o core vai gravar. Fechar de novo com outro número gera
    outra chave de propósito — aí não é retry, é um segundo fechamento de uma
    fornada já fechada, e o conflito tem que aparecer.

    Derivada no servidor, sem contrato novo com a superfície: o quiosque
    reenvia o mesmo POST e a chave cai igual sozinha.
    """
    import hashlib
    import json

    payload = json.dumps(
        {
            "work_order": work_order.pk,
            "finished": finished_items,
            "wasted": wasted_items,
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"production.finish:{work_order.pk}:{digest}"


def apply_advance_step(*, work_order_id, actor: str) -> int:
    """Advance the manual step pointer of a STARTED work order by one.

    Stores the new index in ``WorkOrder.meta["steps_progress"]`` (1-based).
    Returns the new step index. Capped at the number of recipe steps.
    Raises ProductionError if the work order is not in STARTED state or has
    no recipe steps.
    """
    from shopman.craftsman.models import WorkOrder

    work_order = _get_work_order(work_order_id)
    if work_order.status != WorkOrder.Status.STARTED:
        raise ProductionError("Só é possível avançar passo em ordens iniciadas.")

    steps = (work_order.recipe.meta or {}).get("steps") or work_order.recipe.steps or []
    total = len(steps)
    if total <= 0:
        raise ProductionError("Receita sem passos configurados.")

    meta = dict(work_order.meta or {})
    current = meta.get("steps_progress")
    try:
        current_value = int(current) if current not in (None, "") else 0
    except (TypeError, ValueError):
        current_value = 0
    new_index = max(1, min(total, current_value + 1))
    meta["steps_progress"] = new_index
    meta["steps_progress_actor"] = actor
    meta["steps_progress_updated_at"] = timezone.now().isoformat()
    work_order.meta = meta
    work_order.save(update_fields=["meta", "updated_at"])
    return new_index


def _csv_safe(value) -> str:
    """Neutraliza injeção de fórmula no CSV do relatório.

    Só o campo textual passa por aqui — número entra formatado e não é tocado.
    A regra (gatilhos, exceção de número puro) vive em
    ``shopman.utils.spreadsheet``, compartilhada com o cofre de backup.
    """
    return escape_cell("" if value is None else str(value))


def export_reports_csv(report_kind: str, filters: dict | None = None) -> bytes:
    """Export a production report as UTF-8 BOM CSV for spreadsheet tools."""
    from shopman.backstage.projections.production import build_production_reports

    requested = dict(filters or {})
    requested["report_kind"] = report_kind
    reports = build_production_reports(requested)
    output = StringIO()
    writer = csv.writer(output)

    if reports.filters.report_kind == "operator_productivity":
        writer.writerow([
            "Operador",
            "Nome",
            "Ordens concluídas",
            "Qtd total",
            "Rendimento médio",
            "Tempo médio (min)",
        ])
        for row in reports.operator_rows:
            writer.writerow([
                _csv_safe(row.operator_ref),
                _csv_safe(row.operator_name),
                row.wo_count,
                row.qty_total,
                row.yield_avg,
                row.duration_avg_minutes,
            ])
    elif reports.filters.report_kind == "quality":
        # Sem este ramo o "quality" caía no else e exportava o HISTÓRICO —
        # o gestor baixava a tabela errada com o nome certo.
        writer.writerow([
            "Receita",
            "Nome",
            "Grau",
            "Defeito",
            "Qtd",
            "% da receita",
        ])
        for row in reports.quality_rows:
            writer.writerow([
                _csv_safe(row.recipe_ref),
                _csv_safe(row.recipe_name),
                _csv_safe(row.grade_label),
                _csv_safe(row.defect_label),
                row.quantity,
                row.share,
            ])
    elif reports.filters.report_kind == "recipe_waste":
        writer.writerow([
            "Receita",
            "Nome",
            "Ordens",
            "Perda total",
            "Rendimento médio",
            "Utilização capacidade",
        ])
        for row in reports.waste_rows:
            writer.writerow([
                _csv_safe(row.recipe_ref),
                _csv_safe(row.recipe_name),
                row.wo_count,
                row.loss_total,
                row.yield_avg,
                row.capacity_utilization,
            ])
    else:
        writer.writerow([
            "Ref",
            "Data",
            "Receita",
            "Nome da receita",
            "Posição",
            "Qtd planejada",
            "Qtd iniciada",
            "Qtd concluída",
            "Perda",
            "Rendimento",
            "Operador",
            "Iniciada em",
            "Concluída em",
            "Duração (min)",
        ])
        for row in reports.history_rows:
            writer.writerow([
                _csv_safe(row.ref),
                _csv_safe(row.date),
                _csv_safe(row.recipe_ref),
                _csv_safe(row.recipe_name),
                _csv_safe(row.position_ref),
                row.qty_planned,
                row.qty_started,
                row.qty_finished,
                row.qty_loss,
                row.yield_rate,
                _csv_safe(row.operator_ref),
                _csv_safe(row.started_at),
                _csv_safe(row.finished_at),
                row.duration_minutes,
            ])

    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _check_linked_order_coverage(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str,
    operator_ref: str,
    force: bool,
) -> None:
    if force:
        return
    try:
        from shopman.craftsman.models import Recipe, WorkOrder

        from shopman.shop.handlers.production_order_sync import linked_order_refs, order_requirement_for_work_order
        from shopman.shop.services.production import _default_position_ref, _target_date_or_today

        recipe = Recipe.objects.get(pk=recipe_id)
        requested = Decimal(str(quantity or "0"))
        # ⚠️ A busca aqui tem de ser a MESMA de quem escreve
        # (`shop/services/production.py:set_planned_quantity`). Ela divergia em três
        # eixos, e a primeira divergência era fatal no uso normal:
        #
        #   eixo          guardrail (antes)        escritor
        #   position_ref  `position_ref or ""`     `.strip() or _default_position_ref()`
        #   operator_ref  filtrava por operador    NÃO filtra
        #   data          string crua              `_target_date_or_today(...)`
        #
        # O board manda `position_ref: undefined` quando nenhum filtro de posição está
        # escolhido — que é o estado PADRÃO da tela. O guardrail procurava `""`, o
        # escritor procurava `"massa"` (o default do seed vivo), e o guardrail não
        # achava nada, retornava cedo, e o planejado era reduzido SEM CHECAGEM.
        #
        # É encomenda de cliente que não vai existir, reduzida em silêncio.
        work_order = (
            WorkOrder.objects.filter(
                recipe=recipe,
                target_date=_target_date_or_today(target_date_value),
                status=WorkOrder.Status.PLANNED,
                position_ref=str(position_ref or "").strip() or _default_position_ref(),
            )
            .first()
        )
        if not work_order:
            return
        order_refs = linked_order_refs(work_order)
        if not order_refs:
            return
        required = order_requirement_for_work_order(work_order)
        if requested < required:
            raise ProductionOrderShortError(
                work_order_ref=work_order.ref,
                required=required,
                requested=requested,
                order_refs=order_refs,
            )
    except ProductionOrderShortError:
        raise
    # ⚠️ WARNING, e não DEBUG, no `except` abaixo. Ele engole qualquer falha do
    # guardrail, e em DEBUG a mensagem é invisível na prática: um guardrail CEGO
    # parecia um guardrail que passou. Continuar não levantando é deliberado — uma
    # falha aqui não deve impedir o planejamento —, mas ela tem de aparecer no log de
    # quem opera, senão a proteção some sem ninguém saber.
    #
    # (O comentário fica ACIMA do `except` de propósito: o gate de higiene de exceções
    # procura `logger.`/`raise` nas linhas imediatamente seguintes, e um comentário no
    # meio empurraria a chamada para fora da janela dele.)
    except Exception:
        logger.warning(
            "production_order_coverage_check_failed recipe_id=%s — guardrail de cobertura CEGO nesta chamada",
            recipe_id,
            exc_info=True,
        )


def _looks_like_stock_error(exc: Exception) -> bool:
    lower = str(exc).lower()
    return any(token in lower for token in ("estoque", "stock", "insuficiente", "inventory"))


def _create_stock_short_alert(*, work_order_id, error: str) -> None:
    try:
        from shopman.shop.handlers.production_alerts import create_stock_short_alert

        work_order = _get_work_order(work_order_id)
        create_stock_short_alert(
            work_order_ref=work_order.ref,
            output_sku=work_order.output_sku,
            error=error,
        )
    except Exception:
        logger.warning("production_stock_short_alert_failed work_order_id=%s", work_order_id, exc_info=True)


def check_finish_materials(work_order) -> list[MissingMaterial]:
    """Validate materials needed to finish a specific WorkOrder.

    Active guardrail when INVENTORY_BACKEND is configured (Buyman WP-B5b): returns
    the missing ingredients so apply_finish() can block (or alert with force=True).
    Returns [] when no backend is configured (standalone). Ingredients carry real
    Stockman stock via the seed.
    """
    backend_path = _craftsman_setting("INVENTORY_BACKEND")
    if not backend_path:
        return []

    material_needs = _material_needs_for_work_order(work_order)
    if not material_needs:
        return []

    try:
        from django.utils.module_loading import import_string

        result = import_string(backend_path)().available(material_needs)
    except Exception as exc:
        mode = _craftsman_setting("MODE")
        if mode == "strict":
            raise ProductionError(f"Falha ao consultar estoque de insumos: {exc}") from exc
        logger.warning("production_material_check_failed work_order=%s", work_order.ref, exc_info=True)
        return []

    return [
        MissingMaterial(
            sku=status.sku,
            needed=status.needed,
            available=status.available,
        )
        for status in result.materials
        if not status.sufficient
    ]


def _material_needs_for_work_order(work_order):
    from shopman.craftsman.protocols.inventory import MaterialNeed

    recipe = work_order.recipe
    started_qty = work_order.started_qty or work_order.quantity
    snapshot = (work_order.meta or {}).get("_recipe_snapshot")
    if snapshot:
        batch_size = Decimal(str(snapshot["batch_size"]))
        items = snapshot.get("items") or []
    else:
        batch_size = recipe.batch_size
        items = [
            {
                "input_sku": item.input_sku,
                "quantity": str(item.quantity),
                "unit": item.unit,
            }
            for item in recipe.items.filter(is_optional=False).order_by("sort_order")
        ]

    coefficient = started_qty / batch_size
    return [
        MaterialNeed(
            sku=item["input_sku"],
            quantity=Decimal(str(item["quantity"])) * coefficient,
            unit=item.get("unit", "un"),
            position_ref=work_order.position_ref or None,
        )
        for item in items
    ]


def _record_batch_traceability(*, work_order_id) -> None:
    """Um ``Batch`` por linha de OUTPUT — N grupos viram N lotes (ADR-017 §5).

    O ``batch_ref`` sai da LINHA (gravado pelo ``resolve_partition``), não de
    fórmula derivada em ``WorkOrder.meta`` — fórmula só admitia um lote por
    ordem, e era por isso que a partição parecia impossível. Grupo com grau de
    desconto grava ``nonconformity_percent`` (o percentual RESOLVIDO do
    catálogo, congelado no lote: mudar a tabela amanhã não reescreve os lotes
    de ontem) e ``nonconformity_reason`` (o label do defeito, ou do grau).

    Falha aqui vira OperatorAlert, não só log: lote não gravado é preço cheio
    indevido e rastreabilidade perdida.
    """
    work_order = _get_work_order(work_order_id)
    recipe_meta = work_order.recipe.meta or {}
    if not recipe_meta.get("requires_batch_tracking"):
        return

    try:
        from shopman.craftsman.models import WorkOrderItem
        from shopman.stockman.models import Batch

        from shopman.shop.models import QualityDefect, QualityGrade

        production_date = work_order.target_date or timezone.localdate()
        shelf_life_days = recipe_meta.get("shelf_life_days")
        expiry_date = None
        if shelf_life_days not in (None, ""):
            expiry_date = production_date + timedelta(days=int(shelf_life_days))

        grades = {
            ref: (label, markdown)
            for ref, label, markdown in QualityGrade.objects.values_list(
                "ref", "label", "markdown_percent"
            )
        }
        defect_labels = dict(QualityDefect.objects.values_list("ref", "label"))

        outputs = WorkOrderItem.objects.filter(
            work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT
        ).exclude(batch_ref="")
        for line in outputs:
            grade_label, markdown = grades.get(line.quality_grade_ref, ("", 0))
            defaults = {
                "sku": line.item_ref,
                "production_date": production_date,
                "expiry_date": expiry_date,
                "notes": f"Produção {work_order.ref}",
            }
            if markdown:
                # O grau é o input; o percentual é o FATO, e congela aqui.
                defaults["nonconformity_percent"] = markdown
                defaults["nonconformity_reason"] = (
                    defect_labels.get(line.quality_defect_ref) or grade_label
                )
            # update_or_create, não get_or_create: a ponte de estoque roda
            # ANTES (signal síncrono dentro do craft.finish) e já cria o lote
            # com produção+validade — o fato de qualidade precisa pousar por
            # cima. O congelamento continua: só o fechamento escreve aqui, e
            # ninguém reescreve depois.
            Batch.objects.update_or_create(ref=line.batch_ref, defaults=defaults)
    except Exception as exc:
        logger.warning(
            "production_batch_traceability_failed work_order_id=%s", work_order_id, exc_info=True
        )
        try:
            from shopman.shop.handlers.production_alerts import create_batch_traceability_alert

            create_batch_traceability_alert(
                work_order_ref=work_order.ref,
                output_sku=work_order.output_sku,
                error=str(exc) or type(exc).__name__,
            )
        except Exception:
            logger.warning(
                "production_batch_traceability_alert_failed work_order_id=%s",
                work_order_id,
                exc_info=True,
            )


def _get_work_order(work_order_id):
    from shopman.craftsman.models import WorkOrder

    return WorkOrder.objects.select_related("recipe").prefetch_related("recipe__items").get(pk=work_order_id)


def _craftsman_setting(name):
    from shopman.craftsman.conf import get_setting

    return get_setting(name)


def _missing_summary(missing: list[MissingMaterial]) -> str:
    return "; ".join(
        f"{item.sku} necessário {_qty(item.needed)}, disponível {_qty(item.available)}"
        for item in missing
    )


def _qty(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.001")).normalize(), "f")
