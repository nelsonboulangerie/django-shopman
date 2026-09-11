"""Derivações de qualidade da fornada a partir do livro imutável (ADR-017 §3).

Não existe campo de qualidade em ``WorkOrder`` — o ``meta["quality"]`` morreu.
A qualidade efetiva é uma projeção: nasce das linhas de OUTPUT e, quando a
gestão corrige o QC, passa a vir do último evento versionado sem apagar o fato
original. Quem precisa de um agregado calcula aqui.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def reviewed_saleable_quantity(work_order_ref: str, *, channel_ref: str) -> Decimal | None:
    """Return manager-reviewed quantity eligible for the canonical channel policy."""
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent

    from shopman.shop.projections.channel_policy import resolve_channel_policy

    work_order = WorkOrder.objects.filter(ref=work_order_ref).first()
    if work_order is None:
        return None
    reviewed = WorkOrderEvent.objects.filter(
        work_order=work_order,
        kind__in=(
            WorkOrderEvent.Kind.QUALITY_REVIEWED,
            WorkOrderEvent.Kind.QUALITY_CORRECTED,
        ),
    ).exists()
    if not reviewed:
        return None

    allowed = resolve_channel_policy(channel_ref).stock_scope.get(
        "allowed_quality_grade_refs"
    )
    allowed_refs = None if allowed is None else set(allowed)
    return sum(
        (
            Decimal(str(group.get("quantity") or "0"))
            for group in effective_partition(work_order, include_loss=False)
            if allowed_refs is None
            or str(group.get("quality_grade_ref") or default_grade_ref())
            in allowed_refs
        ),
        Decimal("0"),
    )


def effective_partitions(work_orders, *, include_loss: bool = True) -> dict[int, list[dict]]:
    """Return the latest effective QC partition for several work orders.

    The closing :class:`WorkOrderItem` rows remain the original production
    fact. A manager correction is an immutable ``quality_corrected`` event
    layered on top. The lot is still the owner of the frozen commercial
    markdown, so a later catalog edit cannot rewrite an already inspected
    batch. This bulk form lets BI consume the same semantics without an N+1.
    """
    from shopman.craftsman.models import WorkOrderEvent, WorkOrderItem

    work_orders = [work_order for work_order in work_orders if getattr(work_order, "pk", None)]
    if not work_orders:
        return {}
    work_order_ids = [work_order.pk for work_order in work_orders]
    try:
        corrected_by_work_order: dict[int, list[dict]] = {}
        for work_order_id, payload in (
            WorkOrderEvent.objects.filter(
                work_order_id__in=work_order_ids,
                kind=WorkOrderEvent.Kind.QUALITY_CORRECTED,
            )
            .order_by("work_order_id", "seq")
            .values_list("work_order_id", "payload")
        ):
            corrected = (payload or {}).get("after_partition")
            if isinstance(corrected, list):
                corrected_by_work_order[work_order_id] = [
                    dict(group) for group in corrected if isinstance(group, dict)
                ]

        original_by_work_order: dict[int, list[dict]] = {}
        original_ids = [pk for pk in work_order_ids if pk not in corrected_by_work_order]
        for line in (
            WorkOrderItem.objects.filter(
                work_order_id__in=original_ids,
                kind__in=(WorkOrderItem.Kind.OUTPUT, WorkOrderItem.Kind.WASTE),
            )
            .order_by("work_order_id", "pk")
            .values(
                "work_order_id",
                "kind",
                "quantity",
                "quality_grade_ref",
                "quality_defect_ref",
                "batch_ref",
                "meta",
            )
        ):
            loss = line["kind"] == WorkOrderItem.Kind.WASTE
            meta = dict(line["meta"] or {})
            original_by_work_order.setdefault(line["work_order_id"], []).append(
                {
                    "quantity": str(line["quantity"]),
                    "quality_grade_ref": "" if loss else (line["quality_grade_ref"] or ""),
                    "quality_defect_ref": line["quality_defect_ref"] or "",
                    "loss": loss,
                    "batch_ref": "" if loss else (line["batch_ref"] or ""),
                    "markdown_percent": int(meta.get("quality_markdown_percent") or 0),
                    "quality_reason": str(meta.get("quality_reason") or ""),
                }
            )

        raw_by_work_order = {
            pk: corrected_by_work_order.get(pk, original_by_work_order.get(pk, []))
            for pk in work_order_ids
        }
        batch_refs = {
            str(group.get("batch_ref") or "")
            for groups in raw_by_work_order.values()
            for group in groups
            if group.get("batch_ref") and not bool(group.get("loss"))
        }
        from shopman.stockman.models import Batch

        lot_facts = {
            ref: (percent, reason)
            for ref, percent, reason in Batch.objects.filter(ref__in=batch_refs).values_list(
                "ref", "nonconformity_percent", "nonconformity_reason"
            )
        }
        fallback = default_grade_ref()
        result: dict[int, list[dict]] = {}
        for work_order_id, raw_groups in raw_by_work_order.items():
            groups: list[dict] = []
            for raw in raw_groups:
                loss = bool(raw.get("loss"))
                if loss and not include_loss:
                    continue
                batch_ref = "" if loss else str(raw.get("batch_ref") or "")
                markdown = int(raw.get("markdown_percent") or 0)
                reason = str(raw.get("quality_reason") or "")
                if batch_ref in lot_facts:
                    markdown, reason = lot_facts[batch_ref]
                groups.append(
                    {
                        "quantity": str(raw.get("quantity") or "0"),
                        "quality_grade_ref": (
                            "" if loss else str(raw.get("quality_grade_ref") or fallback)
                        ),
                        "quality_defect_ref": str(raw.get("quality_defect_ref") or ""),
                        "loss": loss,
                        "batch_ref": batch_ref,
                        "markdown_percent": 0 if loss else int(markdown or 0),
                        "quality_reason": reason,
                    }
                )
            result[work_order_id] = groups
        return result
    except Exception:
        logger.debug(
            "quality.effective_partitions_lookup_failed work_orders=%r",
            work_order_ids,
            exc_info=True,
        )
        return {work_order_id: [] for work_order_id in work_order_ids}


def effective_partition(work_order, *, include_loss: bool = True) -> list[dict]:
    """Return one work order's latest QC partition without rewriting history."""
    if not getattr(work_order, "pk", None):
        return []
    return effective_partitions([work_order], include_loss=include_loss).get(work_order.pk, [])


