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
    assert set(rules) == {
        "faturamento-abaixo-do-esperado", "importacao-yooga-silenciosa",
        "pedido-nativo-apagou-historico", "quebra-de-caixa-acumulada", "de-para-de-produto-pendente",
    }
    assert rules["faturamento-abaixo-do-esperado"].is_active is True
    assert rules["importacao-yooga-silenciosa"].is_active is False
    assert rules["quebra-de-caixa-acumulada"].metric in BIAlertRule.AUDIT_ONLY_METRICS
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


# ── Alarmes 3–5 ──────────────────────────────────────────────────────────────


def _rule(ref, metric, **params):
    return BIAlertRule.objects.create(
        ref=ref, label=ref, metric=metric, severity="warning", cooldown_minutes=60, **params,
    )


@pytest.mark.django_db
def test_native_override_fires_from_the_persisted_guard_or_live():
    from shopman.orderman.models import Order

    from shopman.backstage.bi.alerts import native_overrides_history
    from shopman.backstage.bi.canonical import CONFLICT_MIN_HISTORICAL
    from shopman.backstage.bi.daily_series import refresh

    rule = _rule("guard", BIAlertRule.Metric.NATIVE_OVERRIDES_HISTORY,
                 lookback_days=7, max_native_orders=5, min_historical_dropped=CONFLICT_MIN_HISTORICAL)
    # Dia 3: um pedido de teste apaga 25 vendas do Yooga.
    local = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
    order = Order.objects.create(ref="TESTE", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=100)
    Order.objects.filter(pk=order.pk).update(created_at=local - timedelta(days=3))
    for _ in range(25):
        _sale(3, 700)

    live = native_overrides_history(rule, today=timezone.localdate())
    assert live.fired is True and live.value == 25.0 and "1 nativo(s) apagaram 25" in live.message

    refresh(_day(6), _day(0))  # com a série materializada, lê o guard persistido
    persisted = native_overrides_history(rule, today=timezone.localdate())
    assert persisted.fired is True and persisted.value == 25.0


@pytest.mark.django_db
def test_native_override_stays_quiet_below_the_ruler():
    from shopman.backstage.bi.alerts import native_overrides_history

    rule = _rule("guard", BIAlertRule.Metric.NATIVE_OVERRIDES_HISTORY,
                 lookback_days=7, max_native_orders=5, min_historical_dropped=20)
    _sale(2, 700)
    reading = native_overrides_history(rule, today=timezone.localdate())
    assert reading.fired is False and reading.value == 0.0


@pytest.mark.django_db
def test_cash_variance_warns_blind_and_keeps_the_detail_for_auditors():
    from django.contrib.auth.models import User
    from shopman.cashman import services as cash
    from shopman.cashman.models import Terminal

    _rule("caixa", BIAlertRule.Metric.CASH_VARIANCE_BY_OPERATOR, lookback_days=7, threshold_q=5000)
    ana = User.objects.create_user("caixa-ana", password="pw", is_staff=True)
    bia = User.objects.create_user("caixa-bia", password="pw", is_staff=True)
    terminal = Terminal.objects.create(ref="t1", label="Caixa 1")
    for operator, counted in ((ana, 2000), (bia, 9800)):  # fundo 100: Ana −80,00; Bia −2,00
        shift = cash.open_shift(operator=operator, terminal=terminal, float_q=10000)
        cash.close_shift(shift, counted_q=counted, actor=operator)

    summary = evaluate_all()
    assert summary.fired == 1
    alert = OperatorAlert.objects.get(type="bi_cash_variance")
    assert "caixa-ana" not in alert.message and "80,00" not in alert.message  # cego para o operador
    assert "1 operador(es)" in alert.message
    event = BIAlertEvent.objects.get()
    assert "caixa-ana" in event.message and "−R$ 80,00" in event.message  # o detalhe, para quem audita
    assert "caixa-bia" not in event.message


@pytest.mark.django_db
def test_curation_pending_counts_lines_without_a_confirmed_alias():
    from decimal import Decimal

    from shopman.offerman.models import Product

    from shopman.backstage.bi.alerts import curation_pending
    from shopman.backstage.models import HistoricalSaleItem, ProductAlias

    rule = _rule("curadoria", BIAlertRule.Metric.CURATION_PENDING, source="yooga", threshold_percent=20)
    assert curation_pending(rule).fired is False  # sem lote, nada a curar

    batch = ImportBatch.objects.create(source="yooga", status="done", file_sha256="c" * 64)
    sale = HistoricalSale.objects.create(batch=batch, source="yooga", external_id=1,
                                         occurred_at=timezone.now(), total_q=300)
    for seq, sku in enumerate(("CT", "PC", "BA", ""), start=1):
        HistoricalSaleItem.objects.create(sale=sale, seq=seq, product_name=f"Produto {seq}", sku=sku,
                                          qty=Decimal("1"), unit_price_q=100, line_total_q=100)
    before = curation_pending(rule)
    assert before.fired is True and before.value == 100.0

    croissant = Product.objects.create(sku="CROISSANT", name="Croissant")
    ProductAlias.objects.create(source="yooga", external_sku="CT", product=croissant, status="confirmed")
    ProductAlias.objects.create(source="yooga", external_sku="PC", product=croissant, status="confirmed")
    ProductAlias.objects.create(source="yooga", external_sku="BA", product=croissant, status="confirmed")
    ProductAlias.objects.create(source="yooga", external_sku="", external_name="Produto 4", product=croissant)  # proposto: não conta
    after = curation_pending(rule)
    assert after.value == 25.0 and after.fired is True  # 1 de 4 (25%) > 20%
    ProductAlias.objects.filter(external_name="Produto 4").update(status="confirmed")
    assert curation_pending(rule).fired is False


@pytest.mark.django_db
def test_admin_hides_cash_audit_detail_from_non_auditors(client):
    from django.contrib.auth.models import Permission, User
    from django.contrib.contenttypes.models import ContentType
    from django.urls import reverse
    from shopman.cashman.models import Shift

    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    rule = _rule("caixa", BIAlertRule.Metric.CASH_VARIANCE_BY_OPERATOR, lookback_days=7, threshold_q=5000)
    rule.last_reading = {"value": 1, "baseline": 5000, "fired": True, "message": "caixa-ana: −R$ 80,00"}
    rule.save()
    BIAlertEvent.objects.create(rule=rule, severity="warning", value=1, baseline=5000, message="caixa-ana: −R$ 80,00")

    manager = User.objects.create_user("gerente", password="pw", is_staff=True)
    manager.user_permissions.add(*Permission.objects.filter(codename__in=("view_bialertrule", "view_bialertevent")))
    client.force_login(manager)
    rules_page = client.get(reverse("admin:backstage_bialertrule_changelist")).content.decode()
    assert "caixa-ana" not in rules_page and "só para quem audita" in rules_page
    events_page = client.get(reverse("admin:backstage_bialertevent_changelist")).content.decode()
    assert "caixa-ana" not in events_page

    manager.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Shift), codename="audit_shift"))
    client.force_login(manager)
    assert "caixa-ana" in client.get(reverse("admin:backstage_bialertrule_changelist")).content.decode()
    assert "caixa-ana" in client.get(reverse("admin:backstage_bialertevent_changelist")).content.decode()
