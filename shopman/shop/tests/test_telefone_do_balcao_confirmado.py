"""Telefone digitado no balcão só vale depois que o cliente confirma (D4, OC-08).

Decisão do dono (23/11/2026): quando o balcão grava um telefone, o cliente recebe
no WhatsApp "Confirme que este número é seu" e confirma com um toque. Até
confirmar, o número não abre a conta existente (laudo S4).

Três partes, um teste cada lado:

- a porta: o código no número sem prova não entra na conta do balcão;
- o pedido: o PDV (e o Gestor) gravando um telefone novo pede a confirmação, e
  sem o modelo da Meta ligado o pedido fica registrado como pendente de modelo;
- a confirmação: a mensagem do próprio número chega pelo ManyChat, o vínculo do
  assinante marca o contato como verificado pelo canal, e daí o número abre a conta.
"""

from __future__ import annotations

import pytest
from django.test import Client
from shopman.guestman.contrib.manychat.service import ManychatService
from shopman.guestman.models import ContactPoint, Customer

from shopman.shop.models import Channel, Shop
from shopman.shop.protocols import NotificationResult
from shopman.shop.services import phone_confirmation
from shopman.shop.services.pos import resolve_or_create_customer

pytestmark = pytest.mark.django_db

NUMERO = "+5543999995101"
OUTRO_NUMERO = "+5543999995102"


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


@pytest.fixture
def envios(monkeypatch):
    """O que sairia pelo registro de notificações (nada vai ao provedor)."""
    chamadas: list[dict] = []

    def _notify(**kwargs):
        chamadas.append(kwargs)
        return NotificationResult(success=True)

    monkeypatch.setattr("shopman.shop.notifications.notify", _notify)
    return chamadas


@pytest.fixture
def modelo_aprovado(monkeypatch):
    monkeypatch.setattr(phone_confirmation, "template_ready", lambda: True)


def _cadastrar_no_balcao(django_capture_on_commit_callbacks, numero: str = NUMERO, **extra) -> Customer:
    with django_capture_on_commit_callbacks(execute=True):
        resolvido = resolve_or_create_customer(
            name="Ana Prado", phone=numero, operator_username="caixa", **extra,
        )
    return Customer.objects.get(ref=resolvido["ref"])


def _registro(customer: Customer) -> dict | None:
    customer.refresh_from_db()
    return (customer.metadata or {}).get(phone_confirmation.METADATA_KEY)


def _confirmar_pelo_whatsapp(numero: str) -> None:
    """O toque no botão: uma mensagem do próprio número, que o ManyChat entrega."""
    ManychatService.sync_subscriber({"id": "mc-oc08-1", "first_name": "Ana", "whatsapp_id": numero})


def _last_code() -> str:
    from shopman.storefront.tests.identity_fakes import CapturingSender

    assert CapturingSender.last_code
    code = CapturingSender.last_code
    CapturingSender.last_code = ""
    return code


def _entrar_por_codigo(client: Client, numero: str):
    pedido = client.post("/api/v1/auth/request-code/", data={"phone": numero}, content_type="application/json")
    assert pedido.status_code == 200, pedido.content
    csrf = client.get("/api/v1/storefront/cart/").cookies["csrftoken"].value
    return client.post(
        "/api/v1/auth/verify-code/",
        data={"phone": numero, "code": _last_code()},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


# ── A porta ──────────────────────────────────────────────────────────────────


def test_s4_codigo_no_numero_do_balcao_nao_abre_a_conta_ate_o_cliente_confirmar(
    django_capture_on_commit_callbacks, envios,
):
    cadastro = _cadastrar_no_balcao(django_capture_on_commit_callbacks)
    contas_antes = Customer.objects.count()

    cliente = Client()
    recusa = _entrar_por_codigo(cliente, NUMERO)

    assert recusa.status_code == 400
    assert recusa.json()["error_code"] == "identity_conflict"
    assert cliente.get("/api/v1/auth/session/").json().get("customer_ref") in (None, "")
    assert Customer.objects.count() == contas_antes

    _confirmar_pelo_whatsapp(NUMERO)
    contato = ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=NUMERO)
    assert contato.customer_id == cadastro.pk
    assert contato.is_verified is True
    assert contato.verification_method == ContactPoint.VerificationMethod.CHANNEL_ASSERTED

    entrada = _entrar_por_codigo(cliente, NUMERO)
    assert entrada.status_code == 200, entrada.content
    assert cliente.get("/api/v1/auth/session/").json()["customer_ref"] == cadastro.ref


