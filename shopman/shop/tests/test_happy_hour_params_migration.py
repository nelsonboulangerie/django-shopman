"""``shop.0099``: o banco recebe a janela que o fallback do código fazia valer (A7-2)."""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps

from shopman.shop.models import RuleConfig
from shopman.shop.rules.pricing import HappyHourRule

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.shop.migrations.0099_happy_hour_params_explicit")


def _rule(params):
    return RuleConfig.objects.create(
        ref="happy_hour",
        rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Hora da Xepa",
        params=params,
        priority=65,
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ({}, {"discount_percent": 25, "start": "17:30", "end": "18:00"}),
        ({"discount_percent": 30}, {"discount_percent": 30, "start": "17:30", "end": "18:00"}),
        ({"discount_percent": 0, "start": "", "end": "x"}, {"discount_percent": 0, "start": "17:30", "end": "18:00"}),
        ({"discount_percent": 25, "start": "9:00", "end": "10:00"}, {"discount_percent": 25, "start": "09:00", "end": "10:00"}),
    ],
)
def test_o_banco_passa_a_dizer_o_que_o_fallback_fazia_valer(before, after):
    rule = RuleConfig.objects.bulk_create([RuleConfig(
        ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Hora da Xepa", params=before, priority=65,
    )])[0]

    migration.forwards(apps, None)

    rule.refresh_from_db()
    assert rule.params == after
    HappyHourRule.validate_params(rule.params)


def test_params_completos_nao_mudam_e_a_segunda_rodada_e_inerte():
    rule = _rule({"discount_percent": 40, "start": "16:00", "end": "17:00", "extra": "fica"})

    migration.forwards(apps, None)
    migration.forwards(apps, None)

    rule.refresh_from_db()
    assert rule.params == {"discount_percent": 40, "start": "16:00", "end": "17:00", "extra": "fica"}
