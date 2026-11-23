"""Conformidade de escopo adapter: o que o motor agora exige da porta de comércio do Shopman.

``spec/03-ports.md`` ("O que o motor exige da porta de comércio para dizer o estado depois do
efeito"): o ``read_order`` com ``total`` em ``{price_minor, currency}``, o recibo de sucesso do
``change_cart`` e do ``commit_order`` com ``effect``, e o fato dos termos sem o destinatário.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conversational_commerce.contracts import Known
from conversational_commerce.engine.turn import terms_fact
from conversational_commerce.ports import TrustedContext
from conversational_commerce.testing.conformance import conformance
from shopman.orderman.models import Order, Session

from shopman.shop.conversational.commerce_read import ShopmanCommerceRead
from shopman.shop.models import Channel, Conversation, Shop
from shopman.storefront.concierge.effect_site import ConciergeEffectSite
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CHANNEL = "whatsapp"
CTX = TrustedContext(tenant="nelson-boulangerie", environment="test", subject="conversation:1")


class Owns:
    def cart(self, ctx):
        return "sess-1"

    def new_cart(self, ctx):
        return None

    def customer(self, ctx):
        return "cust-1"

    def owns_order(self, ctx, ref):
        return ref == "ORD-1"


@pytest.fixture
def shop():
    from shopman.offerman.models import Product

    Shop.objects.create(name="Nelson Boulangerie")
    Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={})
    Product.objects.create(sku="PAO", name="Pão", base_price_q=450, is_published=True, is_sellable=True)


def reader():
    return ShopmanCommerceRead(channel_ref=CHANNEL, ownership=Owns())


@conformance("K23", invariants=("N01", "N03"), scope="adapter")
def test_the_order_read_says_the_total_as_money(shop):
    Order.objects.create(ref="ORD-1", channel_ref=CHANNEL, session_key="sess-1", status="new", total_q=2400,
                         snapshot={"items": []}, data={})
    fact = reader().read_order(CTX, "ORD-1")
    assert isinstance(fact, Known)
    assert dict(fact.value["total"]) == {"price_minor": 2400, "currency": "BRL"}


@conformance("K23", invariants=("N01", "N03"), scope="adapter")
def test_the_terms_fact_has_the_document_and_never_the_recipient(shop):
    """P17: o destinatário (quem recebe) é dado pessoal e não vai ao lastro da resposta."""
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL,
                           items=[{"sku": "PAO", "qty": 2, "unit_price_q": 450}],
                           data={"payment": {"method": "pix"}})
    terms = reader().quote(CTX, "sess-1")
    fact = terms_fact(terms, {"PAO": "Pão"})
    assert "recipient" not in fact and CTX.subject not in str(fact)
    assert fact["items"][0]["name"] == "Pão" and fact["conditions"] == {"payment_method": "pix"}


@conformance("K24", invariants=("N01",), scope="adapter")
def test_the_cart_and_order_receipts_point_the_effect(shop, monkeypatch):
    from shopman.storefront.concierge import tools

    conversation = Conversation.objects.create(pk=1, session_key="sess-1", channel_ref=CHANNEL)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    site = ConciergeEffectSite(ToolContext(conversation=conversation, channel_ref=CHANNEL))
    monkeypatch.setattr(tools, "set_item", lambda ctx, sku, qty: {"ok": True})
    monkeypatch.setattr(tools, "place_order", lambda ctx, token, method, notes: {"ok": True, "order_ref": "ORD-1"})
    command = lambda action, **parameters: SimpleNamespace(action=action, targets=("sess-1",),  # noqa: E731
                                                          parameters=parameters)
    cart = site.apply(CTX, command("change_cart", lines=[{"item": "PAO", "quantity": "2"}]))
    order = site.apply(CTX, command("commit_order", terms_ref="tok", payment_method="pix"))
    assert cart.domain_refs["effect"] == "sess-1" and order.domain_refs["effect"] == "ORD-1"


def test_the_terms_show_the_payment_the_order_will_be_placed_with(shop):
    """Sem forma escolhida, a revisão que grava usa a única do canal; a cotação mostra a mesma."""
    Channel.objects.filter(ref=CHANNEL).update(config={"payment": {"method": ["pix"]}})
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL,
                           items=[{"sku": "PAO", "qty": 1, "unit_price_q": 450}], data={})
    terms = reader().quote(CTX, "sess-1")
    assert {c.code: c.value for c in terms.conditions}["payment_method"] == "pix"
