"""Prazos e o fim da conversa: o compromisso sobrevive (K21) e o prazo vencido escala (K22)."""

from __future__ import annotations

from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.journeys import j3
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine, only_open

BYE = JourneyStep(
    message=j3.message("j3-bye", "thanks"),
    understanding={"acts": [{"act": "thank"}]},
    expect_moves=("acknowledge",),
)
LATER = JourneyStep(
    message=j3.message("j3-later", "what are your hours?"),
    understanding={"acts": [{"act": "ask_hours"}]},
    expect_moves=("inform",),
)

def _without_escalation_line():
    from conversational_commerce.profile.test_profile import DECIDED_AT, TEST_LINES

    return tuple({"id": line_id, "setting": {"status": "set", "value": value}, "owner": "framework",
                  "decided_at": DECIDED_AT, "state": "approved"}
                 for line_id, value, _ in TEST_LINES if line_id != "commitment.escalation")


@conformance("K21", invariants=("N15",), scope="core")
def test_k21_conversation_ends_with_an_open_commitment_and_both_carry_on():
    turn_engine, world = engine(steps=(j3.ASK, BYE, LATER))
    asked = turn_engine.turn(CTX, j3.ASK.message)
    bye = turn_engine.turn(CTX, BYE.message)
    # A interação encerra; o episódio não se resolve e o compromisso segue aberto.
    assert bye.chosen_moves == ["acknowledge"] and bye.episode.state == "active"
    entry = only_open(turn_engine)
    assert entry.commitment.state == "open"
    # Passada a janela de inatividade, o episódio continua, porque há compromisso aberto.
    world.clock.advance(25 * 3600)
    later = turn_engine.turn(CTX, LATER.message)
    assert later.episode.episode_id == asked.episode.episode_id
    # E a resposta da equipe ainda chega ao cliente, pelo vínculo em que a promessa nasceu.
    world.staff.answer(entry.ticket_id, j3.ANSWER)
    answered = turn_engine.staff_answered(CTX, entry.commitment_id)
    assert answered.text == "Item Z costs XTS 8.00."
    assert answered.exposure is not None and answered.exposure.recipient == asked.episode.subject
    assert turn_engine.commitments.entries[entry.commitment_id].binding == asked.event.channel_binding


@conformance("K22", invariants=("N04",), scope="adapter")
def test_k22_deadline_passes_without_the_team_event_escalation_customer_told_once():
    turn_engine, world = engine(steps=(j3.ASK,))
    asked = turn_engine.turn(CTX, j3.ASK.message)
    entry = only_open(turn_engine)
    assert turn_engine.tick(CTX) == ()  # dentro do prazo, nada

    world.clock.advance(31 * 60)
    (notice,) = turn_engine.tick(CTX)
    # Evento de prazo; escala ao dono que o perfil diz, com prazo novo; o episódio vai a pessoa.
    assert turn_engine.commitments.events_of(entry.commitment_id) == [
        "acknowledged", "deadline_passed", "escalated", "customer_notified"]
    escalated = entry.commitment
    assert escalated.owner == "supervisor" and escalated.deadline.at == "2026-01-05T10:01:00.000000Z"
    assert notice.chosen_moves == ["wait"]
    assert notice.text == "Sorry for the wait. You'll hear back from our supervisor by 2026-01-05T10:01:00.000000Z."
    episode = world.store.load_episode(CTX, asked.episode.episode_id)
    assert episode.state == "awaiting_handoff"
    sent = len(world.channel.outbox)

    # Avisado uma vez: outro tique não repete; o prazo escalado que vence quebra a promessa, sem novo aviso.
    assert turn_engine.tick(CTX) == ()
    world.clock.advance(31 * 60)
    assert turn_engine.tick(CTX) == ()
    assert entry.commitment.state == "broken"
    assert len(world.channel.outbox) == sent
    assert turn_engine.commitments.events_of(entry.commitment_id).count("customer_notified") == 1


def test_without_the_escalation_line_nothing_is_invented_and_the_customer_is_told_once():
    turn_engine, world = engine(steps=(j3.ASK,), lines=_without_escalation_line())
    asked = turn_engine.turn(CTX, j3.ASK.message)
    entry = only_open(turn_engine)
    world.clock.advance(31 * 60)
    (notice,) = turn_engine.tick(CTX)
    assert turn_engine.commitments.events_of(entry.commitment_id) == [
        "acknowledged", "deadline_passed", "escalation_absent", "customer_notified"]
    assert entry.commitment.owner == "attendant"
    assert notice.text.startswith("Sorry for the wait. You'll hear back from our attendant by")
    assert world.store.load_episode(CTX, asked.episode.episode_id).state == "active"
    assert turn_engine.tick(CTX) == ()
