# ruff: noqa: F401, F811
"""Da sacola da loja para a conversa, e de volta (OC-16, cenário C02; #3515; #3517).

- **Loja → Nice (C02, J7).** "Continuar pelo WhatsApp" oferece a sacola da loja e
  guarda a oferta sob um código ``NB-`` (o mecanismo da entrada pelo WhatsApp). A
  mensagem chega à Nice pelo número verificado, e o aceite é do serviço: sacola com
  dono só vai para o dono; a anônima vira do cliente verificado no aceite.
- **Nice → loja, no mesmo navegador (#3515).** "Trazer para cá" é oferta e aceite
  no mesmo gesto, para a cliente que entrou com o próprio dispositivo.
- **Depois da passagem (#3517).** A loja mostra cada diferença do recibo numa frase
  e, quando o navegador já tem sacola, pergunta "substituir ou manter".

X1: as ações só existem quando a projeção diz que são possíveis. X4: o mesmo aceite
outra vez não abre uma segunda sacola. X5: a sacola que mudou depois da oferta é
recusada (``source_changed``), e a ação volta a ser oferecida.
"""

from __future__ import annotations

import pytest
from django.contrib.sessions.backends.db import SessionStore
from rest_framework.test import APIRequestFactory
from shopman.orderman.models import Session

from shopman.shop.models import Conversation, ConversationBinding
from shopman.shop.models import ConversationMessage as Message
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions
from shopman.storefront.concierge import service, tools
from shopman.storefront.identity import IDENTITY_NUMBER, IDENTITY_SESSION_KEY
from shopman.storefront.tests.identity_fakes import make_identity_view
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    CONCIERGE_SETTINGS,
    SKU,
    _binding,
    _create_inbound,
    conversation,
    ctx,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db

WEB = "web"
BRIDGE_ON = {**CONCIERGE_SETTINGS, "transfer_enabled": True}


@pytest.fixture(autouse=True)
def _no_rate_limit(settings):
    settings.RATELIMIT_ENABLE = False


@pytest.fixture
def bridge(settings):
    settings.SHOPMAN_CONCIERGE = BRIDGE_ON
    return settings


def _web_cart(qty: int = 2, *, owner=None) -> Session:
    _session, key = cart_service.add_item(
        session_key=None, channel_ref=WEB, origin_channel=WEB, sku=SKU, qty=qty, unit_price_q=90, name="Pão Francês",
    )
    if owner is not None:
        sessions.assign_customer(session_key=key, channel_ref=WEB, customer_uuid=owner.uuid)
    return Session.objects.get(session_key=key, channel_ref=WEB)


def _other_customer():
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    return customer_service.create(
        ref=Customer.generate_ref(), first_name="Bia", phone="+5543999990000", source_system="test"
    )


def _browser(*, cart: Session | None = None, customer=None, strength: str = "") -> SessionStore:
    store = SessionStore()
    if cart is not None:
        store["cart_session_key"] = cart.session_key
    if strength:
        store[IDENTITY_SESSION_KEY] = strength
    store.save()
    store._customer = customer  # carregado pelo _request, abaixo
    return store


def _request(method: str, path: str, browser: SessionStore, data=None):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path, data or {}, format="json")
    request.session = browser
    customer = getattr(browser, "_customer", None)
    request.customer = (
        make_identity_view(subject_id=customer.uuid, name=customer.name, phone=customer.phone) if customer else None
    )
    return request


def _post(view, path: str, browser: SessionStore, data=None):
    response = view.as_view()(_request("post", path, browser, data))
    response.render()
    return response


def _cart(browser: SessionStore) -> dict:
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.cart import build_cart

    return projection_data(build_cart(request=_request("get", "/api/v1/storefront/cart/", browser), channel_ref=WEB))


def _continue(browser: SessionStore):
    from shopman.storefront.api.cart_transfer import CartContinueInConversationView

    return _post(CartContinueInConversationView, "/api/v1/cart/continue-in-conversation/", browser)


