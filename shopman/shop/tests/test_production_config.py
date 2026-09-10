"""
ProductionConfig — contrato, cascata Shop.defaults["production"] e validação.

Espelha o padrão de conformance do ChannelConfig: defaults sensatos, overrides
via Shop.defaults, validação que acusa cedo com mensagens específicas.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from shopman.shop.models import Shop
from shopman.shop.production_config import ProductionConfig

pytestmark = pytest.mark.django_db


# ── Defaults ──


class TestDefaults:
    def test_defaults_are_sane(self):
        config = ProductionConfig()
        assert config.suggestion.seasons == {}
        assert config.suggestion.high_demand_multiplier is None
        assert config.suggestion.safety_stock_percent is None
        assert config.alerts.low_yield_threshold == "0.80"
        assert config.alerts.default_max_started_minutes == 240
        assert config.alerts.late_check_cadence_minutes == 15
        assert config.order_match == "first_planned"

    def test_defaults_validate(self):
        ProductionConfig().validate()

    def test_load_without_shop_returns_defaults(self):
        config = ProductionConfig.load()
        assert config.to_dict() == ProductionConfig.defaults()


# ── Cascata ──


class TestCascade:
    def test_shop_defaults_override(self):
        Shop.objects.create(
            name="Nelson",
            defaults={
                "production": {
                    "suggestion": {
                        "seasons": {"hot": [12, 1, 2]},
                        "high_demand_multiplier": "1.2",
                        "safety_stock_percent": "0.30",
                    },
                    "alerts": {"low_yield_threshold": "0.70"},
                    "order_match": "earliest_target",
                }
            },
        )
        config = ProductionConfig.load()
        assert config.suggestion.seasons == {"hot": [12, 1, 2]}
        assert config.suggestion.high_demand_multiplier_decimal == Decimal("1.2")
        assert config.suggestion.safety_stock_percent_decimal == Decimal("0.30")
        assert config.alerts.low_yield_threshold_decimal == Decimal("0.70")
        # Chave ausente herda o default.
        assert config.alerts.default_max_started_minutes == 240
        assert config.order_match == "earliest_target"

    def test_unknown_keys_are_ignored(self):
        Shop.objects.create(
            name="Nelson",
            defaults={"production": {"suggestion": {"typo_key": 1}, "another": True}},
        )
        config = ProductionConfig.load()
        assert config.to_dict() == ProductionConfig.defaults()

    def test_invalid_override_raises_on_load(self):
        Shop.objects.create(
            name="Nelson",
            defaults={"production": {"order_match": "bogus"}},
        )
        with pytest.raises(ValueError, match="order_match"):
            ProductionConfig.load()

    def test_non_mapping_production_override_raises_on_load(self):
        Shop.objects.create(name="Nelson", defaults={"production": ["invalid"]})
        with pytest.raises(ValueError, match="Shop.defaults.production deve ser um dict"):
            ProductionConfig.load()

    def test_all_blocks_override_and_inherit_independently(self):
        Shop.objects.create(
            name="Nelson",
            defaults={
                "production": {
                    "alerts": {"default_max_started_minutes": 90},
                    "episodes": {"sales_silence_minutes": 0},
                    "notifications": {
                        "enabled": True,
                        "severities": ["warning", "critical"],
                    },
                    "panel": {"confirmed_ttl_minutes": 45},
                    "order_match": "manual",
                }
            },
        )

        config = ProductionConfig.load()

        assert config.alerts.default_max_started_minutes == 90
        assert config.alerts.low_yield_threshold == "0.80"
        assert config.episodes.sales_silence_minutes == 0
        assert config.notifications.enabled is True
        assert config.notifications.severities == ["warning", "critical"]
        assert config.panel.delay_tolerance_minutes == 15
        assert config.panel.confirmed_ttl_minutes == 45
        assert config.order_match == "manual"


# ── Sugestão ──


class TestSuggestion:
    def test_season_months_for_resolves_containing_season(self):
        config = ProductionConfig.from_dict({"suggestion": {"seasons": {"hot": [12, 1, 2], "cold": [6, 7, 8]}}})
        assert config.suggestion.season_months_for(1) == [12, 1, 2]
        assert config.suggestion.season_months_for(7) == [6, 7, 8]

    def test_season_months_for_returns_none_outside_seasons(self):
        config = ProductionConfig.from_dict({"suggestion": {"seasons": {"hot": [12, 1]}}})
        assert config.suggestion.season_months_for(5) is None

    def test_season_months_for_without_seasons(self):
        assert ProductionConfig().suggestion.season_months_for(3) is None

    def test_decimal_properties_none_when_unset(self):
        config = ProductionConfig()
        assert config.suggestion.high_demand_multiplier_decimal is None
        assert config.suggestion.safety_stock_percent_decimal is None


# ── Validação ──


class TestValidation:
    @pytest.mark.parametrize(
        ("overrides", "match"),
        [
            ({"suggestion": {"seasons": "not-a-dict"}}, "seasons"),
            ({"suggestion": {"seasons": {"hot": [13]}}}, "meses 1-12"),
            ({"suggestion": {"seasons": {"hot": "jan"}}}, "meses 1-12"),
            (
                {"suggestion": {"seasons": {"hot": [1, 2], "mild": [2, 3]}}},
                "mesmo mês",
            ),
            ({"suggestion": {"high_demand_multiplier": "abc"}}, "high_demand_multiplier"),
            ({"suggestion": {"high_demand_multiplier": "-1"}}, "high_demand_multiplier"),
            ({"suggestion": {"safety_stock_percent": "x"}}, "safety_stock_percent"),
            ({"suggestion": {"safety_stock_percent": "1.01"}}, "safety_stock_percent"),
            ({"alerts": {"low_yield_threshold": "1.5"}}, "low_yield_threshold"),
            ({"alerts": {"low_yield_threshold": "nope"}}, "low_yield_threshold"),
            ({"alerts": {"default_max_started_minutes": 0}}, "default_max_started_minutes"),
            ({"alerts": {"default_max_started_minutes": True}}, "default_max_started_minutes"),
            ({"alerts": {"late_check_cadence_minutes": -5}}, "late_check_cadence_minutes"),
            ({"weight": {"default_bake_loss_pct": "100"}}, "default_bake_loss_pct"),
            ({"weight": {"default_bake_loss_pct": "-1"}}, "default_bake_loss_pct"),
            ({"weight": {"default_bake_loss_pct": "muita"}}, "default_bake_loss_pct"),
            ({"weight": {"default_slack_pct": "100"}}, "default_slack_pct"),
            ({"weight": {"default_slack_pct": "-0.5"}}, "default_slack_pct"),
            ({"episodes": {"sales_silence_minutes": "120"}}, "sales_silence_minutes"),
            ({"notifications": {"enabled": "yes"}}, "enabled"),
            (
                {"notifications": {"severities": ["error", "error"]}},
                "duplicatas",
            ),
            (
                {"notifications": {"enabled": True, "severities": []}},
                "ao menos uma severidade",
            ),
            ({"panel": {"confirmed_ttl_minutes": False}}, "confirmed_ttl_minutes"),
            ({"order_match": "wrong"}, "order_match"),
        ],
    )
    def test_invalid_values_raise(self, overrides, match):
        config = ProductionConfig.from_dict(overrides)
        with pytest.raises(ValueError, match=match):
            config.validate()

    def test_cadence_zero_is_valid_meaning_disabled(self):
        ProductionConfig.from_dict({"alerts": {"late_check_cadence_minutes": 0}}).validate()

    def test_zero_loss_and_zero_slack_are_valid(self):
        """Ficha que não perde nada no forno e não pede folga é declaração legítima."""
        ProductionConfig.from_dict({"weight": {"default_bake_loss_pct": "0", "default_slack_pct": "0"}}).validate()

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {"suggestion": []},
            {"alerts": []},
            {"episodes": []},
            {"weight": []},
            {"notifications": []},
            {"panel": []},
        ],
    )
    def test_root_and_blocks_must_be_mappings(self, payload):
        with pytest.raises(ValueError, match="deve ser um dict"):
            ProductionConfig.from_dict(payload)


# ── Peso anunciado ──


class TestWeightAspect:
    def test_the_house_numbers_are_the_documented_ones(self):
        config = ProductionConfig()
        assert config.weight.default_bake_loss_pct_decimal == Decimal("12")
        assert config.weight.default_slack_pct_decimal == Decimal("5")

    def test_the_shop_can_override_them(self):
        config = ProductionConfig.from_dict({"weight": {"default_slack_pct": "8"}})
        assert config.weight.default_slack_pct_decimal == Decimal("8")
        assert config.weight.default_bake_loss_pct_decimal == Decimal("12")
