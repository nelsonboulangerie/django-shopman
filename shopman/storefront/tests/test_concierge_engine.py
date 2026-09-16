"""O motor do concierge: ferramentas, laço do agente e o turno completo.

Três desenhos protegidos aqui:

1. **O dinheiro é do código.** ``set_item`` reserva estoque de verdade e devolve o
   saldo real quando falta; ``review_order`` fecha o orçamento com um token;
   ``place_order`` recusa token velho e cria o pedido no canal do concierge com o
   Pix vindo do adapter, numa mensagem separada. Nada disso passa pelo modelo.
2. **O laço não conhece rede.** ``run_agent`` recebe um cliente com roteiro e devolve
   a transcrição no formato da API, com as ferramentas executadas no meio.
3. **O turno responde sempre.** Mídia, teto diário, handoff e o modelo fora do ar
   viram copy da casa e ficam na transcrição; a resposta sai pelo transporte.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.orderman.models import Directive, Order, Session

from shopman.shop.models import Channel, Conversation, ConversationBinding, ConversationMessage, FAQEntry, Shop
from shopman.storefront.concierge import agent as agent_module
from shopman.storefront.concierge import service, tools
from shopman.storefront.concierge.contracts import (
    ChannelCapabilities,
    HandoffOutcome,
    InboundEvent,
    ResponseAuthorization,
    SendOutcome,
    TransportScope,
    WindowEvidence,
)
from shopman.storefront.concierge.handoff import classify_handoff_request
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CHANNEL = "whatsapp"
SKU = "PAO-FRANCES"
PHONE = "+5543984049009"
ADAPTER_PATH = "shopman.storefront.tests.test_concierge_engine.CommercialTestAdapter"
CONNECTION_KEY = "commercial-test"
PROVIDER = "provider-test"
ACCOUNT = "test-account"
SUBJECT = "1962036908"


class CommercialTestAdapter:
    """Transporte hermético: os testes comerciais não acessam rede externa."""

    def __init__(self, *, connection):
        self.connection = connection
        self.provider = connection.provider
        self.channel = connection.channel
        self.capabilities = ChannelCapabilities(
            max_text_chars=4000,
            response_window=timedelta(hours=24),
            stable_event_identity_verified=True,
            supports_handoff=True,
        )

    def send_text(self, subject, text):
        return SendOutcome("accepted", "accepted", f"test:{subject}:{hash(text)}")

    def set_handoff(self, subject, on):
        return HandoffOutcome("accepted", "accepted", f"handoff:{subject}:{on}")

    def identify(self, subject, profile):
        return None

    def window_evidence(self, envelope, now):
        return WindowEvidence.from_value(envelope.get("window_evidence"))

    def authorize_response(self, evidence, now, *, purpose):
        evidence = WindowEvidence.from_value(evidence)
        allowed = bool(evidence and evidence.valid_until > now)
        return ResponseAuthorization(
            allowed,
            "test_window" if allowed else "window_closed",
            evidence.valid_until if evidence else None,
        )


CONCIERGE_SETTINGS = {
    "contract_version": 3,
    "suggest_add_ons": True,
    "enabled": True,
    "model": "claude-sonnet-5",
    "effort": "low",
    "max_tokens": 512,
    "channel_ref": CHANNEL,
    "window_messages": 40,
    "max_turns_per_day": 80,
    "max_iterations": 6,
    "dispatch_delay_seconds": 1,
    "connections": {
        CONNECTION_KEY: {
            "active": True,
            "provider": PROVIDER,
            "account": ACCOUNT,
            "channel": CHANNEL,
            "adapter_path": ADAPTER_PATH,
            "options": {
                "allowed_subjects": [SUBJECT],
                "stable_event_identity_verified": True,
            },
        }
    },
}


# ── Cenário ──────────────────────────────────────────────────────────


def _seed_stock(sku: str, qty: Decimal) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=qty, sku=sku, position=position, target_date=date.today(), reason="concierge test")


@pytest.fixture
def surface():
    # TransactionTestCase faz flush dos dados semeados pelas migrations.
    from importlib import import_module
    seed = import_module("shopman.shop.migrations.0028_seed_attribute_definitions")
    for definition in seed.DEFINITIONS:
        from shopman.shop.models import AttributeDefinition
        AttributeDefinition.objects.get_or_create(ref=definition["ref"], defaults={k: v for k, v in definition.items() if k != "ref"})
    Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        short_name="Nelson",
        phone="554333231997",
        defaults={
            "pickup_slots": [
                {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
                {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
                {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
            ]
        },
    )
    Channel.objects.create(ref="web", name="Loja online")
    Channel.objects.create(
        ref=CHANNEL,
        name="WhatsApp",
        config={
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5},
            "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
            "notifications": {"backend": "manychat"},
            "stock": {"hold_ttl_minutes": 30, "allow_untracked": False},
        },
    )
    collection = Collection.objects.create(name="Pães", ref="paes", is_active=True, sort_order=1)
    product = Product.objects.create(
        sku=SKU, name="Pão Francês", base_price_q=90, is_published=True, is_sellable=True
    )
    CollectionItem.objects.create(collection=collection, product=product, sort_order=1)
    for ref, name in (("web", "Loja online"), (CHANNEL, "WhatsApp")):
        listing = Listing.objects.create(ref=ref, name=name, is_active=True, priority=5)
        ListingItem.objects.create(listing=listing, product=product, price_q=90, is_published=True, is_sellable=True)
    _seed_stock(SKU, Decimal("10"))
    return product


@pytest.fixture
def customer():
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    return customer_service.create(
        ref=Customer.generate_ref(), first_name="Ana", phone=PHONE, source_system="test"
    )


@pytest.fixture
def conversation(surface, customer, settings):
    settings.AI_ASSIST_API_KEY = "isolated-fixture"
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    conversation = Conversation.objects.create(
        phone=PHONE,
        customer_name="Ana",
        customer_ref=customer.ref,
        channel_ref=CHANNEL,
    )
    ConversationBinding.objects.create(
        conversation=conversation,
        provider=PROVIDER,
        account=ACCOUNT,
        transport_channel=CHANNEL,
        subject=SUBJECT,
        connection_key=CONNECTION_KEY,
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance="verified_customer",
        activated_at=timezone.now(),
    )
    return conversation


@pytest.fixture
def ctx(conversation, settings):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    settings.AI_ASSIST_API_KEY = "isolated-fixture"
    context = ToolContext(conversation=conversation, channel_ref=CHANNEL)
    _create_inbound(conversation, "autoridade da fixture", "fixture-authority")
    _reclaim(context)
    return context


@pytest.fixture
def outbox(monkeypatch):
    sent: list[str] = []
    flags: list[bool] = []

    def send(binding, text):
        sent.append(text)
        return SendOutcome("accepted", "accepted", f"test:{binding.subject}:{len(sent)}")

    def handoff(binding, on):
        flags.append(on)
        return HandoffOutcome("accepted", "accepted", f"handoff:{binding.subject}:{on}")

    monkeypatch.setattr("shopman.storefront.concierge.transport.send_for", send)
    monkeypatch.setattr("shopman.storefront.concierge.transport.handoff_for", handoff)
    return SimpleNamespace(sent=sent, flags=flags)


def _binding(conversation: Conversation) -> ConversationBinding:
    return ConversationBinding.objects.get(conversation=conversation)


def _event(
    *,
    text: str,
    event_id: str,
    subject: str = SUBJECT,
    profile: dict | None = None,
    occurred_at=None,
    message_type="text",
) -> InboundEvent:
    now = timezone.now()
    occurred_at = occurred_at or now
    return InboundEvent(
        scope=TransportScope(
            provider=PROVIDER,
            account=ACCOUNT,
            channel=CHANNEL,
            subject=subject,
            connection_key=CONNECTION_KEY,
        ),
        text=text,
        message_type=message_type,
        received_at=now,
        event_id=event_id,
        event_identity_assurance="verified",
        occurred_at=occurred_at,
        occurred_at_assurance="verified",
        profile=profile or {},
        authentication_assurance="test",
        payload_hash=f"hash:{event_id}:{text}",
        window_evidence=WindowEvidence(
            policy="commercial-test-v1",
            source="authenticated-test-event",
            observed_at=now,
            valid_until=now + timedelta(hours=24),
            assurance="provider_window",
        ),
    )


def _receive(conversation: Conversation, text: str, event_id: str, *, message_type="text"):
    return service.receive_inbound(
        _event(
            text=text,
            event_id=event_id,
            subject=_binding(conversation).subject,
            message_type=message_type,
        )
    )


def _create_inbound(
    conversation: Conversation,
    text: str,
    event_id: str,
    *,
    occurred_at=None,
) -> ConversationMessage:
    event = _event(text=text, event_id=event_id, occurred_at=occurred_at)
    return ConversationMessage.objects.create(
        conversation=conversation,
        binding=_binding(conversation),
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text=text,
        content=[{"type": "text", "text": text}],
        external_id=service._external_id(event_id),
        envelope={**event.as_envelope(), "input_assurance": "provider_event"},
    )


def _reclaim(ctx: ToolContext) -> None:
    ctx.conversation = _claim_conversation(ctx.conversation)


def _claim_conversation(conversation: Conversation) -> Conversation:
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=None)
    claimed, _claimed_binding, inbound = service._claim(
        conversation.pk, _binding(conversation).pk
    )
    assert inbound
    return claimed


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def _pickup_ready(ctx) -> dict:
    """Sacola com 2 pães, retirada amanhã ao meio-dia: pronta para orçar."""
    assert tools.set_item(ctx, SKU, 2)["ok"]
    result = tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-12", "")
    assert result["ok"], result
    return tools.review_order(ctx, "pix")


def _accept_review(ctx, review, *, confirm=True):
    ConversationMessage.objects.create(conversation=ctx.conversation, binding=_binding(ctx.conversation), role="assistant", kind="reply",
        text=tools.render_result("review_order", review), transport_state="accepted",
        envelope={"quote_token": review["quote_token"]})
    if confirm:
        _create_inbound(
            ctx.conversation,
            "confirmo",
            f"confirm-{ConversationMessage.objects.count()}",
        )
        _reclaim(ctx)


# ── Cliente com roteiro ──────────────────────────────────────────────


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool(name: str, arguments: dict, call_id: str = "toolu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=arguments)


def _response(*blocks, stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=100, output_tokens=20, cache_read_input_tokens=50, cache_creation_input_tokens=0
        ),
    )


class ScriptedClient:
    """Devolve as respostas do roteiro em ordem e guarda cada request."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # Cópia rasa da lista: o laço continua anexando ao mesmo objeto depois.
        self.requests.append({**kwargs, "messages": list(kwargs.get("messages") or [])})
        if not self._responses:
            raise AssertionError("roteiro esgotado")
        return self._responses.pop(0)