def _turn(conversation, text: str) -> str:
    message = _create_inbound(conversation, text, f"oc16-{Message.objects.count()}")
    assert message.pk
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=None)
    service.run_turn(conversation.pk, _binding(conversation).pk)
    return (
        Message.objects.filter(conversation=conversation, kind="reply").order_by("-pk").values_list("text", flat=True).first()
        or ""
    )


def _holds(session_key: str) -> list:
    from shopman.stockman import Hold

    return list(Hold.objects.filter(metadata__reference=session_key, status__in=["pending", "confirmed"]).values_list("sku", "quantity"))


def _conversation_cart(conversation) -> Session | None:
    conversation.refresh_from_db()
    return Session.objects.filter(session_key=conversation.session_key, channel_ref=CHANNEL, state="open").first()


# ── X1: a ação só aparece quando a passagem é possível ───────────────


def test_x1_continue_in_conversation_only_with_the_bridge_on(surface, settings):
    browser = _browser(cart=_web_cart())

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS  # a chave da ponte desligada
    assert _cart(browser)["continue_in_conversation"] is None
    refused = _continue(browser)
    assert refused.status_code == 409 and refused.data["error_code"] == "transfer_unavailable"

    settings.SHOPMAN_CONCIERGE = BRIDGE_ON
    action = _cart(browser)["continue_in_conversation"]
    assert (action["ref"], action["label"], action["enabled"]) == ("continue_in_conversation", "Continuar pelo WhatsApp", True)

    settings.SHOPMAN_CONCIERGE = {**BRIDGE_ON, "enabled": False}  # a Nice desligada
    assert _cart(browser)["continue_in_conversation"] is None


def test_x1_no_action_with_an_empty_cart_or_a_forwarded_link(surface, customer, bridge):
    assert _cart(_browser())["continue_in_conversation"] is None
    forwarded = _browser(cart=_web_cart(owner=customer), customer=customer, strength=IDENTITY_NUMBER)
    assert _cart(forwarded)["continue_in_conversation"] is None
    assert _continue(forwarded).status_code == 409


def test_offering_never_touches_the_store_cart(surface, bridge):
    web = _web_cart()
    before = (web.state, web.rev, web.items, _holds(web.session_key))

    started = _continue(_browser(cart=web))

    assert started.status_code == 200, started.data
    assert started.data["code"].startswith("NB-")
    assert started.data["message"] == (
        f"Olá! Quero continuar por aqui a sacola que montei no site (ref. {started.data['code']})"
    )
    assert started.data["deep_link"].startswith("https://wa.me/554333231997?text=")
    web.refresh_from_db()
    assert (web.state, web.rev, web.items, _holds(web.session_key)) == before


# ── C02: a sacola chega à conversa pelo número verificado ────────────


def test_c02_anonymous_store_cart_becomes_the_verified_customers_in_the_conversation(conversation, outbox, bridge):
    web = _web_cart(qty=2)
    assert (web.data or {}).get("customer") is None
    started = _continue(_browser(cart=web)).data

    reply = _turn(conversation, started["message"])

    arrived = _conversation_cart(conversation)
    assert arrived is not None, reply
    assert [(item["sku"], int(item["qty"])) for item in arrived.items] == [(SKU, 2)]
    assert arrived.data["customer"]["ref"] == conversation.customer_ref  # vinculada no aceite
    assert arrived.data["concierge"] == {"conversation_id": conversation.pk}
    assert arrived.data["transferred_from"]["channel_ref"] == WEB
    web.refresh_from_db()
    assert web.state == "abandoned" and web.data["transferred_to"]["session_key"] == arrived.session_key
    assert _holds(web.session_key) == [] and len(_holds(arrived.session_key)) == 1  # nenhuma reserva dobrada
    assert reply.startswith("Sua sacola do site chegou aqui na conversa.")
    assert "2 × “Pão Francês”: R$ 1,80" in reply and "Total: R$ 1,80" in reply
    assert "—" not in reply


