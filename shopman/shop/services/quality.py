"""Derivações de qualidade da fornada a partir das linhas de OUTPUT (ADR-017 §3).

Não existe campo de qualidade em ``WorkOrder`` — o ``meta["quality"]`` morreu.
A qualidade da fornada é DERIVADA da partição: as linhas de OUTPUT carregam
``quality_grade_ref``, e quem precisa de um agregado calcula aqui.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


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
    """A partição da fornada: ``[{grade_ref, quantity}, ...]`` das linhas de OUTPUT.

    Linha sem grau (finish escalar, fornada antiga) conta como o grau padrão —
    o mesmo default do fechamento sem classificação.
    """
    from shopman.craftsman.models import WorkOrderItem

    # Quem consome isto são receivers de marketing/fomo — que NUNCA podem
    # derrubar a operação que os disparou. Sender sem pk (dublê, evento
    # sintético) ou lookup quebrado degradam para partição vazia.
    if not getattr(work_order, "pk", None):
        return []
    try:
        lines = list(
            WorkOrderItem.objects.filter(
                work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT
            ).values_list("quality_grade_ref", "quantity")
        )
    except Exception:
        logger.debug("quality.partition_lookup_failed wo=%r", work_order, exc_info=True)
        return []
    fallback = default_grade_ref()
    return [
        {"grade_ref": grade_ref or fallback, "quantity": str(quantity)}
        for grade_ref, quantity in lines
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
