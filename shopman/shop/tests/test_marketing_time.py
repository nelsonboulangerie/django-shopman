"""Adversarial civil-time contract for Marketing schedules."""

from datetime import datetime

import pytest
from django.test import override_settings

from shopman.shop.services import marketing_time


def test_dst_gap_has_no_real_instant():
    wall = datetime(2026, 3, 8, 2, 30)

    assert marketing_time.wall_candidates(
        wall,
        timezone_name="America/New_York",
    ) == ()
    with pytest.raises(ValueError, match="nonexistent_local_time"):
        marketing_time.resolve_wall_time(
            wall,
            timezone_name="America/New_York",
        )


def test_dst_fold_requires_an_explicit_occurrence():
    wall = datetime(2026, 11, 1, 1, 30)
    candidates = marketing_time.wall_candidates(
        wall,
        timezone_name="America/New_York",
    )

    assert [item.isoformat() for item in candidates] == [
        "2026-11-01T01:30:00-04:00",
        "2026-11-01T01:30:00-05:00",
    ]
    with pytest.raises(ValueError, match="ambiguous_local_time"):
        marketing_time.resolve_wall_time(
            wall,
            timezone_name="America/New_York",
        )
    assert marketing_time.resolve_wall_time(
        wall,
        timezone_name="America/New_York",
        fold="later",
    ).isoformat() == "2026-11-01T01:30:00-05:00"


def test_named_zone_rejects_an_offset_that_does_not_apply_on_that_date():
    forged = datetime.fromisoformat("2026-07-18T07:00:00-02:00")

    with pytest.raises(ValueError, match="timezone_offset_mismatch"):
        marketing_time.validate_named_instant(
            forged,
            timezone_name="America/Sao_Paulo",
        )

    valid = datetime.fromisoformat("2026-07-18T07:00:00-03:00")
    assert marketing_time.validate_named_instant(
        valid,
        timezone_name="America/Sao_Paulo",
    ).isoformat() == valid.isoformat()


@pytest.mark.parametrize(
    ("instant", "allowed", "next_allowed"),
    [
        ("2026-09-09T19:59:00-03:00", True, None),
        ("2026-09-09T20:00:00-03:00", False, "2026-09-10T08:00:00-03:00"),
        ("2026-09-10T07:59:00-03:00", False, "2026-09-10T08:00:00-03:00"),
        ("2026-09-10T08:00:00-03:00", True, None),
    ],
)
def test_quiet_hours_boundary_is_exact(instant, allowed, next_allowed):
    result = marketing_time.delivery_window(
        datetime.fromisoformat(instant),
        timezone_name="America/Sao_Paulo",
    )

    assert result.allowed is allowed
    assert (
        result.next_allowed_at.isoformat() if result.next_allowed_at else None
    ) == next_allowed


@override_settings(TIME_ZONE="America/Sao_Paulo")
def test_client_cannot_replace_the_configured_shop_timezone():
    assert marketing_time.require_configured_timezone("America/Sao_Paulo") == (
        "America/Sao_Paulo"
    )
    with pytest.raises(ValueError, match="timezone_mismatch"):
        marketing_time.require_configured_timezone("UTC")