def test_c02_a_store_cart_with_an_owner_goes_only_to_the_owner(conversation, outbox, bridge):
    other = _other_customer()
    web = _web_cart(owner=other)
    started = _continue(_browser(cart=web, customer=other)).data

    reply = _turn(conversation, started["message"])

    assert reply.startswith("Recebi o código da sacola do site, mas ela é de outra conta")
    web.refresh_from_db()
    assert web.state == "open" and "transferred_to" not in web.data
    assert _conversation_cart(conversation) is None


def test_c02_an_unverified_number_does_not_take_an_anonymous_cart(conversation, outbox, bridge):
    ConversationBinding.objects.filter(conversation=conversation).update(identity_assurance="unverified")
    Conversation.objects.filter(pk=conversation.pk).update(customer_ref="")
    web = _web_cart()
    started = _continue(_browser(cart=web)).data

    reply = _turn(conversation, started["message"])

    web.refresh_from_db()
    assert web.state == "open"
    assert "A sacola continua no site" in reply


def test_x4_the_same_message_twice_lands_on_one_cart(conversation, outbox, bridge):
    web = _web_cart()
    started = _continue(_browser(cart=web)).data
    _turn(conversation, started["message"])
    first = _conversation_cart(conversation)

    again = _turn(conversation, started["message"])

    assert again.startswith("Sua sacola do site já está aqui na conversa.")
    assert _conversation_cart(conversation).session_key == first.session_key
    assert Session.objects.filter(channel_ref=CHANNEL).count() == 1
    assert len(_holds(first.session_key)) == 1


def test_x5_a_store_cart_that_changed_after_the_offer_is_offered_again(conversation, outbox, bridge):
    web = _web_cart(qty=2)
    browser = _browser(cart=web)
    started = _continue(browser).data
    cart_service.add_item(session_key=web.session_key, channel_ref=WEB, origin_channel=WEB, sku=SKU, qty=1, unit_price_q=90, name="Pão Francês")

    reply = _turn(conversation, started["message"])

    assert reply.startswith("A sacola do site mudou depois que você tocou em Continuar pelo WhatsApp.")
    web.refresh_from_db()
    assert web.state == "open"
    assert _conversation_cart(conversation) is None
    # A loja oferece de novo, e a nova oferta passa.
    assert _cart(browser)["continue_in_conversation"]["enabled"] is True
    fresh = _continue(browser).data
    assert _turn(conversation, fresh["message"]).startswith("Sua sacola do site chegou aqui na conversa.")


def test_a_conversation_with_its_own_cart_keeps_both_and_never_merges(ctx, outbox, bridge):
    tools.set_item(ctx, SKU, 1)
    conversation = ctx.conversation
    own = _conversation_cart(conversation)
    web = _web_cart(qty=2)
    started = _continue(_browser(cart=web)).data

    reply = _turn(conversation, started["message"])

    assert reply.startswith("Você já tem uma sacola aqui na conversa, então a do site continua lá")
    web.refresh_from_db()
    assert web.state == "open"
    assert [(item["sku"], int(item["qty"])) for item in _conversation_cart(conversation).items] == [(SKU, 1)]
    assert _conversation_cart(conversation).session_key == own.session_key


def test_the_login_message_and_order_refs_are_not_this_door(conversation, outbox, bridge):
    from shopman.doorman.services.link_state import pop_state, store_state

    code = store_state({"cart_session_key": "abc"})
    _turn(conversation, f"Olá! Quero entrar no site da Nelson Boulangerie (ref. {code})")
    assert pop_state(code) == {"cart_session_key": "abc"}  # o login segue com o estado dele

    reply = _turn(conversation, "Cadê o pedido NB-261003-M63?")
    assert "sacola do site" not in reply


def test_an_expired_code_says_how_to_get_another(conversation, outbox, bridge):
    reply = _turn(conversation, "Olá! Quero continuar por aqui a sacola que montei no site (ref. NB-ABCDEF)")

    assert reply == (
        "Esse código de sacola venceu ou já foi usado. No site, toque de novo em Continuar pelo WhatsApp "
        "para gerar outro."
    )


