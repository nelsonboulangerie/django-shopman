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
from django.test import override_settings
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.orderman.models import Directive, Order, Session

from shopman.shop.models import Channel, Conversation, ConversationMessage, Shop
from shopman.storefront.concierge import agent as agent_module
from shopman.storefront.concierge import service, tools
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CHANNEL = "whatsapp"
SKU = "PAO-FRANCES"
PHONE = "+5543984049009"
CONCIERGE_SETTINGS = {
    "enabled": True,
    "api_key": "chave-s2s",
    "model": "claude-sonnet-5",
    "effort": "low",
    "max_tokens": 512,
    "channel_ref": CHANNEL,
    "window_messages": 40,
    "max_turns_per_day": 80,
    "max_iterations": 6,
    "handoff_field": "concierge_handoff",
    "dispatch_delay_seconds": 1,
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
def conversation(surface, customer):
    return Conversation.objects.create(
        subscriber_id="1962036908",
        phone=PHONE,
        customer_name="Ana",
        customer_ref=customer.ref,
        channel_ref=CHANNEL,
    )


@pytest.fixture
def ctx(conversation):
    return ToolContext(conversation=conversation, channel_ref=CHANNEL)


@pytest.fixture
def outbox(monkeypatch):
    sent: list[str] = []
    flags: list[bool] = []
    monkeypatch.setattr("shopman.storefront.concierge.transport.send_text", lambda sid, text: sent.append(text) or True)
    monkeypatch.setattr("shopman.storefront.concierge.transport.set_handoff", lambda sid, on: flags.append(on) or True)
    return SimpleNamespace(sent=sent, flags=flags)


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def _pickup_ready(ctx) -> dict:
    """Sacola com 2 pães, retirada amanhã ao meio-dia: pronta para orçar."""
    assert tools.set_item(ctx, SKU, 2)["ok"]
    result = tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-12", "")
    assert result["ok"], result
    return tools.review_order(ctx)


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


def test_browse_menu_reads_price_and_availability_from_the_listing(ctx):
    result = tools.browse_menu(ctx, "pao", "")
    assert result["ok"] and result["count"] == 1
    item = result["items"][0]
    assert item["sku"] == SKU
    assert item["price"] == "R$ 0,90"
    assert item["can_order"] is True
    assert item["available_qty"] == 10


def test_browse_menu_without_arguments_is_an_overview_by_collection(ctx):
    result = tools.browse_menu(ctx)
    assert result["overview"] is True and result["available_count"] == 1
    assert [c["ref"] for c in result["collections"]] == ["paes"]
    assert result["collections"][0]["available_count"] == 1
    assert result["collections"][0]["examples"][0]["sku"] == SKU


def test_browse_menu_accepts_the_collection_by_label_and_ignores_unknown_ones(ctx):
    by_label = tools.browse_menu(ctx, "", "Pães")
    assert by_label["count"] == 1 and "note" not in by_label
    unknown = tools.browse_menu(ctx, "", "folhados")
    assert unknown["count"] == 1 and "não existe" in unknown["note"]


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
    assert placed["payment"]["pix_code_sent_separately"] is True
    assert ctx.extra_replies == [order.data["payment"]["copy_paste"]]
    assert placed["tracking_url"].endswith(f"/pedido/{order.ref}/")

    conversation.refresh_from_db()
    assert conversation.session_key == "" and conversation.quote == {}


def test_place_order_refuses_a_stale_quote(ctx):
    review = _pickup_ready(ctx)
    token = review["quote_token"]
    tools.set_item(ctx, SKU, 3)  # a sacola mudou depois do orçamento
    refused = tools.place_order(ctx, token, "pix", "")
    assert refused["ok"] is False and refused["error"] == "quote_stale"
    assert not Order.objects.exists()


def test_place_order_refuses_a_payment_method_the_channel_does_not_offer(ctx):
    review = _pickup_ready(ctx)
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
    with django_capture_on_commit_callbacks(execute=True):
        placed = tools.place_order(ctx, review["quote_token"], "pix", "")
    status = tools.order_status(ctx, "")
    assert status["orders"][0]["order_ref"] == placed["order_ref"]
    assert status["orders"][0]["needs_payment"] is True
    assert tools.order_status(ctx, "XYZ-000")["orders"] == []


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


def test_notify_when_available_subscribes_the_same_alerts_as_the_site(ctx, conversation):
    from shopman.storefront.models import StockAlertSubscription

    result = tools.notify_when_available(ctx, SKU)
    assert result["ok"], result
    subs = StockAlertSubscription.objects.filter(sku=SKU, customer_ref=conversation.customer_ref)
    assert sorted(subs.values_list("alert_type", flat=True)) == ["production_ready", "stock_back"]
    # Idempotente: pedir de novo não duplica.
    tools.notify_when_available(ctx, SKU)
    assert subs.count() == 2
    assert tools.notify_when_available(ctx, "NAO-EXISTE")["error"] == "unknown_sku"


def test_execute_never_raises(ctx):
    assert tools.execute("nao_existe", {}, ctx)["error"] == "unknown_tool"
    assert tools.execute("set_item", {"sku": SKU}, ctx)["error"] == "bad_arguments"


# ── Laço do agente ───────────────────────────────────────────────────


def test_run_agent_executes_tools_and_keeps_the_transcript_in_api_format(conversation):
    ConversationMessage.objects.create(
        conversation=conversation,
        role="user",
        kind="inbound",
        text="tem pão francês?",
        content=[{"type": "text", "text": "tem pão francês?"}],
    )
    client = ScriptedClient(
        _response(_tool("browse_menu", {"query": "pão", "collection": ""}), stop_reason="tool_use"),
        _response(_text("Temos sim. Quantos você quer?"), stop_reason="end_turn"),
    )
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )

    assert outcome.reply_text == "Temos sim. Quantos você quer?"
    assert [m["role"] for m in outcome.messages] == ["assistant", "user", "assistant"]
    tool_result = outcome.messages[1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "toolu_1"
    assert json.loads(tool_result["content"])["items"][0]["sku"] == SKU
    assert outcome.tool_events == [{"name": "browse_menu", "input": {"query": "pão"}, "ok": True}]
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
    browse = next(t for t in first["tools"] if t["name"] == "browse_menu")
    assert browse["input_schema"]["required"] == []
    # A segunda ida leva a chamada e o resultado da ferramenta de volta.
    assert client.requests[1]["messages"][-1]["content"][0]["type"] == "tool_result"


LEAK_TAG = "<" + "/antml:parameter>"
LEAK_NAME = 'name="browse_menu">'


def test_history_replays_tool_calls_and_text_without_leaked_syntax(conversation):
    """Transcrição com lixo não volta ao modelo como exemplo do formato."""
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="inbound", text="oi", content=[{"type": "text", "text": "oi"}]
    )
    ConversationMessage.objects.create(
        conversation=conversation,
        role="assistant",
        kind="tool_call",
        content=[{"type": "tool_use", "id": "t1", "name": "browse_menu", "input": {"query": LEAK_TAG + "pao", "collection": ""}}],
    )
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="tool_result",
        content=[{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}],
    )
    history = agent_module.history_for(conversation)
    # Chave vazada some, e chave vazia também: nenhuma das duas vira exemplo.
    assert history[1]["content"][0]["input"] == {}


