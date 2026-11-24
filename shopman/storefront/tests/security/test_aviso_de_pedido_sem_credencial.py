"""OC-01 · aviso de pedido não carrega credencial (decisão D5 do dono, invariante X6).

Antes, todo aviso de pedido de cliente identificado levava um link de entrada
(``/a?t=<token>``) cunhado com ``source="manychat"``. Trocado, ele dava identidade
forte e confiança de dispositivo por 180 dias: um aviso encaminhado e aberto a tempo
entregava a conta. Agora o aviso leva o link COMUM do pedido (``/pedido/<ref>``):

- o texto renderizado de TODO aviso de pedido, em todo canal, não tem token;
- quem recebe o aviso encaminhado não abre a conta nem o pedido;
- o dono, no próprio celular (sessão ou dispositivo confiável), abre direto;
- em outro dispositivo, a entrada pelo WhatsApp volta para o mesmo pedido, e o link
  que o PRÓPRIO cliente pediu continua confiando no dispositivo como antes.
"""
from __future__ import annotations

import json
import re

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from shopman.doorman.models import AccessLink
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.adapters import notification_email, notification_manychat, notification_sms
from shopman.shop.adapters._notification_templates import derive_context, render_message, render_template
from shopman.shop.services import notification as notification_service
from shopman.storefront.tests.identity_fakes import proven

from .conftest import login_as_customer

pytestmark = pytest.mark.django_db

LOJA = "https://loja.test"
REF = "ORD-OC01"
TELEFONE = "+5543999990777"

#: Prefixos dos eventos servidos por ``notification._build_context`` (fluxo de pedido),
#: os mesmos do guardrail de placeholders.
_ORDER_EVENT_PREFIXES = ("order_", "payment_", "waitlist_", "preorder_", "loyalty_")

#: Qualquer forma de link de entrada: a rota ``/a?t=`` e o token na query.
_CREDENCIAL = re.compile(r"/a\?t=|[?&]t=")

WA_SETTINGS = {"number": "554333231997", "ttl_seconds": 600}
ACCESS_SETTINGS = {
    "ACCESS_LINK_API_KEY": "test-access-key",
    "ACCESS_LINK_ENTRY_URL": LOJA,
    "IDENTITY_RESOLVER_CLASS": "shopman.guestman.adapters.auth.IdentityResolver",
}


@pytest.fixture(autouse=True)
def _sem_portarias_de_ritmo(settings):
    settings.RATELIMIT_ENABLE = False
    settings.SHOPMAN_STOREFRONT_BASE_URL = LOJA
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def dona(db) -> Customer:
    # A dona já provou o número (contato sem prova não abre a conta, OC-08).
    return proven(Customer.objects.create(ref="CUS-OC01", first_name="Lia", phone=TELEFONE))


@pytest.fixture
def pedido(channel, dona) -> Order:
    """Pedido de cliente IDENTIFICADO (com ``customer.uuid``): o que cunhava o link de entrada."""
    return Order.objects.create(
        ref=REF,
        channel_ref=channel.ref,
        status="new",
        total_q=4200,
        handle_type="phone",
        handle_ref=TELEFONE,
        data={
            "customer_ref": dona.ref,
            "customer": {"ref": dona.ref, "uuid": str(dona.uuid), "name": "Lia", "phone": TELEFONE},
            "fulfillment_type": "pickup",
            "payment": {"method": "pix", "status": "pending", "copy_paste": "00020126PIXOC01"},
        },
    )


def _eventos_de_pedido() -> set[str]:
    from config.management.commands.seed import NOTIFICATION_TEMPLATES
    from shopman.shop.models import NotificationTemplate

    eventos = set(NOTIFICATION_TEMPLATES)
    eventos |= set(NotificationTemplate.objects.values_list("event", flat=True))
    for textos in (
        notification_manychat.MESSAGE_TEMPLATES,
        notification_sms.MESSAGE_TEMPLATES,
        notification_email.BODY_TEMPLATES,
        notification_email.SUBJECT_TEMPLATES,
    ):
        eventos |= set(textos)
    return {evento for evento in eventos if evento.startswith(_ORDER_EVENT_PREFIXES)}


def _textos_renderizados(pedido: Order) -> dict[str, str]:
    """Todo texto de aviso de pedido que um cliente pode receber, já renderizado.

    Admin (o que as migrações semeiam no banco), seed e o fallback de cada canal, para
    cada evento de pedido e para a variante qualificada dele (Pix, entrega...).
    """
    from config.management.commands.seed import NOTIFICATION_TEMPLATES

    textos: dict[str, str] = {}
    for evento in sorted(_eventos_de_pedido()):
        contexto = notification_service._build_context(pedido, {"order_ref": pedido.ref}, evento)
        qualificado = notification_service._qualify_template(evento, contexto)
        derivado = derive_context(contexto)
        for nome in {evento, qualificado}:
            for canal, fallback in (
                ("whatsapp", notification_manychat.MESSAGE_TEMPLATES),
                ("sms", notification_sms.MESSAGE_TEMPLATES),
                ("email", notification_email.BODY_TEMPLATES),
            ):
                textos[f"{canal}[{nome}]"] = render_message(nome, contexto, fallback)
            assunto = notification_email.SUBJECT_TEMPLATES.get(nome)
            if assunto:
                textos[f"email.assunto[{nome}]"] = render_template(assunto, derivado)
            semeado = NOTIFICATION_TEMPLATES.get(nome)
            if semeado:
                corpo = f"{semeado.get('subject') or ''}\n{semeado.get('body') or ''}"
                textos[f"seed[{nome}]"] = render_template(corpo, derivado)
    return textos


