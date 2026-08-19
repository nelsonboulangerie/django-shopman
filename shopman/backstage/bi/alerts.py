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


def _measure(rule, now) -> Reading:
    from shopman.backstage.models import BIAlertRule

    Metric = BIAlertRule.Metric
    today = timezone.localtime(now).date()
    if rule.metric == Metric.IMPORT_SILENCE:
        return import_silence(rule, now=now)
    if rule.metric == Metric.DAILY_REVENUE_VS_BASELINE:
        return revenue_vs_baseline(rule, today=today)
    if rule.metric == Metric.NATIVE_OVERRIDES_HISTORY:
        return native_overrides_history(rule, today=today)
    if rule.metric == Metric.CASH_VARIANCE_BY_OPERATOR:
        return cash_variance_by_operator(rule, today=today)
    if rule.metric == Metric.CURATION_PENDING:
        return curation_pending(rule)
    return Reading(value=None, baseline=None, fired=False, message=f"métrica desconhecida: {rule.metric}")


def _evaluate(rule, now, summary: CycleSummary) -> None:
    reading = _measure(rule, now)
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


#: O tipo de OperatorAlert por métrica — o bus do operador fala o vocabulário dele.
_ALERT_TYPE_BY_METRIC = {
    "import_silence": "bi_import_silence",
    "daily_revenue_vs_baseline": "bi_below_baseline",
    "native_overrides_history": "bi_source_conflict",
    "cash_variance_by_operator": "bi_cash_variance",
    "curation_pending": "bi_curation_pending",
}

#: O que o operador lê quando a métrica é apuração de caixa: nem nome, nem
#: valor. O detalhe mora no BIAlertEvent, que o Admin só mostra a quem audita.
_CASH_AUDIT_PUBLIC_MESSAGE = (
    "quebra de caixa acumulada passou da régua em {count} operador(es) nos últimos {days} dias. "
    "Detalhe no B.I. › Caixa (quem audita)."
)


def _fire(rule, reading: Reading, now) -> None:
    from shopman.backstage.models import BIAlertEvent, BIAlertRule
    from shopman.backstage.services.alerts import create_alert

    alert_type = _ALERT_TYPE_BY_METRIC[rule.metric]
    public_message = reading.message
    if rule.metric in BIAlertRule.AUDIT_ONLY_METRICS:
        public_message = _CASH_AUDIT_PUBLIC_MESSAGE.format(
            count=int(reading.value or 0), days=int(rule.lookback_days or 0),
        )
    with transaction.atomic():
        operator_alert = create_alert(
            type=alert_type, severity=rule.severity, message=f"{rule.label}: {public_message}",
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
                f"{target:%d/%m} ({_weekday_name(target)}) faturou {_brl(measured)}, "
                f"{share:.0f}% do esperado ({_brl(baseline)} na média de {len(samples)} "
                f"{_weekday_name(target)}s); régua: {threshold}%"
            ),
        )
    return Reading(
        value=measured, baseline=baseline, fired=False,
        message=f"{target:%d/%m}: {share:.0f}% do esperado, acima da régua de {threshold}%",
    )


def native_overrides_history(rule, *, today: date) -> Reading:
    """Dias recentes em que um punhado de pedidos nativos apagou muito histórico.

    Lê o guard persistido na série diária (``DailySalesFact.historical_dropped``);
    sem a série materializada para a janela, recompõe pela canônica. Um pedido
    de teste num dia antigo apaga ~110 vendas do Yooga daquele dia — a regra é
    certa, ficar mudo é que não era.
    """
    from shopman.backstage.bi.canonical import read_sales
    from shopman.backstage.bi.daily_series import materialized
    from shopman.backstage.models import DailySalesFact

    days = int(rule.lookback_days or 7)
    since, until = today - timedelta(days=days - 1), today
    max_native = int(rule.max_native_orders or 0)
    min_dropped = int(rule.min_historical_dropped or 0)

    if materialized(since, until) is not None:
        rows = DailySalesFact.objects.filter(
            date__range=(since, until), source="shopman", historical_dropped__gt=min_dropped,
            orders__lte=max_native,
        ).values_list("date", "orders", "historical_dropped")
        hits = [(day, orders, dropped) for day, orders, dropped in rows]
    else:
        window = read_sales(since, until)
        native_per_day: dict[date, int] = {}
        for sale in window.sales:
            if sale.source == "shopman":
                native_per_day[sale.day] = native_per_day.get(sale.day, 0) + 1
        hits = [
            (day, native_per_day[day], dropped)
            for day, dropped in sorted(window.historical_dropped.items())
            if native_per_day.get(day, 0) <= max_native and dropped > min_dropped
        ]
    if not hits:
        return Reading(value=0.0, baseline=float(min_dropped), fired=False,
                       message=f"nenhum dia nos últimos {days} em que pedido nativo apagou histórico acima da régua")
    worst = max(hits, key=lambda hit: hit[2])
    listing = "; ".join(f"{day:%d/%m}: {orders} nativo(s) apagaram {dropped}" for day, orders, dropped in hits)
    return Reading(
        value=float(worst[2]), baseline=float(min_dropped), fired=True,
        message=f"{len(hits)} dia(s) em que um pedido nativo apagou histórico — {listing}",
    )