def test_history_summarizes_old_tool_results(conversation):
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="inbound", text="oi", content=[{"type": "text", "text": "oi"}]
    )
    ConversationMessage.objects.create(
        conversation=conversation, role="assistant", kind="tool_call",
        content=[{"type": "tool_use", "id": "t1", "name": "browse_menu", "input": {"query": "pao"}}],
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
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="inbound", text="folhados?", content=[{"type": "text", "text": "folhados?"}]
    )
    same = {"query": "", "collection": "folhados"}
    script = [_response(_tool("browse_menu", same, f"toolu_{i}"), stop_reason="tool_use") for i in range(4)]
    script.append(_response(_text("Hoje não temos folhados."), stop_reason="end_turn"))
    client = ScriptedClient(*script)
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )
    # As duas primeiras rodam; da terceira em diante a ferramenta devolve "já feito".
    assert [e["ok"] for e in outcome.tool_events] == [True, True, False, False]
    assert outcome.reply_text == "Hoje não temos folhados."


def test_run_agent_keeps_what_the_model_said_before_calling_a_tool(conversation):
    """"A taxa é R$ 8,00, deixa eu ver os horários" + chamada → o cliente lê a taxa."""
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="inbound", text="qual a taxa?", content=[{"type": "text", "text": "qual a taxa?"}]
    )
    client = ScriptedClient(
        _response(_text("A taxa é *R$ 8,00*. Deixa eu ver os horários."), _tool("view_cart", {}), stop_reason="tool_use"),
        _response(_text("Temos janelas a partir das 13:30. Qual prefere?"), stop_reason="end_turn"),
    )
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )
    assert outcome.reply_text == "A taxa é *R$ 8,00*. Deixa eu ver os horários.\n\nTemos janelas a partir das 13:30. Qual prefere?"