def test_differences_are_said_one_per_line(conversation, outbox, bridge):
    from shopman.offerman.models import ListingItem

    web = _web_cart(qty=2)
    started = _continue(_browser(cart=web)).data
    ListingItem.objects.filter(listing__ref=CHANNEL, product__sku=SKU).update(price_q=120)

    reply = _turn(conversation, started["message"])

    assert "Chegou com estas mudanças:\n• Pão Francês: o preço aqui é R$ 1,20 (era R$ 0,90)." in reply


# ── #3515: "Trazer para cá" na loja ──────────────────────────────────


def _bring(browser: SessionStore, channel: str = CHANNEL):
    from shopman.storefront.api.cart_transfer import CartBringView

    return _post(CartBringView, "/api/v1/cart/bring/", browser, {"channel": channel})


def _choice(browser: SessionStore, choice: str):
    from shopman.storefront.api.cart_transfer import CartTransferChoiceView

    return _post(CartTransferChoiceView, "/api/v1/cart/transfer-choice/", browser, {"choice": choice})


def test_3515_bring_is_on_only_with_the_bridge(ctx, customer, settings):
    tools.set_item(ctx, SKU, 3)
    browser = _browser(customer=customer)

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    entry = _cart(browser)["open_elsewhere"][0]
    assert (entry["bring"]["label"], entry["bring"]["enabled"]) == ("Trazer para cá", False)
    assert _bring(browser).status_code == 409

    settings.SHOPMAN_CONCIERGE = BRIDGE_ON
    entry = _cart(browser)["open_elsewhere"][0]
    assert entry["bring"]["enabled"] is True and entry["bring"]["href"] == "/api/v1/cart/bring/"


def test_3515_bring_moves_the_conversation_cart_here(ctx, customer, bridge):
    tools.set_item(ctx, SKU, 3)
    source = _conversation_cart(ctx.conversation)
    browser = _browser(customer=customer)

    response = _bring(browser)

    assert response.status_code == 200, response.data
    assert response.data["cart_transfer"] == {"status": "accepted", "differences": []}
    cart = response.data["cart"]
    assert cart["items_count"] == 3 and cart["open_elsewhere"] == []
    source.refresh_from_db()
    assert source.state == "abandoned"
    assert Session.objects.get(session_key=browser["cart_session_key"]).channel_ref == WEB


def test_3515_bring_never_for_a_forwarded_link(ctx, customer, bridge):
    tools.set_item(ctx, SKU, 3)

    assert _bring(_browser(customer=customer, strength=IDENTITY_NUMBER)).status_code == 409
    assert _conversation_cart(ctx.conversation) is not None


# ── #3517: diferenças e "substituir ou manter" ───────────────────────


def test_3517_the_store_shows_each_difference_after_the_transfer(ctx, customer, bridge):
    from shopman.offerman.models import ListingItem

    tools.set_item(ctx, SKU, 3)
    ListingItem.objects.filter(listing__ref=WEB, product__sku=SKU).update(price_q=100)
    browser = _browser(customer=customer)

    cart = _bring(browser).data["cart"]

    arrival = cart["transfer_arrival"]
    assert arrival["title"] == "Sua sacola veio do WhatsApp com mudanças"
    assert arrival["lines"] == ["Pão Francês: o preço aqui é R$ 1,00 (era R$ 0,90)."]
    assert arrival["total_line"] == "Soma dos itens agora: R$ 3,00 (era R$ 2,70)."
    assert "—" not in repr(arrival)


def test_3517_no_arrival_notice_when_everything_came_the_same(ctx, customer, bridge):
    tools.set_item(ctx, SKU, 3)

    assert _bring(_browser(customer=customer)).data["cart"]["transfer_arrival"] is None


