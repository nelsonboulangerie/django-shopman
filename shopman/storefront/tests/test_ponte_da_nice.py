# ruff: noqa: F401, F811
"""A Nice oferece o site e diz onde está a sacola (OC-18, §4.4, J6; #3518).

O turno inteiro pelo harness (``service.run_turn``, sem modelo), com a ponte ligada
por override (``SHOPMAN_CONCIERGE["transfer_enabled"]``), e a troca do link pela API
da loja, de verdade:

- **Ida (C01 pela conversa).** "Quero ver as fotos no site": a Nice manda o link, que
  leva a OFERTA da sacola, e diz que ela vai junto ao abrir o link e fica pausada aqui.
  Oferecer não tira a sacola daqui; a troca do link é o aceite.
- **A mensagem seguinte.** A sacola da conversa foi aceita no site (``transferred_to``):
  a Nice diz onde ela está, uma vez, antes da resposta do turno, e como trazê-la de volta.
- **Volta (a oferta inversa).** "Traz a sacola para cá": oferta e aceite no mesmo turno,
  pelo serviço de transferência; nunca mescla com a sacola que a conversa já tem.
- **C09.** Quem não pede o site nunca recebe o link; frase com negação não é pedido.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from django.test import Client
from shopman.orderman.models import Session

from shopman.shop.models import Conversation, ConversationBinding
from shopman.shop.models import ConversationMessage as Message
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions
from shopman.storefront.concierge import service, site_passage, tools
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    CONCIERGE_SETTINGS,
    SKU,
    _binding,
    _create_inbound,
    _pickup_ready,
    _reclaim,
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


def _turn(conversation, text: str) -> str:
    _create_inbound(conversation, text, f"oc18-{Message.objects.count()}")
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=None)
    service.run_turn(conversation.pk, _binding(conversation).pk)
    return (
        Message.objects.filter(conversation=conversation, kind="reply").order_by("-pk").values_list("text", flat=True).first()
        or ""
    )


def _bridge(ctx, settings, value=None) -> None:
    """A ponte ligada por override (nunca ambiente vivo), e a mensagem da fixture já respondida."""
    settings.SHOPMAN_CONCIERGE = BRIDGE_ON if value is None else value
    Message.objects.filter(conversation=ctx.conversation, kind="inbound", consumed_by__isnull=True).update(
        consumed_by=Conversation.objects.get(pk=ctx.conversation.pk).turn_fence
    )


def _with_cart(ctx, settings, qty: int = 2) -> Session:
    """Sacola de ``qty`` pães na conversa, e a ponte ligada (override, nunca ambiente vivo)."""
    assert tools.set_item(ctx, SKU, qty)["ok"]
    _bridge(ctx, settings)
    ctx.conversation.refresh_from_db()
    return Session.objects.get(session_key=ctx.conversation.session_key, channel_ref=CHANNEL)


def _token(reply: str) -> str:
    url = next(word for word in reply.split() if word.startswith("http"))
    query = parse_qs(urlparse(url).query)
    return (query.get("t") or query.get("token") or [""])[0] or urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def _open_link(reply: str) -> Client:
    """A cliente abre o link no navegador: a troca do link é o aceite da sacola."""
    browser = Client()
    response = browser.post("/api/v1/auth/access/", {"token": _token(reply)})
    assert response.status_code == 200, response.content
    return browser


def _web_cart_of(browser: Client) -> Session:
    return Session.objects.get(session_key=browser.session["cart_session_key"], channel_ref=WEB)


def _holds(session_key: str) -> list:
    from shopman.stockman import Hold

    return list(
        Hold.objects.filter(metadata__reference=session_key, status__in=["pending", "confirmed"]).values_list("sku", "quantity")
    )


# ── O pedido do site: o que é e o que não é ──────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "quero ver as fotos no site",
        "Manda o link do site",
        "prefiro terminar pelo site",
        "me passa o link do cardápio",
        "qual o site de vocês?",
        "Posso finalizar pelo site?",
    ],
)
def test_the_customer_asks_for_the_site(text):
    assert site_passage.asks_for_site(text)


@pytest.mark.parametrize(
    "text",
    [
        "não quero o site, prefiro pedir por aqui",
        "o site não abre",
        "deu erro no site",
        "cadê meu pedido do site?",
        "quero 2 pães",
        "Olá! Quero continuar por aqui a sacola que montei no site (ref. NB-ABC123)",
        "quero entrar no site",
        "bom dia",
    ],
)
def test_c09_what_is_not_a_request_for_the_site(text):
    assert not site_passage.asks_for_site(text)


@pytest.mark.parametrize(
    "text", ["traz a sacola pra cá", "pode trazer a sacola", "prefiro pedir por aqui", "quero terminar pelo whatsapp"]
)
def test_the_customer_asks_to_bring_the_cart_here(text):
    assert site_passage.asks_to_bring_here(text)


@pytest.mark.parametrize(
    "text", ["não traz a sacola", "não quero pedir por aqui", "quero 2 pães", "manda o link do site", "oi"]
)
def test_what_is_not_a_request_to_bring_the_cart(text):
    assert not site_passage.asks_to_bring_here(text)


@pytest.mark.parametrize(
    ("text", "alone"),
    [
        ("não quero o site, prefiro pedir por aqui", True),
        ("prefiro pedir por aqui mesmo", True),
        ("não quero o site", True),
        ("quero 2 pães, prefiro pedir por aqui", False),
        ("prefiro pedir por aqui um croissant", False),
        ("manda o link do site", False),
    ],
)
def test_c09_a_message_only_about_the_channel(text, alone):
    assert site_passage.only_about_the_channel(text) is alone


# ── Ida e volta pelo harness (C01 pela conversa, #3518) ──────────────


def test_c01_the_nice_sends_the_site_and_the_cart_goes_along_only_when_the_link_opens(ctx, settings, outbox):
    chat = _with_cart(ctx, settings)

    reply = _turn(ctx.conversation, "quero ver as fotos no site")

    assert reply.startswith("Continue no site: http"), reply
    assert reply.endswith(tools.CART_GOES_ALONG), reply
    assert "—" not in reply
    chat.refresh_from_db()
    assert chat.state == "open" and "transferred_to" not in chat.data  # oferecer não leva
    assert not Session.objects.filter(channel_ref=WEB).exists()

    browser = _open_link(reply)

    web = _web_cart_of(browser)
    chat.refresh_from_db()
    assert chat.state == "abandoned" and chat.data["transferred_to"]["session_key"] == web.session_key
    assert [(item["sku"], int(item["qty"])) for item in web.items] == [(SKU, 2)]
    assert _holds(chat.session_key) == [] and len(_holds(web.session_key)) == 1  # nenhuma reserva dobrada


def test_3518_the_next_message_says_where_the_cart_is_once(ctx, settings, outbox):
    _with_cart(ctx, settings)
    _open_link(_turn(ctx.conversation, "manda o link do site"))

    reply = _turn(ctx.conversation, "oi")

    where = "Sua sacola está no site, com 2 itens (R$ 1,80). " + site_passage.BRING_IT_HERE
    assert where in reply, reply
    assert "—" not in reply
    again = _turn(ctx.conversation, "oi")
    assert "Sua sacola está no site" not in again  # uma vez só
    ctx.conversation.refresh_from_db()
    assert ctx.conversation.session_key == ""


def test_3518_the_inverse_offer_brings_the_site_cart_back_to_the_conversation(ctx, settings, outbox):
    _with_cart(ctx, settings)
    browser = _open_link(_turn(ctx.conversation, "quero ver as fotos no site"))
    web = _web_cart_of(browser)

    reply = _turn(ctx.conversation, "pode trazer a sacola pra cá")

    assert reply.startswith("Trouxe os itens do site para cá."), reply
    web.refresh_from_db()
    ctx.conversation.refresh_from_db()
    back = Session.objects.get(session_key=ctx.conversation.session_key, channel_ref=CHANNEL)
    assert back.state == "open" and back.data["transferred_from"]["session_key"] == web.session_key
    assert web.state == "abandoned" and web.data["transferred_to"]["session_key"] == back.session_key
    assert [(item["sku"], int(item["qty"])) for item in back.items] == [(SKU, 2)]
    assert _holds(web.session_key) == [] and len(_holds(back.session_key)) == 1
    assert Session.objects.filter(state="open", data__customer__ref=ctx.conversation.customer_ref).count() == 1


def test_x4_asking_twice_brings_the_cart_once(ctx, settings, outbox):
    _with_cart(ctx, settings)
    _open_link(_turn(ctx.conversation, "quero ver as fotos no site"))
    _turn(ctx.conversation, "traz a sacola pra cá")
    first = Conversation.objects.get(pk=ctx.conversation.pk).session_key

    again = _turn(ctx.conversation, "traz a sacola pra cá")

    assert Conversation.objects.get(pk=ctx.conversation.pk).session_key == first
    assert Session.objects.filter(state="open", data__customer__ref=ctx.conversation.customer_ref).count() == 1
    assert "Trouxe os itens" not in again


def _site_cart_and_own_cart(ctx, settings):
    """A sacola foi para o site, e a cliente começou outra aqui (1 pão)."""
    _with_cart(ctx, settings)
    web = _web_cart_of(_open_link(_turn(ctx.conversation, "quero ver as fotos no site")))
    started = _create_inbound(ctx.conversation, "quero 1 pão", "oc18-own-cart")
    _reclaim(ctx)
    assert tools.set_item(ctx, SKU, 1)["ok"]
    Message.objects.filter(pk=started.pk).update(consumed_by=ctx.conversation.turn_fence)
    return web, Conversation.objects.get(pk=ctx.conversation.pk).session_key


def test_the_inverse_offer_with_a_cart_here_too_merges_the_items(ctx, settings, outbox):
    """Decisão do dono (24/11): trazer mescla, sem pergunta; o mesmo item soma."""
    web, own = _site_cart_and_own_cart(ctx, settings)

    reply = _turn(ctx.conversation, "traz a sacola pra cá")

    assert reply.startswith("Trouxe os itens do site para cá."), reply
    web.refresh_from_db()
    assert web.state == "abandoned"
    here = Session.objects.get(session_key=own, channel_ref=CHANNEL)
    assert here.state == "open" and Conversation.objects.get(pk=ctx.conversation.pk).session_key == own
    assert [(item["sku"], int(item["qty"])) for item in here.items] == [(SKU, 3)]
    assert _holds(web.session_key) == [] and sum(int(qty) for _sku, qty in _holds(own)) == 3


@pytest.mark.parametrize("first", ["", "oi"])
def test_the_link_after_the_passage_says_the_cart_is_already_there(ctx, settings, outbox, first):
    _with_cart(ctx, settings)
    _open_link(_turn(ctx.conversation, "quero ver as fotos no site"))
    if first:
        _turn(ctx.conversation, first)  # o aviso de onde a sacola está já saiu

    reply = _turn(ctx.conversation, "me manda o link do site de novo")

    assert reply.startswith("Continue no site: http"), reply
    assert tools.CART_GOES_ALONG not in reply  # nada a levar: a sacola já está lá
    assert reply.endswith(site_passage.ALREADY_THERE)


def test_the_link_without_a_cart_carries_nothing(ctx, settings, outbox):
    _bridge(ctx, settings)

    reply = _turn(ctx.conversation, "manda o link do site")

    assert reply.startswith("Continue no site: http") and "\n" not in reply, reply
    assert not Session.objects.filter(channel_ref=WEB).exists()


def test_no_notice_when_the_site_cart_is_already_closed(ctx, settings, outbox):
    _with_cart(ctx, settings)
    web = _web_cart_of(_open_link(_turn(ctx.conversation, "quero ver as fotos no site")))
    sessions.abandon_session(session_key=web.session_key, channel_ref=WEB)  # venceu, ou virou pedido

    reply = _turn(ctx.conversation, "oi")

    assert "Sua sacola está no site" not in reply


def test_x1_without_the_right_to_bring_it_back_the_notice_has_no_offer(ctx, settings, outbox):
    _with_cart(ctx, settings)
    _open_link(_turn(ctx.conversation, "quero ver as fotos no site"))
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS  # a ponte desligada depois da passagem

    reply = _turn(ctx.conversation, "oi")

    assert "Sua sacola está no site, com 2 itens (R$ 1,80)." in reply
    assert site_passage.BRING_IT_HERE not in reply


def test_asking_for_the_cart_that_is_already_here_shows_it(ctx, settings, outbox):
    _with_cart(ctx, settings)

    reply = _turn(ctx.conversation, "traz a sacola pra cá")

    assert reply.startswith(site_passage.ALREADY_HERE), reply
    assert "2 × “Pão Francês”: R$ 1,80" in reply
    assert not Session.objects.filter(channel_ref=WEB).exists()


def test_asking_for_a_site_cart_that_does_not_exist_says_so(ctx, settings, outbox):
    _bridge(ctx, settings)

    assert _turn(ctx.conversation, "traz a sacola do site") == site_passage.NO_SITE_CART


def test_bring_with_a_product_is_an_order_not_the_cart(ctx, settings, outbox):
    _bridge(ctx, settings)

    assert site_passage.handle(ctx.conversation, _binding(ctx.conversation), "traz 2 pães pra cá") is None


# ── Com a ponte desligada, nada muda ─────────────────────────────────


def test_the_bridge_off_answers_as_before(ctx, settings, outbox):
    assert tools.set_item(ctx, SKU, 2)["ok"]
    _bridge(ctx, settings, CONCIERGE_SETTINGS)
    key = Conversation.objects.get(pk=ctx.conversation.pk).session_key

    reply = _turn(ctx.conversation, "quero ver as fotos no site")

    assert tools.CART_GOES_ALONG not in reply and "/a?t=" not in reply
    assert Session.objects.get(session_key=key).state == "open"
    assert site_passage.handle(ctx.conversation, _binding(ctx.conversation), "manda o link do site") is None


# ── C09: quem não quer trocar de canal nunca é empurrado ─────────────


def test_c09_a_conversation_that_never_asks_for_the_site_never_gets_the_link(ctx, settings, outbox):
    _bridge(ctx, settings)

    replies = [_turn(ctx.conversation, text) for text in ("oi", "não quero o site, prefiro pedir por aqui")]

    for reply in replies:
        assert "Continue no site" not in reply and "/a?t=" not in reply, reply
    assert replies[1] == site_passage.STAY_HERE_ASK
    assert not Session.objects.filter(channel_ref=WEB).exists()


def test_c09_staying_here_with_a_cart_shows_the_cart_and_never_the_site(ctx, settings, outbox):
    _with_cart(ctx, settings)

    reply = _turn(ctx.conversation, "prefiro pedir por aqui mesmo")

    assert reply.startswith(site_passage.STAY_HERE) and "Total: R$ 1,80" in reply, reply
    assert "site" not in reply


def test_c09_not_wanting_the_site_with_the_cart_there_says_where_it_is(ctx, settings, outbox):
    _with_cart(ctx, settings)
    _open_link(_turn(ctx.conversation, "quero ver as fotos no site"))
    _turn(ctx.conversation, "oi")

    reply = _turn(ctx.conversation, "não quero o site")

    assert reply == "\n\n".join((
        site_passage.STAY_HERE,
        "Sua sacola está no site, com 2 itens (R$ 1,80). " + site_passage.BRING_IT_HERE,
    ))


# ── A entrada de hoje do ManyChat (sem identificador de mensagem, ADR-050) ──


def _turn_at_least_once(conversation, text: str) -> str:
    """O turno pela entrada "pelo menos uma vez": autoridade de sacola, nunca a comercial completa."""
    message = _create_inbound(conversation, text, f"oc18-alo-{Message.objects.count()}")
    envelope = {**message.envelope, "input_assurance": "at_least_once", "event_identity_assurance": "unavailable"}
    envelope.pop("event_id", None)
    Message.objects.filter(pk=message.pk).update(envelope=envelope)
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=None)
    service.run_turn(conversation.pk, _binding(conversation).pk)
    return (
        Message.objects.filter(conversation=conversation, kind="reply").order_by("-pk").values_list("text", flat=True).first()
        or ""
    )


_PERSONAL = {
    "delivery_address": "Rua das Flores, 100",
    "delivery_address_structured": {"street": "Rua das Flores", "number": "100"},
    "is_gift": True,
    "recipient": "Maria",
    "gift_message": "Feliz aniversário",
    "order_notes": "Apto 3, falar com a Maria",
    "payment": {"method": "pix"},
    "fulfillment_type": "delivery",
}


def _personal_cart(ctx, settings) -> Session:
    """Sacola de 2 pães na conversa, com cliente, endereço, presente, observação e pagamento."""
    chat = _with_cart(ctx, settings)
    sessions.modify_session(
        session_key=chat.session_key, channel_ref=CHANNEL,
        ops=[{"op": "set_data", "path": key, "value": value} for key, value in _PERSONAL.items()],
    )
    chat.refresh_from_db()
    assert chat.data["customer"]["phone"] and chat.data["customer"]["name"] == "Ana"
    return chat


def test_c01_real_manychat_without_message_id_carries_the_cart_to_the_site(ctx, settings, outbox):
    """A decisão da #3529: pela entrada sem identificador, o convite com a sacola vale (autoridade de sacola)."""
    chat = _with_cart(ctx, settings)

    reply = _turn_at_least_once(ctx.conversation, "quero ver as fotos no site")

    assert reply.startswith("Continue no site: http") and reply.endswith(tools.CART_GOES_ALONG), reply
    assert "pausado" not in reply and "—" not in reply
    web = _web_cart_of(_open_link(reply))
    chat.refresh_from_db()
    assert chat.state == "abandoned" and chat.data["transferred_to"]["session_key"] == web.session_key
    assert [(item["sku"], int(item["qty"])) for item in web.items] == [(SKU, 2)]
    assert _holds(chat.session_key) == [] and len(_holds(web.session_key)) == 1