def test_run_agent_forces_text_when_iterations_run_out(conversation):
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="inbound", text="oi", content=[{"type": "text", "text": "oi"}]
    )
    script = [_response(_tool("view_cart", {}, f"toolu_{i}"), stop_reason="tool_use") for i in range(2)]
    script.append(_response(_text("Um instante."), stop_reason="end_turn"))
    client = ScriptedClient(*script)
    with override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "max_iterations": 2}):
        outcome = agent_module.run_agent(
            conversation=conversation, history=agent_module.history_for(conversation), client=client
        )
    assert outcome.reply_text == "Um instante."
    assert client.requests[-1]["tool_choice"] == {"type": "none"}


def test_history_window_starts_at_a_customer_message(conversation):
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="tool_result", content=[{"type": "tool_result", "tool_use_id": "x", "content": "{}"}]
    )
    ConversationMessage.objects.create(
        conversation=conversation, role="assistant", kind="reply", text="Olá", content=[{"type": "text", "text": "Olá"}]
    )
    ConversationMessage.objects.create(
        conversation=conversation, role="user", kind="inbound", text="oi", content=[{"type": "text", "text": "oi"}]
    )
    ConversationMessage.objects.create(conversation=conversation, role="assistant", kind="note", text="nota interna")
    history = agent_module.history_for(conversation)
    assert history == [{"role": "user", "content": [{"type": "text", "text": "oi"}]}]


# ── O turno inteiro ──────────────────────────────────────────────────


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_receive_inbound_queues_one_deferred_directive_per_conversation(surface, customer, monkeypatch):
    monkeypatch.setattr(service, "identify", lambda conversation, profile=None: conversation)
    first = service.receive_inbound(subscriber_id="1962036908", text="oi", external_id="m1")
    again = service.receive_inbound(subscriber_id="1962036908", text="oi", external_id="m1")
    more = service.receive_inbound(subscriber_id="1962036908", text="tem croissant?", external_id="m2")

    assert first.queued and first.reason == "queued"
    assert again.reason == "duplicate"
    assert more.queued
    directives = Directive.objects.filter(topic=service.TURN_TOPIC)
    assert directives.count() == 1  # uma diretiva viva por conversa
    directive = directives.get()
    assert directive.payload == {"conversation_id": first.conversation_id}
    assert directive.status == "queued"  # não rodou inline no request
    assert ConversationMessage.objects.filter(kind="inbound").count() == 2


@override_settings(
    SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "allowed_subscribers": ["1962036908", "+5543984049009"]},
    AI_ASSIST_API_KEY="sk-teste",
)
def test_pilot_allowlist_keeps_everyone_else_out_without_side_effects(surface, monkeypatch):
    """Piloto fechado: quem não está na lista não ganha conversa, mensagem nem cliente."""
    monkeypatch.setattr(service, "identify", lambda conversation, profile=None: conversation)
    monkeypatch.setattr(
        "shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.fetch_subscriber_info",
        lambda subscriber_id: {"whatsapp_phone": "+5543984049009"} if subscriber_id == "777" else {},
    )
    by_id = service.receive_inbound(subscriber_id="1962036908", text="oi", external_id="a")
    by_phone_in_body = service.receive_inbound(
        subscriber_id="555", text="oi", external_id="b", profile={"whatsapp_phone": "+55 43 98404-9009"}
    )
    by_phone_from_getinfo = service.receive_inbound(subscriber_id="777", text="oi", external_id="c")
    stranger = service.receive_inbound(subscriber_id="999", text="oi", external_id="d")

    assert by_id.queued and by_phone_in_body.queued and by_phone_from_getinfo.queued
    assert stranger.reason == "not_allowed" and stranger.conversation_id is None
    assert not Conversation.objects.filter(subscriber_id="999").exists()
    assert Conversation.objects.count() == 3


