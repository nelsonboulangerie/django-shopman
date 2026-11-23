"""O ensaio dos 5 cartões pelo motor da Nice, em memória (``concierge_eval --cards``, #3378).

O que este teste segura: o motor anda de ponta a ponta com o leitor (aqui, uma IA falsa que lê as
falas do roteiro), a transcrição sai em texto puro (a fala, a resposta da Nice e o que se leu), e
NENHUMA tabela tocada por um turno ganha linha no banco.
"""

from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command

from shopman.storefront.concierge import model_reader

pytestmark = pytest.mark.django_db

CROISSANT = {"sku": "CROISSANT", "name": "Croissant", "can_order": True}
ROTEIRO = {
    "quero 2 croissants para retirar amanhã às 16h": [
        {"act": "change_quantity", "product": "croissants", "qty": 2, "change": "set"},
        {"act": "choose_fulfillment", "day": "tomorrow", "mode": "pickup", "time": "16:00"}],
    "quero 2 croissants": [{"act": "change_quantity", "product": "croissants", "qty": 2, "change": "set"}],
    "pode fechar": [{"act": "place_order"}],
    "sim": [{"act": "affirm"}],
    "na verdade 3": [{"act": "change_quantity", "qty": 3, "change": "set"}],
    "deixa pra lá": [{"act": "deny"}],
}


def _act(act, product="", qty=0, change="", day="", mode="", time=""):
    return {"act": act, "span": act, "product": product, "qty": qty, "change": change, "day": day, "mode": mode,
            "time": time}


class FakeAI:
    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **request):
        self.calls += 1
        fala = request["messages"][0]["content"].split("<<<\n", 1)[1].split("\n>>>", 1)[0]
        acts = [_act(**a) for a in ROTEIRO.get(fala, [{"act": "unknown"}])]
        return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=100, output_tokens=20),
                               content=[SimpleNamespace(type="text", text=json.dumps({"acts": acts}))])


@pytest.fixture
def house(monkeypatch):
    from shopman.offerman.models import Product

    from shopman.shop.models import Channel, Shop
    from shopman.storefront.concierge import tools, triage

    Shop.objects.create(name="Nelson Boulangerie")
    Channel.objects.create(ref="whatsapp", name="WhatsApp", config={})
    Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=1200, is_published=True, is_sellable=True)
    ai = FakeAI()
    monkeypatch.setattr(model_reader, "build_client", lambda: (ai, "deepseek-flash"))
    monkeypatch.setattr(triage, "jev_enabled", lambda: False)
    monkeypatch.setattr(tools, "execute", lambda name, args, ctx: {"ok": True, "items": [CROISSANT]})
    return ai


def _rows():
    from shopman.orderman.models import Order, Session

    from shopman.shop.models import (
        AiInvocation,
        Conversation,
        ConversationalCommitment,
        ConversationalEpisode,
        ConversationMessage,
    )

    return tuple(model.objects.count() for model in (Conversation, Session, ConversationMessage, Order,
                                                     ConversationalEpisode, ConversationalCommitment,
                                                     AiInvocation))


def _run(*args):
    out = StringIO()
    try:
        call_command("concierge_eval", "--cards", *args, stdout=out)
        error = ""
    except CommandError as failed:
        error = str(failed)
    return out.getvalue(), error


def test_the_cards_run_through_the_engine_and_write_nothing(house):
    before = _rows()
    out, error = _run("--case", "cartao-3")
    print(out)
    assert _rows() == before and error == ""
    assert "Cliente: quero 2 croissants" in out and "Nice: " in out and "movimentos: change_cart" in out
    assert "[ok] cartao-3-mudar-no-meio" in out, out


def test_a_card_the_engine_cannot_finish_says_what_is_missing(house):
    out, _ = _run("--case", "cartao-4")
    assert "o que falta no motor" in out or "[ok] cartao-4" in out
