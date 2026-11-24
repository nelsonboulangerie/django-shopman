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
    from shopman.offerman.models import Product

    from shopman.shop.ai import FittedClient
    from shopman.storefront.concierge import tools, triage

    # O cardápio do teste: a bateria pula o caso cujo produto não está no cardápio (#3484).
    Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=1200, is_published=True, is_sellable=True)
    ai = FakeAI()
    # O cliente medido da casa, como no ar: cada chamada paga passa pelo freio e grava uma AiInvocation.
    metered = FittedClient(ai, frozenset(), purpose="intents", connection_ref="eval-test", default_model="deepseek-flash")
    monkeypatch.setattr(model_reader, "build_client", lambda: (metered, "deepseek-flash"))
    monkeypatch.setattr(triage, "jev_enabled", lambda: False)
    monkeypatch.setattr(tools, "execute", lambda name, args, ctx: {"ok": True, "items": [CROISSANT]})
    return ai


def _run(*args) -> str:
    out = StringIO()
    call_command("concierge_eval", "--battery", *args, stdout=out)
    return out.getvalue()


def _rows():
    """As tabelas que um turno da Concierge toca. No ensaio, só o medidor de gasto (a última) cresce."""
    from shopman.orderman.models import Order

    from shopman.shop.models import AiInvocation, ConversationalCommitment, ConversationalEpisode

    return tuple(model.objects.count() for model in (Conversation, Session, ConversationMessage, Order,
                                                     ConversationalEpisode, ConversationalCommitment,
                                                     AiInvocation))


def test_the_battery_scores_the_reader_and_writes_only_the_house_meter(house):
    before = _rows()
    out = _run("--case", "frase-cartao-1", "--max-calls", "10")
    after = _rows()
    assert after[:-1] == before[:-1]  # conversa, sacola, mensagem, pedido, episódio, compromisso: nenhuma linha
    assert after[-1] - before[-1] == house.calls == 2  # o medidor da casa: uma AiInvocation por chamada paga
    assert out.startswith("bateria: 2 / 2 passaram")  # o caso e a variante sem acento
    assert "chamadas à IA: 2 | tokens: 200 in, 40 out" in out
    assert "concierge-model-reader" in out and "choose_fulfillment" in out
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    assert tomorrow in out


def test_a_wrong_reading_fails_with_the_reason(house):
    out = _run("--case", "entrega-com", "--max-calls", "10")  # a IA falsa não lê "entrega"
    assert "[FALHOU] entrega-com" in out and "recebimento -, esperado delivery" in out


def _failing(*args):
    out = StringIO()
    with pytest.raises(CommandError) as failed:
        call_command("concierge_eval", "--battery", *args, stdout=out)
    return out.getvalue(), str(failed.value)


def test_the_call_ceiling_stops_the_run_with_an_error(house):
    out, error = _failing("--case", "espalhado-tres", "--max-calls", "1")
    assert "INTERROMPIDO: teto de 1 chamadas" in out and house.calls == 1
    assert "teto de 1 chamadas" in error


def test_the_cost_ceiling_stops_the_run_and_the_report_says_the_spend(house):
    out, error = _failing("--case", "espalhado-tres", "--max-usd", "0.0000001")
    assert "custo estimado: US$" in out and "teto de US$" in error and house.calls == 1


def test_when_the_ai_refuses_the_run_fails_with_the_true_error(house):
    house.error = TimeoutError("a DeepSeek não respondeu em 8 s")
    out, error = _failing("--case", "so-pedido-hoje", "--max-calls", "5")
    assert "caíram para a regra local" in out and "TimeoutError: a DeepSeek não respondeu em 8 s" in out
    assert "a IA recusou 1 falas" in error and "TimeoutError" in error


def test_without_a_connection_nothing_is_called(monkeypatch):
    monkeypatch.setattr(model_reader, "build_client", lambda: (None, ""))
    with pytest.raises(CommandError, match="intents"):
        _run()



def test_a_case_whose_product_left_the_menu_is_skipped_without_calling_the_ai(house):
    """#3484: o caso que espera um produto fora do cardápio reprovaria pelo dado, não pela leitura. Ele sai
    pulado, com o nome do que falta, e nenhuma chamada à IA é feita."""
    out = _run("--case", "sem-hoje-tem-amanha")
    assert "[pulado] sem-hoje-tem-amanha" in out and "sem produto no cardápio: sonho" in out
    assert "bateria: 0 / 0 passaram (1 pulados: produto fora do cardápio)" in out
    assert house.calls == 0