def test_3529_condition_1_the_cart_only_link_brings_no_person_to_the_site(ctx, settings, outbox):
    chat = _personal_cart(ctx, settings)
    phone = chat.data["customer"]["phone"]
    reply = _turn_at_least_once(ctx.conversation, "quero ver as fotos no site")
    browser = Client()

    exchanged = browser.post("/api/v1/auth/access/", {"token": _token(reply)})

    body = exchanged.json()
    assert exchanged.status_code == 200, body
    # Ninguém entrou: nem sessão, nem confiança no dispositivo, nem nome ou telefone na resposta.
    assert (body["is_authenticated"], body["customer_name"], body["customer_phone"], body["customer_ref"]) == (
        False, "", "", "",
    )
    assert "_auth_user_id" not in browser.session and "device_trusted" not in body
    web = _web_cart_of(browser)
    # A sacola chega sem dono e só com itens e quantidades.
    assert [(item["sku"], int(item["qty"])) for item in web.items] == [(SKU, 2)]
    carried = set(web.data) - {"origin_channel", "transferred_from", "delivery_date", "delivery_time_slot"}
    assert not carried & {"customer", "payment", "coupon_code", *_PERSONAL}, web.data
    assert web.handle_ref in (None, "") and web.data["transferred_from"]["channel_ref"] == CHANNEL
    # O que ficou para trás vai pelo nome do campo, e a loja pede ao fechar.
    assert body["cart_transfer"]["differences"] == [
        {"kind": "details_not_carried", "fields": [
            "delivery_address", "delivery_address_structured", "is_gift", "recipient", "gift_message",
        ]},
    ]
    # E a loja, para este navegador, não mostra ninguém.
    page = browser.get("/api/v1/storefront/cart/").content.decode()
    for secret in ("Ana", phone, phone[-8:], "Rua das Flores", "Maria", "Apto 3"):
        assert secret not in page, secret
    assert browser.get("/api/v1/account/summary/").status_code in (401, 403)


