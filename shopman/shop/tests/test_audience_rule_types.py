"""Regra inteira com valor que não converte: recusa nomeada, nunca ``ValueError`` cru.

``bought_within_days``, ``vip_first_minutes`` e ``preferred_hour_window_hours`` eram
lidos com ``int()`` direto. Uma regra salva com ``"sete"`` derrubava contagem,
disparo, aprovação e o anúncio do evento com 500 — e continuava salva. Aqui o
resolvedor grita no dialeto do contrato (``invalid_audience_rules``) e regra válida
segue com a mesma semântica de sempre.
"""

from __future__ import annotations

import pytest

from shopman.shop.services import audience
from shopman.shop.services.marketing_contracts import MarketingContractError

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("key", audience.INTEGER_RULE_KEYS)
def test_a_non_integer_rule_is_a_named_contract_error(key):
    with pytest.raises(MarketingContractError) as caught:
        audience.resolve({key: "sete"})

    assert caught.value.code == "invalid_audience_rules"
    assert caught.value.field_errors == {"audience_rules": (key,)}
    assert caught.value.detail


def test_every_offending_key_is_named_at_once():
    offending = audience.invalid_integer_rules(
        {
            "bought_within_days": "sete",
            "vip_first_minutes": ["dez"],
            "preferred_hour_window_hours": 2,
        }
    )

    assert offending == ["bought_within_days", "vip_first_minutes"]


@pytest.mark.parametrize("value", [7, "7", 7.9, 0, None, "", False])
def test_values_that_int_always_accepted_keep_resolving(value):
    """Mesma régua de sempre: ausente/vazio/zero valem 0, numérico converte."""
    result = audience.resolve(
        {
            "bought_within_days": value,
            "vip_first_minutes": value,
            "preferred_hour_window_hours": value,
        }
    )

    assert result.total == 0
    assert audience.invalid_integer_rules({"preferred_hour_window_hours": value}) == []


def test_a_broken_payload_is_treated_as_no_rules():
    assert audience.invalid_integer_rules("atacado") == []
    assert audience.invalid_integer_rules(None) == []


def test_the_dead_profile_helper_is_gone():
    assert not hasattr(audience, "_profile")