# ── Ferramentas ──────────────────────────────────────────────────────


def test_search_storefront_reads_price_and_availability_from_the_listing(ctx):
    result = tools.search_storefront(ctx, "pao")
    assert result["ok"] and result["count"] == 1
    item = result["items"][0]
    assert item["sku"] == SKU
    assert item["price"] == "R$ 0,90"
    assert item["can_order"] is True
    assert item["available_qty"] == 10


def test_search_storefront_generic_menu_question_is_an_overview_by_collection(ctx):
    result = tools.search_storefront(ctx, "o que tem disponível?")
    assert result["overview"] is True and result["available_count"] == 1
    assert [c["ref"] for c in result["collections"]] == ["paes"]
    assert result["collections"][0]["available_count"] == 1
    assert result["collections"][0]["examples"][0]["sku"] == SKU


def test_search_storefront_finds_a_collection_and_does_not_dump_menu_on_no_match(ctx):
    by_label = tools.search_storefront(ctx, "quais pães vocês têm?")
    assert by_label["count"] == 1 and by_label["items"][0]["sku"] == SKU
    unknown = tools.search_storefront(ctx, "vocês vendem bicicletas?")
    assert unknown["code"] == "no_match" and unknown["items"] == []


def test_search_storefront_uses_the_public_storefront_projection(ctx):
    shop = Shop.load()
    shop.formatted_address = "Av. Madre Leônia Milito, 446 - Londrina - PR"
    shop.email = "oi@nelsonboulangerie.com.br"
    shop.save()
    FAQEntry.objects.create(
        question="Tem opção vegana?",
        answer="As opções variam; consulte o cardápio do dia.",
        search_terms="sem ingredientes animais, plant based",
        is_published=True,
    )

    delivery = tools.search_storefront(ctx, "vocês entregam?")
    location = tools.search_storefront(ctx, "onde vocês ficam?")
    faq = tools.search_storefront(ctx, "plant based")

    assert delivery["ok"] and "Fazemos entrega" in delivery["answers"][0]["answer"]
    assert location["answers"][0]["answer"].endswith("Londrina - PR.")
    assert location["links"][0]["url"].startswith("https://www.google.com/maps/")
    assert faq["answers"] == [
        {
            "ref": "curated-tem-opcao-vegana",
            "question": "Tem opção vegana?",
            "answer": "As opções variam; consulte o cardápio do dia.",
        }
    ]