def test_3529_condition_2_the_cart_only_link_is_single_use_with_the_same_ttl(ctx, settings, outbox):
    from django.utils import timezone
    from shopman.doorman.models import AccessLink

    _with_cart(ctx, settings)
    cart_only = _turn_at_least_once(ctx.conversation, "quero ver as fotos no site")
    only = AccessLink.objects.order_by("-created_at").first()
    full = _turn(ctx.conversation, "manda o link do site de novo")  # a sacola segue aqui até a troca
    invite = AccessLink.objects.order_by("-created_at").first()

    assert only.metadata.get("cart_only") is True and "cart_only" not in invite.metadata
    assert invite.metadata["cart_transfer"]["items_only"] is False and only.metadata["cart_transfer"]["items_only"]
    # O mesmo prazo e a mesma porta do convite de hoje.
    assert (only.expires_at - only.created_at).total_seconds() == pytest.approx(
        (invite.expires_at - invite.created_at).total_seconds(), abs=1
    )
    assert only.audience == invite.audience
    assert full.startswith("Continue no site: http")

    first = Client().post("/api/v1/auth/access/", {"token": _token(cart_only)})
    again = Client().post("/api/v1/auth/access/", {"token": _token(cart_only)})

    assert first.status_code == 200 and again.status_code == 400  # uso único
    only.refresh_from_db()
    assert only.used_at is not None and only.user_id is None  # gasto, e ninguém entrou

    # Vencido não vale (um convite novo, com o prazo passado).
    stale_reply = _turn_at_least_once(ctx.conversation, "traz a sacola pra cá")
    assert stale_reply.startswith("Trouxe os itens do site para cá."), stale_reply
    late = _turn_at_least_once(ctx.conversation, "quero ver as fotos no site")
    AccessLink.objects.filter(pk=AccessLink.objects.order_by("-created_at").first().pk).update(
        expires_at=timezone.now() - timezone.timedelta(seconds=1)
    )
    assert Client().post("/api/v1/auth/access/", {"token": _token(late)}).status_code == 400


