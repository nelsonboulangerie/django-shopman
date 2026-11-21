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
    # Achado da própria conferência: "sua sacola ficou assim ... Total" não diz o que vem depois.
    assert record["checks"]["useful"] == {"status": "fail", "reason": "no_next_step"}
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
