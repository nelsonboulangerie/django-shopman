# ruff: noqa: F401, F811
"""A mensagem de entrada no site não é conversa (dono, 25/11/2026).

Medido no ar, conversa 2, 25/11 12:11: "Olá! Quero entrar no site da Nelson Boulangerie
(ref. NB-DETPVA)" virou 'Sobre "Quero entrar no site…", já chamei a equipe' e a conversa
foi à equipe; nenhum link de acesso nasceu, e o dono não entrou. O pedido de entrada é
atendido pela casa: o link sai com o contexto do código, a mensagem de entrada é a da casa,
e a Nice não responde por cima nem chama a equipe.
"""

from __future__ import annotations

import json

import pytest
from shopman.doorman.models import AccessLink
from shopman.doorman.services.link_state import store_state

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import login_door, service
from shopman.storefront.tests.test_concierge_engine import (
    PHONE,
    SUBJECT,
    _binding,
    _receive,
    conversation,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db

REAL = "Olá! Quero entrar no site da Nelson Boulangerie (ref. {code})"


@pytest.fixture
def delivered(monkeypatch):
    """O que a casa manda pelo ManyChat quando o link nasce (``shop.handlers.access_link``)."""
    sent = []

    def notify(*, event, recipient, context, backend):
        sent.append({"event": event, "recipient": recipient, "context": context, "backend": backend})
        return type("R", (), {"success": True, "error": ""})()

    monkeypatch.setattr("shopman.shop.notifications.notify", notify)
    return sent


def _turn(conversation, text, event_id="login-1"):
    _receive(conversation, text, event_id)
    return service.run_turn(conversation.pk, _binding(conversation).pk)


def test_the_real_login_message_logs_in_and_the_nice_stays_quiet(
    conversation, outbox, delivered, django_capture_on_commit_callbacks
):
    code = store_state({"site_return": "phone", "next": "/sacola"})
    with django_capture_on_commit_callbacks(execute=True):
        _turn(conversation, REAL.format(code=code))
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE  # nunca equipe
    assert outbox.sent == []  # a Nice não responde por cima da mensagem de entrada
    assert not Message.objects.filter(conversation=conversation, kind=Message.Kind.NOTE).exists()
    link = AccessLink.objects.get()
    assert link.metadata["login_source"] == "concierge" and link.metadata["deliver_to"] == SUBJECT
    assert link.metadata["site_return"] == "phone" and link.metadata["next"] == "/sacola"
    assert [(d["event"], d["recipient"], d["backend"]) for d in delivered] == [("access_link", SUBJECT, "manychat")]
    assert delivered[0]["context"]["access_caption"] == "Voltar à loja"
    assert not Message.objects.filter(conversation=conversation, kind=Message.Kind.INBOUND,
                                      consumed_by__isnull=True).exists()


def test_an_expired_code_says_how_to_try_again_and_never_calls_the_team(conversation, outbox, delivered):
    _turn(conversation, REAL.format(code="NB-DETPVA"))
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE
    assert outbox.sent == [login_door.EXPIRED]
    assert not AccessLink.objects.exists() and delivered == []


def _manychat_endpoint(customer, text, settings):
    """O External Request do fluxo do ManyChat com a mesma mensagem (``AccessLinkCreateView``)."""
    import json

    from django.test import RequestFactory
    from shopman.doorman.views.access_link import AccessLinkCreateView

    settings.DOORMAN = {**getattr(settings, "DOORMAN", {}), "ACCESS_LINK_API_KEY": "chave-de-teste"}
    request = RequestFactory().post(
        "/auth/access-link/create/",
        json.dumps({"customer_id": str(customer.uuid), "access_code": text, "subscriber_id": SUBJECT,
                    "whatsapp_id": PHONE}),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer chave-de-teste",
    )
    return AccessLinkCreateView.as_view()(request)


def test_when_the_manychat_flow_answered_first_the_concierge_stays_quiet(
    conversation, customer, outbox, delivered, settings, django_capture_on_commit_callbacks
):
    """A corrida, de um lado: o fluxo do ManyChat consumiu a referência e criou o link."""
    code = store_state({"site_return": "phone", "next": "/finalizar"})
    with django_capture_on_commit_callbacks(execute=True):
        assert _manychat_endpoint(customer, REAL.format(code=code), settings).status_code == 200
        _turn(conversation, REAL.format(code=code))
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE
    assert outbox.sent == [] and AccessLink.objects.count() == 1
    assert len(delivered) == 1  # uma mensagem de entrada só


def test_when_the_concierge_answered_first_the_manychat_flow_makes_no_second_link(
    conversation, customer, outbox, delivered, settings, django_capture_on_commit_callbacks
):
    """A corrida, do outro (#3621): sem a marca, o endpoint criava um segundo link com o aviso
    falso de "sua sacola não veio"."""
    code = store_state({"site_return": "phone", "next": "/finalizar"})
    with django_capture_on_commit_callbacks(execute=True):
        _turn(conversation, REAL.format(code=code))
        response = _manychat_endpoint(customer, REAL.format(code=code), settings)
    assert response.status_code == 200 and json.loads(response.content)["already_answered"] is True
    link = AccessLink.objects.get()
    assert "handoff_expired" not in link.metadata and link.metadata["next"] == "/finalizar"
    assert len(delivered) == 1


def test_an_old_link_of_another_reference_does_not_silence_an_expired_one(
    conversation, customer, outbox, delivered, settings, django_capture_on_commit_callbacks
):
    """A marca é da referência: o link de outra entrada, mesmo recente, não cala a vencida."""
    other = store_state({"site_return": "phone"})
    with django_capture_on_commit_callbacks(execute=True):
        _turn(conversation, REAL.format(code=other), "login-outra")
    _turn(conversation, REAL.format(code="NB-DETPVA"), "login-vencida")
    assert outbox.sent == [login_door.EXPIRED]


def test_with_the_team_the_login_still_goes_through(
    conversation, outbox, delivered, django_capture_on_commit_callbacks
):
    Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.HANDOFF)
    code = store_state({"site_return": "phone"})
    with django_capture_on_commit_callbacks(execute=True):
        intake = _receive(conversation, REAL.format(code=code), "login-team")
    assert intake.reason == "login"
    assert AccessLink.objects.get().metadata["login_source"] == "concierge"
    assert [d["recipient"] for d in delivered] == [SUBJECT]
    assert outbox.sent == []


