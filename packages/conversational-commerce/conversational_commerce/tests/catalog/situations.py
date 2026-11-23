"""Situação em que cada movimento é elegível, e o que quebra cada precondição.

``happy(move)`` devolve (situação, perfil) em que o movimento passa em tudo.
``BREAKERS[código]`` transforma (situação, perfil) para que AQUELA precondição
falhe. O meta-teste exige um quebrador para cada precondição do catálogo:
precondição nova sem quebrador reprova.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from conversational_commerce.catalog import Situation
from conversational_commerce.contracts import DeploymentProfile, Known, Unknown
from conversational_commerce.profile.test_profile import CHANNEL, build_test_profile

NOW = "2026-11-18T14:00:00.000000Z"
LATER = "2026-11-18T15:00:00.000000Z"
HASH = "sha256:" + "1" * 64
OTHER_HASH = "sha256:" + "2" * 64

KNOWN = {"opening_hours": Known(value="07:00-19:00", source="commerce", observed_at=NOW, valid_until=LATER)}
UNKNOWN = {"opening_hours": Unknown(reason="source_failed")}

BASE: dict[str, Any] = {
    "now": NOW,
    "channel": CHANNEL,
    "identity": "weak_verified",
    "event_assurance": "provider_claimed",
    "reply_only_courtesy": True,
    "facts_needed": KNOWN,
    "fact_is_personal": False,
    "reading_count": 2,
    "request_kind": "query",
    "missing_required_field": False,
    "answer_changes_decision": True,
    "question_open_for_need": False,
    "requested_move_ineligible": True,
    "staff_owner_possible": True,
    "complaint": True,
    "handoff_reason": "customer_request",
    "wait_has_condition_owner_deadline": True,
    "quantity_is_absolute": True,
    "change_reversible": True,
    "fulfillment_is_absolute": True,
    "current_terms_hash": HASH,
    "grant_terms_hash": HASH,
    "confirmation_after_terms": True,
    "confirmation_same_subject": True,
    "confirmation_bound_to_target": True,
    "ownership_epoch_current": True,
    "within_self_service_window": True,
    "amendment_addition_only": True,
    "discounts_on_order": 0,
    "open_problem": False,
    "need_explicit": True,
    "advisor_constraint_satisfied": True,
    "unsolicited_initiatives_in_episode": 0,
    "friction_high": False,
    "overdue_commitment": False,
    "customer_declined_offers": False,
}

HAPPY_OVERRIDES: dict[str, dict[str, Any]] = {
    "ask_clarification": {"request_kind": "change"},
    "verify_with_staff": {"facts_needed": UNKNOWN},
}

Pair = tuple[Situation, DeploymentProfile]


def happy(move: str) -> Pair:
    return Situation(**{**BASE, **HAPPY_OVERRIDES.get(move, {})}), build_test_profile()


def with_rule(profile: DeploymentProfile, name: str, **changes: Any) -> DeploymentProfile:
    actions = dict(profile.actions)
    actions[name] = dataclasses.replace(actions[name], **changes)
    return dataclasses.replace(profile, actions=actions)


def without_rule(profile: DeploymentProfile, name: str) -> DeploymentProfile:
    actions = {key: rule for key, rule in profile.actions.items() if key != name}
    return dataclasses.replace(profile, actions=actions)


def _situation(**changes: Any) -> Callable[[Pair, str], Pair]:
    def breaker(pair: Pair, move: str) -> Pair:
        situation, profile = pair
        return dataclasses.replace(situation, **changes), profile

    return breaker


def _profile(fn: Callable[[DeploymentProfile, str], DeploymentProfile]) -> Callable[[Pair, str], Pair]:
    def breaker(pair: Pair, move: str) -> Pair:
        situation, profile = pair
        return situation, fn(profile, move)

    return breaker


def _identity_too_low(pair: Pair, move: str) -> Pair:
    situation, profile = pair
    return dataclasses.replace(situation, identity="anonymous"), with_rule(
        profile, move, min_identity={CHANNEL: "strong_verified"}
    )


def _personal_fact(pair: Pair, move: str) -> Pair:
    situation, profile = pair
    return dataclasses.replace(situation, fact_is_personal=True), with_rule(
        profile, "inform.personal", min_identity={CHANNEL: "strong_verified"}
    )


def _no_quote(profile: DeploymentProfile, move: str) -> DeploymentProfile:
    adapters = dict(profile.adapters)
    adapters["commerce"] = tuple(cap for cap in adapters["commerce"] if cap != "quote")
    return dataclasses.replace(profile, adapters=adapters)


BREAKERS: dict[str, Callable[[Pair, str], Pair]] = {
    # comuns
    "profile_enables_move": _profile(without_rule),
    "authority_permitted": _profile(lambda p, m: with_rule(p, m, authority="A5")),
    "confirmation_matches_level": _profile(lambda p, m: with_rule(p, m, authority="A3", confirmation=False)),
    "identity_sufficient": _identity_too_low,
    # do movimento
    "only_courtesy": _situation(reply_only_courtesy=False),
    "facts_known_and_valid": _situation(facts_needed=UNKNOWN),
    "personal_fact_identity": _personal_fact,
    "two_readings": _situation(reading_count=1),
    "request_is_query": _situation(request_kind="change"),
    "requested_action_ineligible": _situation(requested_move_ineligible=False),
    "clarification_needed": _situation(missing_required_field=False, request_kind="query"),
    "answer_changes_decision": _situation(missing_required_field=False, answer_changes_decision=False),
    "one_question_per_need": _situation(question_open_for_need=True),
    "fact_unknown": _situation(facts_needed=KNOWN),
    "staff_owner_possible": _situation(staff_owner_possible=False),
    "staff_rule_declared": _profile(lambda p, m: dataclasses.replace(p, staff_queue=None)),
    "complaint_present": _situation(complaint=False),
    "handoff_reason": _situation(handoff_reason="none"),
    "wait_is_defined": _situation(wait_has_condition_owner_deadline=False),
    "commerce_can_quote": _profile(_no_quote),
    "stable_event_identity": _situation(event_assurance="none"),
    "absolute_quantity": _situation(quantity_is_absolute=False),
    "absolute_fulfillment": _situation(fulfillment_is_absolute=False),
    "change_is_reversible": _situation(change_reversible=False),
    "grant_bound_to_current_terms": _situation(grant_terms_hash=OTHER_HASH),
    "confirmation_after_terms": _situation(confirmation_after_terms=False),
    "ownership_epoch_current": _situation(ownership_epoch_current=False),
    "within_self_service_window": _situation(within_self_service_window=False),
    "confirmation_bound_to_target": _situation(confirmation_bound_to_target=False),
    "addition_only": _situation(amendment_addition_only=False),
    "one_discount_per_order": _situation(discounts_on_order=1),
    "no_open_problem": _situation(open_problem=True),
    "explicit_need": _situation(need_explicit=False),
    "advisor_constraint": _situation(advisor_constraint_satisfied=False),
    "unsolicited_within_limit": _situation(unsolicited_initiatives_in_episode=1),
    "commercial_context_clear": _situation(friction_high=True),
    "refusal_respected": _situation(customer_declined_offers=True),
}
