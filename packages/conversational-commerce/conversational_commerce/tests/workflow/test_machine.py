"""Toda transição da tabela de v2 5.7 tem teste; o que não está na tabela é recusa."""

from __future__ import annotations

import dataclasses
import itertools
import typing

import pytest

from conversational_commerce.contracts import ContractError, Wait
from conversational_commerce.workflow import TABLE, InvalidTransition, StaleVersion, transition
from conversational_commerce.workflow.machine import EventKind

from .helpers import LATER, T0, T1, commitment, episode_in, event_for, need

STATES = ("active", "waiting_input", "waiting_authorization", "waiting_effect", "awaiting_handoff", "human_owned",
          "resolved")
EVENTS = typing.get_args(EventKind)


def test_table_is_the_one_of_v2_5_7():
    expected = {
        ("active", "question_sent"), ("waiting_input", "evidence_arrived"), ("active", "terms_presented"),
        ("waiting_authorization", "grant_valid"), ("waiting_authorization", "authorization_invalidated"),
        ("active", "command_handed_off"), ("waiting_effect", "receipt_terminal"), ("waiting_effect", "receipt_open"),
        ("waiting_effect", "reconciliation_overdue"), ("awaiting_handoff", "handoff_accepted"),
        ("awaiting_handoff", "handoff_not_accepted"), ("human_owned", "returned"), ("active", "resolved"),
        ("human_owned", "resolved"), ("resolved", "reopened"),
        *((state, "handoff_requested") for state in ("active", "waiting_input", "waiting_authorization",
                                                     "waiting_effect", "human_owned")),
    }
    assert set(TABLE) == expected


@pytest.mark.parametrize(("state", "kind"), sorted(TABLE), ids=lambda v: str(v))
def test_every_transition_of_the_table(state, kind):
    episode = episode_in(state)
    event = event_for(kind)
    new = transition(episode, event, expected_version=episode.version, record_id="rec-2")
    assert new.state == TABLE[(state, kind)]
    assert new.version == episode.version + 1
    assert (new.id, new.cause_id, new.occurred_at) == ("rec-2", event.cause_id, T1)
    assert episode.state == state  # o registro anterior não muda (N14)
    if new.state.startswith("waiting") or new.state == "awaiting_handoff":
        assert new.waits == (event.wait,)
    else:
        assert new.waits == ()


@pytest.mark.parametrize(("state", "kind"), [pair for pair in itertools.product(STATES, EVENTS) if pair not in TABLE])
def test_everything_else_is_refused(state, kind):
    with pytest.raises(InvalidTransition):
        transition(episode_in(state), event_for(kind), expected_version=1, record_id="rec-2")


def test_stale_version_is_refused():
    with pytest.raises(StaleVersion):
        transition(episode_in("active"), event_for("question_sent"), expected_version=0, record_id="rec-2")


@pytest.mark.parametrize("kind", ["question_sent", "terms_presented", "command_handed_off", "handoff_requested"])
def test_wait_without_condition_owner_and_deadline_is_refused(kind):
    with pytest.raises(InvalidTransition, match="espera"):
        transition(episode_in("active"), event_for(kind, wait=None), expected_version=1, record_id="rec-2")
    with pytest.raises(InvalidTransition, match="vencido"):
        transition(episode_in("active"), event_for(kind, wait=Wait(condition="c", owner="o", deadline=T0)),
                   expected_version=1, record_id="rec-2")
    for missing in ({"owner": None}, {"deadline": None}, {"condition": ""}):
        with pytest.raises(ContractError):
            Wait(**{"condition": "c", "owner": "o", "deadline": LATER, **missing})


def test_epoch_only_grows_and_handoff_revokes_automation():
    episode = episode_in("active")
    handed = transition(episode, event_for("handoff_requested"), expected_version=1, record_id="r2")
    assert (handed.ownership.owner, handed.ownership.epoch) == ("queue", 1)
    accepted = transition(handed, event_for("handoff_accepted", at="2026-01-05T09:06:00.000000Z"),
                          expected_version=2, record_id="r3")
    assert (accepted.ownership.owner, accepted.ownership.holder_ref, accepted.ownership.epoch) == ("person",
                                                                                                    "staff-1", 2)
    back = transition(accepted, event_for("returned", at="2026-01-05T09:07:00.000000Z"), expected_version=3,
                      record_id="r4")
    assert (back.ownership.owner, back.ownership.epoch, back.ownership.holder_ref) == ("automation", 3, None)


def test_acceptance_is_nominal():
    with pytest.raises(InvalidTransition, match="nominal"):
        transition(episode_in("awaiting_handoff"), event_for("handoff_accepted", holder_ref=None),
                   expected_version=1, record_id="r2")


def test_not_accepted_stays_monitored_and_affirms_nothing():
    episode = episode_in("awaiting_handoff")
    new = transition(episode, event_for("handoff_not_accepted"), expected_version=1, record_id="r2")
    assert new.state == "awaiting_handoff" and new.ownership.owner == "queue"
    assert new.ownership.holder_ref is None


def test_resolution_needs_evidence():
    episode = episode_in("active", needs=("n1", "n2"))
    with pytest.raises(InvalidTransition, match="sem estado"):
        transition(episode, event_for("resolved", needs=(need("n1"),)), expected_version=1, record_id="r2")
    with pytest.raises(InvalidTransition, match="aberta"):
        transition(episode, event_for("resolved", needs=(need("n1"), need("n2", "open"))), expected_version=1,
                   record_id="r2")
    with pytest.raises(InvalidTransition, match="compromisso"):
        transition(episode, event_for("resolved", needs=(need("n1"), need("n2", "withdrawn")),
                                      commitments=(commitment("open"),)), expected_version=1, record_id="r2")
    resolved = transition(episode, event_for("resolved", needs=(need("n1"), need("n2", "withdrawn")),
                                             commitments=(commitment(),)), expected_version=1, record_id="r2")
    assert (resolved.state, resolved.resolved_at) == ("resolved", T1)


def test_reopening_is_an_event_with_its_origin():
    resolved = episode_in("resolved")
    reopened = transition(resolved, event_for("reopened"), expected_version=1, record_id="r2")
    assert (reopened.state, reopened.reopened_from, reopened.resolved_at) == ("active", resolved.id, None)


def test_event_before_the_current_state_is_refused():
    episode = dataclasses.replace(episode_in("active"), occurred_at=T1)
    with pytest.raises(InvalidTransition, match="anterior"):
        transition(episode, event_for("question_sent", at=T0), expected_version=1, record_id="r2")