def test_an_unverified_number_is_told_how_to_try_again(conversation, outbox, delivered):
    from shopman.shop.models import ConversationBinding

    ConversationBinding.objects.filter(conversation=conversation).update(identity_assurance="unverified")
    code = store_state({"site_return": "phone"})
    assert login_door.answer(conversation, _binding(conversation), REAL.format(code=code)) == login_door.NOT_CONFIRMED
    assert not AccessLink.objects.exists()


@pytest.mark.parametrize("text", ["quero 2 croissants", "entrar no site amanhã cedo?", "NB-ABC234"])
def test_other_messages_are_not_the_login(text):
    assert not login_door.is_login(text)


def test_the_link_honours_the_site_destination_like_the_manychat_endpoint(
    conversation, outbox, delivered, django_capture_on_commit_callbacks, settings
):
    """Quem tocou em Finalizar volta a Finalizar (DEV-2026-092, #3619): o link da Concierge leva o
    contexto da referência pelo MESMO serviço do ``AccessLinkCreateView`` (``site_context``)."""
    from urllib.parse import parse_qs, urlparse

    from rest_framework.test import APIClient

    settings.RATELIMIT_ENABLE = False
    code = store_state({"site_return": "phone", "next": "/finalizar"})
    with django_capture_on_commit_callbacks(execute=True):
        _turn(conversation, REAL.format(code=code), "login-finalizar")
    link = AccessLink.objects.get()
    # A marca do contexto do site que a troca reconhece (``access.link_carries_site_context``, #3619).
    assert link.metadata["site_return"] == "phone"
    token = parse_qs(urlparse(delivered[0]["context"]["access_url"]).query)["t"][0]
    response = APIClient().post("/api/v1/auth/access/", {"token": token}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["redirect"] == "/finalizar"
