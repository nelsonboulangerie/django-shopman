"""K39: requisito crítico ausente no perfil torna a ação inelegível, com código;
informar a limitação e encaminhar seguem possíveis. E linha ``proposed`` não vale."""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.catalog import CATALOG, evaluate_catalog, evaluate_move
from conversational_commerce.contracts import DeploymentProfile, ProfileLine
from conversational_commerce.profile import IneligibilityCode, read_line
from conversational_commerce.profile.test_profile import TEST_LINES, build_test_profile
from conversational_commerce.testing.conformance import conformance

from .situations import happy

ALWAYS = {"inform_limitation", "handoff"}


def _replace_line(profile: DeploymentProfile, line_id: str, **changes) -> DeploymentProfile:
    lines = tuple(dataclasses.replace(line, **changes) if line.id == line_id else line for line in profile.lines)
    return dataclasses.replace(profile, lines=lines)


@conformance("K39", scope="adapter")
@pytest.mark.parametrize("move", ["cancel_order", "amend_order", "grant_discount"])
def test_absent_line_makes_the_dependent_action_ineligible_with_code(move):
    situation, profile = happy(move)
    line_id = profile.actions[move].line_ref
    profile = _replace_line(profile, line_id, setting={"status": "absent", "reason": "owner has not decided"},
                            state="proposed", decided_at=None)
    evaluation = evaluate_move(move, situation, profile)
    assert not evaluation.eligible
    assert IneligibilityCode.PROFILE_LINE_ABSENT in evaluation.blocked_by
    # Informar e encaminhar seguem possíveis.
    for always in ALWAYS:
        assert evaluate_move(always, *happy(always)[:1], profile).eligible


@pytest.mark.parametrize("state", ["proposed", "validating"])
def test_proposed_line_is_not_approved(state):
    situation, profile = happy("cancel_order")
    profile = _replace_line(profile, "commerce.cancel_order", state=state)
    assert read_line(profile, "commerce.cancel_order").usable is False
    evaluation = evaluate_move("cancel_order", situation, profile)
    assert evaluation.blocked_by == (IneligibilityCode.PROFILE_LINE_NOT_APPROVED,)


def test_line_ref_to_a_missing_line_is_not_possible_but_missing_line_reads_absent():
    profile = build_test_profile()
    assert read_line(profile, "no.such.line").code == IneligibilityCode.PROFILE_LINE_ABSENT


def test_move_that_needs_a_line_without_line_ref_is_ineligible():
    situation, profile = happy("cancel_order")
    from .situations import with_rule

    profile = with_rule(profile, "cancel_order", line_ref=None)
    assert evaluate_move("cancel_order", situation, profile).blocked_by == (IneligibilityCode.PROFILE_LINE_ABSENT,)


def test_unsolicited_limit_line_absent_blocks_recommend():
    situation, profile = happy("recommend")
    profile = dataclasses.replace(
        profile, lines=tuple(line for line in profile.lines if line.id != "commerce.unsolicited_initiatives_per_episode")
    )
    evaluation = evaluate_move("recommend", situation, profile)
    assert evaluation.blocked_by == (IneligibilityCode.PROFILE_LINE_ABSENT,)


def test_empty_profile_turns_off_everything_but_limitation_and_handoff():
    situation, profile = happy("inform_limitation")
    empty = dataclasses.replace(profile, actions={}, lines=())
    for evaluation in evaluate_catalog(situation, empty):
        move = evaluation.move
        if move in ALWAYS:
            assert evaluation.eligible, (move, evaluation.blocked_by)
        else:
            assert IneligibilityCode.PROFILE_ACTION_ABSENT in evaluation.blocked_by, move


def test_the_test_profile_turns_every_move_on_with_approved_lines():
    profile = build_test_profile()
    assert {move.name for move in CATALOG} <= set(profile.actions)
    assert all(isinstance(line, ProfileLine) and line.state == "approved" for line in profile.lines)
    assert {line.id for line in profile.lines} == {line_id for line_id, _, _ in TEST_LINES}
    for line_id, value, _ in TEST_LINES:
        assert read_line(profile, line_id).value == value
    # O perfil de teste é um documento válido, ida e volta.
    assert type(profile).from_document(profile.to_document()) == profile


def test_the_test_profile_never_spends():
    profile = build_test_profile()
    assert profile.limits.max_model_calls == 0
    assert profile.limits.max_spend.amount_minor == 0
