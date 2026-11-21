# ruff: noqa: F401, F811
"""A pergunta da casa respondida pela IA a partir das FAQs publicadas (#2935).

Palavra do dono (21/11/2026, "1) sim") depois do placar do WP-18 (a IA cobriu 24/24 sem
inventar; a FAQ direta respondeu horário com a FAQ de CPF). A IA compõe usando SÓ as FAQs
publicadas e cita as que usou; o verificador do placar fica no caminho: invenção, falha,
sem modelo ou freio fechado, vale a FAQ direta; nenhuma FAQ cobre, "vou verificar".
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from shopman.storefront.concierge import intents
from shopman.storefront.tests.test_concierge_executor_certo import (
    GLUTEN,
    VERIFY,
    _turn,
    conversation,
    customer,
    menu,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act

pytestmark = pytest.mark.django_db

#: A fábrica de verdade, guardada antes de o conftest trocá-la pela que nunca abre rede.
REAL_BUILD_FAQ_CLIENT = intents.build_faq_client


class FakeModel:
    def __init__(self, payload=None, *, error: Exception | None = None):
        self.payload, self.error, self.requests = payload, error, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload, ensure_ascii=False))],
            stop_reason="end_turn", usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


def _model(monkeypatch, fake):
    monkeypatch.setattr(intents, "build_faq_client", lambda: (fake, "deepseek-flash"))
    return fake


def test_the_house_question_is_answered_by_the_ai_from_the_faqs(conversation, menu, monkeypatch):
    fake = _model(monkeypatch, FakeModel({"refs": ["payment"], "answer": "Aceitamos Pix e cartão, sim!", "uncovered": ""}))
    text = "aceitam pix?"

    outcome = _turn(conversation, text, [_act("house_info", text)], monkeypatch)

    assert outcome.reply_text == "Aceitamos Pix e cartão, sim!"
    request = fake.requests[0]
    assert request["thinking"] == {"type": "disabled"}
    assert "ref: payment" in request["system"][0]["text"], "a IA recebe as FAQs publicadas"


def test_the_ai_picks_the_right_faq_where_the_direct_one_got_cpf(conversation, menu, monkeypatch):
    from shopman.shop.models import Shop
    from shopman.storefront.concierge.faq_eval import live_faq

    shop = Shop.objects.get()
    shop.opening_hours = {day: {"open": "07:00", "close": "19:00"} for day in
                          ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")}
    shop.save(update_fields=["opening_hours"])
    hours = next(f for f in live_faq("whatsapp") if f.ref == "hours")
    _model(monkeypatch, FakeModel({"refs": ["hours"], "answer": hours.answer, "uncovered": ""}))
    text = "vocês fecham que horas mesmo hj?"

    outcome = _turn(conversation, text, [_act("hours_delivery", text)], monkeypatch)

    assert outcome.reply_text == hours.answer
    assert "CPF" not in outcome.reply_text


def test_no_faq_covers_it_so_the_house_verifies(conversation, menu, monkeypatch):
    _model(monkeypatch, FakeModel({"refs": [], "answer": "", "uncovered": "pets"}))
    text = "Aceitam pets ai na padaria?"

    outcome = _turn(conversation, text, [_act("house_info", text)], monkeypatch)

    assert VERIFY in outcome.reply_text and GLUTEN not in outcome.reply_text


def test_an_invention_falls_back_to_the_direct_faq(conversation, menu, monkeypatch):
    _model(monkeypatch, FakeModel({"refs": ["payment"], "answer": "Aceitamos Pix com 10% de desconto!", "uncovered": ""}))
    text = "aceitam pix?"

    outcome = _turn(conversation, text, [_act("house_info", text)], monkeypatch)

    assert "10%" not in outcome.reply_text, "o verificador segurou a invenção"
    assert "Pix" in outcome.reply_text, "a FAQ direta respondeu"


@pytest.mark.parametrize("fake", [None, FakeModel(error=TimeoutError("lento"))], ids=["sem-modelo", "provedor-fora"])
def test_without_a_model_or_with_a_failure_the_direct_faq_answers(conversation, menu, monkeypatch, fake):
    monkeypatch.setattr(intents, "build_faq_client", lambda: (fake, "deepseek-flash" if fake else ""))
    text = "aceitam pix?"

    outcome = _turn(conversation, text, [_act("house_info", text)], monkeypatch)

    assert "Pix" in outcome.reply_text


def test_the_brake_or_no_connection_means_no_ai_client(monkeypatch):
    """A fábrica de verdade: freio fechado (``AIBudgetExceeded``) ou sem conexão, nada de IA."""
    from shopman.shop import ai, ai_governor

    def braked(*args, **kwargs):
        raise ai_governor.AIBudgetExceeded("o freio fechou")

    monkeypatch.setattr(ai, "anthropic_client", braked)
    assert REAL_BUILD_FAQ_CLIENT() == (None, "")

    def missing(*args, **kwargs):
        raise ai.AINotConfigured("sem conexão")

    monkeypatch.setattr(ai, "anthropic_client", missing)
    assert REAL_BUILD_FAQ_CLIENT() == (None, "")
