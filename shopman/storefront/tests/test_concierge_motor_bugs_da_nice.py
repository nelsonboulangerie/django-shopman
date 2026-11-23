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


def _fills(template_id: str, refs, slot: str) -> object:
    """O valor que o espaço do molde do pacote lê do recibo (a faceta dele)."""
    spec = TEMPLATES_BY_ID[template_id].slots[slot]
    evidence = Evidence(now="2026-11-23T10:00:00.000000Z",
                        receipts={"cmd-1": SimpleNamespace(status="success", domain_refs=dict(refs))})
    return evidence.value("receipt", "cmd-1", spec.field)


def command(action, target="sess-1", **parameters):
    return SimpleNamespace(action=action, targets=(target,), parameters=parameters)


# ── 1. o recibo traz o que o molde do pacote cita ─────────────────────────────────────


def test_the_cart_receipt_fills_the_package_template(site, monkeypatch):
    monkeypatch.setattr("shopman.storefront.concierge.tools.set_item", lambda ctx, sku, qty: {"ok": True})
    done = site.apply(CTX, command("change_cart", item="CROISSANT", quantity="2"))
    # O efeito é afirmado pelo estado do recibo; o que ele aponta é a sacola de verdade.
    assert _fills("change_cart.done", done.domain_refs, "done") == "success"
    assert done.domain_refs["effect"] == "sess-1"


def test_the_order_receipt_fills_the_package_template(site, monkeypatch):
    from shopman.storefront.concierge import tools

    monkeypatch.setattr(tools, "place_order", lambda ctx, token, method, notes: {"ok": True, "order_ref": "ORD-1"})
    done = site.apply(CTX, command("commit_order", terms_ref="tok-1", payment_method="pix"))
    assert _fills("commit_order.done", done.domain_refs, "order") == "ORD-1"
    assert _fills("commit_order.done", done.domain_refs, "track") == "ORD-1"


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


# ── 4 e 5. o "total mudou" e o pedido registrado (frases aprovadas pelo dono em 23/11) ──


def _say(template_id: str, **values) -> str:
    from shopman.storefront.concierge import turn_framework

    text = turn_framework.nice_templates()[template_id].text
    formatters = turn_framework.nice_formatters()
    for slot, value in values.items():
        text = text.replace("{" + slot + "}", formatters.get(slot, str)(value))
    return text


def test_the_total_changed_says_the_new_total_in_reais(db):
    assert _say("present_terms.changed", total={"price_minor": 2400, "currency": "BRL"}) == \
        "O total mudou; agora é R$ 24,00. Confira antes de confirmar."


def test_the_order_placed_is_today_phrase_with_the_total(db, settings):
    """Critério de pronto da coordenação: a frase de hoje com o total (sem a frase do Pix, que vem à parte)."""
    from shopman.storefront.concierge.tools import render_result

    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://loja.exemplo/"
    today = render_result("place_order", {"ok": True, "order_ref": "WHATSAPP-261122-S50", "total": "R$ 24,00",
                                          "tracking_url": "https://loja.exemplo/pedido/WHATSAPP-261122-S50/"})
    assert _say("commit_order.done", order="WHATSAPP-261122-S50", total={"price_minor": 2400, "currency": "BRL"},
                track="WHATSAPP-261122-S50") == today == \
        "Pedido WHATSAPP-261122-S50 registrado. Total: R$ 24,00.\nAcompanhar: https://loja.exemplo/pedido/WHATSAPP-261122-S50/"


LINES = [{"ref": "CROISSANT", "quantity": "2", "unit": "unit", "name": "Croissant",
          "unit_price": {"price_minor": 1200, "currency": "BRL"},
          "line_total": {"price_minor": 2400, "currency": "BRL"}}]
TODAY_LINES = [{"qty": 2, "name": "Croissant", "line_total": "R$ 24,00"}]


def test_the_cart_updated_is_today_phrase(db):
    from shopman.storefront.concierge.service import copy_message
    from shopman.storefront.concierge.tools import render_result

    today = "\n".join((copy_message("CONCIERGE_CART_UPDATED").strip(),
                       render_result("set_item", {"ok": True, "lines": TODAY_LINES, "total": "R$ 24,00"}),
                       copy_message("CONCIERGE_CART_NEXT").strip()))
    assert _say("change_cart.done", done="success", items=LINES,
                total={"price_minor": 2400, "currency": "BRL"}) == today


def test_the_terms_summary_is_today_review_ending_in_may_i_register(db):
    from datetime import date, timedelta

    from shopman.storefront.concierge.tools import render_result

    day = (date.today() + timedelta(days=1)).isoformat()
    today = render_result("review_order", {
        "ok": True, "lines": TODAY_LINES, "total": "R$ 24,00", "payment_method": "pix",
        "fulfillment": {"type": "pickup", "date": day, "slot_label": "A partir das 15h"}})
    summary = "\n".join(today.split("\n")[:-1] + ["Posso registrar?"])  # sem o "confirmo <código>" (aprovado 23/11)
    assert _say("present_terms.confirm", items=LINES, total={"price_minor": 2400, "currency": "BRL"},
                fulfillment={"mode": "pickup"},
                conditions={"fulfillment_date": day, "fulfillment_window": "slot-15", "payment_method": "pix"}) == summary


def test_the_money_in_the_fact_is_a_frozen_map_and_still_says_reais(db):
    """O lastro da resposta guarda o dinheiro como ``FrozenMap``: o formatador da Nice lê um ``Mapping``."""
    from conversational_commerce.contracts.canonical import FrozenMap

    from shopman.storefront.concierge import turn_framework

    assert turn_framework.money_text(FrozenMap({"price_minor": 2400, "currency": "BRL"})) == "R$ 24,00"


def test_the_frozen_terms_fact_renders_today_summary(db):
    """O fato dos termos chega congelado (``Known`` guarda ``FrozenMap`` e tuplas): o resumo sai igual."""
    from conversational_commerce.contracts import Known

    fact = Known(value={"items": LINES, "total": {"price_minor": 2400, "currency": "BRL"},
                        "fulfillment": {"mode": "pickup"}, "conditions": {"payment_method": "pix"}},
                 source="commerce-quote", observed_at="2026-11-23T10:00:00.000000Z",
                 valid_until="2026-11-23T11:00:00.000000Z")
    value = fact.value
    text = _say("present_terms.confirm", items=value["items"], total=value["total"],
                fulfillment=value["fulfillment"], conditions=value["conditions"])
    assert text.startswith("2 × “Croissant”: R$ 24,00\nTotal: R$ 24,00\nRetirada")
    assert text.endswith("Pagamento: Pix.\nPosso registrar?")
