"""O ensaio do leitor no ar (``concierge_eval --battery``): o placar sai, e nada é gravado no banco."""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone
from shopman.orderman.models import Session

from shopman.shop.models import Conversation, ConversationMessage
from shopman.storefront.concierge import model_reader

pytestmark = pytest.mark.django_db

CROISSANT = {"sku": "CROISSANT", "name": "Croissant", "can_order": True}


class FakeAI:
    """A IA da rota ``intents``: lê "croissant" com a quantidade, o dia e a hora da fala."""

    def __init__(self, error=None):
        self.error, self.calls = error, 0
        self.messages = self

    def create(self, **request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        text = request["messages"][0]["content"].lower()
        acts = []
        if "croissant" in text:
            acts.append({"act": "change_quantity", "span": "croissants", "product": "croissants", "qty": 2,
                         "change": "set", "day": "", "mode": "", "time": ""})
        if "amanh" in text:
            acts.append({"act": "choose_fulfillment", "span": "amanhã", "product": "", "qty": 0, "change": "",
                         "day": "tomorrow", "mode": "pickup" if "retir" in text else "", "time": "16:00"})
        return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=100, output_tokens=20),
                               content=[SimpleNamespace(type="text", text=json.dumps({"acts": acts}))])


@pytest.fixture
def house(monkeypatch):
    from shopman.storefront.concierge import tools, triage

    ai = FakeAI()
    monkeypatch.setattr(model_reader, "build_client", lambda: (ai, "deepseek-flash"))
    monkeypatch.setattr(triage, "jev_enabled", lambda: False)
    monkeypatch.setattr(tools, "execute", lambda name, args, ctx: {"ok": True, "items": [CROISSANT]})
    return ai


def _run(*args) -> str:
    out = StringIO()
    call_command("concierge_eval", "--battery", *args, stdout=out)
    return out.getvalue()


def _rows():
    return Conversation.objects.count(), Session.objects.count(), ConversationMessage.objects.count()


def test_the_battery_scores_the_reader_and_writes_nothing(house):
    before = _rows()
    out = _run("--case", "frase-cartao-1", "--max-calls", "10")
    assert _rows() == before  # conversa e sacola de memória: nenhuma linha nova
    assert out.startswith("bateria: 2 / 2 passaram")  # o caso e a variante sem acento
    assert "chamadas à IA: 2 | tokens: 200 in, 40 out" in out
    assert "concierge-model-reader" in out and "choose_fulfillment" in out
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    assert tomorrow in out


def test_a_wrong_reading_fails_with_the_reason(house):
    out = _run("--case", "entrega-com", "--max-calls", "10")  # a IA falsa não lê "entrega"
    assert "[FALHOU] entrega-com" in out and "recebimento -, esperado delivery" in out


def test_the_call_ceiling_stops_the_run(house):
    out = _run("--case", "espalhado-tres", "--max-calls", "1")
    assert "INTERROMPIDO: teto de 1 chamadas" in out and house.calls == 1


def test_when_the_ai_fails_the_report_says_so(monkeypatch, house):
    house.error = TimeoutError("rede")
    out = _run("--case", "so-pedido-hoje", "--max-calls", "5")
    assert "caíram para a regra local" in out


def test_without_a_connection_nothing_is_called(monkeypatch):
    monkeypatch.setattr(model_reader, "build_client", lambda: (None, ""))
    with pytest.raises(CommandError, match="intents"):
        _run()
