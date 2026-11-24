"""O código certo do SMS confirma o número digitado no balcão (OC-08, #3446; decisão D).

O número que a equipe grava no balcão nasce sem prova e, desde o OC-08, não resolve
para a conta. Decisão D (24/11/2026): o código CERTO prova a posse do número, como
a mensagem pelo WhatsApp já prova; então ele confirma o contato (prova ``sms``,
gravada na transação do aceite) e entra no cadastro do balcão, sem tela extra e
sem aviso.

Sem oráculo: antes do código certo nada é diferente. Pedir o código, confirmar
sem pedido e errar o código respondem igual para um número que ninguém tem e
para um número do balcão ainda não confirmado. Código errado não muda nada.
"""

from __future__ import annotations

import pytest
from django.test import Client
from shopman.guestman.models import ContactPoint, Customer

from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos import resolve_or_create_customer

pytestmark = pytest.mark.django_db

NUMERO_DO_BALCAO = "+5543999995201"
NUMERO_DE_NINGUEM = "+5543999995202"


@pytest.fixture(autouse=True)
def _ambiente(settings, monkeypatch):
    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
    settings.RATELIMIT_ENABLE = False
    settings.DOORMAN = {
        **settings.DOORMAN,
        "DELIVERY_CHAIN": [],
        "MESSAGE_SENDER_CLASS": "shopman.storefront.tests.identity_fakes.CapturingSender",
    }
    from shopman.doorman.conf import doorman_settings, reset_adapter

    from shopman.storefront.tests.identity_fakes import CapturingSender

    CapturingSender.last_code = ""
    reset_adapter()
    monkeypatch.setattr(doorman_settings, "ACCESS_CODE_COOLDOWN_SECONDS", 0)


def _cadastrar_no_balcao(numero: str = NUMERO_DO_BALCAO) -> Customer:
    resolvido = resolve_or_create_customer(name="Ana Prado", phone=numero, operator_username="caixa")
    return Customer.objects.get(ref=resolvido["ref"])


def _contato(numero: str = NUMERO_DO_BALCAO) -> ContactPoint:
    return ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=numero)


def _ultimo_codigo() -> str:
    from shopman.storefront.tests.identity_fakes import CapturingSender

    code = CapturingSender.last_code
    assert code, "o código não foi enviado"
    CapturingSender.last_code = ""
    return code


def _pedir_codigo(client: Client, numero: str):
    # O formulário "Prefere receber um código por SMS?" da loja pede o canal sms.
    return client.post(
        "/api/v1/auth/request-code/",
        data={"phone": numero, "delivery_method": "sms"},
        content_type="application/json",
    )


def _confirmar(client: Client, numero: str, codigo: str):
    csrf = client.get("/api/v1/storefront/cart/").cookies["csrftoken"].value
    return client.post(
        "/api/v1/auth/verify-code/",
        data={"phone": numero, "code": codigo},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _codigo_errado(codigo: str) -> str:
    return "".join(str((int(d) + 1) % 10) for d in codigo)


def _sem_o_numero(body: dict, numero: str) -> dict:
    """A resposta com o próprio número e o relógio apagados: só eles podem diferir."""
    return {
        chave: "<numero>" if valor == numero else "<hora>" if chave == "code_expires_at" else valor
        for chave, valor in body.items()
    }


def _conta_da_sessao(client: Client) -> str:
    return client.get("/api/v1/auth/session/").json().get("customer_ref") or ""


def test_codigo_certo_confirma_o_numero_do_balcao_com_prova_sms_e_entra_na_conta():
    cadastro = _cadastrar_no_balcao()
    contas_antes = Customer.objects.count()
    assert _contato().is_verified is False
    cliente = Client()

    assert _pedir_codigo(cliente, NUMERO_DO_BALCAO).status_code == 200
    entrada = _confirmar(cliente, NUMERO_DO_BALCAO, _ultimo_codigo())

    assert entrada.status_code == 200, entrada.content
    assert _conta_da_sessao(cliente) == cadastro.ref
    # Entrou no cadastro que existia, sem conta nova por cima do mesmo número.
    assert Customer.objects.count() == contas_antes
    contato = _contato()
    assert contato.customer_id == cadastro.pk
    assert contato.is_verified is True
    assert contato.verification_method == ContactPoint.VerificationMethod.OTP_SMS


def test_codigo_errado_nao_muda_nada_e_o_contato_segue_sem_prova():
    _cadastrar_no_balcao()
    contas_antes = Customer.objects.count()
    cliente = Client()

    assert _pedir_codigo(cliente, NUMERO_DO_BALCAO).status_code == 200
    recusa = _confirmar(cliente, NUMERO_DO_BALCAO, _codigo_errado(_ultimo_codigo()))

    assert recusa.status_code == 400
    assert recusa.json()["detail"].startswith("Código incorreto.")
    assert _conta_da_sessao(cliente) == ""
    assert Customer.objects.count() == contas_antes
    assert _contato().is_verified is False


def test_quem_nao_tem_o_numero_nao_distingue_o_do_balcao_de_um_numero_de_ninguem():
    """Confirmar sem pedido, pedir o código e errar o código respondem igual nos dois."""
    _cadastrar_no_balcao()

    respostas = {}
    for numero in (NUMERO_DO_BALCAO, NUMERO_DE_NINGUEM):
        cliente = Client()
        sem_pedido = _confirmar(cliente, numero, "000000")
        pedido = _pedir_codigo(cliente, numero)
        errado = _confirmar(cliente, numero, _codigo_errado(_ultimo_codigo()))
        respostas[numero] = (
            sem_pedido.status_code,
            _sem_o_numero(sem_pedido.json(), numero),
            pedido.status_code,
            _sem_o_numero(pedido.json(), numero),
            errado.status_code,
            _sem_o_numero(errado.json(), numero),
        )

    assert respostas[NUMERO_DO_BALCAO] == respostas[NUMERO_DE_NINGUEM]
    assert [respostas[NUMERO_DO_BALCAO][i] for i in (0, 2, 4)] == [400, 200, 400]
    assert _contato().is_verified is False
