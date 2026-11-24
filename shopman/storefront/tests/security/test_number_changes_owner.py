"""Número de WhatsApp que muda de dono não herda a conta (D3, OC-07).

O cenário adversarial do laudo (S3): a operadora recicla o número da Ana e ele cai
com o Bruno. O assinante do WhatsApp é o número, então o Bruno escreve pelo MESMO
assinante, passa no código do MESMO número e toca no MESMO link. As camadas:

(a) o número sozinho pede, vê os pedidos recentes e paga; endereço salvo, histórico
    completo e troca de dados pedem acesso de dispositivo;
(b) prova do número vencida (mais de 12 meses) volta a pedir prova;
(c) o sinal de troca de dono tira o número do cadastro antigo e desliga a conversa;
(d) "não sou eu / troquei de número" desliga o vínculo antigo.

O casamento de pedido por telefone (o Bruno ver pedido da Ana por coincidência de
número) é do OC-02 (#3436) e não é repetido aqui.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from shopman.doorman.models import AccessLink, TrustedDevice
from shopman.guestman.adapters.auth import IdentityResolver
from shopman.guestman.contrib.manychat.service import ManychatService
from shopman.guestman.models import ContactPoint, Customer, CustomerAddress
from shopman.guestman.services import identity as identity_service
from shopman.orderman.models import Order

from shopman.shop.models import Conversation, ConversationBinding
from shopman.shop.services import auth as auth_service
from shopman.storefront.concierge import service as concierge
from shopman.storefront.concierge.contracts import InboundEvent, TransportScope
from shopman.storefront.identity import IDENTITY_NUMBER, IDENTITY_SESSION_KEY

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

NUMERO = "+5543999992001"
ASSINANTE = "990001"


# ── O mundo da Ana, antes de perder o número ─────────────────────────


@pytest.fixture
def ana():
    """Entrou pelo WhatsApp (assinante 990001), tem endereço, pedido e conversa."""
    customer, created = ManychatService.sync_subscriber(
        {"id": ASSINANTE, "first_name": "Ana", "whatsapp_id": NUMERO}
    )
    assert created
    CustomerAddress.objects.create(
        customer=customer,
        formatted_address="Rua das Flores, 123 - Centro, Londrina - PR",
        label="home",
        is_default=True,
        route="Rua das Flores",
        street_number="123",
        neighborhood="Centro",
        city="Londrina",
    )
    return customer


def _conversa(customer, *, subject=ASSINANTE):
    conversation = Conversation.objects.create(
        customer_ref=customer.ref, customer_name=customer.name, phone=NUMERO,
    )
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="manychat-account",
        transport_channel="whatsapp",
        subject=subject,
        connection_key="manychat-wa",
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER,
        activated_at=timezone.now(),
    )
    return conversation, binding


def _pedido(customer, *, ref, days_ago=0, status="completed"):
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=1500,
        data={"customer_ref": customer.ref},
    )
    if days_ago:
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return order


def _entrar(client: Client, customer: Customer, *, strength: str | None = None) -> None:
    from shopman.doorman import get_or_create_user_for_customer

    from shopman.storefront.tests.identity_fakes import make_identity_view

    info = make_identity_view(
        subject_id=customer.uuid, name=customer.name, phone=customer.phone, is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    if strength:
        session = client.session
        session[IDENTITY_SESSION_KEY] = strength
        session.save()


def _prova_do_numero_ha(customer, days: int) -> None:
    ContactPoint.objects.filter(customer=customer, value_normalized=NUMERO).update(
        is_verified=True, verified_at=timezone.now() - timedelta(days=days),
    )


def _evento(subject=ASSINANTE) -> InboundEvent:
    return InboundEvent(
        scope=TransportScope(
            provider="manychat",
            account="manychat-account",
            channel="whatsapp",
            subject=subject,
            connection_key="manychat-wa",
        ),
        text="oi",
        message_type="text",
        received_at=timezone.now(),
    )


# ── (c) O sinal de troca de dono ─────────────────────────────────────


def test_numero_reciclado_o_novo_titular_nao_herda_endereco_pedido_nem_conversa(ana):
    conversa_da_ana, vinculo = _conversa(ana)
    _pedido(ana, ref="ORD-ANA-1")
    fence = conversa_da_ana.turn_fence

    auth_service.release_reassigned_number(NUMERO, source="camara_number_recycling")

    # O número não abre mais a conta da Ana: nem por código, nem pelo assinante.
    assert IdentityResolver().resolve("phone", NUMERO) is None
    vinculo.refresh_from_db()
    assert vinculo.identity_assurance == ConversationBinding.IdentityAssurance.UNVERIFIED
    assert vinculo.status == ConversationBinding.Status.DISABLED
    assert vinculo.subject != ASSINANTE
    conversa_da_ana.refresh_from_db()
    assert conversa_da_ana.turn_fence == fence + 1
    assert conversa_da_ana.customer_ref == ana.ref  # a história da Ana fica com a Ana

    # O Bruno escreve pelo MESMO assinante e nasce cadastro próprio.
    bruno, created = ManychatService.sync_subscriber(
        {"id": ASSINANTE, "first_name": "Bruno", "whatsapp_id": NUMERO}
    )
    assert created and bruno.pk != ana.pk
    assert not bruno.addresses.exists()
    from shopman.storefront.services import orders as order_service

    assert order_service.order_history_for_customer(customer_ref=bruno.ref, filter_param="todos") == []

    # E a mensagem dele abre uma conversa nova, sem a transcrição da Ana.
    novo_vinculo = concierge._get_or_create_binding(_evento())
    assert novo_vinculo.conversation_id != conversa_da_ana.pk
    assert novo_vinculo.conversation.customer_ref == ""


def test_trocar_o_proprio_numero_desliga_a_conversa_do_numero_antigo(ana):
    _conversa_da_ana, vinculo = _conversa(ana)

    identity_service.replace_primary_contact(ana, field="phone", new_value="+5543999992999")

    vinculo.refresh_from_db()
    assert vinculo.status == ConversationBinding.Status.DISABLED
    assert vinculo.identity_assurance == ConversationBinding.IdentityAssurance.UNVERIFIED


def test_conversa_de_outro_numero_da_mesma_pessoa_fica_intacta(ana):
    outra = Conversation.objects.create(customer_ref=ana.ref, phone="+5543999992888")
    vinculo = ConversationBinding.objects.create(
        conversation=outra,
        provider="manychat",
        account="manychat-account",
        transport_channel="whatsapp",
        subject="990777",
        connection_key="manychat-wa",
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER,
    )

    auth_service.release_reassigned_number(NUMERO, source="camara_number_recycling")

    vinculo.refresh_from_db()
    assert vinculo.status == ConversationBinding.Status.ACTIVE
    assert vinculo.identity_assurance == ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER


# ── (b) Prova do número vencida volta a pedir prova ──────────────────


def test_prova_do_numero_vence_em_12_meses(ana):
    _prova_do_numero_ha(ana, 300)
    assert not auth_service.number_proof_expired(customer_ref=ana.ref, phone=NUMERO)

    _prova_do_numero_ha(ana, 400)
    assert auth_service.number_proof_expired(customer_ref=ana.ref, phone=NUMERO)
    assert auth_service.number_proof_expired(customer_uuid=ana.uuid, phone=NUMERO)


def test_codigo_no_numero_renova_a_prova(ana):
    _prova_do_numero_ha(ana, 400)

    IdentityResolver().bind_verified_handle(ana.uuid, "phone", NUMERO, proof="whatsapp")

    assert not auth_service.number_proof_expired(customer_ref=ana.ref, phone=NUMERO)


def test_conversa_com_prova_vencida_perde_a_verificacao(ana):
    conversation, binding = _conversa(ana)
    _prova_do_numero_ha(ana, 400)

    assert concierge._number_proof_lapsed(conversation, binding) is True

    binding.refresh_from_db()
    assert binding.identity_assurance == ConversationBinding.IdentityAssurance.UNVERIFIED


def test_conversa_com_prova_recente_segue_verificada(ana):
    conversation, binding = _conversa(ana)
    _prova_do_numero_ha(ana, 30)

    assert concierge._number_proof_lapsed(conversation, binding) is False

    binding.refresh_from_db()
    assert binding.identity_assurance == ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER


def test_assinante_com_prova_vencida_nao_e_reconhecido_pela_concierge(ana, monkeypatch):
    from shopman.storefront.concierge import transport

    info = auth_service.identity_by_customer_ref(ana.ref)
    monkeypatch.setattr(auth_service, "identify_manychat_subject", lambda subject: info)
    adapter = transport.ManyChatWhatsAppAdapter.__new__(transport.ManyChatWhatsAppAdapter)

    _prova_do_numero_ha(ana, 30)
    assert adapter.identify(ASSINANTE, {}).verified

    _prova_do_numero_ha(ana, 400)
    assert not adapter.identify(ASSINANTE, {}).verified


def _link_da_mensagem(customer):
    _link, raw = AccessLink.create_with_token(
        customer_id=customer.uuid,
        audience=AccessLink.Audience.WEB_ACCOUNT,
        source=AccessLink.Source.MANYCHAT,
        expires_at=timezone.now() + timedelta(minutes=10),
        metadata={"next": "/conta"},
    )
    return raw


def test_link_da_mensagem_com_prova_vencida_sabe_so_o_numero(client, ana):
    _prova_do_numero_ha(ana, 400)

    response = client.post("/api/v1/auth/access/", {"token": _link_da_mensagem(ana)})

    assert response.status_code == 200, response.content
    assert response.json()["identity_strength"] == IDENTITY_NUMBER
    assert "device_trusted" not in response.json()
    assert not TrustedDevice.objects.filter(subject_id=str(ana.uuid)).exists()
    endereco = client.get("/api/v1/account/addresses/").json()[0]
    assert "Rua das Flores" not in json.dumps(endereco)


def test_link_da_mensagem_com_prova_recente_confia_como_sempre(client, ana):
    _prova_do_numero_ha(ana, 30)

    response = client.post("/api/v1/auth/access/", {"token": _link_da_mensagem(ana)})

    assert response.status_code == 200
    assert response.json()["device_trusted"] is True


# ── (a) O número sozinho não lê endereço, histórico nem troca dados ──


def test_sessao_de_numero_nao_le_endereco_pela_porta_da_edicao(client, ana):
    """O PATCH devolvia o endereço INTEIRO: a lista reduzia, a edição entregava."""
    _entrar(client, ana, strength=IDENTITY_NUMBER)
    address = ana.addresses.get()

    for response in (
        client.patch(f"/api/v1/account/addresses/{address.pk}/", data="{}", content_type="application/json"),
        client.post(f"/api/v1/account/addresses/{address.pk}/?action=default"),
        client.delete(f"/api/v1/account/addresses/{address.pk}/"),
    ):
        assert response.status_code == 403, response.content
        assert response.json()["code"] == "step_up_required"
        assert "Rua das Flores" not in response.content.decode()
    assert ana.addresses.filter(pk=address.pk).exists()


def test_sessao_de_numero_edita_o_endereco_que_ela_mesma_criou(client, ana):
    """O checkout cria o endereço e logo dá o apelido: isso não é mexer no cadastro de antes."""
    _entrar(client, ana, strength=IDENTITY_NUMBER)
    created = client.post(
        "/api/v1/account/addresses/",
        data=json.dumps({"label": "home", "formatted_address": "Rua Nova, 9 - Centro, Londrina - PR"}),
        content_type="application/json",
    )
    assert created.status_code == 201

    response = client.patch(
        f"/api/v1/account/addresses/{created.json()['id']}/",
        data=json.dumps({"label": "other", "label_custom": "Trabalho"}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content


def test_sessao_de_numero_nao_troca_o_nome(client, ana):
    _entrar(client, ana, strength=IDENTITY_NUMBER)

    response = client.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "Bruno"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "step_up_required"
    ana.refresh_from_db()
    assert ana.first_name == "Ana"


def test_sessao_de_numero_ve_so_os_pedidos_recentes(client, ana):
    _pedido(ana, ref="ORD-ANA-ANTIGO", days_ago=90)
    _pedido(ana, ref="ORD-ANA-RECENTE", days_ago=3)
    _entrar(client, ana, strength=IDENTITY_NUMBER)

    body = client.get("/api/v1/account/orders/").json()

    assert [order["ref"] for order in body["orders"]] == ["ORD-ANA-RECENTE"]
    assert body["counts"]["total"] == 1


def test_sessao_de_dispositivo_ve_o_historico_completo(client, ana):
    _pedido(ana, ref="ORD-ANA-ANTIGO", days_ago=90)
    _pedido(ana, ref="ORD-ANA-RECENTE", days_ago=3)
    _entrar(client, ana)

    body = client.get("/api/v1/account/orders/").json()

    assert {order["ref"] for order in body["orders"]} == {"ORD-ANA-ANTIGO", "ORD-ANA-RECENTE"}
    assert body["counts"]["total"] == 2


# ── (d) "Não sou eu / troquei de número" ─────────────────────────────


def test_nao_sou_eu_pede_confirmacao_e_nada_muda_sem_ela(client, ana):
    _entrar(client, ana)

    response = client.post("/api/v1/account/not-me/", data="{}", content_type="application/json")

    assert response.status_code == 400
    assert response.json()["code"] == "confirmation_required"
    assert IdentityResolver().resolve("phone", NUMERO).subject_id == ana.uuid


def test_nao_sou_eu_desliga_o_numero_da_conta_e_encerra_a_sessao(client, ana):
    """O Bruno entrou pelo código no número que era da Ana e diz: não sou eu."""
    _conversa_da_ana, vinculo = _conversa(ana)
    _entrar(client, ana)

    response = client.post(
        "/api/v1/account/not-me/", data=json.dumps({"confirm": True}), content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["released"] is True
    assert IdentityResolver().resolve("phone", NUMERO) is None
    vinculo.refresh_from_db()
    assert vinculo.status == ConversationBinding.Status.DISABLED
    assert client.get("/api/v1/account/addresses/").status_code == 401
    ana.refresh_from_db()
    assert ana.phone == ""
    assert ana.addresses.exists()  # o endereço segue da Ana; só o número saiu