def test_search_storefront_is_the_only_public_read_contract(ctx):
    names = set(tools.TOOL_NAMES)
    assert "search_storefront" in names
    assert not names.intersection({"browse_menu", "store_info"})
    schema = next(spec["input_schema"] for spec in tools.TOOL_SPECS if spec["name"] == "search_storefront")
    assert set(schema["properties"]) == {"query"}
    assert schema["required"] == []


def test_search_storefront_keeps_public_answers_when_catalog_is_unavailable(ctx, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("isolated catalog failure")

    monkeypatch.setattr("shopman.storefront.presentation.catalog.build_catalog", unavailable)
    result = tools.search_storefront(ctx, "vocês entregam?")

    assert result["ok"] is True
    assert result["code"] == "partial_results"
    assert "Fazemos entrega" in result["answers"][0]["answer"]
    assert result["items"] == []
    assert result["issues"] == [{"source": "catalog", "code": "unavailable"}]


def test_search_storefront_uses_the_channel_fulfillment_policy(ctx):
    channel = Channel.objects.get(ref=CHANNEL)
    channel.config = {
        **channel.config,
        "surface_policy": {"fulfillment_types": ["pickup"]},
    }
    channel.save()

    result = tools.search_storefront(ctx, "vocês entregam?")

    assert result["answers"][0]["ref"] == "delivery"
    assert "retirada na loja" in result["answers"][0]["answer"]
    assert "Fazemos entrega" not in result["answers"][0]["answer"]


def test_fulfillment_tools_obey_the_canonical_channel_policy(ctx):
    channel = Channel.objects.get(ref=CHANNEL)
    channel.config = {
        **channel.config,
        "surface_policy": {"fulfillment_types": ["pickup"]},
    }
    channel.save()

    slots = tools.list_fulfillment_slots(ctx, _tomorrow(), "delivery")
    selected = tools.set_fulfillment(ctx, "delivery", _tomorrow(), "", "Rua das Flores, 10")

    assert slots["error"] == "fulfillment_unavailable"
    assert selected["error"] == "fulfillment_unavailable"


def test_set_item_reserves_stock_and_tells_the_real_balance(ctx, conversation):
    ok = tools.set_item(ctx, SKU, 3)
    assert ok["ok"] and ok["lines"][0]["qty"] == 3
    conversation.refresh_from_db()
    session = Session.objects.get(session_key=conversation.session_key)
    assert session.channel_ref == CHANNEL
    assert session.data["origin_channel"] == "whatsapp"
    assert session.data["concierge"] == {"conversation_id": conversation.pk}
    assert session.handle_ref == PHONE

    short = tools.set_item(ctx, SKU, 20)
    assert short["ok"] is False
    assert short["error"] == "insufficient_stock"
    assert short["available_qty"] == 10

    removed = tools.set_item(ctx, SKU, 0)
    assert removed["ok"] and removed["empty"]


def test_set_item_rejects_unknown_sku(ctx):
    result = tools.set_item(ctx, "NAO-EXISTE", 1)
    assert result["error"] == "unknown_sku"


def test_review_order_names_what_is_missing_before_issuing_a_quote(ctx, conversation):
    assert tools.review_order(ctx)["missing"] == ["items"]
    tools.set_item(ctx, SKU, 1)
    review = tools.review_order(ctx)
    assert review["ready"] is False
    assert "fulfillment_type" in review["missing"]
    assert "quote_token" not in review
    conversation.refresh_from_db()
    assert conversation.quote == {}


def test_place_order_creates_the_order_and_sends_the_pix_apart(ctx, conversation, django_capture_on_commit_callbacks):
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    assert review["ready"], review
    assert review["payment_methods"][0]["ref"] == "pix"
    token = review["quote_token"]

    # O Pix nasce no `on_commit` do lifecycle (timing at_commit); no worker isso
    # roda logo após o COMMIT do checkout, antes de a ferramenta reler o pedido.
    with django_capture_on_commit_callbacks(execute=True):
        placed = tools.place_order(ctx, token, "pix", "")
    assert placed["ok"], placed
    order = Order.objects.get(ref=placed["order_ref"])
    assert order.channel_ref == CHANNEL
    assert order.data["origin_channel"] == "whatsapp"
    assert order.data["fulfillment_type"] == "pickup"
    assert order.data["delivery_time_slot"] == "slot-12"
    assert order.data["customer"]["phone"] == PHONE
    assert order.data["payment"]["method"] == "pix"
    # O Pix nasce no commit (timing at_commit) e vai numa mensagem separada.
    # TestCase contém um outer atomic: callback só executa após o retorno da tool.
    # Consulta pura recupera o pagamento já criado pelo callback, sem iniciar outro.
    recovered = tools.place_order(ctx, token, "pix", "")
    assert recovered["payment"]["pix_code_prepared_separately"] is True
    assert ctx.extra_replies == [order.data["payment"]["copy_paste"]]
    assert placed["tracking_url"].endswith(f"/pedido/{order.ref}/")

    conversation.refresh_from_db()
    assert conversation.session_key == "" and conversation.quote["token"] == token


def test_the_add_on_suggestion_is_offered_once_per_conversation(ctx, conversation, monkeypatch):
    from types import SimpleNamespace as NS

    from shopman.shop.projections import cart as cart_projection

    original = cart_projection.build_cart

    def with_upsell(session_key, channel_ref="web"):
        cart = original(session_key, channel_ref)
        return type(cart)(**{**cart.__dict__, "upsell": NS(sku="CAFE", name="Café", price_display="R$ 8,00")})

    monkeypatch.setattr("shopman.shop.projections.cart.build_cart", with_upsell)
    tools.set_item(ctx, SKU, 1)
    tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-12", "")

    # LIGADA por padrão desde a F1 do WP-SUGESTÃO: quem escolhe agora é o motor
    # de sugestão (co-ocorrência + pareamentos configuráveis), e não mais "o
    # item mais popular que não está na sacola" — a regra cega ao contexto que
    # ofereceu Água a quem levava pão.
    first = tools.review_order(ctx)
    assert first["suggestion"]["name"] == "Café"

    # E uma por conversa: o segundo recap não repete a oferta.
    conversation.refresh_from_db()
    assert conversation.flags == {"suggestion_offered": True}
    second = tools.review_order(ctx)
    assert "suggestion" not in second


def test_the_add_on_suggestion_can_still_be_turned_off_by_env(ctx, conversation, monkeypatch):
    from types import SimpleNamespace as NS

    from shopman.shop.projections import cart as cart_projection

    original = cart_projection.build_cart

    def with_upsell(session_key, channel_ref="web"):
        cart = original(session_key, channel_ref)
        return type(cart)(**{**cart.__dict__, "upsell": NS(sku="CAFE", name="Café", price_display="R$ 8,00")})

    monkeypatch.setattr("shopman.shop.projections.cart.build_cart", with_upsell)
    monkeypatch.setitem(settings.SHOPMAN_CONCIERGE, "suggest_add_ons", False)
    tools.set_item(ctx, SKU, 1)
    tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-12", "")

    assert "suggestion" not in tools.review_order(ctx)


def test_place_order_refuses_a_stale_quote(ctx):
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    token = review["quote_token"]
    tools.set_item(ctx, SKU, 3)  # a sacola mudou depois do orçamento
    refused = tools.place_order(ctx, token, "pix", "")
    assert refused["ok"] is False and refused["error"] == "revision_conflict"
    assert not Order.objects.exists()


def test_place_order_refuses_a_payment_method_the_channel_does_not_offer(ctx):
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    refused = tools.place_order(ctx, review["quote_token"], "cash", "")
    assert refused["error"] == "invalid_payment_method"


def test_set_fulfillment_validates_the_slot_like_the_site(ctx):
    tools.set_item(ctx, SKU, 1)
    bad = tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-99", "")
    assert bad["ok"] is False and "delivery_time_slot" in bad["errors"]
    open_slots = tools.set_fulfillment(ctx, "pickup", _tomorrow(), "", "")
    assert open_slots["ok"] and open_slots["pickup_slots"]


def test_set_fulfillment_refuses_delivery_without_coordinates(ctx, monkeypatch):
    """Sem coordenada não há taxa honesta: falha fechado, aponta retirada ou o site."""
    tools.set_item(ctx, SKU, 1)
    monkeypatch.setattr("shopman.shop.services.geocoding.forward_geocode", lambda address: None)
    refused = tools.set_fulfillment(ctx, "delivery", _tomorrow(), "", "Rua das Flores, 10")
    assert refused["ok"] is False and refused["error"] == "address_not_located"
    assert tools.view_cart(ctx)["fulfillment"]["type"] == ""


def test_set_fulfillment_delivery_stores_the_located_address(ctx, monkeypatch):
    tools.set_item(ctx, SKU, 1)
    monkeypatch.setattr("shopman.shop.services.geocoding.forward_geocode", lambda address: (-23.31, -51.16))
    result = tools.set_fulfillment(ctx, "delivery", _tomorrow(), "", "Rua das Flores, 10, Centro")
    assert result["ok"], result
    assert result["fulfillment"]["type"] == "delivery"
    assert result["fulfillment"]["address"] == "Rua das Flores, 10, Centro"
    session = Session.objects.get(session_key=ctx.conversation.session_key)
    assert session.data["delivery_address_structured"]["latitude"] == -23.31


def test_order_status_reads_the_customer_orders_through_the_projection(ctx, django_capture_on_commit_callbacks):
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    with django_capture_on_commit_callbacks(execute=True):
        placed = tools.place_order(ctx, review["quote_token"], "pix", "")
    status = tools.order_status(ctx, "")
    assert status["orders"][0]["order_ref"] == placed["order_ref"]
    assert status["orders"][0]["needs_payment"] is True
    assert tools.order_status(ctx, "XYZ-000")["orders"] == []


@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "transfer_enabled": True}, AI_ASSIST_API_KEY="fixture")
def test_send_web_link_carries_the_cart_to_the_store_channel(ctx, conversation, monkeypatch):
    tools.set_item(ctx, SKU, 2)
    chat_key = Conversation.objects.get(pk=conversation.pk).session_key

    captured: dict = {}

    def fake_create_token(info, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(success=True, url="https://loja.exemplo/a?t=abc", expires_at="2026-09-03T10:00:00")

    monkeypatch.setattr("shopman.doorman.services.access_link.AccessLinkService.create_token", fake_create_token)

    result = tools.send_web_link(ctx, "checkout")
    assert result["ok"] and result["logged_in"] and result["cart_carried"]
    web_key = captured["metadata"]["cart_session_key"]
    web_session = Session.objects.get(session_key=web_key)
    assert web_session.channel_ref == "web"
    assert web_session.items[0]["sku"] == SKU and int(Decimal(str(web_session.items[0]["qty"]))) == 2
    assert Session.objects.get(session_key=chat_key).state == "abandoned"
    assert captured["metadata"]["next"] == "/finalizar"


def test_notify_when_available_subscribes_the_same_alert_as_the_site(ctx, conversation):
    """UMA assinatura, no eixo que o produto pede — igual ao sino do site.

    Assinava os dois "por garantia", e o preço era mensagem dobrada quando o
    produto tinha os dois gatilhos vivos no mesmo instante.
    """
    from shopman.storefront.models import StockAlertSubscription

    offer = tools.notify_when_available(ctx, SKU)
    ConversationMessage.objects.create(
        conversation=conversation,
        binding=_binding(conversation),
        role="assistant",
        kind="reply",
        transport_state="accepted",
        envelope={"disclosure": offer["disclosure"]},
    )
    _create_inbound(conversation, "aceito", "consent")
    _reclaim(ctx)
    result = tools.notify_when_available(ctx, SKU)
    assert result["ok"], result
    subs = StockAlertSubscription.objects.filter(sku=SKU, customer_ref=conversation.customer_ref)
    assert list(subs.values_list("alert_type", flat=True)) == ["stock_back"]
    # Idempotente: pedir de novo não duplica.
    tools.notify_when_available(ctx, SKU)
    assert subs.count() == 1
    assert tools.notify_when_available(ctx, "NAO-EXISTE")["error"] == "unknown_sku"


def test_the_pending_quote_token_is_visible_in_the_system_prompt(ctx, conversation):
    """O resultado antigo volta resumido; sem o token à vista o modelo o inventava."""
    from shopman.storefront.concierge import prompt as prompt_module

    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    conversation.refresh_from_db()
    system = prompt_module.build_system(conversation, is_first_turn=False, cart_summary="")
    dynamic = system[1]["text"]
    assert f"quote_token: {review['quote_token']}" in dynamic


def test_send_web_link_for_a_placed_order_points_at_the_tracking_page(
    ctx, conversation, django_capture_on_commit_callbacks
):
    """Pagar pedido feito é no acompanhamento; o checkout ficaria vazio (o "link quebrado")."""
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    with django_capture_on_commit_callbacks(execute=True):
        placed = tools.place_order(ctx, review["quote_token"], "pix", "")

    assert tools.send_web_link(ctx, "order")["error"] == "target_required"
    by_order = tools.send_web_link(ctx, "order", placed["order_ref"])
    assert by_order["order_ref"] == placed["order_ref"]
    assert by_order["url"]
    # Link tem alvo autorizado explícito; checkout não escolhe pedido implicitamente.
    assert tools.send_web_link(ctx, "checkout")["error"] == "transfer_disabled"


def test_execute_never_raises(ctx):
    assert tools.execute("nao_existe", {}, ctx)["error"] == "unknown_tool"
    assert tools.execute("set_item", {"sku": SKU}, ctx)["error"] == "invalid_input"


# ── Laço do agente ───────────────────────────────────────────────────


def test_run_agent_executes_tools_and_keeps_the_transcript_in_api_format(conversation):
    _create_inbound(conversation, "tem pão francês?", "agent-menu")
    conversation = _claim_conversation(conversation)
    client = ScriptedClient(
        _response(_tool("search_storefront", {"query": "pão"}), stop_reason="tool_use"),
        _response(_text("Temos sim. Quantos você quer?"), stop_reason="end_turn"),
    )
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )

    assert "R$ 0,90" in outcome.reply_text and "Pão Francês" in outcome.reply_text
    assert [m["role"] for m in outcome.messages] == ["assistant", "user", "assistant"]
    tool_result = outcome.messages[1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "toolu_1"
    assert json.loads(tool_result["content"])["items"][0]["sku"] == SKU
    assert outcome.tool_events == [{"name": "search_storefront", "input": {"query": "pão"}, "ok": True}]
    assert outcome.usage["input_tokens"] == 200 and outcome.usage["cache_read_input_tokens"] == 100

    first = client.requests[0]
    assert first["model"] == "claude-sonnet-5"
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Nelson Boulangerie" in first["system"][0]["text"]
    assert first["output_config"] == {"effort": "low"}
    assert first["thinking"] == {"type": "adaptive"}
    assert first["cache_control"] == {"type": "ephemeral"}
    assert [t["name"] for t in first["tools"]] == list(tools.TOOL_NAMES)
    # Sem `strict` e só o obrigatório em `required`: parâmetro que o modelo quer
    # omitir não pode virar string preenchida com sintaxe interna.
    assert all("strict" not in t for t in first["tools"])
    search = next(t for t in first["tools"] if t["name"] == "search_storefront")
    assert search["input_schema"]["required"] == []
    # A segunda ida leva a chamada e o resultado da ferramenta de volta.
    assert client.requests[1]["messages"][-1]["content"][0]["type"] == "tool_result"


def test_run_agent_answers_product_and_delivery_in_the_same_turn(conversation):
    """Regressão do piloto: "pain perdu, vocês entregam?" precisa dos dois fatos."""
    product = Product.objects.create(
        sku="PAIN-PERDU",
        name="Pain Perdu",
        base_price_q=1800,
        is_published=True,
        is_sellable=True,
    )
    CollectionItem.objects.create(
        collection=Collection.objects.get(ref="paes"),
        product=product,
        sort_order=2,
    )
    ListingItem.objects.create(
        listing=Listing.objects.get(ref=CHANNEL),
        product=product,
        price_q=1800,
        is_published=True,
        is_sellable=True,
    )
    _seed_stock(product.sku, Decimal("4"))
    _create_inbound(
        conversation,
        "vou querer um pain perdu, vcs entregam?",
        "agent-product-delivery",
    )
    conversation = _claim_conversation(conversation)
    conversation._limited_event_assurance = True
    conversation._commercial_authority = False
    client = ScriptedClient(
        # Reproduz a falha live: o modelo reduziu a pergunta a "entrega".
        # A fala original imutável no ToolContext preserva também Pain Perdu.
        _response(
            _tool("search_storefront", {"query": "entrega"}, "toolu_public"),
            stop_reason="tool_use",
        ),
        _response(_text("Temos sim. Quantos você quer?"), stop_reason="end_turn"),
    )

    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation,
            history=agent_module.history_for(conversation),
            client=client,
        )

    assert "Pain Perdu" in outcome.reply_text
    assert "R$ 18,00" in outcome.reply_text
    assert "Fazemos entrega" in outcome.reply_text
    assert outcome.tool_events == [
        {"name": "search_storefront", "input": {"query": "entrega"}, "ok": True}
    ]
    assert not Session.objects.exists()


