"""Bugs da Nice no caminho do motor, achados pela revisão independente (23/11/2026), sem tocar o Core.

1. O recibo do sítio não trazia ``effect``, a faceta que os moldes do pacote citam
   (``change_cart.done`` e ``commit_order.done``): a composição levantava, e o turno caía no
   caminho de hoje.
2. A cotação não trazia a forma de pagamento escolhida: o cliente confirmaria sem ver como paga.
3. O "sim" do motor (``commit_order`` com ``parameters={}``) nunca passava: a guarda só via os
   termos vigentes pelo código da revisão da casa (ADR-050), que o motor não manda, e o sítio
   exigia esse código e a forma de pagamento nos parâmetros.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.reply import TEMPLATES_BY_ID
from conversational_commerce.reply.evidence import Evidence
from shopman.orderman.models import Session

from shopman.shop.conversational.commerce_execute import Reading, ShopmanCommerceExecute
from shopman.shop.models import Conversation
from shopman.storefront.concierge.effect_site import ConciergeEffectSite
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CTX = SimpleNamespace(tenant="t", environment="test", subject="conversation:1")
CHANNEL = "whatsapp"
HASH = "sha256:" + "a" * 64


@pytest.fixture
def site(monkeypatch):
    conversation = Conversation.objects.create(pk=1, session_key="sess-1", channel_ref=CHANNEL)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    return ConciergeEffectSite(ToolContext(conversation=conversation, channel_ref=CHANNEL))


def _fills(template_id: str, refs) -> object:
    """O valor que o molde do pacote lê do recibo (a faceta do espaço)."""
    template = TEMPLATES_BY_ID[template_id]
    [(slot, spec)] = template.slots.items()
    evidence = Evidence(now="2026-11-23T10:00:00.000000Z",
                        receipts={"cmd-1": SimpleNamespace(status="success", domain_refs=dict(refs))})
    return evidence.value("receipt", "cmd-1", spec.field)


def command(action, target="sess-1", **parameters):
    return SimpleNamespace(action=action, targets=(target,), parameters=parameters)


# ── 1. o recibo traz o que o molde do pacote cita ─────────────────────────────────────


def test_the_cart_receipt_fills_the_package_template(site, monkeypatch):
    monkeypatch.setattr("shopman.storefront.concierge.tools.set_item", lambda ctx, sku, qty: {"ok": True})
    done = site.apply(CTX, command("change_cart", item="CROISSANT", quantity="2"))
    assert _fills("change_cart.done", done.domain_refs) == "sess-1"


def test_the_order_receipt_fills_the_package_template(site, monkeypatch):
    from shopman.storefront.concierge import tools

    monkeypatch.setattr(tools, "place_order", lambda ctx, token, method, notes: {"ok": True, "order_ref": "ORD-1"})
    done = site.apply(CTX, command("commit_order", terms_ref="tok-1", payment_method="pix"))
    assert _fills("commit_order.done", done.domain_refs) == "ORD-1"


# ── 2. a forma de pagamento é condição dos termos ──────────────────────────────────────


def test_the_quote_says_how_the_customer_pays(db):
    from shopman.offerman.models import Product

    from shopman.shop.conversational.commerce_read import ShopmanCommerceRead
    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="Nelson Boulangerie")
    Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={})
    Product.objects.create(sku="PAO", name="Pão", base_price_q=450, is_published=True, is_sellable=True)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL, items=[{"sku": "PAO", "qty": 1,
                                                                               "unit_price_q": 450}],
                           data={"payment": {"method": "pix"}})
    owns = SimpleNamespace(cart=lambda ctx: "sess-1")
    terms = ShopmanCommerceRead(channel_ref=CHANNEL, ownership=owns).quote(
        SimpleNamespace(tenant="t", environment="test", subject="conversation:1"), "sess-1")
    assert {c.code: c.value for c in terms.conditions}["payment_method"] == "pix"


# ── 3. o "sim" do motor fecha o pedido ─────────────────────────────────────────────────


def _engine_commit(versions):
    return SimpleNamespace(terms_hash=HASH, parameters={}, expected_versions=versions)


def test_the_engine_terms_are_in_force_while_the_cart_is_the_same_revision():
    executor = ShopmanCommerceExecute(site=SimpleNamespace(actions=()))
    same = executor._state(_engine_commit({"sess-1": 4}), Reading(ownership_epoch=1, versions={"sess-1": 4}))
    assert same.terms_hash == HASH  # a guarda vê os termos confirmados vigentes
    moved = executor._state(_engine_commit({"sess-1": 4}), Reading(ownership_epoch=1, versions={"sess-1": 5}))
    assert moved.terms_hash != HASH  # a sacola mudou depois do "sim": termos novos, confirmação nova (K07)


def test_the_engine_yes_places_the_order_by_a_fresh_house_review(site, monkeypatch):
    from shopman.storefront.concierge import tools

    placed = []
    monkeypatch.setattr(tools, "execute", lambda name, args, ctx: {
        "ok": True, "ready": True, "quote_token": "tok-9", "payment_method": "pix"})
    monkeypatch.setattr(tools, "place_order",
                        lambda ctx, token, method, notes: placed.append((token, method)) or
                        {"ok": True, "order_ref": "ORD-9"})
    done = site.apply(CTX, command("commit_order"))
    assert done.applied and placed == [("tok-9", "pix")]
    assert dict(done.domain_refs) == {"effect": "ORD-9", "order": "ORD-9"}


def test_an_incomplete_order_never_places(site, monkeypatch):
    from shopman.storefront.concierge import tools

    monkeypatch.setattr(tools, "execute", lambda name, args, ctx: {"ok": True, "ready": False,
                                                                   "missing": ["payment_method"]})
    monkeypatch.setattr(tools, "place_order", lambda *a: pytest.fail("pedido incompleto não grava"))
    done = site.apply(CTX, command("commit_order"))
    assert (done.applied, done.refusal) == (False, ErrorCode.INVALID_CONTENT.value)
