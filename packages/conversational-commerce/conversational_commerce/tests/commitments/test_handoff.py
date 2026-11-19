"""Encaminhar: receber não é aceitar, e a fila que recusa não vira aceite (K20)."""

from __future__ import annotations

import pytest

from conversational_commerce.ports import PortError
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.fakes import Fault
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine, only_open

HANDOFF = JourneyStep(
    message={"id": "h-m1", "from": "addr-h", "conversation": "conv-h", "content_ref": "text:talk to a person"},
    understanding={"acts": [{"act": "request_human"}]},
    expect_moves=("handoff",),
)
ACCEPTANCE_WORDS = ("accepted", "has taken", "took over", "is now", "picked this up")


def test_handoff_routed_is_not_accepted_until_someone_accepts_by_name():
    turn_engine, world = engine(steps=(HANDOFF,))
    result = turn_engine.turn(CTX, HANDOFF.message)
    assert result.chosen_moves == ["handoff"]
    assert result.text == ("I've asked our attendant to take over. If no one picks this up by "
                           "2026-01-05T09:10:00.000000Z, I'll let you know.")
    assert result.episode.state == "awaiting_handoff" and result.episode.ownership.owner == "queue"
    assert len(world.channel.handoffs) == 1
    entry = only_open(turn_engine)
    assert entry.commitment.state == "open" and turn_engine.commitments.events_of(entry.commitment_id) == [
        "acknowledged"]

    accepted = turn_engine.staff_accepted(CTX, entry.commitment_id)
    assert accepted.state == "accepted" and accepted.owner == "staff-1"
    episode = world.store.load_episode(CTX, result.episode.episode_id)
    assert episode.state == "human_owned" and episode.ownership.holder_ref == "staff-1"
    assert episode.ownership.epoch == result.episode.ownership.epoch + 1


@conformance("K20", invariants=("N04", "N15"), scope="adapter")
def test_k20_queue_refuses_the_handoff_monitored_with_contingency_nothing_claims_acceptance():
    turn_engine, world = engine(steps=(HANDOFF,))
    world.faults.arm("ask", Fault.QUEUE_REJECTS)
    result = turn_engine.turn(CTX, HANDOFF.message)
    assert result.chosen_moves == ["handoff"]
    assert not any(word in result.text for word in ACCEPTANCE_WORDS)
    assert result.text.startswith("I've asked the team to take over. Until someone does,")
    # Monitorado: a automação é dona do acompanhamento, com prazo e a contingência do perfil.
    entry = only_open(turn_engine)
    assert entry.commitment.owner == "core" and entry.commitment.deadline.status == "set"
    assert turn_engine.commitments.events_of(entry.commitment_id) == ["acknowledged", "contingency"]
    assert result.episode.state == "awaiting_handoff"
    assert result.episode.waits[0].condition == "contingency: inform_and_wait"
    assert world.channel.handoffs == []
    # Não há aceite a registrar: o erro sobe e nada muda.
    with pytest.raises(PortError):
        turn_engine.staff_accepted(CTX, entry.commitment_id)
    assert only_open(turn_engine).commitment.state == "open"
    assert world.store.load_episode(CTX, result.episode.episode_id).state == "awaiting_handoff"