def test_3529_condition_3_the_link_goes_only_to_this_subscriber_in_this_turn(ctx, settings, monkeypatch):
    from shopman.doorman.models import AccessLink

    from shopman.storefront.concierge.transport import SendOutcome

    _with_cart(ctx, settings)
    sent: list[tuple[str, str]] = []

    def send(binding, text):
        sent.append((binding.subject, text))
        return SendOutcome("accepted", "accepted", f"test:{binding.subject}:{len(sent)}")

    monkeypatch.setattr("shopman.storefront.concierge.transport.send_for", send)

    reply = _turn_at_least_once(ctx.conversation, "quero ver as fotos no site")

    # A resposta com o link saiu uma vez, pelo vínculo desta conversa (o assinante dela).
    with_link = [subject for subject, text in sent if _token(reply) in text]
    assert with_link == [_binding(ctx.conversation).subject]
    link = AccessLink.objects.order_by("-created_at").first()
    assert link.metadata["conversation_id"] == ctx.conversation.pk
    # A ferramenta não aceita destinatário.
    assert tools.execute("send_web_link", {"destination": "checkout", "phone": "+5543999990000"}, ctx)[
        "error"
    ] == "invalid_input"
    # Fora do turno (sem a cerca e o vínculo que o turno prende), nada se cunha.
    loose = tools.ToolContext(conversation=Conversation.objects.get(pk=ctx.conversation.pk), channel_ref=CHANNEL)
    before = AccessLink.objects.count()
    assert tools.send_web_link(loose, "checkout")["error"] == "authority_unavailable"
    # Turno vencido por uma mensagem nova: a cerca mudou, e nada se cunha.
    _reclaim_with(ctx, "manda o link do site")
    Conversation.objects.filter(pk=ctx.conversation.pk).update(turn_fence=ctx.conversation.turn_fence + 1)
    assert tools.send_web_link(ctx, "checkout")["error"] == "authority_unavailable"
    assert AccessLink.objects.count() == before