def default_grade_ref() -> str:
    """O grau padrão do catálogo; "standard" em banco sem o data seed."""
    from shopman.shop.models import QualityGrade

    try:
        ref = QualityGrade.objects.filter(is_default=True).values_list("ref", flat=True).first()
        return ref or "standard"
    except Exception:
        logger.debug("quality.default_lookup_failed", exc_info=True)
        return "standard"


def output_partition(work_order) -> list[dict]:
    """A partição efetiva: ``[{grade_ref, quantity}, ...]`` do QC vigente.

    Linha sem grau (finish escalar, fornada antiga) conta como o grau padrão —
    o mesmo default do fechamento sem classificação.
    """
    # Quem consome isto são receivers de marketing/fomo — que NUNCA podem
    # derrubar a operação que os disparou. Sender sem pk (dublê, evento
    # sintético) ou lookup quebrado degradam para partição vazia.
    if not getattr(work_order, "pk", None):
        return []
    return [
        {
            "grade_ref": str(group.get("quality_grade_ref") or default_grade_ref()),
            "quantity": str(group.get("quantity") or "0"),
        }
        for group in effective_partition(work_order, include_loss=False)
    ]


def derived_quality(work_order) -> str:
    """O grau DOMINANTE da fornada (maior quantidade; empate = melhor grau).

    É o agregado para rótulo e log — o gate de campanha não usa isto, usa a
    partição inteira (``quality_min`` + ``quality_min_share``): "dominante"
    esconderia 8 unidades mínimas atrás de 32 ótimas.
    """
    from shopman.shop.models import QualityGrade

    partition = output_partition(work_order)
    if not partition:
        return default_grade_ref()

    ranks = dict(QualityGrade.objects.values_list("ref", "rank"))
    totals: dict[str, Decimal] = {}
    for group in partition:
        totals[group["grade_ref"]] = totals.get(group["grade_ref"], Decimal("0")) + Decimal(
            group["quantity"]
        )
    return max(totals, key=lambda ref: (totals[ref], ranks.get(ref, 0)))
