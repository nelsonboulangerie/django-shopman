"""Executor certo, só fato (coordenação, 20/11/2026; conversas reais do dono).

- "Aceitam pets ai na padaria?" recebeu o texto do glúten (que diz "Somos uma padaria") e o
  de pagamento (que diz "aceitamos");
- "O pain perdu é doce ou salgado?" recebeu só o preço;
- "quanto custa o pain perdu?" recebeu o preço, o texto do glúten e o do cancelamento.

A regra: pergunta de produto responde pela ficha; sem dado, "vou verificar"; nunca colar o
texto vizinho. A pergunta da casa recebe a resposta que melhor casou, só ela.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.offerman.models import Collection, CollectionItem

from config.management.commands.apply_search_presence import PUBLIC_FAQ
from shopman.shop.models import FAQEntry
from shopman.storefront.concierge import intents, triage
from shopman.storefront.tests import test_concierge_engine as engine
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    CONCIERGE_SETTINGS,
    _binding,
    _claim_conversation,
    _create_inbound,
    _listed,
)
from shopman.storefront.tests.test_concierge_intents import ReaderClient, _act

surface = engine.surface
customer = engine.customer
conversation = engine.conversation
outbox = engine.outbox
pytestmark = pytest.mark.django_db

PERDU = "Fatia de brioche banhada no creme e dourada, com caramelo salgado, chantilly e flor de sal"
GLUTEN = "Somos uma padaria"
VERIFY = "Já perguntei para a equipe"


@pytest.fixture
def menu(surface):
    """O cardápio e a FAQ do seed: os doces de verdade e as perguntas frequentes publicadas."""
    doces, _ = Collection.objects.get_or_create(ref="doces", defaults={"name": "Doces"})
    for sku, name, description in (
        ("PERDU", "Pain Perdu", PERDU),
        ("MDLN", "Madeleine", "Bolinho clássico francês, simples e delicioso"),
        ("MELSA", "Melon Iced Sando", "Sanduíche gelado de frutas com chantilly, no shokupan"),
    ):
        product = _listed(sku, name, description=description)
        CollectionItem.objects.filter(product=product).delete()
        CollectionItem.objects.create(collection=doces, product=product, sort_order=1)
    _listed("CROISSANT", "Croissant", description="Folhado amanteigado", stock="50")
    _listed("LEVAIN", "Levain", description="Pão de fermentação natural")
    for entry in PUBLIC_FAQ:
        FAQEntry.objects.create(
            ref=entry["ref"], question=entry["question"], answer=entry["answer"],
            search_terms=entry["search_terms"], is_published=True, position=entry["position"],
        )


def _turn(conversation, text, acts, monkeypatch):  # noqa: F811
    """Um turno com o leitor de partes dizendo os atos, como em produção."""
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _create_inbound(conversation, text, f"exec-{abs(hash(text))}")
    conversation = _claim_conversation(conversation)
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        decision = triage.decide(text, context=triage.context_for(conversation), channel_ref=CHANNEL)
        triage.record(conversation, list(conversation.messages.filter(pk__in=conversation._inbound_ids)), decision)
        return intents.run(conversation, binding=_binding(conversation), decision=decision, client=ReaderClient(acts))


def test_pets_never_gets_the_gluten_or_payment_text(conversation, menu, monkeypatch):  # noqa: F811
    text = "Aceitam pets ai na padaria?"
    outcome = _turn(conversation, text, [_act("house_info", text)], monkeypatch)

    assert GLUTEN not in outcome.reply_text and "aceitamos" not in outcome.reply_text
    assert VERIFY in outcome.reply_text  # sem fato: a casa pergunta à equipe


def test_sweet_or_savory_answers_from_the_product_sheet(conversation, menu, monkeypatch):  # noqa: F811
    text = "O pain perdu é doce ou salgado?"
    outcome = _turn(conversation, text, [_act("product_question", text, "pain perdu")], monkeypatch)

    assert "Pain Perdu" in outcome.reply_text
    assert PERDU in outcome.reply_text  # a ficha, com o caramelo salgado
    assert GLUTEN not in outcome.reply_text and VERIFY not in outcome.reply_text


def test_attribute_the_sheet_does_not_cover_is_verified(conversation, menu, monkeypatch):  # noqa: F811
    text = "o croissant é grande?"
    outcome = _turn(conversation, text, [_act("product_question", text, "croissant")], monkeypatch)

    assert VERIFY in outcome.reply_text
    assert "R$" not in outcome.reply_text  # nada de preço no lugar da resposta


def test_he_is_sweet_without_the_product_is_verified(conversation, menu, monkeypatch):  # noqa: F811
    text = "ele é doce?"
    outcome = _turn(conversation, text, [_act("product_question", text)], monkeypatch)

    assert VERIFY in outcome.reply_text and "R$" not in outcome.reply_text


def test_a_suggestion_lists_the_sheets_and_nothing_about_delivery(conversation, menu, monkeypatch):  # noqa: F811
    text = "quero algo doce… o que sugere?"
    outcome = _turn(conversation, text, [_act("product_question", text)], monkeypatch)

    for name in ("Pain Perdu", "Madeleine", "Melon Iced Sando"):
        assert name in outcome.reply_text
    assert "entrega" not in outcome.reply_text.lower() and GLUTEN not in outcome.reply_text


@pytest.mark.parametrize("text", ["quanto custa o pain perdu?", "tem croissant?"])
def test_price_and_presence_get_only_the_menu_line(conversation, menu, monkeypatch, text):  # noqa: F811
    product = "pain perdu" if "perdu" in text else "croissant"
    outcome = _turn(conversation, text, [_act("product_question", text, product)], monkeypatch)

    assert "R$" in outcome.reply_text
    assert GLUTEN not in outcome.reply_text and "Cancelar pedido" not in outcome.reply_text


def test_a_house_question_gets_only_the_best_answer(conversation, menu, monkeypatch):  # noqa: F811
    text = "quanto custa a entrega?"
    outcome = _turn(conversation, text, [_act("hours_delivery", text)], monkeypatch)

    assert "Fazemos entrega" in outcome.reply_text
    assert "acompanha cada etapa" not in outcome.reply_text


def test_payment_question_still_finds_payment(conversation, menu, monkeypatch):  # noqa: F811
    text = "aceitam pix?"
    outcome = _turn(conversation, text, [_act("house_info", text)], monkeypatch)

    assert "Pix" in outcome.reply_text and GLUTEN not in outcome.reply_text
