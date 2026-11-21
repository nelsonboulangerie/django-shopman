"""A conferência antes do envio: correta, útil e aceitável; o juiz que cai nunca vira "passou"."""

from __future__ import annotations

from conversational_commerce.reply import JudgeVerdict, confer, conferred


class Judge:
    def __init__(self, answer=None, *, boom=False):
        self.answer, self.boom, self.calls = answer, boom, []

    def judge(self, *, customer, reply, previous=""):
        self.calls.append((customer, reply, previous))
        if self.boom:
            raise TimeoutError("juiz fora")
        return JudgeVerdict(self.answer, 0.9)


def base(**kw):
    return {"customer": "tem croissant?", "reply": "Croissant: Indisponível. Quer pain au chocolat?",
            "held": False, "by_construction": True, "has_next_step": True, **kw}


def test_template_reply_with_next_step_passes_without_judge():
    assert confer(**base()).decision == "send"


def test_held_by_house_rules_is_not_acceptable():
    c = confer(**base(held=True))
    assert c.decision == "fallback" and "acceptable:held" in c.failed


def test_dead_end_is_not_useful_unless_the_customer_only_thanked():
    assert "useful:no_next_step" in confer(**base(has_next_step=False)).failed
    assert confer(**base(has_next_step=False, next_step_needed=False)).decision == "send"


def test_drafted_reply_needs_the_judge_and_a_fallen_judge_is_never_a_pass():
    assert confer(**base(by_construction=False)).failed == ("correct:unconferred",)
    fallen = confer(**base(by_construction=False), judge=Judge(boom=True))
    assert fallen.decision == "fallback" and fallen.failed == ("correct:unconferred",)
    assert confer(**base(by_construction=False), judge=Judge("answers")).decision == "send"


def test_judge_off_target_or_contradiction_fails_even_a_template_reply():
    assert confer(**base(), judge=Judge("off_target")).failed == ("useful:judge_off_target",)
    assert confer(**base(), judge=Judge("contradicts")).failed == ("correct:judge_contradicts",)


def test_a_fallen_judge_does_not_block_a_template_reply():
    assert confer(**base(), judge=Judge(boom=True)).decision == "send"


def test_shadow_sends_the_candidate_and_enforce_sends_the_safe_alternative():
    c = confer(**base(has_next_step=False))
    safe = lambda conference: "Vou verificar e te respondo."  # noqa: E731
    assert conferred(c, candidate="X", safe=safe) == "X"
    assert conferred(c, candidate="X", safe=safe, mode="enforce") == "Vou verificar e te respondo."
    ok = confer(**base())
    assert conferred(ok, candidate="X", safe=safe, mode="enforce") == "X"


def test_record_is_plain_data():
    record = confer(**base(), judge=Judge("answers")).as_record()
    assert record == {"decision": "send", "checks": {"acceptable": {"status": "pass"}, "correct": {"status": "pass"},
                                                     "useful": {"status": "pass"}},
                      "judge": {"answer": "answers", "confidence": 0.9}}
