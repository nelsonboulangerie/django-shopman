"""A escada: regerar com o motivo, subir de degrau, parar no teto, e sempre sair algo seguro."""

from __future__ import annotations

from conversational_commerce.reply import Draft, JudgeVerdict, LadderPolicy, climb, confer, numbers_outside


class Judge:
    def __init__(self, *answers):
        self.answers = list(answers) or ["answers"]

    def judge(self, *, customer, reply, previous=""):
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return JudgeVerdict(answer, 0.9)


class Drafter:
    def __init__(self, name, text, cost=0.001, boom=False):
        self.name, self.text, self.cost, self.boom, self.seen = name, text, cost, boom, []

    def draft(self, *, customer, facts, allowed_steps, rejection, previous=""):
        self.seen.append({"facts": facts, "rejection": rejection, "steps": allowed_steps})
        if self.boom:
            raise TimeoutError("fora")
        return Draft(self.text, self.cost)


HOUSE = "Croissant: R$ 12,00. Disponível."
STEP = lambda text: "?" in text  # noqa: E731


def house_conference(**kw):
    return confer(customer="tem croissant?", reply=HOUSE, held=False, by_construction=True,
                  has_next_step=STEP(HOUSE), **kw)


def run(drafters, *, judge=None, policy=None, estimate=lambda d: d.cost, **kw):
    return climb(customer="tem croissant?", house_text=HOUSE, house_conference=house_conference(),
                 drafters=drafters, judge=judge or Judge(), policy=policy or LadderPolicy(), allowed_steps=("pedir quantas",),
                 safe=lambda attempts: "Vou verificar e já te respondo.", has_next_step=STEP,
                 estimate_usd=estimate, **kw)


def test_house_reply_that_passes_does_not_climb():
    cheap = Drafter("cheap", "x")
    ok = confer(customer="c", reply="Temos. Quer quantas?", held=False, by_construction=True, has_next_step=True)
    result = climb(customer="c", house_text="Temos. Quer quantas?", house_conference=ok, drafters=[cheap],
                   judge=Judge(), policy=LadderPolicy(), allowed_steps=(), safe=lambda a: "s", has_next_step=STEP,
                   estimate_usd=lambda d: 0.001)
    assert result.chosen == "house" and not cheap.seen and result.cost_usd == 0.0


def test_rejected_house_reply_is_redrafted_with_the_reason_and_only_the_facts():
    cheap = Drafter("cheap", "Croissant: R$ 12,00, disponível hoje. Quer que eu separe quantos?")
    result = run([cheap], policy=LadderPolicy(mode="enforce"))
    assert result.chosen == "cheap" and result.text.endswith("quantos?")
    assert cheap.seen[0]["facts"] == HOUSE and cheap.seen[0]["rejection"] == ("useful:no_next_step",)
    assert cheap.seen[0]["steps"] == ("pedir quantas",)


def test_shadow_climbs_and_records_but_sends_the_house_reply():
    cheap = Drafter("cheap", "Croissant: R$ 12,00. Quer quantos?")
    result = run([cheap])
    assert result.chosen == "cheap" and result.text == HOUSE
    assert [a["source"] for a in result.as_record()["attempts"]] == ["house", "cheap"]


def test_climbs_to_the_capable_rung_when_the_cheap_one_is_rejected():
    cheap = Drafter("cheap", "Temos croissant de chocolate também. Quer?")  # o juiz diz: fala de outra coisa
    capable = Drafter("capable", "Croissant: R$ 12,00. Quer que eu separe?")
    result = run([cheap, capable], judge=Judge("off_target", "answers"), policy=LadderPolicy(mode="enforce"))
    assert result.chosen == "capable" and len(result.attempts) == 3
    assert "useful:judge_off_target" in capable.seen[0]["rejection"]  # a redigida sem aval também não é "correta"


def test_a_number_that_is_not_in_the_facts_is_never_sent():
    liar = Drafter("cheap", "Croissant: R$ 9,90. Quer quantos?")
    assert numbers_outside("R$ 9,90", HOUSE) == ("9,90",)
    result = run([liar], policy=LadderPolicy(mode="enforce", max_attempts=2))
    assert result.chosen == "safe" and result.text == "Vou verificar e já te respondo."
    assert result.attempts[1].error == "number_outside_facts:9,90"


def test_exhausted_ladder_falls_to_the_safe_alternative_and_counts_reasons():
    cheap = Drafter("cheap", "Croissant disponível.")
    result = run([cheap], policy=LadderPolicy(mode="enforce", max_attempts=3))
    assert result.chosen == "safe" and result.stopped == "max_attempts" and len(result.attempts) == 3
    assert result.rejections.count("useful:no_next_step") == 3


def test_a_fallen_rung_is_a_rejected_attempt_and_the_climb_goes_on():
    fallen = Drafter("cheap", "", boom=True)
    capable = Drafter("capable", "Croissant: R$ 12,00. Quer quantos?")
    result = run([fallen, capable], policy=LadderPolicy(mode="enforce"))
    assert result.attempts[1].error == "TimeoutError" and result.chosen == "capable"


def test_budget_and_unknown_cost_stop_the_climb():
    pricey = Drafter("cheap", "x", cost=0.02)
    assert run([pricey], policy=LadderPolicy(turn_budget_usd=0.01)).stopped == "turn_budget"
    assert run([pricey], estimate=lambda d: None).stopped == "cost_unknown:cheap"  # desconhecido não é zero


def test_without_drafters_the_rejected_house_reply_goes_safe():
    result = run([])
    assert result.chosen == "safe" and result.stopped == "no_drafter"
