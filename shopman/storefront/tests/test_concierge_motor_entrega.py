"""A entrega pelo motor, do lado da Nice (cartão 2, #3382).

O que estes testes seguram:

- o fato do canal pede o endereço, o que falta nele e o complemento, ANTES do pagamento;
- os termos levam o endereço só por referência, e a taxa como condição (as linhas do resumo de hoje);
- o sítio lê o texto ORIGINAL pela referência da fala, mantém o dia e a janela, e o recibo leva só a
  referência; sem entrega combinada, ou fora da área, nada fica gravado;
- a localização do WhatsApp é o endereço, sem IA;
- o formatador de referência resolve só o endereço da sacola da conversa, e o resto segura;
- as perguntas são as de hoje, e o feito diz "Combinado: entrega na Rua das Flores, 120.".
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.reply import UnresolvedReference
from shopman.orderman.models import Session

from shopman.shop.conversational.commerce_read import ShopmanCommerceRead, address_ref
from shopman.shop.models import Channel, Conversation, ConversationMessage
from shopman.storefront.concierge import turn_framework
from shopman.storefront.concierge.effect_site import ConciergeEffectSite, address_parts
from shopman.storefront.concierge.ports import ConversationOwnership, shared_location_of
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CHANNEL = "whatsapp"
CTX = SimpleNamespace(tenant="t", environment="test", subject="conversation:1")
FULL = {"route": "Rua das Flores", "street_number": "120", "neighborhood": "Centro", "city": "Londrina",
        "state_code": "PR", "postal_code": "86010-000", "latitude": -23.3, "longitude": -51.1,
        "formatted_address": "Rua das Flores, 120 - Centro, Londrina - PR, 86010-000"}


@pytest.fixture
def conversation():
    Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={"payment": {"method": ["pix", "card"]}})
    return Conversation.objects.create(pk=1, session_key="sess-1", channel_ref=CHANNEL)


def _session(**data):
    return Session.objects.create(session_key="sess-1", channel_ref=CHANNEL, data=data)


def _ctx():
    from conversational_commerce.ports import TrustedContext

    return TrustedContext(tenant="t", environment="test", subject="conversation:1")


def _missing(**data):
    _session(**data)
    fact = ShopmanCommerceRead(channel_ref=CHANNEL, ownership=ConversationOwnership()).requirements(_ctx(), "sess-1")
    return list(fact.value["missing"]), fact.value


# ── o fato do canal: o endereço antes do pagamento ────────────────────────────────────────


def test_delivery_without_address_asks_the_address_before_the_payment(conversation):
    missing, value = _missing(fulfillment_type="delivery")
    assert missing == ["delivery_address", "payment_method"]
    assert list(value["delivery_address"]) == []


def test_who_has_a_saved_address_hears_it_first_by_today_closing(conversation, monkeypatch):
    """Decisão do dono (25/09): o endereço cadastrado vem antes de qualquer pergunta. O motor não pergunta
    o endereço novo; a condição é outra, sem molde da Nice, e o turno segue o fechamento de hoje."""
    from shopman.guestman.services import address as address_service

    conversation.customer_ref = "cust-1"
    conversation.save(update_fields=["customer_ref"])
    monkeypatch.setattr(address_service, "addresses", lambda ref: [object()] if ref == "cust-1" else [])
    missing, _ = _missing(fulfillment_type="delivery", payment={"method": "pix"})
    assert missing == ["delivery_address_saved"]
    assert "present_terms.needs_delivery_address_saved" not in turn_framework.nice_templates()


def test_an_incomplete_address_asks_what_is_missing_in_house_words(conversation):
    incomplete = {key: value for key, value in FULL.items() if key not in {"street_number", "postal_code"}}
    missing, value = _missing(fulfillment_type="delivery", delivery_address_structured=incomplete,
                              payment={"method": "pix"})
    assert missing == ["delivery_address_details"]
    assert list(value["delivery_address_details"]) == ["o número (ou S/N)", "o CEP"]


def test_a_complete_address_asks_the_complement_once(conversation):
    assert _missing(fulfillment_type="delivery", delivery_address_structured=FULL,
                    payment={"method": "pix"})[0] == ["delivery_complement"]


def test_without_complement_answered_nothing_is_missing(conversation):
    assert _missing(fulfillment_type="delivery", delivery_address_structured={**FULL, "complement": ""},
                    payment={"method": "pix"})[0] == []


def test_pickup_never_asks_an_address(conversation):
    assert _missing(fulfillment_type="pickup", payment={"method": "pix"})[0] == []


# ── os termos: o endereço por referência, a taxa como condição ────────────────────────────


def test_the_terms_carry_the_address_only_by_reference_and_the_fee(conversation):
    from shopman.offerman.models import Product

    from shopman.shop.models import Shop

    Shop.objects.create(name="Nelson Boulangerie")
    Product.objects.create(sku="PAO", name="Pão", base_price_q=450, is_published=True, is_sellable=True)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL,
                           items=[{"sku": "PAO", "qty": 1, "unit_price_q": 450, "line_total_q": 450}],
                           data={"fulfillment_type": "delivery", "delivery_address": FULL["formatted_address"],
                                 "delivery_address_structured": FULL, "delivery_fee_q": 800,
                                 "payment": {"method": "pix"}})
    terms = ShopmanCommerceRead(channel_ref=CHANNEL, ownership=ConversationOwnership()).quote(_ctx(), "sess-1")
    assert terms.fulfillment.address_ref == address_ref("sess-1")
    conditions = {c.code: c.value for c in terms.conditions}
    assert conditions["delivery_address"] == address_ref("sess-1") and conditions["delivery_fee"] == 800
    assert "Flores" not in json.dumps(terms.to_json() if hasattr(terms, "to_json") else str(terms))


# ── a leitura da casa ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("text", "structured", "expected"), [
    ("Rua das Flores 120, Centro", None, {"address": "Rua das Flores 120, Centro"}),
    ("apto 12", FULL, {"complement": "apto 12"}),
    ("sem complemento", FULL, {"complement": "sem complemento"}),
    ("120", {k: v for k, v in FULL.items() if k != "street_number"}, {"street_number": "120"}),
    ("sem número", {k: v for k, v in FULL.items() if k != "street_number"}, {"street_number": "sem número"}),
    ("86010-000", {k: v for k, v in FULL.items() if k != "postal_code"}, {"postal_code": "86010-000"}),
    ("Jardim Botânico", {k: v for k, v in FULL.items() if k != "neighborhood"}, {"neighborhood": "Jardim Botânico"}),
    ("Avenida Brasil 500", {k: v for k, v in FULL.items() if k != "street_number"},
     {"address": "Avenida Brasil 500"}),
    ("", FULL, {}),
])
def test_the_house_reads_what_the_customer_wrote(text, structured, expected):
    assert address_parts(text, structured) == expected


# ── o sítio ───────────────────────────────────────────────────────────────────────────────


def _site(conversation):
    return ConciergeEffectSite(ToolContext(conversation=conversation, channel_ref=CHANNEL))


def _command(source):
    return SimpleNamespace(action="set_delivery_address", targets=("sess-1",), parameters={"source": source})


def _message(conversation, text="", **envelope):
    from shopman.shop.models import ConversationBinding

    binding = ConversationBinding.objects.filter(conversation=conversation).first() or \
        ConversationBinding.objects.create(
            conversation=conversation, provider="manychat", account="nelson", transport_channel="whatsapp",
            subject="5543999990000", connection_key="manychat-whatsapp-primary",
            status=ConversationBinding.Status.ACTIVE, identity_assurance="transport_subject")
    return ConversationMessage.objects.create(conversation=conversation, binding=binding,
                                              role=ConversationMessage.Role.USER,
                                              kind=ConversationMessage.Kind.INBOUND, text=text, envelope=envelope)


def test_the_site_reads_the_original_text_keeps_the_day_and_returns_only_the_reference(conversation, monkeypatch):
    from shopman.storefront.concierge import tools

    _session(fulfillment_type="delivery", delivery_date="2026-11-24", delivery_time_slot="slot-15")
    message = _message(conversation, "Rua das Flores 120, Centro")
    calls = []
    monkeypatch.setattr(tools, "set_fulfillment", lambda ctx, **kw: calls.append(kw) or {"ok": True})
    done = _site(conversation).apply(CTX, _command(f"message:{message.pk}"))
    assert calls == [{"fulfillment_type": "delivery", "delivery_date": "2026-11-24", "slot_ref": "slot-15",
                      "address": "Rua das Flores 120, Centro"}]
    assert done.applied and dict(done.domain_refs) == {"effect": "sess-1", "cart": "sess-1",
                                                       "address_ref": address_ref("sess-1")}


def test_the_location_pin_is_the_address(conversation, monkeypatch):
    from shopman.storefront.concierge import tools

    _session(fulfillment_type="delivery")
    pin = _message(conversation, message_type="location", location={"latitude": -23.3, "longitude": -51.1})
    calls = []
    monkeypatch.setattr(tools, "set_fulfillment", lambda ctx, **kw: calls.append(kw) or {"ok": True})
    assert shared_location_of(f"message:{pin.pk}") and not shared_location_of("text:Rua")
    assert _site(conversation).apply(CTX, _command(f"message:{pin.pk}")).applied
    assert calls[0]["use_shared_location"] is True


def test_without_delivery_nothing_is_written(conversation, monkeypatch):
    from shopman.storefront.concierge import tools

    _session(fulfillment_type="pickup")
    monkeypatch.setattr(tools, "set_fulfillment", lambda *a, **k: pytest.fail("sem entrega, nada se grava"))
    done = _site(conversation).apply(CTX, _command("text:Rua das Flores 120"))
    assert (done.applied, done.refusal) == (False, ErrorCode.FACT_UNAVAILABLE.value)


@pytest.mark.parametrize(("result", "code"), [
    ({"ok": True, "delivery_out_of_zone": True}, ErrorCode.FULFILLMENT_UNAVAILABLE),
    ({"ok": False, "error": "address_not_located"}, ErrorCode.INVALID_CONTENT),
    ({"ok": True, "code": "saved_address_offer", "message": "..."}, ErrorCode.FACT_UNAVAILABLE),
    ({"ok": False, "error": "validation", "errors": {"delivery_time_slot": "..."}}, ErrorCode.FACT_UNAVAILABLE),
])
def test_an_address_the_house_cannot_deliver_to_is_refused(conversation, monkeypatch, result, code):
    from shopman.storefront.concierge import tools

    _session(fulfillment_type="delivery")
    monkeypatch.setattr(tools, "set_fulfillment", lambda ctx, **kw: result)
    done = _site(conversation).apply(CTX, _command("text:Rua Longe 1"))
    assert (done.applied, done.refusal) == (False, code.value)


def test_delivery_address_is_a_cart_action():
    from shopman.storefront.concierge import effect_site

    assert "set_delivery_address" in effect_site.ACTIONS and "set_delivery_address" in effect_site.CART_ACTIONS
    assert "set_delivery_address" not in effect_site.NEW_CART_ACTIONS  # o endereço vem depois da entrega


# ── o leitor ─────────────────────────────────────────────────────────────────────────────


def test_the_reader_marks_the_address_without_fields(conversation):
    from conversational_commerce.engine.acts import ACTS

    from shopman.storefront.tests.test_concierge_model_reader import FakeAI, _fields, _read

    ai = FakeAI(raw=json.dumps({"acts": [{"act": "give_address", "span": "[endereço omitido]", "product": "",
                                          "qty": 0, "change": "", "day": "", "mode": "", "time": "",
                                          "payment": ""}]}))
    understanding, _ = _read("Rua das Flores 120", ai, allowed=ACTS)
    assert _fields(understanding) == [("give_address", {})]


def test_the_reader_takes_the_location_pin_without_the_ai(conversation):
    from conversational_commerce.engine.acts import ACTS

    from shopman.storefront.concierge.model_reader import NiceReader
    from shopman.storefront.tests.test_concierge_model_reader import FakeAI, _fields, _request

    pin = _message(conversation, message_type="location", location={"latitude": -23.3, "longitude": -51.1})
    ai = FakeAI(error=AssertionError("a localização não vai à IA"))
    request = _request("", ACTS)
    request = type(request)(request=request.request, event_id="evt-1", content_ref=f"message:{pin.pk}",
                            allowed_acts=ACTS)
    understanding, consumption = NiceReader(client=ai, model="m", gate=lambda text: "").interpret(_ctx(), request)
    assert _fields(understanding) == [("give_address", {})] and consumption.calls == 0 and ai.requests == []


# ── o formatador de referência e as frases ───────────────────────────────────────────────


def _say(template_id, formatters, **values):
    text = turn_framework.nice_templates()[template_id].text
    for slot, value in values.items():
        text = text.replace("{" + slot + "}", formatters[slot](value))
    return text


def test_the_address_resolves_only_for_the_conversation_cart(conversation):
    _session(fulfillment_type="delivery", delivery_address=FULL["formatted_address"],
             delivery_address_structured=FULL)
    formatters = turn_framework.nice_formatters(conversation)
    assert _say("set_delivery_address.done", formatters, address=address_ref("sess-1")) == \
        "Combinado: entrega na Rua das Flores, 120."
    with pytest.raises(UnresolvedReference):
        formatters["address"](address_ref("sess-2"))  # a sacola de outra conversa nunca se resolve
    with pytest.raises(UnresolvedReference):
        turn_framework.nice_formatters()["address"](address_ref("sess-1"))  # sem conversa, nada


def test_the_summary_has_the_address_and_the_fee_lines_as_today(conversation):
    _session(fulfillment_type="delivery", delivery_address=FULL["formatted_address"],
             delivery_address_structured=FULL)
    conditions = turn_framework.nice_formatters(conversation)["conditions"]
    text = conditions({"fulfillment_date": "2026-11-24", "delivery_address": address_ref("sess-1"),
                       "delivery_fee": 800, "payment_method": "pix"})
    lines = text.split("\n")
    assert lines[1:] == [FULL["formatted_address"], "Entrega: R$ 8,00", "Pagamento: Pix."]


def test_the_questions_are_today_questions(conversation):
    from shopman.storefront.concierge import address
    from shopman.storefront.concierge.service import copy_message

    formatters = turn_framework.nice_formatters(conversation)
    templates = turn_framework.nice_templates()
    assert templates["present_terms.needs_delivery_address"].text == \
        copy_message("CONCIERGE_CLOSE_ASK_ADDRESS").strip()
    incomplete = {k: v for k, v in FULL.items() if k not in {"street_number", "postal_code"}}
    assert _say("present_terms.needs_delivery_address_details", formatters,
                delivery_address_details=["o número (ou S/N)", "o CEP"]) == \
        address.question(incomplete, from_pin=False)
    assert templates["present_terms.needs_delivery_complement"].text == address.question(FULL, from_pin=False)


def test_the_profile_turns_the_address_on_with_the_order(db):
    from shopman.storefront.concierge import profile

    assert "set_delivery_address" in profile.ORDER_MOVES and profile.LEVEL_OF_MOVE["set_delivery_address"] == "A2"
    assert turn_framework.CLASS_OF_MOVE["set_delivery_address"] == "order"


def test_the_refusals_are_today_phrases(conversation):
    from shopman.storefront.concierge.service import copy_message
    from shopman.storefront.concierge.tools import render_result

    templates = turn_framework.nice_templates()
    out_of_zone = "Esse endereço está fora da nossa área de entrega."  # ``tools.set_fulfillment``, fora da área
    assert templates["set_delivery_address.not_delivered"].text == \
        f"{out_of_zone} {copy_message('CONCIERGE_CLOSE_ASK_ADDRESS').strip()}"
    from shopman.storefront.concierge import tools

    assert out_of_zone in open(tools.__file__, encoding="utf-8").read()
    not_located = render_result("set_fulfillment", {"ok": False, "error": "address_not_located", "message": (
        "Não consegui localizar esse endereço para calcular a entrega. Confira a rua, o número e o bairro, "
        "ou envie sua localização pelo WhatsApp.")})
    assert templates["set_delivery_address.not_located"].text in not_located
