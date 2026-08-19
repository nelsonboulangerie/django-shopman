"""Os primeiros alarmes do B.I.: régua como dado, baseline sem modelo, cooldown obrigatório.

Cobre as duas métricas (importação silenciosa; faturamento de ontem contra a
média do mesmo dia da semana), a abstenção declarada (dia fechado, baseline
curto), o disparo que vira OperatorAlert + BIAlertEvent, o cooldown que cala
sem esquecer, e as regras padrão do seed.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.backstage.bi.alerts import evaluate_all, import_silence, revenue_vs_baseline
from shopman.backstage.models import (
    BIAlertEvent,
    BIAlertRule,
    HistoricalSale,
    ImportBatch,
    OperatorAlert,
)
from shopman.backstage.tests.support import historical_batch


def _day(days_ago: int):
    return timezone.localdate() - timedelta(days=days_ago)


def _sale(days_ago: int, total_q: int):
    local = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
    HistoricalSale.objects.create(
        batch=historical_batch("yooga"), source="yooga", external_id=HistoricalSale.objects.count() + 1,
        occurred_at=local - timedelta(days=days_ago), total_q=total_q,
    )


@pytest.fixture
def revenue_rule(db):
    return BIAlertRule.objects.create(
        ref="faturamento", label="Faturamento do dia abaixo do esperado",
        metric=BIAlertRule.Metric.DAILY_REVENUE_VS_BASELINE, severity="warning",
        cooldown_minutes=24 * 60, threshold_percent=70, baseline_weeks=4,
    )


@pytest.fixture
def silence_rule(db):
    return BIAlertRule.objects.create(
        ref="silencio", label="Importação do Yooga não chegou",
        metric=BIAlertRule.Metric.IMPORT_SILENCE, severity="warning",
        cooldown_minutes=60, source="yooga", expected_every_days=7,
    )


# ── Faturamento contra o mesmo dia da semana ─────────────────────────────────


@pytest.mark.django_db
def test_yesterday_below_the_same_weekday_average_fires(revenue_rule):
    for weeks_ago in (1, 2, 3, 4):
        _sale(1 + 7 * weeks_ago, 10000)  # quatro "ontens" de semanas passadas: R$ 100
    _sale(1, 5000)  # ontem: R$ 50 = 50% < 70%
    reading = revenue_vs_baseline(revenue_rule, today=timezone.localdate())
    assert reading.fired is True
    assert (reading.value, reading.baseline) == (5000.0, 10000.0)
    assert "50% do esperado" in reading.message


@pytest.mark.django_db
def test_short_baseline_abstains_instead_of_guessing(revenue_rule):
    _sale(8, 10000)
    _sale(15, 10000)
    _sale(1, 100)
    reading = revenue_vs_baseline(revenue_rule, today=timezone.localdate())
    assert reading.fired is False and reading.value is None
    assert "sem baseline" in reading.message


@pytest.mark.django_db
def test_yesterday_without_a_single_sale_on_an_open_day_is_a_loud_zero(revenue_rule):
    for weeks_ago in (1, 2, 3, 4):
        _sale(1 + 7 * weeks_ago, 10000)
    # nada ontem, e o calendário diz que a casa abre — zero é o pior caso, não ausência
    from shopman.backstage.services.day_similarity import untrustworthy_days

    yesterday = _day(1)
    if yesterday in untrustworthy_days(since=yesterday, until=yesterday):
        pytest.skip("ontem é dia fechado no calendário desta loja; o alarme se abstém de propósito")
    reading = revenue_vs_baseline(revenue_rule, today=timezone.localdate())
    assert reading.fired is True and reading.value == 0.0


# ── Importação silenciosa ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_import_silence_fires_when_the_expected_batch_is_late_or_never_came(silence_rule):
    never = import_silence(silence_rule, now=timezone.now())
    assert never.fired is True and "nenhum lote" in never.message

    ImportBatch.objects.create(source="yooga", status="done", file_sha256="a" * 64)
    fresh = import_silence(silence_rule, now=timezone.now())
    assert fresh.fired is False

    late = import_silence(silence_rule, now=timezone.now() + timedelta(days=8))
    assert late.fired is True and late.value >= 8
    # Lote que FALHOU não conta como chegada.
    ImportBatch.objects.create(source="yooga", status="failed", file_sha256="b" * 64)
    assert import_silence(silence_rule, now=timezone.now() + timedelta(days=8)).fired is True


# ── O ciclo: avisa, registra, respeita o cooldown ────────────────────────────


@pytest.mark.django_db
def test_a_fired_rule_warns_the_operator_once_and_then_keeps_quiet(silence_rule):
    first = evaluate_all()
    assert (first.evaluated, first.fired, first.silenced) == (1, 1, 0)
    event = BIAlertEvent.objects.get()
    alert = OperatorAlert.objects.get()
    assert event.operator_alert == alert
    assert alert.type == "bi_import_silence" and alert.severity == "warning"
    assert alert.message.startswith("Importação do Yooga não chegou: ")
    silence_rule.refresh_from_db()
    assert silence_rule.last_fired_at is not None and silence_rule.last_reading["fired"] is True

    second = evaluate_all()  # dentro do cooldown de 60 min: mede, registra, não grita
    assert (second.fired, second.silenced) == (0, 1)
    assert OperatorAlert.objects.count() == 1 and BIAlertEvent.objects.count() == 1

    third = evaluate_all(now=timezone.now() + timedelta(hours=2))
    assert third.fired == 1
    assert OperatorAlert.objects.count() == 2


@pytest.mark.django_db
def test_inactive_rules_are_not_evaluated(silence_rule):
    silence_rule.is_active = False
    silence_rule.save()
    assert evaluate_all().evaluated == 0
    assert OperatorAlert.objects.count() == 0


@pytest.mark.django_db
def test_command_and_worker_wiring(silence_rule, capsys):
    from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

    call_command("evaluate_bi_alerts")
    assert "1 avaliados, 1 disparados" in capsys.readouterr().out
    assert MAINTENANCE_COMMANDS.index("evaluate_bi_alerts") > MAINTENANCE_COMMANDS.index("refresh_bi_daily_series")


@pytest.mark.django_db
def test_seed_installs_the_default_rules_with_the_import_one_switched_off():
    from config.management.commands.seed import Command as Seed

    Seed()._seed_bi_alert_rules()
    Seed()._seed_bi_alert_rules()
    rules = {rule.ref: rule for rule in BIAlertRule.objects.all()}
    assert set(rules) == {"faturamento-abaixo-do-esperado", "importacao-yooga-silenciosa"}
    assert rules["faturamento-abaixo-do-esperado"].is_active is True
    assert rules["importacao-yooga-silenciosa"].is_active is False
    for rule in rules.values():
        rule.full_clean()  # as regras padrão passam pela própria validação
        assert rule.cooldown_minutes >= 60


@pytest.mark.django_db
def test_rule_validation_demands_what_each_metric_needs(db):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        BIAlertRule(ref="x", label="x", metric="import_silence", cooldown_minutes=10).full_clean()
    with pytest.raises(ValidationError):
        BIAlertRule(ref="y", label="y", metric="daily_revenue_vs_baseline", cooldown_minutes=10,
                    threshold_percent=150).full_clean()
