"""Capacidade dos apps de operação — a regra que transforma leitura em aviso.

O que o dono pediu (17/09): saber se os apps de chão de loja vão engasgar no pico e
receber notificação quando passar de X% da capacidade. As promessas travadas aqui:

- pico curto NÃO vira alarme (duração mínima acima do crítico);
- um aviso aberto por serviço (dedupe), e só um;
- lacuna na série não inventa "acima há 5 min";
- o uso folgado pelo mesmo tempo RESOLVE o aviso (senão o dedupe calaria o próximo pico);
- os números vêm do Admin, com padrão quando ausentes.
"""

from __future__ import annotations

import logging

import pytest
from django.core.cache import cache

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Shop
from shopman.shop.operator_capacity_policy import (
    OperatorCapacityPolicy,
    resolve_operator_capacity_policy,
)
from shopman.shop.services.operator_capacity import (
    ALERT_TYPE,
    STALE_GAP_SECONDS,
    CapacitySample,
    InvalidCapacitySample,
    dedupe_key,
    evaluate_sample,
    parse_sample,
)

POLICY = OperatorCapacityPolicy(attention_percent=75, critical_percent=90, sustain_minutes=5)
T0 = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _sample(memory: float | None, cpu: float | None = 10.0, *, service: str = "operator-floor", available=True):
    return CapacitySample(service=service, available=available, memory_percent=memory, cpu_percent=cpu)


def _feed(values, *, start=T0, step=45, service="operator-floor", policy=POLICY):
    """Uma amostra a cada ``step`` segundos, como as abas fazem."""
    result = None
    for index, memory in enumerate(values):
        result = evaluate_sample(_sample(memory, service=service), policy, now=start + index * step)
    return result


def _open_alerts(service="operator-floor"):
    return OperatorAlert.objects.filter(
        type=ALERT_TYPE,
        resolved_at__isnull=True,
        message__contains=dedupe_key(service),
    )


class TestPolicy:
    def test_absent_block_uses_the_defaults(self):
        for defaults in (None, {}, {"operator_capacity": {}}):
            policy = OperatorCapacityPolicy.from_defaults(defaults)
            assert (policy.attention_percent, policy.critical_percent, policy.sustain_minutes) == (75, 90, 5)

    def test_configured_values_win(self):
        policy = OperatorCapacityPolicy.from_defaults(
            {"operator_capacity": {"attention_percent": 60, "critical_percent": 80, "sustain_minutes": 10}}
        )
        assert policy.as_payload() == {"attention_percent": 60, "critical_percent": 80, "sustain_minutes": 10}

    @pytest.mark.parametrize(
        "block",
        [
            {"attention_percent": 0},
            {"critical_percent": 101},
            {"sustain_minutes": 0},
            {"sustain_minutes": "5"},
            {"attention_percent": True},
            {"critical_percent": 90.5},
        ],
    )
    def test_value_outside_the_admin_contract_falls_back_loudly(self, block, caplog):
        policy_logger = logging.getLogger("shopman.shop.operator_capacity_policy")
        policy_logger.addHandler(caplog.handler)
        try:
            with caplog.at_level(logging.WARNING, logger="shopman.shop.operator_capacity_policy"):
                policy = OperatorCapacityPolicy.from_defaults({"operator_capacity": block})
        finally:
            policy_logger.removeHandler(caplog.handler)

        assert policy == OperatorCapacityPolicy()
        assert any("_invalid" in record.getMessage() for record in caplog.records)

    def test_inverted_pair_falls_back_together(self, caplog):
        policy = OperatorCapacityPolicy.from_defaults(
            {"operator_capacity": {"attention_percent": 95, "critical_percent": 80, "sustain_minutes": 3}}
        )
        assert (policy.attention_percent, policy.critical_percent) == (75, 90)
        # A duração é decisão independente do par e sobrevive.
        assert policy.sustain_minutes == 3

    @pytest.mark.django_db
    def test_resolves_from_the_shop_singleton(self):
        Shop.objects.create(
            name="Loja",
            defaults={"operator_capacity": {"critical_percent": 85, "sustain_minutes": 2}},
        )
        cache.clear()
        policy = resolve_operator_capacity_policy()
        assert policy.as_payload() == {"attention_percent": 75, "critical_percent": 85, "sustain_minutes": 2}