def test_run_agent_reconciles_public_facts_when_model_skips_tools(conversation):
    product = Product.objects.create(
        sku="PAIN-PERDU-FALLBACK",
        name="Pain Perdu",
        base_price_q=1800,
        is_published=True,
        is_sellable=True,
    )
    CollectionItem.objects.create(
        collection=Collection.objects.get(ref="paes"),
        product=product,
        sort_order=2,
    )
    ListingItem.objects.create(
        listing=Listing.objects.get(ref=CHANNEL),
        product=product,
        price_q=1800,
        is_published=True,
        is_sellable=True,
    )
    _seed_stock(product.sku, Decimal("4"))
    _create_inbound(
        conversation,
        "vou querer um pain perdu, vcs entregam?",
        "agent-public-reconciliation",
    )
    conversation = _claim_conversation(conversation)
    conversation._limited_event_assurance = True
    conversation._commercial_authority = False
    client = ScriptedClient(
        _response(_text("Claro!"), stop_reason="end_turn"),
    )

    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation,
            history=agent_module.history_for(conversation),
            client=client,
        )

    assert "Pain Perdu" in outcome.reply_text
    assert "R$ 18,00" in outcome.reply_text
    assert "Fazemos entrega" in outcome.reply_text
    assert outcome.tool_events == [{"name": "search_storefront", "input": {}, "ok": True}]
    assert not Session.objects.exists()