# ── X6: nenhum texto de aviso carrega credencial ─────────────────────────────


def test_todo_aviso_de_pedido_renderizado_nao_carrega_credencial(pedido):
    textos = _textos_renderizados(pedido)

    assert len(textos) > 50, "o varredor tem de achar os textos, não passar vazio"
    assert any(f"{LOJA}/pedido/{REF}" in texto for texto in textos.values()), (
        "algum aviso tem de levar o link comum do pedido, senão a varredura não prova nada"
    )
    com_credencial = sorted(nome for nome, texto in textos.items() if _CREDENCIAL.search(texto))
    assert not com_credencial, f"aviso com link de entrada (token): {com_credencial}"
    assert not AccessLink.objects.exists(), "montar aviso de pedido não cunha link de entrada"


def test_links_do_aviso_sao_os_comuns_do_pedido(pedido):
    contexto = notification_service._build_context(pedido, {"order_ref": REF}, "order_ready")

    assert contexto["tracking_url"] == f"{LOJA}/pedido/{REF}"
    assert contexto["payment_url"] == f"{LOJA}/pedido/{REF}"
    assert contexto["reorder_url"] == f"{LOJA}/conta/pedidos"


# ── Encaminhado: quem recebe não abre conta nem pedido ───────────────────────


def test_aviso_encaminhado_nao_abre_conta_nem_pedido(pedido, attacker):
    contexto = notification_service._build_context(pedido, {"order_ref": REF}, "payment_requested")
    for chave in ("tracking_url", "payment_url", "reorder_url"):
        assert not _CREDENCIAL.search(contexto[chave]), chave
    assert not AccessLink.objects.exists(), "não há token nenhum para o encaminhado trocar"

    # O link comum abre `/pedido/<ref>`, que pergunta ao Django por estes endpoints.
    assert attacker.get(f"/api/v1/tracking/{REF}/").status_code == 404
    assert attacker.get(f"/api/v1/payment/{REF}/").status_code == 404
    sessao = attacker.get("/api/v1/auth/session/").json()
    assert sessao["is_authenticated"] is False


# ── Dono no próprio celular: abre direto ─────────────────────────────────────


def test_dono_com_sessao_no_proprio_celular_abre_direto(pedido, dona):
    celular = Client()
    login_as_customer(celular, dona)

    resposta = celular.get(f"/api/v1/tracking/{REF}/")
    assert resposta.status_code == 200
    assert resposta.json()["ref"] == REF


def test_dono_com_dispositivo_confiavel_entra_sem_codigo_e_abre_o_pedido(pedido, dona):
    from shopman.doorman import TrustedDevice
    from shopman.doorman.conf import doorman_settings

    celular = Client()
    _, cookie = TrustedDevice.create_for(
        "customer", dona.uuid, user_agent="Mozilla/5.0 Test", ip_address="127.0.0.1"
    )
    celular.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = cookie
    assert celular.get(f"/api/v1/tracking/{REF}/").status_code == 404

    entrada = celular.post(
        "/api/v1/auth/device-check/", data={"target": TELEFONE}, content_type="application/json"
    )
    assert entrada.status_code == 200
    assert entrada.json()["trusted"] is True

    assert celular.get(f"/api/v1/tracking/{REF}/").status_code == 200


# ── Outro dispositivo: a entrada pelo WhatsApp volta para o pedido ───────────


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=ACCESS_SETTINGS)
def test_em_outro_dispositivo_a_entrada_pelo_whatsapp_volta_ao_pedido(pedido, dona):
    """``/pedido/<ref>`` sem sessão manda a ``/entrar?next=/pedido/<ref>``; o código NB
    carrega o destino, a mensagem do próprio cliente gera o link, e a troca cai no pedido.
    """
    outro = Client()
    assert outro.get(f"/api/v1/tracking/{REF}/").status_code == 404

    inicio = outro.post(
        "/api/v1/auth/whatsapp/start/",
        data=json.dumps({"next": f"/pedido/{REF}"}),
        content_type="application/json",
    ).json()
    assert inicio["code"].startswith("NB-")

    criado = Client().post(
        "/api/auth/access/create/",
        data=json.dumps({"customer_id": str(dona.uuid), "access_code": inicio["message"]}),
        content_type="application/json",
        HTTP_X_API_KEY=ACCESS_SETTINGS["ACCESS_LINK_API_KEY"],
    )
    assert criado.status_code == 200, criado.content

    troca = outro.post(
        "/api/v1/auth/access/",
        data=json.dumps({"token": criado.json()["token"]}),
        content_type="application/json",
    )
    assert troca.status_code == 200, troca.content
    assert troca.json()["redirect"] == f"/pedido/{REF}"
    # O link que o PRÓPRIO cliente pediu (mensagem dele, código NB) prova posse do
    # número e continua confiando no dispositivo, como antes de OC-01.
    assert troca.json().get("device_trusted") is True

    assert outro.get(f"/api/v1/tracking/{REF}/").status_code == 200