def _reclaim_with(ctx, text: str) -> None:
    _create_inbound(ctx.conversation, text, f"oc18-fence-{Message.objects.count()}")
    _reclaim(ctx)


def test_manychat_without_message_id_and_no_cart_sends_the_public_site(ctx, settings, outbox):
    from shopman.doorman.models import AccessLink

    _bridge(ctx, settings)
    links = AccessLink.objects.count()

    reply = _turn_at_least_once(ctx.conversation, "manda o link do site")

    assert reply == f"Continue no site: {tools.public_site_url()}"
    assert AccessLink.objects.count() == links  # sem sacola, seria acesso à conta: não com esta autoridade


def test_manychat_without_message_id_still_brings_the_site_cart_back(ctx, settings, outbox):
    _with_cart(ctx, settings)
    web = _web_cart_of(_open_link(_turn(ctx.conversation, "quero ver as fotos no site")))

    notice = _turn_at_least_once(ctx.conversation, "oi")
    reply = _turn_at_least_once(ctx.conversation, "traz a sacola pra cá")

    assert site_passage.BRING_IT_HERE in notice  # a autoridade de sacola basta para trazer (ADR-050)
    assert reply.startswith("Trouxe os itens do site para cá."), reply
    web.refresh_from_db()
    assert web.state == "abandoned"