def test_run_agent_refuses_unfounded_handoff_and_answers_public_facts(conversation):
    """Outra consulta do modelo não pode apagar os fatos públicos da pergunta."""
    product = Product.objects.create(
        sku="PAIN-PERDU-HANDOFF", name="Pain Perdu", base_price_q=1800,
        is_published=True, is_sellable=True,
    )
    CollectionItem.objects.create(
        collection=Collection.objects.get(ref="paes"), product=product, sort_order=2,
    )
    ListingItem.objects.create(
        listing=Listing.objects.get(ref=CHANNEL), product=product, price_q=1800,
        is_published=True, is_sellable=True,
    )
    _seed_stock(product.sku, Decimal("4"))
    _create_inbound(
        conversation, "vou querer um pain perdu, vcs entregam?", "agent-unfounded-handoff",
    )
    conversation = _claim_conversation(conversation)
    conversation._limited_event_assurance = True
    conversation._commercial_authority = False
    client = ScriptedClient(
        _response(
            _tool("view_cart", {}, "toolu_irrelevant_cart"),
            stop_reason="tool_use",
        ),
        _response(_text("Vou verificar."), stop_reason="end_turn"),
    )

    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client,
        )

    assert not outcome.handoff
    assert "Pain Perdu" in outcome.reply_text
    assert "R$ 18,00" in outcome.reply_text
    assert "Fazemos entrega" in outcome.reply_text
    assert [event["name"] for event in outcome.tool_events] == [
        "view_cart", "search_storefront",
    ]
    assert not Session.objects.exists()


