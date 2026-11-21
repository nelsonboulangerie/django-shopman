"""Placar de conversa: desfecho por turno, lastro desconhecido à parte, e o alcance da alternativa."""

from __future__ import annotations

from conversational_commerce.evaluation import IncumbentProfile, TurnEvidence, incumbent_reach, outcome_of, score

#: Uma alternativa que responde pela base de conhecimento, sem dado vivo e sem agir.
KNOWLEDGE_BOT = IncumbentProfile("knowledge_bot", reads_live_data=False, acts_on_commerce=False,
                                 free_text_in_channel=True)
#: A mesma alternativa num canal em que ela só roteia para fluxo pronto.
ROUTER_ONLY = IncumbentProfile("router_only", reads_live_data=False, acts_on_commerce=False,
                               free_text_in_channel=False)


def turn(turn_id="t", **kw):
    return TurnEvidence(turn_id=turn_id, **{"replied": True, **kw})


def test_outcome_order_is_silent_then_unbacked_then_dead_end_then_useful():
    assert outcome_of(turn(replied=False)) == "silent"
    assert outcome_of(turn(replied=False, silence_expected=True)) is None
    assert outcome_of(turn(backed=False, next_step=True)) == "unbacked"
    assert outcome_of(turn(next_step=False)) == "dead_end"
    assert outcome_of(turn(next_step=True)) == "useful"


def test_unknown_backing_is_counted_apart_and_blocks_ready():
    card = score([turn(next_step=True), turn(backed=None, next_step=True)])
    assert card.outcomes["useful"] == 2 and card.unknown_backing == 1
    assert not card.meets(useful_at_least=0.5)  # desconhecido não vira "com lastro"


def test_ready_needs_no_silence_no_unbacked_and_enough_useful():
    useful = [turn(str(i), next_step=True) for i in range(9)]
    assert score([*useful, turn("d", next_step=False)]).meets(useful_at_least=0.9)
    assert not score([*useful, turn("s", replied=False)]).meets(useful_at_least=0.9)
    assert not score([*useful, turn("u", backed=False, next_step=True)]).meets(useful_at_least=0.5)


def test_empty_scorecard_rate_is_unknown_not_zero():
    card = score([])
    assert card.rate("useful") is None and not card.meets()


def test_excused_silence_stays_out_of_the_rate():
    card = score([turn(next_step=True), turn(replied=False, silence_expected=True)])
    assert card.scored == 1 and card.excused_silence == 1 and card.rate("useful") == 1.0


def test_incumbent_reach_names_the_first_missing_capability():
    assert incumbent_reach(turn(), ROUTER_ONLY) == "no_free_text"
    assert incumbent_reach(turn(needs_live_data=True, needs_action=True), KNOWLEDGE_BOT) == "no_live_data"
    assert incumbent_reach(turn(needs_action=True), KNOWLEDGE_BOT) == "cannot_act"
    assert incumbent_reach(turn(), KNOWLEDGE_BOT) == "reaches"


def test_scorecard_counts_incumbent_reach_and_repeats():
    card = score(
        [turn("a", next_step=True, needs_live_data=True), turn("b", next_step=True, repeated=True)],
        [KNOWLEDGE_BOT],
    )
    assert card.incumbents["knowledge_bot"] == {"no_live_data": 1, "reaches": 1}
    assert card.repeated == 1
