"""Avaliação dos alarmes do B.I. contra a camada de leitura (BI-DATA-FOUNDATION-PLAN §7.2).

Um ciclo: para cada regra ativa, medir, comparar com a régua, respeitar o
cooldown, registrar o que viu e — se disparou — avisar pelo bus do operador
(``OperatorAlert``) e gravar o ``BIAlertEvent``. Nada aqui lê dado cru: a
série diária vem de ``sales_series.daily_sales`` (materializada quando há
cobertura), os lotes de ``ImportBatch``.

**Sem amostra a regra não opina.** Ontem fechado ou atrapalhado, baseline
com menos de ``MIN_BASELINE_SAMPLES`` dias parecidos, origem que nunca teve
lote E nunca foi esperada: ``Reading.fired=False`` com o motivo em
``message`` — o Admin mostra "não opinou, porque…", nunca um zero inventado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Mesmo dia da semana com menos dias que isto no baseline não é baseline.
MIN_BASELINE_SAMPLES = 3


@dataclass(frozen=True)
class Reading:
    value: float | None
    baseline: float | None
    fired: bool
    message: str

    def as_json(self) -> dict:
        return {"value": self.value, "baseline": self.baseline, "fired": self.fired, "message": self.message}


@dataclass
class CycleSummary:
    evaluated: int = 0
    fired: int = 0
    silenced: int = 0  # disparou, mas dentro do cooldown: não avisou de novo
    abstained: int = 0  # sem amostra para opinar


def evaluate_all(*, now=None) -> CycleSummary:
    """Avalia toda regra ativa. Falha de uma não derruba as outras (o worker continua)."""
    from shopman.backstage.models import BIAlertRule

    now = now or timezone.now()
    summary = CycleSummary()
    for rule in BIAlertRule.objects.filter(is_active=True).order_by("ref"):
        try:
            _evaluate(rule, now, summary)
        except Exception:
            logger.exception("bi.alerts: regra %s falhou na avaliação (ciclo continua)", rule.ref)
    return summary


def _evaluate(rule, now, summary: CycleSummary) -> None:
    from shopman.backstage.models import BIAlertRule

    reading = (
        import_silence(rule, now=now)
        if rule.metric == BIAlertRule.Metric.IMPORT_SILENCE
        else revenue_vs_baseline(rule, today=timezone.localtime(now).date())
    )
    summary.evaluated += 1
    if reading.value is None and not reading.fired:
        summary.abstained += 1

    fields = ["last_evaluated_at", "last_reading"]
    rule.last_evaluated_at = now
    rule.last_reading = reading.as_json()
    if reading.fired:
        in_cooldown = rule.last_fired_at is not None and (
            now - rule.last_fired_at < timedelta(minutes=rule.cooldown_minutes)
        )
        if in_cooldown:
            summary.silenced += 1
        else:
            _fire(rule, reading, now)
            rule.last_fired_at = now
            fields.append("last_fired_at")
            summary.fired += 1
    rule.save(update_fields=fields)


def _fire(rule, reading: Reading, now) -> None:
    from shopman.backstage.models import BIAlertEvent, BIAlertRule
    from shopman.backstage.services.alerts import create_alert

    alert_type = (
        "bi_import_silence"
        if rule.metric == BIAlertRule.Metric.IMPORT_SILENCE
        else "bi_below_baseline"
    )
    with transaction.atomic():
        operator_alert = create_alert(
            type=alert_type, severity=rule.severity, message=f"{rule.label}: {reading.message}",
        )
        BIAlertEvent.objects.create(
            rule=rule,
            severity=rule.severity,
            value=reading.value,
            baseline=reading.baseline,
            message=reading.message,
            operator_alert=operator_alert,
        )


# ── Métricas ────────────────────────────────────────────────────────────────


def import_silence(rule, *, now) -> Reading:
    """Dias desde o último lote concluído da origem, contra a cadência esperada."""
    from shopman.backstage.models import ImportBatch

    last = (
        ImportBatch.objects.filter(source=rule.source, status=ImportBatch.Status.DONE)
        .order_by("-imported_at")
        .values_list("imported_at", flat=True)
        .first()
    )
    expected = int(rule.expected_every_days or 0)
    if last is None:
        return Reading(
            value=None, baseline=float(expected), fired=True,
            message=f"nenhum lote de '{rule.source}' concluído até hoje; esperado a cada {expected} dias",
        )
    age_days = (now - last).total_seconds() / 86400
    if age_days > expected:
        return Reading(
            value=round(age_days, 1), baseline=float(expected), fired=True,
            message=(
                f"último lote de '{rule.source}' há {age_days:.0f} dias "
                f"({timezone.localtime(last):%d/%m %H:%M}); esperado a cada {expected} dias"
            ),
        )
    return Reading(
        value=round(age_days, 1), baseline=float(expected), fired=False,
        message=f"último lote de '{rule.source}' há {age_days:.0f} dias, dentro do esperado",
    )


def revenue_vs_baseline(rule, *, today: date) -> Reading:
    """Faturamento de ontem contra a média do mesmo dia da semana nas últimas N semanas.

    Ontem, porque o dia de hoje ainda está acontecendo. Dias fechados ou
    atrapalhados (``untrustworthy_days``) não entram no baseline nem valem
    como "ontem" — fechado não é zero, e dia sem luz não ensina demanda.
    """
    from shopman.backstage.projections.sales_series import daily_sales
    from shopman.backstage.services.day_similarity import untrustworthy_days

    target = today - timedelta(days=1)
    weeks = int(rule.baseline_weeks or 0)
    since = target - timedelta(days=7 * weeks)
    excluded = untrustworthy_days(since=since, until=target)
    if target in excluded:
        return Reading(value=None, baseline=None, fired=False,
                       message=f"{target:%d/%m} foi dia fechado ou atrapalhado: sem leitura")

    series = daily_sales(since, target)
    samples = [
        series[day].revenue_q
        for day in (target - timedelta(days=7 * k) for k in range(1, weeks + 1))
        if day not in excluded and day in series and series[day].orders > 0
    ]
    if len(samples) < MIN_BASELINE_SAMPLES:
        return Reading(
            value=None, baseline=None, fired=False,
            message=f"só {len(samples)} {_weekday_name(target)}(s) parecido(s) nas últimas {weeks} semanas: sem baseline",
        )
    baseline = sum(samples) / len(samples)
    measured = float(series[target].revenue_q) if target in series else 0.0
    threshold = int(rule.threshold_percent or 0)
    share = (measured / baseline * 100) if baseline else 0.0
    if share < threshold:
        return Reading(
            value=measured, baseline=baseline, fired=True,
            message=(
                f"{target:%d/%m} ({_weekday_name(target)}) faturou R$ {measured / 100:,.2f}, "
                f"{share:.0f}% do esperado (R$ {baseline / 100:,.2f} na média de {len(samples)} "
                f"{_weekday_name(target)}s); régua: {threshold}%"
            ).replace(",", "X").replace(".", ",").replace("X", "."),
        )
    return Reading(
        value=measured, baseline=baseline, fired=False,
        message=f"{target:%d/%m}: {share:.0f}% do esperado, acima da régua de {threshold}%",
    )


_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _weekday_name(day: date) -> str:
    return _WEEKDAYS[day.weekday()]