@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "enabled": False}, AI_ASSIST_API_KEY="sk-teste")
def test_receive_inbound_is_silent_when_disabled(surface):
    result = service.receive_inbound(subscriber_id="1", text="oi")
    assert result.reason == "disabled" and not Conversation.objects.exists()


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_answers_everything_pending_and_persists_the_transcript(conversation, outbox):
    for i, text in enumerate(("oi", "tem pão?")):
        service.receive_inbound(subscriber_id=conversation.subscriber_id, text=text, external_id=f"m{i}")
    client = ScriptedClient(
        _response(_tool("browse_menu", {"query": "pão", "collection": ""}), stop_reason="tool_use"),
        _response(_text("Temos pão francês a R$ 0,90. Quantos?"), stop_reason="end_turn"),
    )

    result = service.run_turn(conversation.pk, client=client)

    assert result.replies == ["Temos pão francês a R$ 0,90. Quantos?"]
    assert outbox.sent == result.replies
    assert result.processed_message_ids and not result.pending_more and not result.fallback
    kinds = list(conversation.messages.order_by("id").values_list("kind", flat=True))
    assert kinds == ["inbound", "inbound", "tool_call", "tool_result", "reply"]
    reply = conversation.messages.get(kind="reply")
    assert reply.delivered is True
    conversation.refresh_from_db()
    assert conversation.turns_today == 1 and conversation.input_tokens == 200
    # As duas mensagens do cliente foram ao modelo, na ordem.
    sent_roles = [m["role"] for m in client.requests[0]["messages"]]
    assert sent_roles == ["user", "user"]
    assert service.unanswered_inbound(conversation) == []


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_sends_the_pix_code_as_its_own_message(conversation, outbox, django_capture_on_commit_callbacks):
    ctx = ToolContext(conversation=conversation, channel_ref=CHANNEL)
    review = _pickup_ready(ctx)
    service.receive_inbound(subscriber_id=conversation.subscriber_id, text="confirmo, pix", external_id="m9")
    client = ScriptedClient(
        _response(
            _tool("place_order", {"quote_token": review["quote_token"], "payment_method": "pix", "order_notes": ""}),
            stop_reason="tool_use",
        ),
        _response(_text("Pedido feito. O código Pix chega na próxima mensagem."), stop_reason="end_turn"),
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = service.run_turn(conversation.pk, client=client)
    order = Order.objects.get()
    assert result.replies == [
        "Pedido feito. O código Pix chega na próxima mensagem.",
        order.data["payment"]["copy_paste"],
    ]
    assert outbox.sent == result.replies


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_handoff_marks_the_conversation_and_flags_manychat(conversation, outbox):
    service.receive_inbound(subscriber_id=conversation.subscriber_id, text="quero falar com alguém", external_id="m1")
    client = ScriptedClient(
        _response(_text("Claro."), _tool("handoff_to_human", {"reason": "pediu uma pessoa"}), stop_reason="tool_use"),
    )
    result = service.run_turn(conversation.pk, client=client)

    conversation.refresh_from_db()
    assert result.handoff and conversation.state == Conversation.State.HANDOFF
    assert conversation.handoff_reason == "pediu uma pessoa"
    assert outbox.flags == [True]
    assert outbox.sent == ["Claro."]
    from shopman.backstage.models import OperatorAlert

    assert OperatorAlert.objects.get(type="concierge_handoff").acknowledged is False

    # Com a equipe na conversa, a próxima mensagem fica na transcrição e o bot cala.
    later = service.receive_inbound(subscriber_id=conversation.subscriber_id, text="oi?", external_id="m2")
    assert later.reason == "handoff" and not later.queued
    assert service.run_turn(conversation.pk, client=client).replies == []

    service.return_to_concierge(conversation)
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE and outbox.flags == [True, False]


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_falls_back_to_house_copy_when_the_model_fails(conversation, outbox, monkeypatch):
    monkeypatch.setattr(service, "copy_message", lambda key: f"[{key}]")
    service.receive_inbound(subscriber_id=conversation.subscriber_id, text="oi", external_id="m1")

    class BrokenClient:
        messages = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))

    for _ in range(3):
        result = service.run_turn(conversation.pk, client=BrokenClient())
        service.receive_inbound(subscriber_id=conversation.subscriber_id, text="oi de novo", external_id=str(_))
    assert result.fallback == "error" and result.replies == ["[CONCIERGE_UNAVAILABLE]"]
    conversation.refresh_from_db()
    assert conversation.consecutive_failures == 3
    from shopman.backstage.models import OperatorAlert

    assert OperatorAlert.objects.filter(type="concierge_unavailable").count() == 1


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_run_turn_answers_media_and_daily_limit_without_the_model(conversation, outbox, monkeypatch):
    monkeypatch.setattr(service, "copy_message", lambda key: f"[{key}]")
    service.receive_inbound(
        subscriber_id=conversation.subscriber_id, text="https://lookaside.fbsbx.com/x/audio.ogg", external_id="a1"
    )
    result = service.run_turn(conversation.pk, client=ScriptedClient())
    assert result.fallback == "media" and outbox.sent == ["[CONCIERGE_MEDIA_UNSUPPORTED]"]

    conversation.refresh_from_db()
    conversation.turns_today = 80
    conversation.turns_day = date.today()
    conversation.save()
    service.receive_inbound(subscriber_id=conversation.subscriber_id, text="oi", external_id="a2")
    result = service.run_turn(conversation.pk, client=ScriptedClient())
    assert result.fallback == "turn_limit" and outbox.sent[-1] == "[CONCIERGE_TURN_LIMIT]"