def cash_variance_by_operator(rule, *, today: date) -> Reading:
    """|Σ quebra| por operador nos turnos fechados da janela, contra a régua em centavos.

    O valor é a CONTAGEM de operadores acima da régua; o detalhe (quem, quanto)
    vai na mensagem do disparo — que o Admin só mostra a quem audita.
    """
    from shopman.backstage.bi.sources import cashman

    days = int(rule.lookback_days or 7)
    threshold = abs(int(rule.threshold_q or 0))
    since, until = today - timedelta(days=days - 1), today
    by_operator: dict[str, int] = {}
    shifts = 0
    for shift in cashman.read_closed_shifts(since, until):
        shifts += 1
        by_operator[shift.operator_key] = by_operator.get(shift.operator_key, 0) + (shift.difference_q or 0)
    if not shifts:
        return Reading(value=None, baseline=float(threshold), fired=False,
                       message=f"nenhum turno fechado nos últimos {days} dias: sem leitura")
    over = {op: total for op, total in by_operator.items() if abs(total) > threshold}
    if not over:
        return Reading(value=0.0, baseline=float(threshold), fired=False,
                       message=f"{shifts} turno(s) em {days} dias; nenhum operador acima da régua")
    detail = "; ".join(
        f"{op}: {'−' if total < 0 else '+'}{_brl(abs(total))}" for op, total in sorted(over.items())
    )
    return Reading(
        value=float(len(over)), baseline=float(threshold), fired=True,
        message=f"{len(over)} operador(es) com quebra acumulada acima de {_brl(threshold)} em {days} dias — {detail}",
    )


def curation_pending(rule) -> Reading:
    """No último lote concluído da origem, a fatia de linhas sem de-para de produto confirmado."""
    from shopman.backstage.models import HistoricalSaleItem, ImportBatch, ProductAlias

    batch = (
        ImportBatch.objects.filter(source=rule.source, status=ImportBatch.Status.DONE)
        .order_by("-imported_at")
        .first()
    )
    if batch is None:
        return Reading(value=None, baseline=None, fired=False,
                       message=f"nenhum lote concluído de '{rule.source}': nada a curar")
    confirmed_skus = set(
        ProductAlias.objects.confirmed().filter(source=rule.source).exclude(external_sku="")
        .values_list("external_sku", flat=True)
    )
    confirmed_names = set(
        ProductAlias.objects.confirmed().filter(source=rule.source, external_sku="")
        .values_list("external_name", flat=True)
    )
    total = 0
    pending = 0
    for sku, name in HistoricalSaleItem.objects.filter(sale__batch=batch).order_by().values_list("sku", "product_name"):
        total += 1
        key_ok = (sku in confirmed_skus) if sku else ((name or "") in confirmed_names)
        if not key_ok:
            pending += 1
    if not total:
        return Reading(value=None, baseline=None, fired=False,
                       message=f"lote #{batch.pk} de '{rule.source}' não tem linhas de item")
    share = pending / total * 100
    threshold = int(rule.threshold_percent or 0)
    message = (
        f"lote #{batch.pk} de '{rule.source}' ({timezone.localtime(batch.imported_at):%d/%m}): "
        f"{pending} de {total} linhas ({share:.0f}%) sem de-para de produto confirmado; régua {threshold}%"
    )
    return Reading(value=round(share, 1), baseline=float(threshold), fired=share > threshold, message=message)


def _brl(cents: float) -> str:
    """Centavos → "R$ 1.234,56", para a frase do alarme."""
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(int(round(cents)))}"


_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _weekday_name(day: date) -> str:
    return _WEEKDAYS[day.weekday()]