@pytest.mark.parametrize(("text", "category"), [
    ("quero falar com alguém da equipe", "customer_request"),
    ("meu pedido veio queimado", "complaint"),
    ("preciso de uma encomenda especial", "special_order"),
    ("sou celíaca, tem glúten?", "allergy_review"),
])
def test_handoff_policy_classifies_supported_customer_intent(text, category):
    assert classify_handoff_request(text) == category


@pytest.mark.parametrize("text", [
    "vou querer um pain perdu, vcs entregam?",
    "quais ingredientes tem no Pain Perdu?",
    "sem problema, quero um Pain Perdu",
    "a equipe recomenda qual pão?",
])
def test_handoff_policy_does_not_infer_human_intent_from_public_questions(text):
    assert classify_handoff_request(text) == ""


def test_run_agent_only_sends_the_latest_cart_state(conversation):
    _create_inbound(conversation, "quero dois pães", "agent-two-cart-states")
    conversation = _claim_conversation(conversation)
    client = ScriptedClient(
        _response(
            _tool("set_item", {"sku": SKU, "qty": 1}, "toolu_one"),
            _tool("set_item", {"sku": SKU, "qty": 2}, "toolu_two"),
            stop_reason="tool_use",
        ),
        _response(_text("Coloquei dois."), stop_reason="end_turn"),
    )

    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation,
            history=agent_module.history_for(conversation),
            client=client,
        )

    assert "2 ×" in outcome.reply_text
    assert "1 ×" not in outcome.reply_text
    assert outcome.reply_text.count("Total:") == 1


def test_run_agent_preserves_ready_quote_across_later_read_only_tool(ctx):
    tools.set_item(ctx, SKU, 1)
    tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-12", "")
    _create_inbound(ctx.conversation, "pode revisar e confirmar a entrega?", "agent-quote-and-info")
    conversation = _claim_conversation(ctx.conversation)
    client = ScriptedClient(
        _response(
            _tool("review_order", {"payment_method": "pix"}, "toolu_review"),
            _tool("search_storefront", {"query": "entrega"}, "toolu_info"),
            stop_reason="tool_use",
        ),
        _response(_text("Confira e confirme."), stop_reason="end_turn"),
    )

    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation,
            history=agent_module.history_for(conversation),
            client=client,
        )

    assert outcome.quote_token
    assert "Confira o resumo" in outcome.reply_text
    assert "Fazemos entrega" in outcome.reply_text


def test_run_agent_keeps_language_intelligence_but_hides_mutations_without_authority(
    conversation,
):
    _create_inbound(conversation, "tem pão francês?", "agent-read-only")
    conversation = _claim_conversation(conversation)
    conversation._limited_event_assurance = True
    conversation._commercial_authority = False
    client = ScriptedClient(
        _response(_tool("search_storefront", {"query": "pão"}), stop_reason="tool_use"),
        _response(_text("Temos Pão Francês a R$ 0,90."), stop_reason="end_turn"),
    )

    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation,
            history=agent_module.history_for(conversation),
            client=client,
        )

    assert "Pão Francês" in outcome.reply_text
    names = {spec["name"] for spec in client.requests[0]["tools"]}
    assert names == set(tools.LIMITED_AUTHORITY_TOOL_NAMES)
    assert not names.intersection(
        {"set_item", "set_fulfillment", "review_order", "place_order", "send_web_link", "notify_when_available"}
    )
    assert "Modo de consulta" in client.requests[0]["system"][1]["text"]
    assert not Session.objects.exists()


LEAK_TAG = "<" + "/antml:parameter>"
LEAK_NAME = 'name="search_storefront">'


