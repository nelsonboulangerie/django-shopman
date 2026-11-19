"""Regras que cruzam campos, uma por contrato onde a v2 escreve um invariante."""

from __future__ import annotations

import copy

import pytest

from conversational_commerce.contracts import (
    ActionCommand,
    AuthorizationGrant,
    Commitment,
    ContractError,
    DecisionRecord,
    DeploymentProfile,
    Episode,
    InteractionEvent,
    Known,
    Need,
    OutcomeEvent,
    ReplyPlan,
    Understanding,
    Unknown,
)

from . import examples


def _refused(contract, document, path=None):
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "invalid_content"
    if path is not None:
        assert caught.value.dotted_path == path
    return caught.value


def test_fact_is_known_or_unknown_with_a_closed_reason():
    Known(value="3", source="commerce", observed_at=examples.T0)
    with pytest.raises(ContractError):
        Unknown(reason="probably_fine")
    with pytest.raises(ContractError, match="valid_until"):
        Known(value="3", source="commerce", observed_at=examples.T1, valid_until=examples.T0)


def test_estimate_value_is_decimal_text_not_float():
    document = examples.understanding()
    document["acts"][0]["confidence"] = {"status": "estimate", "value": 0.82, "method": "m", "population": "p",
                                         "version": "1"}
    _refused(Understanding, document, "acts.0.confidence.value")


def test_grant_staff_approval_needs_no_terms():
    document = examples.authorization_grant()
    document.update(basis="staff_approval")
    for key in ("terms_hash", "confirmation_evidence", "identity_evidence"):
        document.pop(key)
    assert AuthorizationGrant.from_document(document).terms_hash is None


def test_grant_customer_confirmation_needs_identity():
    document = examples.authorization_grant()
    document.pop("identity_evidence")
    _refused(AuthorizationGrant, document, "identity_evidence")


def test_command_content_hash_covers_action_targets_parameters_and_terms():
    base = examples.action_command()
    ActionCommand.from_document(base)
    for change in (
        lambda d: d.__setitem__("action", "cancel_order"),
        lambda d: d.__setitem__("targets", ["terms-2"]),
        lambda d: d["parameters"].__setitem__("quantity", "3"),
        lambda d: d.__setitem__("terms_hash", "sha256:" + "b" * 64),
    ):
        document = copy.deepcopy(base)
        change(document)
        _refused(ActionCommand, document, "content_hash")
    document = copy.deepcopy(base)
    document["idempotency"]["key"] = "another-key"  # a chave não entra no conteúdo
    ActionCommand.from_document(document)


def test_decision_chooses_only_eligible_candidates():
    document = examples.decision_record()
    document["chosen"] = [1]
    _refused(DecisionRecord, document, "chosen.0")
    document["chosen"] = [5]
    _refused(DecisionRecord, document, "chosen.0")


def test_eligible_and_blocked_are_exclusive():
    document = examples.decision_record()
    document["candidates"][1]["blocked_by"] = []
    _refused(DecisionRecord, document, "candidates.1.blocked_by")


def test_deterministic_selection_is_not_applicable_never_probability_one():
    document = examples.decision_record()
    document["selection"]["propensity"] = {"status": "recorded", "distribution": [{"candidate": 0, "probability": "1"}],
                                           "seed": "s", "executed_probability": "1"}
    _refused(DecisionRecord, document, "selection.propensity")


def test_seeded_selection_records_distribution_after_filters():
    document = examples.decision_record()
    document["candidates"][1].update(eligible=True, blocked_by=[])
    document["selection"] = {
        "method": "seeded",
        "propensity": {"status": "recorded", "seed": "42", "executed_probability": "0.7",
                       "distribution": [{"candidate": 0, "probability": "0.7"},
                                        {"candidate": 1, "probability": "0.3"}]},
    }
    record = DecisionRecord.from_document(document)
    assert record.selection.propensity.executed_probability == "0.7"
    broken = copy.deepcopy(document)
    broken["selection"]["propensity"]["distribution"][1]["probability"] = "0.2"
    _refused(DecisionRecord, broken, "selection.propensity.distribution")
    blocked = copy.deepcopy(document)
    blocked["candidates"][1].update(eligible=False, blocked_by=["advisor_constraint"])
    _refused(DecisionRecord, blocked, "selection.propensity.distribution.1")


def test_reply_claim_needs_backing():
    document = examples.reply_plan()
    document["parts"][1]["claims"][0].pop("ref")
    _refused(ReplyPlan, document, "parts.1.claims.0.ref")


def test_outcome_unknown_never_carries_a_value():
    document = examples.outcome_event()
    document["value"] = 0
    _refused(OutcomeEvent, document, "value")
    document["observation"] = "observed"
    assert OutcomeEvent.from_document(document).value == 0


def test_commitment_promise_has_owner_and_case_has_problem():
    document = examples.commitment()
    document.pop("owner")
    _refused(Commitment, document, "owner")
    document = examples.commitment()
    document["type"] = "case"
    _refused(Commitment, document, "problem_code")
    document["deadline"] = {"status": "absent", "absent_reason": "staff has no fixed hours", "contingency": "next_day"}
    document["problem_code"] = "late_delivery"
    assert Commitment.from_document(document).deadline.status == "absent"


def test_need_satisfied_needs_evidence():
    document = examples.need()
    document["state"] = "satisfied"
    _refused(Need, document, "evidence")


def test_episode_resolution_and_human_ownership():
    document = examples.episode()
    document["state"] = "resolved"
    _refused(Episode, document, "resolved_at")
    document = examples.episode()
    document["state"] = "human_owned"
    _refused(Episode, document, "ownership")


def test_event_identity_and_assurance_go_together():
    document = examples.interaction_event()
    document["event_identity"] = {"assurance": "verified"}
    _refused(InteractionEvent, document, "event_identity.id")


def test_profile_line_absent_cannot_be_approved_and_refs_must_exist():
    document = examples.deployment_profile()
    document["lines"][1]["state"] = "approved"
    document["lines"][1]["decided_at"] = examples.T0
    _refused(DeploymentProfile, document, "lines.1.state")
    document = examples.deployment_profile()
    document["actions"]["commit_order"]["line_ref"] = "line-missing"
    _refused(DeploymentProfile, document, "actions.commit_order.line_ref")