# ── O pedido ─────────────────────────────────────────────────────────────────


def test_pdv_gravando_telefone_sem_modelo_aprovado_registra_pendente_e_nao_envia(
    django_capture_on_commit_callbacks, envios,
):
    assert phone_confirmation.template_ready() is False

    cadastro = _cadastrar_no_balcao(django_capture_on_commit_callbacks)

    assert envios == []
    registro = _registro(cadastro)
    assert registro["state"] == phone_confirmation.STATE_AWAITING_TEMPLATE
    contato = ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=NUMERO)
    assert registro["contact_id"] == str(contato.pk)
    # O registro aponta o contato pelo id: o número não é copiado para o metadata.
    assert NUMERO not in str(registro)


def test_pdv_gravando_telefone_com_modelo_aprovado_pede_a_confirmacao_no_whatsapp(
    django_capture_on_commit_callbacks, envios, modelo_aprovado,
):
    cadastro = _cadastrar_no_balcao(django_capture_on_commit_callbacks)

    assert envios == [
        {
            "event": phone_confirmation.EVENT,
            "recipient": NUMERO,
            # Sem nome: o número pode ter sido digitado errado.
            "context": {},
            "backend": "manychat",
        }
    ]
    assert _registro(cadastro)["state"] == phone_confirmation.STATE_SENT


def test_envio_recusado_fica_registrado_sem_derrubar_o_cadastro(
    django_capture_on_commit_callbacks, monkeypatch, modelo_aprovado,
):
    monkeypatch.setattr(
        "shopman.shop.notifications.notify",
        lambda **kwargs: NotificationResult(success=False, error="subscriber_not_found"),
    )

    cadastro = _cadastrar_no_balcao(django_capture_on_commit_callbacks)

    registro = _registro(cadastro)
    assert registro["state"] == phone_confirmation.STATE_NOT_SENT
    assert registro["error"] == "subscriber_not_found"


def test_a_venda_seguinte_com_o_mesmo_numero_nao_pede_de_novo(
    django_capture_on_commit_callbacks, envios, modelo_aprovado,
):
    cadastro = _cadastrar_no_balcao(django_capture_on_commit_callbacks)
    assert len(envios) == 1

    with django_capture_on_commit_callbacks(execute=True):
        resolve_or_create_customer(ref=cadastro.ref, phone=NUMERO, operator_username="caixa")

    assert len(envios) == 1


def test_numero_ja_confirmado_nao_pede_confirmacao(django_capture_on_commit_callbacks, envios, modelo_aprovado):
    _confirmar_pelo_whatsapp(NUMERO)
    cliente_do_whatsapp = Customer.objects.get(phone=NUMERO)

    with django_capture_on_commit_callbacks(execute=True):
        resolve_or_create_customer(ref=cliente_do_whatsapp.ref, name="Ana Prado", phone=NUMERO, operator_username="caixa")

    assert envios == []
    assert _registro(cliente_do_whatsapp) is None


def test_gestor_gravando_telefone_novo_pede_a_confirmacao(django_capture_on_commit_callbacks, envios, modelo_aprovado):
    from shopman.backstage.services import customers as gestor

    with django_capture_on_commit_callbacks(execute=True):
        ficha = gestor.create_customer({"firstName": "Bia", "phone": OUTRO_NUMERO}, actor="gestor")
    assert [envio["recipient"] for envio in envios] == [OUTRO_NUMERO]

    ficha.refresh_from_db()
    revisao_depois_do_pedido = ficha.updated_at
    with django_capture_on_commit_callbacks(execute=True):
        gestor.update_customer(
            ficha.ref, {"firstName": "Beatriz", "expectedRevision": revisao_depois_do_pedido.isoformat()},
        )
    # Mudar o nome não manda nada; e o registro do pedido não mexeu na revisão da
    # ficha (a edição acima passou pela conferência de "o cliente mudou").
    assert len(envios) == 1


def test_contato_confirmado_nao_recebe_pedido(django_capture_on_commit_callbacks, envios, modelo_aprovado):
    cadastro = _cadastrar_no_balcao(django_capture_on_commit_callbacks)
    envios.clear()
    _confirmar_pelo_whatsapp(NUMERO)

    assert phone_confirmation.request(cadastro.ref, NUMERO) is None
    assert envios == []
