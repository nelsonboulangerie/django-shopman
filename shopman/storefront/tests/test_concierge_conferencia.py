# ruff: noqa: F401, F811
"""A conferência antes do envio, em sombra: o turno grava o veredito e a resposta não muda.

Dono, 21/11/2026: "é fundamental uma 'conferência' antes de enviar para o cliente, se a
resposta é 'aceitável/correta/útil' ou não... O sistema, em si, deve ser inteligente e a
prova de falhas."
"""

from __future__ import annotations

import pytest
from conversational_commerce.reply import JudgeVerdict

from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import conference
from shopman.storefront.tests.test_concierge_engine import conversation, customer, outbox, surface
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _turn, menu

pytestmark = pytest.mark.django_db


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _judge(monkeypatch, answer, confidence=0.9):
    from shopman.shop import ai

    sent = []
    monkeypatch.setattr(ai, "jev_endpoint", lambda **kw: ("https://jev.invalid", "k", "jev-test"))

    def post(session, url, key, body, **kw):
        sent.append(body)
        probs = {name: (0.9 if name == answer else 0.05) for name in conference.VERDICT_CRITERIA}
        return FakeResponse({"answers": {"verdict": {"type": "choice", "choice": answer, "probabilities": probs,
                                                     "confidence": confidence}},
                             "usage": {"input_tokens": 120}})

    monkeypatch.setattr(ai, "jev_post", post)
    return sent


def _last_reply(conversation):
    return Message.objects.filter(conversation=conversation, kind="reply").order_by("pk").last()


def test_the_turn_records_the_verdict_and_sends_the_same_reply(conversation, outbox, menu, monkeypatch):
    sent = _judge(monkeypatch, "answers")

    reply = _turn(conversation, "quero 2 croissant", [_act("order", "quero 2 croissant", "croissant", 2)])

    first = Message.objects.filter(conversation=conversation, kind="reply").order_by("pk").first()
    assert "Pronto, sua sacola ficou assim:" in reply
    record = first.envelope["conference"]
    assert record["judge"]["answer"] == "answers"
    assert record["checks"]["correct"] == {"status": "pass"}  # molde sobre o fato da sacola
    # A sacola diz o que vem depois ("pode fechar", #3057): a conferência aprova. O beco sem
    # saída que ela reprova continua provado no teste seguinte (item Indisponível, sem passo).
    assert record["checks"]["useful"] == {"status": "pass"}
    assert record["decision"] == "send"
    assert sent and sent[0]["state"]["customer_message"] == "quero 2 croissant"
    calls = {c["stage"]: c for c in first.usage["calls"]}
    assert calls["conference"]["provider"] == "typesafe" and calls["conference"]["input_tokens"] == 120


def test_a_dead_end_would_fall_back_but_in_shadow_it_still_goes_out(conversation, outbox, menu, monkeypatch):
    _judge(monkeypatch, "answers")

    reply = _turn(conversation, "quero 2 brioche", [_act("order", "quero 2 brioche", "brioche", 2)])

    assert "Brioche: Indisponível." in reply  # sombra: o que sai não muda
    record = _last_reply(conversation).envelope["conference"]
    assert record["decision"] == "fallback"
    assert record["checks"]["useful"] == {"status": "fail", "reason": "no_next_step"}


def test_a_fallen_judge_never_breaks_the_turn(conversation, outbox, menu, monkeypatch):
    from shopman.shop import ai

    monkeypatch.setattr(ai, "jev_endpoint", lambda **kw: ("https://jev.invalid", "k", "jev-test"))
    monkeypatch.setattr(ai, "jev_post", lambda *a, **kw: (_ for _ in ()).throw(TimeoutError("fora")))

    reply = _turn(conversation, "quero 2 croissant", [_act("order", "quero 2 croissant", "croissant", 2)])

    assert "Pronto, sua sacola ficou assim:" in reply
    record = Message.objects.filter(conversation=conversation, kind="reply").order_by("pk").first().envelope["conference"]
    assert "judge" not in record  # juiz sem palavra
    assert record["checks"]["correct"] == {"status": "pass"}  # e o molde com lastro não é reprovado por isso


def test_without_jev_configured_there_is_no_judge(conversation, outbox, menu, monkeypatch):
    from shopman.shop import ai

    def not_configured(**kw):
        raise ai.AINotConfigured("sem jev")

    monkeypatch.setattr(ai, "jev_endpoint", not_configured)
    assert conference.judge_for() is None


