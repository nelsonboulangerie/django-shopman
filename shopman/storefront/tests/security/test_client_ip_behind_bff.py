"""O IP de evidência (LGPD) é o do celular do cliente, também quando o pedido passa pelo BFF.

Medido no alpha em 17/09/2026: consentimento e declaração de maioridade do
cliente ``MC-115B31B4`` gravaram ``147.182.186.185`` — IP da DigitalOcean, a
saída do Nitro da loja. O navegador fala com o BFF, o BFF abre conexão nova para
o ``api.`` pela rede pública, e a borda de lá acrescenta os saltos de sempre à
direita do XFF que o BFF repassa. Com ``TRUSTED_PROXY_DEPTH=2`` o N-ésimo da
direita virou o Nitro.

Cadeias usadas abaixo, na forma da App Platform (``depth=2``: cliente + nó de
ingress acrescentados pela borda):

- direto no ``api.``:  ``CLIENTE, ingress``
- pela loja (BFF):     ``CLIENTE, ingress_loja, NITRO, ingress_api``

O que este arquivo trava:

- cliente direto continua resolvido como sempre;
- pelo BFF, com o segredo, grava o cliente e não o Nitro;
- sem o segredo (ou com segredo errado), o salto a mais NÃO é lido — um cliente
  direto não escolhe o IP que fica gravado;
- XFF forjado pelo cliente entra à esquerda e não desloca nenhuma contagem;
- consentimento e maioridade gravam esse IP de ponta a ponta;
- o throttle anônimo do DRF conta pelo mesmo IP.
"""
from __future__ import annotations

import json

import pytest
from django.test import Client, RequestFactory
from shopman.guestman.models import Customer

from shopman.shop.services.auth import client_ip

pytestmark = pytest.mark.django_db

CLIENTE = "203.0.113.9"
INGRESS_LOJA = "10.244.1.7"
NITRO = "147.182.186.185"
INGRESS_API = "10.244.0.3"
SEGREDO = "segredo-do-bff-de-teste"

VIA_BFF = f"{CLIENTE}, {INGRESS_LOJA}, {NITRO}, {INGRESS_API}"
DIRETO = f"{CLIENTE}, {INGRESS_API}"


@pytest.fixture(autouse=True)
def _platform(settings):
    settings.DOORMAN = {**getattr(settings, "DOORMAN", {}), "TRUSTED_PROXY_DEPTH": 2}
    settings.SHOPMAN_BFF_PROXY_SECRET = SEGREDO
    settings.RATELIMIT_ENABLE = False


def _req(xff: str | None, secret: str | None = None, remote: str = "10.0.0.1"):
    extra = {"REMOTE_ADDR": remote}
    if xff is not None:
        extra["HTTP_X_FORWARDED_FOR"] = xff
    if secret is not None:
        extra["HTTP_X_SHOPMAN_PROXY_SECRET"] = secret
    return RequestFactory().get("/", **extra)


# ── resolução ──────────────────────────────────────────────────────────


def test_cliente_direto_continua_resolvido_pela_profundidade():
    assert client_ip(_req(DIRETO)) == CLIENTE


def test_pelo_bff_com_segredo_grava_o_cliente_e_nao_o_nitro():
    assert client_ip(_req(VIA_BFF, secret=SEGREDO)) == CLIENTE


def test_pelo_bff_sem_segredo_configurado_nada_muda(settings):
    """Enquanto o segredo não está no ambiente, o comportamento é o de antes."""
    settings.SHOPMAN_BFF_PROXY_SECRET = ""
    assert client_ip(_req(VIA_BFF, secret="")) == NITRO
    assert client_ip(_req(VIA_BFF, secret=SEGREDO)) == NITRO


def test_cliente_direto_nao_escolhe_o_ip_com_segredo_chutado():
    """Spoofing: cliente direto forja XFF e manda um segredo qualquer.

    A borda acrescenta o IP real e o ingress à direita. Com segredo errado a
    leitura mais funda não acontece, e o forjado nunca é escolhido.
    """
    forjado = f"6.6.6.6, 7.7.7.7, {CLIENTE}, {INGRESS_API}"
    assert client_ip(_req(forjado, secret="chute")) == CLIENTE
    assert client_ip(_req(forjado)) == CLIENTE


def test_xff_forjado_que_atravessa_o_bff_nao_desloca_a_contagem():
    """Spoofing pela loja: o navegador manda XFF ao BFF, que repassa cru."""
    forjado = f"6.6.6.6, {CLIENTE}, {INGRESS_LOJA}, {NITRO}, {INGRESS_API}"
    assert client_ip(_req(forjado, secret=SEGREDO)) == CLIENTE


def test_bff_sem_trecho_interno_cai_na_resolucao_direta():
    """Dev local / BFF que não recebeu XFF: não há salto a mais para ler."""
    assert client_ip(_req(f"{NITRO}, {INGRESS_API}", secret=SEGREDO)) == NITRO
    assert client_ip(_req(None, secret=SEGREDO, remote="127.0.0.1")) == "127.0.0.1"


def test_lixo_no_lugar_do_ip_nao_vira_evidencia():
    lixo = f"nao-e-ip, {INGRESS_LOJA}, {NITRO}, {INGRESS_API}"
    assert client_ip(_req(lixo, secret=SEGREDO)) == NITRO


# ── de ponta a ponta: as duas evidências LGPD ──────────────────────────


def _customer(ref: str) -> Customer:
    return Customer.objects.create(
        ref=ref, first_name="Ana", last_name="Silva", phone="+5543999990177",
    )


def test_consentimento_pelo_bff_grava_o_ip_do_cliente(client: Client):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer
    from shopman.guestman.contrib.consent.models import CommunicationConsent

    customer = _customer("CUS-BFF-IP-01")
    user, _ = get_or_create_user_for_customer(
        AuthCustomerInfo(
            uuid=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True,
        )
    )
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")

    response = client.post(
        "/api/v1/account/preferences/notifications/",
        data=json.dumps({"channel": "whatsapp", "enabled": True}),
        content_type="application/json",
        HTTP_X_FORWARDED_FOR=VIA_BFF,
        HTTP_X_SHOPMAN_PROXY_SECRET=SEGREDO,
    )

    assert response.status_code == 200, response.content
    consent = CommunicationConsent.objects.get(customer__ref=customer.ref, channel="whatsapp")
    assert consent.ip_address == CLIENTE


def test_declaracao_de_maioridade_pelo_bff_grava_o_ip_do_cliente():
    from shopman.shop.services.marketing_age import ADULT_DECLARATION_KEY
    from shopman.storefront.api.auth import _declare_adult

    customer = _customer("CUS-BFF-IP-02")
    _declare_adult(_req(VIA_BFF, secret=SEGREDO), customer)

    customer.refresh_from_db()
    assert customer.metadata[ADULT_DECLARATION_KEY]["ip_address"] == CLIENTE


# ── o balde do throttle anônimo conta igual ────────────────────────────


def test_throttle_anonimo_do_drf_conta_pelo_mesmo_ip():
    from rest_framework.request import Request

    from shopman.shop.api_throttles import ClientIpAnonRateThrottle

    throttle = ClientIpAnonRateThrottle()
    assert throttle.get_ident(Request(_req(VIA_BFF, secret=SEGREDO))) == CLIENTE
    assert throttle.get_ident(Request(_req(DIRETO))) == CLIENTE