def test_history_replays_tool_calls_and_text_without_leaked_syntax(conversation):
    """Transcrição com lixo não volta ao modelo como exemplo do formato."""
    _create_inbound(conversation, "oi", "history-leak")
    ConversationMessage.objects.create(
        conversation=conversation,
        role="assistant",
        kind="tool_call",
        content=[{"type": "tool_use", "id": "t1", "name": "search_storefront", "input": {"query": LEAK_TAG + "pao"}}],
    )
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="tool_result",
        content=[{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}],
    )
    history = agent_module.history_for(conversation)
    # Chave vazada some, e chave vazia também: nenhuma das duas vira exemplo.
    assert history[1]["content"][0]["input"] == {}


def test_history_summarizes_old_tool_results(conversation):
    _create_inbound(conversation, "oi", "history-summary")
    ConversationMessage.objects.create(
        conversation=conversation, role="assistant", kind="tool_call",
        content=[{"type": "tool_use", "id": "t1", "name": "search_storefront", "input": {"query": "pao"}}],
    )
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="tool_result",
        content=[{"type": "tool_result", "tool_use_id": "t1", "content": "x" * 5000}],
    )
    history = agent_module.history_for(conversation)
    content = history[2]["content"][0]["content"]
    assert len(content) < 500 and content.endswith("(resultado antigo, resumido)")


def test_clean_text_and_arguments_drop_leaked_tool_syntax():
    dirty = f"{LEAK_NAME}{{}}\n\n?\n\nDeixa eu confirmar, Pablo.\n{LEAK_TAG}\nPeço desculpa pela demora."
    assert agent_module.clean_text(dirty) == "Deixa eu confirmar, Pablo.\nPeço desculpa pela demora."
    args = agent_module.clean_arguments({"query": "croissant", "collection": LEAK_TAG + "\n", "qty": 2})
    assert args == {"query": "croissant", "qty": 2}


def test_run_agent_stops_repeating_the_same_call(conversation):
    _create_inbound(conversation, "folhados?", "agent-repeat")
    conversation = _claim_conversation(conversation)
    same = {"query": "folhados"}
    script = [_response(_tool("search_storefront", same, f"toolu_{i}"), stop_reason="tool_use") for i in range(4)]
    script.append(_response(_text("Hoje não temos folhados."), stop_reason="end_turn"))
    client = ScriptedClient(*script)
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )
    # As duas primeiras rodam; da terceira em diante a ferramenta devolve "já feito".
    assert [e["ok"] for e in outcome.tool_events] == [True, True, False, False]
    assert "Não encontrei essa informação" in outcome.reply_text
    assert "Hoje não temos folhados" not in outcome.reply_text


def test_run_agent_rejects_unfounded_preamble_and_uses_server_facts(conversation):
    """"A taxa é R$ 8,00, deixa eu ver os horários" + chamada → o cliente lê a taxa."""
    _create_inbound(conversation, "qual a taxa?", "agent-preamble")
    conversation = _claim_conversation(conversation)
    client = ScriptedClient(
        _response(_text("A taxa é *R$ 8,00*. Deixa eu ver os horários."), _tool("view_cart", {}), stop_reason="tool_use"),
        _response(_text("Temos janelas a partir das 13:30. Qual prefere?"), stop_reason="end_turn"),
    )
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )
    assert "R$ 8,00" not in outcome.reply_text and "13:30" not in outcome.reply_text
    assert "sacola" in outcome.reply_text.lower()


def test_run_agent_forces_text_when_iterations_run_out(conversation):
    _create_inbound(conversation, "oi", "agent-iterations")
    conversation = _claim_conversation(conversation)
    script = [_response(_tool("view_cart", {}, f"toolu_{i}"), stop_reason="tool_use") for i in range(2)]
    script.append(_response(_text("Um instante."), stop_reason="end_turn"))
    client = ScriptedClient(*script)
    with override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "max_iterations": 2}):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )
    assert outcome.reply_text == tools.render_result("view_cart", {"ok": True, "empty": True})
    assert client.requests[-1]["tool_choice"] == {"type": "none"}


def test_history_window_starts_at_a_customer_message(conversation):
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="tool_result", content=[{"type": "tool_result", "tool_use_id": "x", "content": "{}"}]
    )
    ConversationMessage.objects.create(
        conversation=conversation,
        binding=_binding(conversation),
        role="assistant",
        kind="reply",
        text="Olá",
        content=[{"type": "text", "text": "Olá"}],
    )
    _create_inbound(conversation, "oi", "history-window")
    ConversationMessage.objects.create(conversation=conversation, role="assistant", kind="note", text="nota interna")
    history = agent_module.history_for(conversation)
    assert history == [{"role": "user", "content": [{"type": "text", "text": "oi"}]}]


# ── O turno inteiro ──────────────────────────────────────────────────


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_receive_inbound_queues_one_deferred_directive_per_conversation(surface, customer, monkeypatch):
    monkeypatch.setattr(service, "identify", lambda conversation, binding, profile=None: conversation)
    first = service.receive_inbound(_event(text="oi", event_id="m1"))
    again = service.receive_inbound(_event(text="oi", event_id="m1"))
    more = service.receive_inbound(_event(text="tem croissant?", event_id="m2"))

    assert first.queued and first.reason == "queued"
    assert again.reason == "duplicate"
    assert more.queued
    directives = Directive.objects.filter(topic=service.TURN_TOPIC)
    assert directives.count() == 1  # uma diretiva viva por conversa
    directive = directives.get()
    binding = ConversationBinding.objects.get(conversation_id=first.conversation_id)
    assert directive.payload == {
        "conversation_id": first.conversation_id,
        "binding_id": binding.pk,
        "contract_version": 3,
    }
    assert directive.status == "queued"  # não rodou inline no request
    assert ConversationMessage.objects.filter(kind="inbound").count() == 2


