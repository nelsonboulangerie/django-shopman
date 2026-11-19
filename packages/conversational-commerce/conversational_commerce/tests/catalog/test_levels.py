"""Níveis A0 a A5 e a escada de identidade (v2 5.6)."""

from __future__ import annotations

import pytest

from conversational_commerce.catalog import (
    MOVES,
    at_least_identity,
    evaluate_move,
    requires_confirmation,
    stricter_authority,
)
from conversational_commerce.profile import IneligibilityCode

from .situations import happy, with_rule


def test_identity_ladder_order():
    ladder = ["anonymous", "transported", "weak_verified", "strong_verified"]
    for lower, higher in zip(ladder, ladder[1:], strict=False):
        assert at_least_identity(higher, lower)
        assert not at_least_identity(lower, higher)


def test_confirmation_from_a3_up():
    assert [requires_confirmation(level) for level in ("A0", "A1", "A2", "A3", "A4", "A5")] == [
        False, False, False, True, True, True,
    ]


def test_profile_can_raise_a_level_but_not_lower_it():
    assert stricter_authority("A3", "A1") == "A3"
    situation, profile = happy("commit_order")
    profile = with_rule(profile, "commit_order", authority="A1", confirmation=False)
    evaluation = evaluate_move("commit_order", situation, profile)
    assert IneligibilityCode.CONFIRMATION_WEAKER_THAN_LEVEL in evaluation.blocked_by


@pytest.mark.parametrize("move", sorted(MOVES))
def test_a5_in_the_profile_forbids_the_move_to_automation(move):
    if MOVES[move].always_available:
        pytest.skip("informar a limitação e encaminhar não são governados pelo perfil")
    situation, profile = happy(move)
    profile = with_rule(profile, move, authority="A5", confirmation=True)
    assert IneligibilityCode.AUTHORITY_FORBIDDEN in evaluate_move(move, situation, profile).blocked_by


def test_identity_rule_missing_for_the_channel():
    situation, profile = happy("inform")
    profile = with_rule(profile, "inform", min_identity={"other-channel": "anonymous"})
    assert evaluate_move("inform", situation, profile).blocked_by == (IneligibilityCode.IDENTITY_RULE_ABSENT,)


def test_expired_fact_is_unavailable_not_stale_value():
    from conversational_commerce.contracts import Known

    situation, profile = happy("inform")
    import dataclasses

    stale = {"opening_hours": Known(value="07:00-19:00", source="commerce", observed_at="2026-11-18T10:00:00.000000Z",
                                    valid_until="2026-11-18T13:00:00.000000Z")}
    evaluation = evaluate_move("inform", dataclasses.replace(situation, facts_needed=stale), profile)
    assert evaluation.blocked_by == (IneligibilityCode.FACT_UNAVAILABLE,)
