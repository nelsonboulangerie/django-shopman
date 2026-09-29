from __future__ import annotations

import pytest

from shopman.shop.address_location_config import (
    build_address_location_divergence,
)


def _valid(**overrides):
    return {
        "mode": "visible",
        "threshold_m": 500,
        "max_accuracy_m": 250,
        "maximum_age_ms": 30_000,
        "policy_version": "v1",
        **overrides,
    }


def test_location_divergence_config_is_off_without_explicit_valid_config():
    assert build_address_location_divergence(None, map_enabled=True).mode == "off"
    assert build_address_location_divergence({}, map_enabled=True).mode == "off"
    assert build_address_location_divergence(_valid(), map_enabled=False).mode == "off"


def test_location_divergence_config_projects_measure_and_visible_modes():
    measured = build_address_location_divergence(_valid(mode="measure"), map_enabled=True)
    visible = build_address_location_divergence(_valid(), map_enabled=True)

    assert measured.mode == "measure"
    assert visible.mode == "visible"
    assert visible.threshold_m == 500
    assert visible.max_accuracy_m == 250
    assert visible.maximum_age_ms == 30_000
    assert visible.policy_version == "v1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "automatic"),
        ("threshold_m", 99),
        ("threshold_m", 10_001),
        ("max_accuracy_m", 19),
        ("max_accuracy_m", 2_001),
        ("maximum_age_ms", -1),
        ("maximum_age_ms", 300_001),
        ("policy_version", ""),
        ("policy_version", "x" * 41),
    ],
)
def test_location_divergence_config_fails_closed(field, value):
    assert build_address_location_divergence(_valid(**{field: value}), map_enabled=True).mode == "off"


def test_location_divergence_config_rejects_boolean_numbers():
    assert build_address_location_divergence(_valid(threshold_m=True), map_enabled=True).mode == "off"


def test_location_divergence_config_rejects_fractional_numbers():
    assert build_address_location_divergence(_valid(threshold_m=500.9), map_enabled=True).mode == "off"
