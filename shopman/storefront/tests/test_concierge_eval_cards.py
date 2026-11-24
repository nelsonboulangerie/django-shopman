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
    from shopman.shop.ai import FittedClient

    ai = FakeAI()
    # O cliente medido da casa, como no ar: cada chamada paga grava uma AiInvocation (o freio vale).
    metered = FittedClient(ai, frozenset(), purpose="intents", connection_ref="eval-test", default_model="deepseek-flash")
    monkeypatch.setattr(model_reader, "build_client", lambda: (metered, "deepseek-flash"))
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


def test_the_five_cards_run_through_the_engine_and_write_nothing(house, monkeypatch):
    from shopman.storefront.concierge import turn_framework

    # Um molde sem frase aprovada, de propósito: a limitação ganhou frase (#3408), e o placar continua tendo de
    # marcar o turno que, no ar, sairia pelo caminho de hoje.
    without = {k: v for k, v in turn_framework.NICE_TEMPLATE_COPY.items() if k != "inform_limitation.offer_team"}
    monkeypatch.setattr(turn_framework, "NICE_TEMPLATE_COPY", without)
    before = _rows()
    out, error = _run()
    after = _rows()
    assert error == "" and after[:-1] == before[:-1]  # nenhuma tabela tocada por um turno ganhou linha
    assert after[-1] - before[-1] == house.calls  # só o medidor da casa: uma AiInvocation por chamada paga
    assert out.startswith("cartões: ") and out.count("\n[") == 5
    assert "Cliente: quero 2 croissants\n  Nice: Pronto, sua sacola ficou assim:" in out
    assert "Posso registrar?" in out and "movimentos: change_cart" in out
    # O turno com frase que a Nice não aprovou (a limitação do pacote) é marcado: no ar, caminho de hoje.
    assert "no ar: sairia pelo caminho de hoje (no_nice_template:inform_limitation.offer_team)" in out


def test_a_card_that_fails_says_what_the_engine_still_lacks(house, monkeypatch):
    """O placar diz o que o motor ainda não tem. Um cartão falso força a falha: os cartões de verdade passam
    um a um conforme o motor cresce (o 3 passou com o #3389), e o teste não pode depender de um deles falhar."""
    from shopman.storefront.concierge import eval_cards

    impossivel = eval_cards.Cartao("cartao-teste-falta", "pede o que o motor não faz", ("quero 2 croissants",),
                                   pedido=True, itens={"croissant": 2},
                                   falta="o motor não fecha pedido sem o cliente pedir o resumo")
    monkeypatch.setattr(eval_cards, "CARTOES", (impossivel,))
    out, _ = _run("--case", "cartao-teste-falta")
    assert "[FALHOU] cartao-teste-falta" in out and "✗ nenhum pedido fechado" in out
    assert "o que falta no motor: o motor não fecha pedido sem o cliente pedir o resumo" in out


def test_the_ensaio_profile_never_changes_the_live_profile(house):
    from shopman.storefront.concierge import eval_cards
    from shopman.storefront.concierge.profile import build_profile

    live = {line.id: line.state for line in build_profile(environment="live").lines}
    ensaio = {line.id: line.state for line in eval_cards._profile().lines}
    assert live[eval_cards.ORDER_LINE] != "approved" and ensaio[eval_cards.ORDER_LINE] == "approved"
    assert {k: v for k, v in live.items() if k != eval_cards.ORDER_LINE} == \
        {k: v for k, v in ensaio.items() if k != eval_cards.ORDER_LINE}  # só a P08 muda, e só no ensaio



def test_the_rehearsal_reads_the_menu_without_the_turn_claim():
    """A conversa do ensaio é de memória e não tem posse de turno. No ar, a busca do cardápio exige a posse; sem
    a leitura do ensaio, TODA leitura de produto voltava ``authority_unavailable`` e o placar não media nada
    (os outros testes não viam, porque trocam ``tools.execute`` inteiro)."""
    from shopman.shop.models import Conversation
    from shopman.storefront.concierge import tools
    from shopman.storefront.concierge.eval_battery import leitura_do_cardapio

    ctx = tools.ToolContext(conversation=Conversation(channel_ref="whatsapp"), channel_ref="whatsapp",
                            customer_text="croissant")
    assert tools.execute("search_storefront", {}, ctx).get("error") == "authority_unavailable"
    with leitura_do_cardapio():
        # A busca roda de verdade (sem loja no banco do teste, ela diz que a informação pública falta).
        assert tools.execute("search_storefront", {}, ctx).get("error") != "authority_unavailable"
    assert tools.execute("search_storefront", {}, ctx).get("error") == "authority_unavailable"  # só no ensaio


def test_the_rehearsal_offers_the_channel_payment_methods(house):
    from shopman.shop.conversational.commerce_read import conversation_payment_methods
    from shopman.storefront.concierge import eval_cards

    _engine, world = eval_cards.engine_for(lambda conversa, linhas: None, today=None)
    assert world.state.payment_methods == tuple(conversation_payment_methods(eval_cards.CHANNEL))


def test_the_rehearsal_takes_the_store_classes_and_refuses_an_unknown_one(house):
    _out, error = _run("--classes", "inform,pedido")
    assert "classe desconhecida: pedido" in error