def test_the_judge_request_is_redacted_and_doubt_does_not_fail(monkeypatch):
    sent = _judge(monkeypatch, "off_target", confidence=0.4)
    judge = conference.JevJudge(session=object())

    verdict = judge.judge(customer="meu cpf é 123.456.789-09, tem pão?",
                          reply="Pedido W29: R$ 24,00. Quer separar?", previous="Oi! Como posso ajudar?")

    state = sent[0]["state"]
    assert "123.456.789-09" not in state["customer_message"]
    assert "24,00" not in state["house_reply"] and "W29" not in state["house_reply"]  # como no 1b
    assert set(state) == {"customer_message", "house_reply"}  # nada da conversa anterior
    assert verdict == JudgeVerdict("answers", 0.4)  # o Jev em dúvida não derruba resposta boa


# ── A escada, em sombra ────────────────────────────────────────────────


class FakeDrafter:
    name = "concierge_rewrite"

    def __init__(self, text):
        self.text, self.seen = text, []

    def estimate_usd(self):
        return 0.0004

    def draft(self, *, customer, facts, allowed_steps, rejection, previous=""):
        from conversational_commerce.reply import Draft

        self.seen.append({"facts": facts, "rejection": rejection, "steps": allowed_steps})
        return Draft(self.text, 0.0003)


def test_the_ladder_climbs_after_sending_and_records_what_it_would_send(conversation, outbox, menu, monkeypatch):
    # O beco sem saída que a conferência reprova: item Indisponível, sem passo (a sacola já diz
    # "pode fechar" desde o #3064 e passa na conferência, então não sobe a escada).
    _judge(monkeypatch, "answers")
    drafter = FakeDrafter(
        "O brioche está indisponível hoje. Quer escolher outro item? Quando terminar, é só escrever 'pode fechar'."
    )
    monkeypatch.setattr(conference, "drafters_for", lambda: [drafter])

    reply = _turn(conversation, "quero 2 brioche", [_act("order", "quero 2 brioche", "brioche", 2)])

    assert "Brioche: Indisponível." in reply  # sombra: o cliente recebe a da casa
    first = Message.objects.filter(conversation=conversation, kind="reply").order_by("pk").first()
    ladder = first.envelope["ladder"]
    assert ladder["chosen"] == "concierge_rewrite" and ladder["cost_usd"] == 0.0003
    assert [a["source"] for a in ladder["attempts"]] == ["house", "concierge_rewrite"]
    assert drafter.seen[0]["rejection"] == ("useful:no_next_step",)
    assert "Brioche: Indisponível." in drafter.seen[0]["facts"]
    assert any("pode fechar" in step for step in drafter.seen[0]["steps"])  # passo que a casa cumpre


def test_a_rewrite_with_a_number_outside_the_facts_is_never_chosen(conversation, outbox, menu, monkeypatch):
    _judge(monkeypatch, "answers")
    monkeypatch.setattr(conference, "drafters_for", lambda: [FakeDrafter("Seu total é R$ 99,00. Quer fechar?")])

    _turn(conversation, "quero 2 brioche", [_act("order", "quero 2 brioche", "brioche", 2)])

    ladder = Message.objects.filter(conversation=conversation, kind="reply").order_by("pk").first().envelope["ladder"]
    assert ladder["chosen"] == "safe"
    assert ladder["attempts"][1]["error"].startswith("number_outside_facts:")


def test_a_rung_without_an_explicit_route_does_not_exist():
    from shopman.shop import ai

    with pytest.raises(ai.AINotConfigured):
        conference.ModelDrafter("concierge_rewrite")  # nunca cai na rota default
    assert conference.drafters_for() == []


def test_the_rewrite_request_is_redacted_and_carries_reason_and_steps(monkeypatch):
    drafter = conference.ModelDrafter.__new__(conference.ModelDrafter)
    drafter.model = "deepseek-flash"

    body = drafter.build_request(customer="meu cpf é 123.456.789-09, tem pão?",
                                 facts="Pedido W29. Pão: R$ 10,00.", previous="Oi, Ana! Como posso ajudar?",
                                 allowed_steps=("perguntar quantas",), rejection=("useful:no_next_step",))

    content = body["messages"][0]["content"]
    assert "123.456.789-09" not in content and "W29" not in content and "Ana" not in content
    assert "R$ 10,00" in content  # o valor é o lastro da reescrita (e /privacidade diz)
    assert "não diz ao cliente o que ele pode fazer em seguida" in content and "perguntar quantas" in content
    assert body["max_tokens"] == conference.REWRITE_MAX_TOKENS


def test_policy_comes_from_the_shop_limits_with_the_owner_default(surface):
    from shopman.shop.models import Shop

    assert conference.ladder_policy().max_attempts == 3
    shop = Shop.load()
    shop.ai_limits = {"conference": {"max_attempts": 9, "turn_usd": 1}}
    shop.save()
    policy = conference.ladder_policy()
    assert policy.max_attempts == 5 and policy.turn_budget_usd == 0.05  # tetos de código
