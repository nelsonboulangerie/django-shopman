"""Levar ao plano: a falta e a sobra de um dia viram o porquê da sugestão seguinte.

O gesto do "Sobrou ou faltou?" (prévia ``bi-sobra4``, pino 3). Não muda número
nenhum: grava uma ``PlanCarryNote`` por produto que faltou ou sobrou, no próximo
dia com o mesmo dia da semana (o ``plan_day`` da leitura), e o Planejamento mostra
a nota no "Por quê" da linha. Na medida não vira nota: não há porquê a levar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import transaction


@dataclass(frozen=True)
class PlanCarryResult:
    plan_day: str
    carried: int


def carry_to_plan(*, day: date | None, actor=None, compare: str = "") -> PlanCarryResult:
    from shopman.backstage.models import PlanCarryNote
    from shopman.backstage.projections.bi_over_short import (
        VERDICT_OVER,
        VERDICT_SHORT,
        build_bi_over_short,
    )

    report = build_bi_over_short(day=day, compare=compare)
    if not report.plan_day:
        return PlanCarryResult(plan_day="", carried=0)
    target = date.fromisoformat(report.plan_day)
    source = date.fromisoformat(report.day)
    rows = [row for row in report.rows if row.verdict in (VERDICT_SHORT, VERDICT_OVER)]
    with transaction.atomic():
        # Levar de novo o mesmo dia reescreve: o produto que deixou de faltar sai.
        PlanCarryNote.objects.filter(target_date=target, source_day=source).exclude(
            sku__in=[row.sku for row in rows]
        ).delete()
        for row in rows:
            PlanCarryNote.objects.update_or_create(
                target_date=target,
                sku=row.sku,
                source_day=source,
                defaults={
                    "verdict": row.verdict,
                    "facts": {
                        "made": row.made,
                        "sold": row.sold,
                        "leftover": row.leftover,
                        "soldout_at": row.soldout_at,
                        "lost_estimate": row.lost_estimate,
                    },
                    "created_by": actor if getattr(actor, "pk", None) else None,
                },
            )
    return PlanCarryResult(plan_day=report.plan_day, carried=len(rows))


def notes_for(target: date) -> dict[str, list]:
    """As notas do dia do plano, por SKU, do dia lido mais recente ao mais antigo."""
    from shopman.backstage.models import PlanCarryNote

    out: dict[str, list] = {}
    for note in PlanCarryNote.objects.filter(target_date=target).order_by("sku", "-source_day"):
        out.setdefault(note.sku, []).append(note)
    return out