def test_3517_a_browser_with_a_cart_is_asked_keep_or_replace(ctx, customer, bridge):
    tools.set_item(ctx, SKU, 3)
    source = _conversation_cart(ctx.conversation)
    here = _web_cart(qty=1, owner=customer)
    browser = _browser(cart=here, customer=customer)

    asked = _bring(browser)

    assert asked.data["cart_transfer"] == {"status": "refused", "code": "destination_conflict"}
    conflict = asked.data["cart"]["transfer_conflict"]
    assert conflict["title"] == "Qual sacola você quer usar aqui?"
    assert conflict["message"] == (
        "Aqui já existe uma sacola, com 1 item (R$ 0,90). A do WhatsApp tem 3 itens (R$ 2,70). "
        "Se trouxer a do WhatsApp, a daqui é descartada. Se ficar com a daqui, a do WhatsApp continua lá."
    )
    assert (conflict["replace"]["label"], conflict["keep"]["label"]) == ("Trazer a do WhatsApp", "Ficar com a daqui")
    source.refresh_from_db()
    here.refresh_from_db()
    assert source.state == "open" and here.state == "open"  # perguntar não muda nada

    replaced = _choice(browser, "replace")

    assert replaced.status_code == 200, replaced.data
    assert replaced.data["cart"]["items_count"] == 3 and replaced.data["cart"]["transfer_conflict"] is None
    here.refresh_from_db()
    source.refresh_from_db()
    assert here.state == "abandoned" and source.state == "abandoned"
    assert _choice(browser, "replace").status_code == 409  # a pergunta já foi respondida


def test_3517_keep_leaves_the_conversation_cart_where_it_is(ctx, customer, bridge):
    tools.set_item(ctx, SKU, 3)
    source = _conversation_cart(ctx.conversation)
    here = _web_cart(qty=1, owner=customer)
    browser = _browser(cart=here, customer=customer)
    _bring(browser)

    kept = _choice(browser, "keep")

    assert kept.data["cart_transfer"] == {"status": "kept"}
    assert kept.data["cart"]["items_count"] == 1 and kept.data["cart"]["transfer_conflict"] is None
    source.refresh_from_db()
    assert source.state == "open"


def test_x5_the_choice_after_the_source_changed_is_refused_and_offered_again(ctx, customer, bridge):
    tools.set_item(ctx, SKU, 3)
    here = _web_cart(qty=1, owner=customer)
    browser = _browser(cart=here, customer=customer)
    _bring(browser)
    tools.set_item(ctx, SKU, 4)  # a sacola da conversa mudou depois da oferta

    assert _cart(browser)["transfer_conflict"] is None  # a pergunta velha some
    refused = _choice(browser, "replace")

    assert refused.status_code == 409 and refused.data["error_code"] == "source_changed"
    here.refresh_from_db()
    assert here.state == "open"
    assert refused.data["cart"]["open_elsewhere"][0]["bring"]["enabled"] is True


def test_3517_the_link_exchange_conflict_becomes_the_question(ctx, customer, bridge):
    """A troca do link da Nice esbarra na sacola do navegador e deixa a pergunta guardada."""
    from shopman.shop.services import session_transfer
    from shopman.storefront.api.auth import _adopt_carried_cart

    tools.set_item(ctx, SKU, 3)
    offer = session_transfer.offer(CHANNEL, ctx.conversation.session_key, WEB, customer_ref=customer.ref, actor="test")
    here = _web_cart(qty=1, owner=customer)
    browser = _browser(cart=here, customer=customer)
    request = _request("get", "/a", browser)

    summary = _adopt_carried_cart(request, {"cart_transfer": offer.as_metadata()}, customer)

    assert summary == {"status": "refused", "code": "destination_conflict"}
    assert _cart(browser)["transfer_conflict"]["replace"]["label"] == "Trazer a do WhatsApp"


def test_a_conversation_offer_never_lands_in_a_browser(ctx, customer, bridge):
    """A oferta para a conversa que cair no fluxo de login não vira sacola do navegador."""
    from shopman.shop.services import session_transfer
    from shopman.storefront.api.auth import _adopt_carried_cart

    web = _web_cart(qty=1)
    offer = session_transfer.offer(WEB, web.session_key, CHANNEL, customer_ref="", actor="test")
    request = _request("get", "/a", _browser(customer=customer))

    assert _adopt_carried_cart(request, {"cart_transfer": offer.as_metadata()}, customer) == {
        "status": "refused", "code": "invalid_offer",
    }
    web.refresh_from_db()
    assert web.state == "open"