# ── C04: o número sem prova não leva a sacola de ninguém ─────────────


def test_c04_an_unverified_number_never_brings_the_site_cart(ctx, settings, outbox):
    _with_cart(ctx, settings)
    web = _web_cart_of(_open_link(_turn(ctx.conversation, "quero ver as fotos no site")))
    ConversationBinding.objects.filter(conversation=ctx.conversation).update(identity_assurance="unverified")

    notice = _turn(ctx.conversation, "oi")
    reply = _turn(ctx.conversation, "traz a sacola pra cá")

    assert site_passage.BRING_IT_HERE not in notice  # X1: sem prova, a oferta inversa não aparece
    assert "Trouxe os itens" not in reply, reply
    web.refresh_from_db()
    assert web.state == "open" and "transferred_to" not in web.data
    assert not Session.objects.filter(channel_ref=CHANNEL, state="open").exists()


# ── C10: o pedido feito no site é o mesmo pedido na conversa ─────────


def test_c10_the_order_placed_on_the_site_is_the_order_the_nice_reads(ctx, settings, outbox):
    from shopman.orderman.models import Order

    _with_cart(ctx, settings)
    web = _web_cart_of(_open_link(_turn(ctx.conversation, "quero ver as fotos no site")))
    Session.objects.filter(pk=web.pk).update(state="committed")
    Order.objects.create(
        ref="SITE-OC18", channel_ref=WEB, session_key=web.session_key, total_q=180,
        data={"customer_ref": ctx.conversation.customer_ref, "fulfillment_type": "pickup",
              "transferred_from": web.data["transferred_from"]},
    )

    notice = _turn(ctx.conversation, "oi")
    _create_inbound(ctx.conversation, "cadê meu pedido", f"oc18-{Message.objects.count()}")
    _reclaim(ctx)
    found = tools.order_status(ctx)

    assert "Sua sacola está no site" not in notice  # virou pedido: não há sacola a apontar
    assert [order["order_ref"] for order in found["orders"]] == ["SITE-OC18"]
    assert Order.objects.get(ref="SITE-OC18").data["transferred_from"]["channel_ref"] == CHANNEL
