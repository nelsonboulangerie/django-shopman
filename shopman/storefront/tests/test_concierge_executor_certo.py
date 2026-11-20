"""probe"""
from __future__ import annotations

import pytest
from shopman.offerman.models import Collection, CollectionItem
from shopman.shop.models import FAQEntry

from config.management.commands.apply_search_presence import PUBLIC_FAQ
from shopman.storefront.tests import test_concierge_engine as engine
from django.test import override_settings
from shopman.storefront.concierge import intents, triage
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL, CONCIERGE_SETTINGS, _binding, _claim_conversation, _create_inbound, _listed,
)
from shopman.storefront.tests.test_concierge_intents import ReaderClient, _act


def _turn(conversation, text, event_id, acts, monkeypatch):
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _create_inbound(conversation, text, event_id)
    conversation = _claim_conversation(conversation)
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        decision = triage.decide(text, context=triage.context_for(conversation), channel_ref=CHANNEL)
        triage.record(conversation, list(conversation.messages.filter(pk__in=conversation._inbound_ids)), decision)
        return intents.run(conversation, binding=_binding(conversation), decision=decision, client=ReaderClient(acts))

surface = engine.surface
customer = engine.customer
conversation = engine.conversation
outbox = engine.outbox
pytestmark = pytest.mark.django_db


@pytest.fixture
def menu(surface):
    doces, _ = Collection.objects.get_or_create(ref="doces", defaults={"name": "Doces"})
    for sku, name, desc in (
        ("PERDU", "Pain Perdu", "Fatia de brioche banhada no creme e dourada, com caramelo salgado, chantilly e flor de sal"),
        ("MDLN", "Madeleine", "Bolinho clássico francês, simples e delicioso"),
        ("MELSA", "Melon Iced Sando", "Sanduíche gelado de frutas com chantilly, no shokupan"),
    ):
        p = _listed(sku, name, description=desc)
        CollectionItem.objects.filter(product=p).delete()
        CollectionItem.objects.create(collection=doces, product=p, sort_order=1)
    _listed("CROISSANT", "Croissant", description="Folhado amanteigado", stock="50")
    _listed("LEVAIN", "Levain", description="Pão de fermentação natural")
    for e in PUBLIC_FAQ:
        FAQEntry.objects.create(ref=e["ref"], question=e["question"], answer=e["answer"],
                                search_terms=e["search_terms"], is_published=True, position=e["position"])


@pytest.mark.parametrize(("text", "acts"), [
    ("Aceitam pets ai na padaria?", [_act("house_info", "Aceitam pets ai na padaria?")]),
    ("O pain perdu é doce ou salgado?", [_act("product_question", "O pain perdu é doce ou salgado?", "pain perdu")]),
    ("ele é doce?", [_act("product_question", "ele é doce?")]),
    ("quero algo doce… o que sugere?", [_act("product_question", "quero algo doce… o que sugere?")]),
    ("ele é doce?", [_act("product_question", "ele é doce?", "pain perdu")]),
    ("o croissant é grande?", [_act("product_question", "o croissant é grande?", "croissant")]),
    ("aceitam pix?", [_act("house_info", "aceitam pix?")]),
    ("quanto custa a entrega?", [_act("hours_delivery", "quanto custa a entrega?")]),
    ("tem croissant?", [_act("product_question", "tem croissant?", "croissant")]),
    ("quanto custa o pain perdu?", [_act("product_question", "quanto custa o pain perdu?", "pain perdu")]),
])
def test_probe(conversation, menu, text, acts, monkeypatch):
    outcome = _turn(conversation, text, f"p-{abs(hash(text))}", acts, monkeypatch)
    print("\n>>>", text, "\n", outcome.reply_text, "\n", getattr(outcome, "verification", None))