class TestParseSample:
    def test_accepts_the_closed_contract(self):
        sample = parse_sample(
            {"service": "operator-floor", "available": True, "memory_percent": 62.44, "cpu_percent": 18}
        )
        assert sample == CapacitySample("operator-floor", True, 62.4, 18.0)
        assert sample.peak == 62.4

    def test_unavailable_never_carries_numbers(self):
        sample = parse_sample({"service": "pos", "available": False, "memory_percent": 50, "cpu_percent": 5})
        assert sample.memory_percent is None and sample.cpu_percent is None
        assert sample.peak is None

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            [],
            {"available": True},
            {"service": "Operator Floor", "available": True},
            {"service": "../etc", "available": True},
            {"service": "pos", "available": "yes"},
            {"service": "pos", "available": True, "memory_percent": 101},
            {"service": "pos", "available": True, "cpu_percent": -1},
            {"service": "pos", "available": True, "cpu_percent": "12"},
            {"service": "pos", "available": True, "memory_percent": True},
            {"service": "pos", "available": True, "memory_percent": float("nan")},
        ],
    )
    def test_refuses_anything_else(self, payload):
        with pytest.raises(InvalidCapacitySample):
            parse_sample(payload)


@pytest.mark.django_db
class TestEvaluation:
    def test_short_peak_does_not_alert(self):
        # 4 min acima do crítico e cai: pico de abertura de caixa, não engasgo.
        _feed([95] * 6 + [40])
        assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()

    def test_sustained_critical_raises_one_critical_alert_with_the_numbers(self):
        # 0..7 min acima (45 s cada) → passa dos 5 min na 8ª amostra.
        result = _feed([93] * 10)

        alerts = list(_open_alerts())
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.severity == "critical"
        assert alert.get_type_display() == "Apps de operação no limite da capacidade"
        assert "Apps do chão de loja" in alert.message
        assert "acima de 90% da capacidade" in alert.message
        assert "memória 93%" in alert.message
        assert "CPU 10%" in alert.message
        assert result.level == "critical"

    def test_cpu_counts_as_much_as_memory(self):
        for index in range(9):
            evaluate_sample(_sample(20.0, cpu=97.0), POLICY, now=T0 + index * 45)
        assert _open_alerts().count() == 1

    def test_dedupe_one_open_alert_per_service_across_many_tabs(self):
        # Várias abas reportando o mesmo contêiner quase ao mesmo tempo.
        for index in range(12):
            for offset in (0, 3, 7):
                evaluate_sample(_sample(96.0), POLICY, now=T0 + index * 45 + offset)
        assert _open_alerts().count() == 1

    def test_services_are_independent(self):
        _feed([96] * 9, service="operator-floor")
        _feed([96] * 9, service="operator-office")
        assert _open_alerts("operator-floor").count() == 1
        assert _open_alerts("operator-office").count() == 1

    def test_attention_band_neither_alerts_nor_resolves(self):
        _feed([80] * 20)
        assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()

    def test_band_between_attention_and_critical_breaks_the_count(self):
        # 4 min acima, 45 s na faixa de atenção, 4 min acima: nunca 5 min seguidos.
        _feed([95] * 6 + [80] + [95] * 6)
        assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()

    def test_gap_in_the_series_does_not_invent_duration(self):
        evaluate_sample(_sample(95.0), POLICY, now=T0)
        # Ninguém reportou por 10 min; a próxima amostra acima começa a contar do zero.
        result = evaluate_sample(_sample(95.0), POLICY, now=T0 + STALE_GAP_SECONDS + 420)
        assert result.alerted is False
        assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()

    def test_sustained_relief_resolves_so_the_next_peak_alerts_again(self):
        _feed([95] * 9)
        assert _open_alerts().count() == 1

        # 5 min folgado depois do pico: o sistema resolve.
        _feed([40] * 9, start=T0 + 9 * 45)
        assert _open_alerts().count() == 0
        resolved = OperatorAlert.objects.get(type=ALERT_TYPE)
        assert resolved.resolved_by == "monitor de capacidade"
        assert resolved.resolved_at is not None

        # Novo pico sustentado: novo aviso (o dedupe não calou).
        _feed([95] * 9, start=T0 + 18 * 45)
        assert _open_alerts().count() == 1
        assert OperatorAlert.objects.filter(type=ALERT_TYPE).count() == 2

    def test_short_relief_does_not_resolve(self):
        _feed([95] * 9)
        _feed([40] * 3, start=T0 + 9 * 45)
        assert _open_alerts().count() == 1

    def test_admin_values_drive_the_rule(self):
        tight = OperatorCapacityPolicy(attention_percent=50, critical_percent=60, sustain_minutes=1)
        _feed([65, 65, 65], policy=tight)
        assert _open_alerts().count() == 1
        assert "acima de 60% da capacidade" in _open_alerts().get().message

    def test_unavailable_sample_is_not_recorded(self):
        result = evaluate_sample(_sample(None, None, available=False), POLICY, now=T0)
        assert result.level == "unknown"
        assert result.recorded is False

    def test_failed_write_is_retried_on_the_next_sample(self, monkeypatch):
        from shopman.shop.services import observability

        calls = []
        real = observability.create_operator_alert

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return None  # falha já logada lá dentro; nenhum alerta aberto
            return real(**kwargs)

        monkeypatch.setattr(observability, "create_operator_alert", flaky)
        _feed([95] * 10)
        assert len(calls) == 2
        assert _open_alerts().count() == 1
