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
from shopman.storefront.concierge.effect_site import ConciergeEffectSite, address_of, address_parts
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


def _ref(cart="sess-1"):
    """A referência do endereço como está gravado agora na sacola."""
    session = Session.objects.filter(session_key=cart).first()
    return address_ref(cart, (session.data if session is not None else None) or {})


def _ctx():
    from conversational_commerce.ports import TrustedContext

    return TrustedContext(tenant="t", environment="test", subject="conversation:1")


#: O quando já dito: estes testes são do endereço (#3482 pôs o dia antes dele, e a janela da entrega depois).
WHEN = {"delivery_date": "2026-11-25", "delivery_time_slot": "slot-15"}


def _missing(**data):
    data = {**WHEN, **data}
    _session(**data)
    fact = ShopmanCommerceRead(channel_ref=CHANNEL, ownership=ConversationOwnership()).requirements(_ctx(), "sess-1")
    return list(fact.value["missing"]), fact.value


# ── o fato do canal: o endereço antes do pagamento ────────────────────────────────────────


def test_delivery_without_address_asks_the_address_before_the_payment(conversation):
    missing, value = _missing(fulfillment_type="delivery")
    assert missing == ["delivery_address", "payment_method"]
    assert list(value["delivery_address"]) == []


def test_who_has_a_saved_address_hears_it_first(conversation, monkeypatch):
    """Decisão do dono (25/09): o endereço cadastrado vem antes de qualquer pergunta. A condição é outra
    (``delivery_address_saved``), com os endereços do cadastro por referência opaca, o padrão primeiro (#3421)."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from shopman.guestman.services import address as address_service

    conversation.customer_ref = "cust-1"
    conversation.save(update_fields=["customer_ref"])
    when = datetime(2026, 11, 1, tzinfo=UTC)
    saved = [SimpleNamespace(pk=3, is_default=False, updated_at=when), SimpleNamespace(pk=8, is_default=True,
                                                                                         updated_at=when)]
    monkeypatch.setattr(address_service, "addresses", lambda ref: saved if ref == "cust-1" else [])
    missing, value = _missing(fulfillment_type="delivery", payment={"method": "pix"})
    assert missing == ["delivery_address_saved"]
    refs = list(value["delivery_address_saved"])
    assert [ref.rsplit(":", 1)[0] for ref in refs] == ["saved-address:sess-1:8", "saved-address:sess-1:3"]
    assert all(len(ref.rsplit(":", 1)[1]) == 16 for ref in refs)  # com o resumo opaco do endereço
    assert "present_terms.needs_delivery_address_saved" in turn_framework.nice_templates()


def test_a_customer_book_that_cannot_be_read_holds_the_close(conversation, monkeypatch):
    """K04: se o cadastro do cliente não se lê, não se sabe se há endereço salvo; o fato é Unknown, nunca "falta"."""
    from conversational_commerce.contracts import Unknown
    from shopman.guestman.services import address as address_service

    conversation.customer_ref = "cust-1"
    conversation.save(update_fields=["customer_ref"])
    monkeypatch.setattr(address_service, "addresses", lambda ref: 1 / 0)
    _session(fulfillment_type="delivery")
    fact = ShopmanCommerceRead(channel_ref=CHANNEL, ownership=ConversationOwnership()).requirements(_ctx(), "sess-1")
    assert isinstance(fact, Unknown)


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


def test_a_complete_address_without_a_window_asks_the_window_of_the_day(conversation):
    """Coordenação, 24/11: a entrega também tem horário (a loja on-line exige a janela). Depois do endereço
    completo, a janela; o fato leva o dia, e a casa diz as janelas no envio."""
    missing, value = _missing(fulfillment_type="delivery", delivery_time_slot="",
                              delivery_address_structured={**FULL, "complement": ""}, payment={"method": "pix"})
    assert missing == ["delivery_window"] and dict(value["delivery_window"]) == {"date": "2026-11-25"}


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
    assert terms.fulfillment.address_ref == _ref()
    conditions = {c.code: c.value for c in terms.conditions}
    assert conditions["delivery_address"] == _ref() and conditions["delivery_fee"] == 800
    assert "Flores" not in json.dumps(terms.to_json() if hasattr(terms, "to_json") else str(terms))


# ── a leitura da casa ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("text", "structured", "expected"), [
    ("Rua das Flores 120, Centro", None, {"address": "Rua das Flores 120, Centro"}),
    ("apto 12", FULL, {"complement": "apto 12"}),
    ("sem complemento", FULL, {"complement": "sem complemento"}),
    # Complemento pendente, mas a fala é outro endereço: endereço novo, nunca complemento.
    ("na verdade é Rua Y, 50", FULL, {"address": "na verdade é Rua Y, 50"}),
    ("Av. Brasil 1200", FULL, {"address": "Av. Brasil 1200"}),
    ("é outro: 86020-120", FULL, {"address": "é outro: 86020-120"}),
    ("casa 2, fundos", FULL, {"complement": "casa 2, fundos"}),
    ("bloco B apto 12", FULL, {"complement": "bloco B apto 12"}),
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
                                                       "address_ref": _ref()}


def test_the_first_delivery_on_a_new_cart_resolves_the_address_said_in_the_same_turn(conversation, monkeypatch):
    """A sacola nasce no turno (a conversa sem ``session_key``): o formatador, montado ANTES dela, resolve o
    endereço gravado pela referência do recibo, porque lê a mesma conversa que o sítio atualizou."""
    from shopman.storefront.concierge import tools

    conversation.session_key = ""
    conversation.save(update_fields=["session_key"])
    conversation._binding = _message(conversation, "oi").binding  # o turno vivo chega com o transporte (service)
    formatters = turn_framework.nice_formatters(conversation)  # como o motor do turno: antes da sacola existir
    site = _site(conversation)
    session = tools._ensure_session(site.tool_context)  # o recebimento do mesmo turno abre a sacola nova
    key = conversation.session_key
    assert key and key != "sess-1"
    tools._set_session_data(site.tool_context, key, {"fulfillment_type": "delivery"})

    def house_writes(ctx, **said):
        tools._set_session_data(ctx, key, {"delivery_address": FULL["formatted_address"],
                                           "delivery_address_structured": FULL})
        return {"ok": True}

    monkeypatch.setattr(tools, "set_fulfillment", house_writes)
    done = site.apply(CTX, SimpleNamespace(action="set_delivery_address", targets=(key,),
                                           parameters={"source": "text:Rua das Flores 120"}))
    assert done.applied and done.domain_refs["address_ref"] == _ref(key) and session.session_key == key
    assert _say("set_delivery_address.done", formatters, address=done.domain_refs["address_ref"]) == \
        "Combinado: entrega na Rua das Flores, 120."


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
    ({"ok": True, "code": "saved_address_offer", "message": "..."}, ErrorCode.PROVIDER_UNAVAILABLE),
    ({"ok": False, "error": "validation", "errors": {"delivery_time_slot": "..."}}, ErrorCode.PROVIDER_UNAVAILABLE),
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


@pytest.mark.parametrize(("pending", "text"), [
    ({k: v for k, v in FULL.items() if k != "neighborhood"}, "Jardim Botânico"),
    (FULL, "apto 12"),
    (FULL, "bloco B apto 12"),
    (FULL, "casa 2, fundos"),
    ({k: v for k, v in FULL.items() if k != "street_number"}, "120"),
])
def test_a_partial_address_answer_never_reaches_the_ai(conversation, pending, text):
    """P17 ao vivo: o redator não mascara o pedaço de endereço; com ele pendente, a fala nem vai à IA."""
    from conversational_commerce.engine.acts import ACTS

    from shopman.storefront.concierge.observation_privacy import redact_observation_text
    from shopman.storefront.tests.test_concierge_model_reader import FakeAI, _fields, _read

    assert redact_observation_text(text).text == text  # o redator sozinho deixaria passar
    _session(fulfillment_type="delivery", delivery_address=pending["formatted_address"],
             delivery_address_structured=pending)
    ai = FakeAI(error=AssertionError("o pedaço de endereço não vai à IA"))
    understanding, consumption = _read(text, ai, allowed=ACTS)
    assert _fields(understanding) == [("give_address", {})] and consumption.calls == 0 and ai.requests == []


@pytest.mark.parametrize("text", ["apto 12, e põe mais um croissant", "apto 12, e quero mais um croissant",
                                  "apto 12, 2 croissants"])
def test_a_mixed_answer_masks_the_address_for_the_ai_and_keeps_the_croissant(conversation, monkeypatch, text):
    """A fala mista com o complemento pendente: a IA lê o trecho de endereço mascarado e o resto inteiro;
    o croissant entra pela sacola, e o executor grava só o trecho de endereço."""
    from conversational_commerce.engine.acts import ACTS
    from shopman.offerman.models import Product

    from shopman.storefront.concierge import tools
    from shopman.storefront.tests.test_concierge_model_reader import FakeAI, _read

    Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=1200, is_published=True, is_sellable=True)
    monkeypatch.setattr(tools, "execute", lambda name, args, ctx: {"ok": True, "items": [
        {"sku": "CROISSANT", "name": "Croissant", "price_q": 1200, "is_available": True}]})
    _session(fulfillment_type="delivery", delivery_address=FULL["formatted_address"], delivery_address_structured=FULL)
    ai = FakeAI([{"act": "give_address", "span": "[endereço omitido]"},
                 {"act": "change_quantity", "span": "mais um croissant", "product": "croissant", "qty": 1,
                  "change": "add"}])
    understanding, consumption = _read(text, ai, allowed=ACTS)
    sent = ai.requests[0]["messages"][0]["content"]  # a fala do cliente, como a IA a lê (sem o prompt do sistema)
    assert consumption.calls == 1 and "[endereço omitido]" in sent
    assert "apto" not in sent and " 12" not in sent  # nada do endereço chega à IA
    assert "croissant" in sent.lower()  # o resto da fala, inteiro
    assert [a.act for a in understanding.acts] == ["give_address", "change_quantity"]
    assert dict(understanding.acts[0].fields) == {}  # o endereço, sem campo: o executor lê pela referência
    assert dict(understanding.acts[1].fields)["item"] == "CROISSANT"  # o croissant entra pela sacola
    assert address_parts(address_of(text), FULL) == {"complement": "apto 12"}  # o executor grava só o endereço


def test_a_pure_address_answer_and_a_pure_order_keep_their_paths(conversation, monkeypatch):
    from conversational_commerce.engine.acts import ACTS

    from shopman.storefront.tests.test_concierge_model_reader import FakeAI, _read

    _session(fulfillment_type="delivery", delivery_address=FULL["formatted_address"], delivery_address_structured=FULL)
    silent = FakeAI(error=AssertionError("o pedaço de endereço não vai à IA"))
    understanding, _ = _read("bloco B, apto 12", silent, allowed=ACTS)
    assert [a.act for a in understanding.acts] == ["give_address"] and silent.requests == []
    order = FakeAI([{"act": "change_quantity", "span": "mais um croissant", "product": "croissant", "qty": 1,
                     "change": "add"}])
    _read("quero mais um croissant", order, allowed=ACTS)
    sent = order.requests[0]["messages"][0]["content"]
    assert "quero mais um croissant" in sent and "[endereço omitido]" not in sent  # nada a mascarar


def test_the_house_reads_only_the_address_clauses():
    from shopman.storefront.concierge.effect_site import masked_for_reading

    assert address_of("Rua das Flores, 120, Centro") == "Rua das Flores, 120, Centro"
    assert address_of("Av. Brasil 1200") == "Av. Brasil 1200"  # o ponto não divide
    assert address_of("apto 12, e põe mais um croissant") == "apto 12"
    assert masked_for_reading("bloco B, apto 12 e quero mais um") == "[endereço omitido] e quero mais um"


@pytest.mark.parametrize("text", ["o do trabalho", "casa da minha mãe", "Clínica Vida"])
def test_the_name_of_a_saved_address_never_reaches_the_ai(conversation, monkeypatch, text):
    """P17: com a oferta do endereço do cadastro no ar, o nome dele não vai à IA; o motor recebe ``give_address``
    sem IA, e o sítio escolhe pela etiqueta, sem depender da IA classificar a fala."""
    from types import SimpleNamespace

    from conversational_commerce.engine.acts import ACTS

    from shopman.storefront.concierge import address
    from shopman.storefront.tests.test_concierge_model_reader import FakeAI, _fields, _read

    monkeypatch.setattr(address, "saved_addresses", lambda ref: [SimpleNamespace(pk=7)])
    _session(fulfillment_type="delivery")
    ai = FakeAI(error=AssertionError("o nome do endereço não vai à IA"))
    understanding, consumption = _read(text, ai, allowed=ACTS)
    assert _fields(understanding) == [("give_address", {})] and ai.requests == []


@pytest.mark.parametrize(("text", "expected"), [
    ("outro", True), ("Quero outro", True), ("outro endereço", True), ("um outro, por favor", True),
    ("quais?", True), ("quais são os meus endereços cadastrados?", True),
    ("não, outro endereço", False), ("outro croissant", False), ("o do trabalho", False), ("sim", False)])
def test_another_to_the_saved_offer_is_read_without_the_ai(conversation, monkeypatch, text, expected):
    from types import SimpleNamespace

    from shopman.storefront.concierge import address
    from shopman.storefront.concierge.model_reader import asks_saved_options

    _session(fulfillment_type="delivery")
    monkeypatch.setattr(address, "saved_addresses", lambda ref: [SimpleNamespace(pk=7), SimpleNamespace(pk=9)])
    assert asks_saved_options(conversation, text) is expected
    monkeypatch.setattr(address, "saved_addresses", lambda ref: [SimpleNamespace(pk=7)])
    assert asks_saved_options(conversation, text) is expected  # um só: o motor diz "esse não" e pede o endereço
    monkeypatch.setattr(address, "saved_addresses", lambda ref: [])
    assert asks_saved_options(conversation, text) is False  # sem cadastro não há oferta


def test_the_list_says_every_offered_address_and_holds_if_one_changed(conversation, monkeypatch):
    from shopman.shop.conversational.commerce_read import saved_address_ref
    from shopman.storefront.concierge import address
    from shopman.storefront.tests.test_concierge_troca_no_turno import _saved

    saved = [_saved(7, "Rua do Cadastro", "10", "Casa", default=True), _saved(9, "Avenida Brasil", "200", "")]
    monkeypatch.setattr(address, "saved_addresses", lambda ref: list(saved))
    refs = [saved_address_ref("sess-1", item) for item in saved]
    formatters = turn_framework.nice_formatters(conversation)
    assert _say("present_terms.needs_delivery_address_saved_options", formatters,
                delivery_address_saved_options=refs) == address.saved_listing(saved)
    saved[1].route, saved[1].formatted_address = "Rua Nova", "Rua Nova, 200"  # mudou depois da oferta
    with pytest.raises(UnresolvedReference):
        formatters["delivery_address_saved_options"](refs)


def test_yes_and_no_to_the_saved_address_offer_are_read_not_taken_as_address(conversation, monkeypatch):
    from types import SimpleNamespace

    from shopman.storefront.concierge import address
    from shopman.storefront.concierge.model_reader import address_answer

    monkeypatch.setattr(address, "saved_addresses", lambda ref: [SimpleNamespace(pk=7)])
    _session(fulfillment_type="delivery")
    for said in ("sim", "pode ser", "esse mesmo", "não"):
        assert not address_answer(conversation, said), said


@pytest.mark.parametrize("text", ["obrigada", "não, deixa pra lá", "pode fechar", "vou pagar no pix",
                                  "quero mais 1 pão", "prefiro retirar"])
def test_with_an_address_detail_pending_other_talk_is_not_an_address(conversation, text):
    from shopman.storefront.concierge.model_reader import address_answer

    _session(fulfillment_type="delivery", delivery_address=FULL["formatted_address"], delivery_address_structured=FULL)
    assert not address_answer(conversation, text)


def test_without_a_pending_detail_nothing_is_taken_as_address(conversation):
    from shopman.storefront.concierge.model_reader import address_answer

    _session(fulfillment_type="pickup")
    assert not address_answer(conversation, "Jardim Botânico")


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
    assert _say("set_delivery_address.done", formatters, address=_ref()) == \
        "Combinado: entrega na Rua das Flores, 120."
    with pytest.raises(UnresolvedReference):
        formatters["address"](_ref("sess-2"))  # a sacola de outra conversa nunca se resolve
    with pytest.raises(UnresolvedReference):
        turn_framework.nice_formatters()["address"](_ref())  # sem conversa, nada


def test_a_reference_to_an_address_that_changed_never_says_the_new_one(conversation):
    """O recibo e o resumo dizem o endereço CONFIRMADO: mudado o endereço, a referência velha segura."""
    _session(fulfillment_type="delivery", delivery_address=FULL["formatted_address"],
             delivery_address_structured=FULL)
    confirmed = _ref()
    other = {**FULL, "route": "Rua Y", "street_number": "50", "formatted_address": "Rua Y, 50 - Centro"}
    Session.objects.filter(session_key="sess-1").update(data={
        "fulfillment_type": "delivery", "delivery_address": other["formatted_address"],
        "delivery_address_structured": other})
    assert _ref() != confirmed
    formatters = turn_framework.nice_formatters(conversation)
    with pytest.raises(UnresolvedReference):
        formatters["address"](confirmed)
    assert _say("set_delivery_address.done", formatters, address=_ref()) == "Combinado: entrega na Rua Y, 50."


def test_the_summary_has_the_address_and_the_fee_lines_as_today(conversation):
    _session(fulfillment_type="delivery", delivery_address=FULL["formatted_address"],
             delivery_address_structured=FULL)
    conditions = turn_framework.nice_formatters(conversation)["conditions"]
    text = conditions({"fulfillment_date": "2026-11-24", "delivery_address": _ref(),
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
    # Endereço sem entrega combinada: a pergunta de hoje do fechamento, "retirada ou entrega?".
    assert templates["set_delivery_address.ask_mode"].text == copy_message("CONCIERGE_CLOSE_ASK_FULFILLMENT").strip()
