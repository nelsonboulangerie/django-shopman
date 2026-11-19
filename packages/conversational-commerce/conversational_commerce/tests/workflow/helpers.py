"""Episódio em qualquer estado e evento com o que a transição exige."""

from __future__ import annotations

import dataclasses

from conversational_commerce.contracts import Commitment, Need, Producer, Wait
from conversational_commerce.workflow import EpisodeEvent, open_episode

T0 = "2026-01-05T09:00:00.000000Z"
T1 = "2026-01-05T09:05:00.000000Z"
LATER = "2026-01-05T10:00:00.000000Z"
PRODUCER = Producer(name="test", version="1")
WAIT = Wait(condition="the customer answers", owner="core", deadline=LATER)


def episode_in(state: str, *, needs=()):
    episode = open_episode(record_id="rec-1", episode_id="ep-1", tenant="tenant-a", environment="test",
                           trace_id="trace-1", at=T0, producer=PRODUCER, subject="subject:customer-1", needs=needs)
    changes = {"state": state}
    if state == "human_owned":
        changes["ownership"] = {"owner": "person", "epoch": 2, "holder_ref": "staff-1"}
    if state == "awaiting_handoff":
        changes["ownership"] = {"owner": "queue", "epoch": 1}
    if state == "resolved":
        changes["resolved_at"] = T0
    if state.startswith("waiting") or state == "awaiting_handoff":
        changes["waits"] = (WAIT,)
    return dataclasses.replace(episode, **changes)


def need(need_id: str, state: str = "satisfied") -> Need:
    return Need(id=f"rec-{need_id}", tenant="tenant-a", environment="test", trace_id="t", occurred_at=T0,
                producer=PRODUCER, episode_id="ep-1", need_id=need_id, type="question", state=state,
                evidence=("evt-1",) if state in ("satisfied", "withdrawn") else ())


def commitment(state: str = "fulfilled") -> Commitment:
    return Commitment(id="rec-c1", tenant="tenant-a", environment="test", trace_id="t", occurred_at=T0,
                      producer=PRODUCER, episode_id="ep-1", commitment_id="c-1", type="promise",
                      obligation="answer the question", owner="staff-1",
                      deadline={"status": "set", "at": LATER, "rule_ref": "r"}, fulfillment_criterion="answered",
                      state=state, evidence=("evt-9",) if state == "fulfilled" else ())


def event_for(kind: str, **extra) -> EpisodeEvent:
    from conversational_commerce.workflow.machine import NEEDS_WAIT

    fields = {"kind": kind, "at": T1, "cause_id": f"cause-{kind}"}
    if kind in NEEDS_WAIT:
        fields["wait"] = WAIT
    if kind in ("handoff_accepted",):
        fields["holder_ref"] = "staff-1"
    fields.update(extra)
    return EpisodeEvent(**fields)