@override_settings(
    SHOPMAN_CONCIERGE={
        **CONCIERGE_SETTINGS,
        "connections": {
            CONNECTION_KEY: {
                **CONCIERGE_SETTINGS["connections"][CONNECTION_KEY],
                "options": {
                    **CONCIERGE_SETTINGS["connections"][CONNECTION_KEY]["options"],
                    "allowed_subjects": [SUBJECT],
                },
            }
        },
    },
    AI_ASSIST_API_KEY="sk-teste",
)
def test_pilot_allowlist_keeps_everyone_else_out_without_side_effects(surface, monkeypatch):
    """A admissão usa o subject autenticado; perfil e telefone não concedem acesso."""
    monkeypatch.setattr(service, "identify", lambda conversation, binding, profile=None: conversation)
    by_id = service.receive_inbound(_event(text="oi", event_id="a"))
    by_phone_in_body = service.receive_inbound(
        _event(
            text="oi",
            event_id="b",
            subject="555",
            profile={"whatsapp_phone": "+55 43 98404-9009"},
        )
    )
    by_phone_from_provider = service.receive_inbound(
        _event(
            text="oi",
            event_id="c",
            subject="777",
            profile={"whatsapp_phone": PHONE},
        )
    )
    stranger = service.receive_inbound(_event(text="oi", event_id="d", subject="999"))

    assert by_id.queued
    assert by_phone_in_body.reason == "not_allowed" and by_phone_from_provider.reason == "not_allowed"
    assert stranger.reason == "not_allowed" and stranger.conversation_id is None
    assert not ConversationBinding.objects.exclude(subject=SUBJECT).exists()
    assert Conversation.objects.count() == 1


@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "enabled": False}, AI_ASSIST_API_KEY="sk-teste")
def test_receive_inbound_is_silent_when_disabled(surface):
    result = service.receive_inbound(_event(text="oi", event_id="disabled", subject="1"))
    assert result.reason == "disabled" and not Conversation.objects.exists()


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_answers_everything_pending_and_persists_the_transcript(conversation, outbox):
    for i, text in enumerate(("oi", "tem pão?")):
        _receive(conversation, text, f"m{i}")
    client = ScriptedClient(
        _response(_tool("search_storefront", {"query": "pão"}), stop_reason="tool_use"),
        _response(_text("Temos pão francês a R$ 0,90. Quantos?"), stop_reason="end_turn"),
    )

    binding = _binding(conversation)
    result = service.run_turn(conversation.pk, binding.pk, client=client)

    assert "R$ 0,90" in result.replies[0]
    assert outbox.sent == result.replies
    assert result.processed_message_ids and not result.pending_more and not result.fallback
    kinds = list(conversation.messages.order_by("id").values_list("kind", flat=True))
    assert kinds == ["inbound", "inbound", "tool_call", "tool_result", "reply"]
    reply = conversation.messages.get(kind="reply")
    assert reply.transport_state == "accepted"
    assert reply.outbound_attempts.get().state == "accepted"
    conversation.refresh_from_db()
    assert conversation.turns_today == 1 and conversation.input_tokens == 200
    # As duas mensagens do cliente foram ao modelo, na ordem.
    sent_roles = [m["role"] for m in client.requests[0]["messages"]]
    assert sent_roles == ["user", "user"]
    assert service.unanswered_inbound(conversation, binding) == []


@pytest.mark.django_db(transaction=True)
@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_sends_the_pix_code_as_its_own_message(ctx, outbox, django_capture_on_commit_callbacks):
    conversation = ctx.conversation
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    conversation = ctx.conversation
    _receive(conversation, "confirmo", "m9")
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=None)
    client = ScriptedClient(
        _response(
            _tool("place_order", {"quote_token": review["quote_token"], "payment_method": "pix", "order_notes": ""}),
            stop_reason="tool_use",
        ),
        _response(_text("Pedido feito. O código Pix chega na próxima mensagem."), stop_reason="end_turn"),
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = service.run_turn(conversation.pk, _binding(conversation).pk, client=client)
    order = Order.objects.get()
    assert len(result.replies) == 2
    assert "registrado" in result.replies[0]
    assert result.replies[1] == order.data["payment"]["copy_paste"]
    assert outbox.sent == result.replies


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_handoff_marks_the_conversation_and_flags_manychat(conversation, outbox):
    _receive(conversation, "quero falar com alguém", "m1")
    client = ScriptedClient()
    binding = _binding(conversation)
    result = service.run_turn(conversation.pk, binding.pk, client=client)

    conversation.refresh_from_db()
    assert result.handoff and conversation.state == Conversation.State.HANDOFF
    assert conversation.handoff_reason == "customer_request"
    assert outbox.flags == [True]
    assert len(outbox.sent) == 1 and "atendimento humano" in outbox.sent[0]
    from shopman.backstage.models import OperatorAlert

    assert OperatorAlert.objects.get(type="concierge_handoff").acknowledged is False

    # Com a equipe na conversa, a próxima mensagem fica na transcrição e o bot cala.
    later = _receive(conversation, "oi?", "m2")
    assert later.reason == "handoff" and not later.queued
    assert service.run_turn(conversation.pk, binding.pk, client=client).replies == []

    assert service.return_to_concierge(conversation) is False
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF and outbox.flags == [True]


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_falls_back_to_house_copy_when_the_model_fails(conversation, outbox, monkeypatch):
    monkeypatch.setattr(service, "copy_message", lambda key: f"[{key}]")
    _receive(conversation, "oi", "m1")
    binding = _binding(conversation)

    class BrokenClient:
        messages = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))

    for _ in range(3):
        result = service.run_turn(conversation.pk, binding.pk, client=BrokenClient())
        _receive(conversation, "oi de novo", f"failure-{_}")
    assert result.fallback == "error" and result.replies == ["[CONCIERGE_UNAVAILABLE]"]
    conversation.refresh_from_db()
    assert conversation.consecutive_failures == 3
    from shopman.backstage.models import OperatorAlert

    assert OperatorAlert.objects.filter(type="concierge_unavailable").count() == 1


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_answers_media_and_daily_limit_without_the_model(conversation, outbox, monkeypatch):
    monkeypatch.setattr(service, "copy_message", lambda key: f"[{key}]")
    _receive(
        conversation,
        "https://lookaside.fbsbx.com/x/audio.ogg",
        "a1",
        message_type="audio",
    )
    binding = _binding(conversation)
    result = service.run_turn(conversation.pk, binding.pk, client=ScriptedClient())
    assert result.fallback == "media" and outbox.sent == ["[CONCIERGE_MEDIA_UNSUPPORTED]"]

    conversation.refresh_from_db()
    conversation.turns_today = 80
    conversation.turns_day = date.today()
    conversation.save()
    _receive(conversation, "oi", "a2")
    result = service.run_turn(conversation.pk, binding.pk, client=ScriptedClient())
    assert result.fallback == "turn_limit" and outbox.sent[-1] == "[CONCIERGE_TURN_LIMIT]"
