"""Contato gravado sem prova não abre a conta (laudo S4, decisão do dono D4, OC-08).

O telefone digitado no balcão nasce sem prova. Antes, quem passasse o código
naquele número entrava na conta de quem estava no balcão: bastava a equipe errar
um dígito para o dono do número errado ver endereço, pedidos e preço de grupo de
outra pessoa. Agora o número só abre a conta depois que o titular confirma (o
toque no WhatsApp, que o vínculo do ManyChat grava como verificado pelo canal).
"""

from __future__ import annotations

import pytest
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.models import VerificationCode
from shopman.doorman.models.verification_code import generate_raw_code
from shopman.doorman.services.verification import AuthService
from shopman.guestman.adapters.auth import IdentityResolver
from shopman.guestman.models import ContactPoint, Customer

pytestmark = pytest.mark.django_db

NUMERO_DO_BALCAO = "+5543999990201"
NUMERO_QUE_NINGUEM_TEM = "+5543999990202"
EMAIL_DO_BALCAO = "ana.balcao@example.com"


@pytest.fixture
def cadastro_do_balcao():
    """O cliente que a equipe cadastrou: telefone e e-mail digitados, sem prova."""
    customer = Customer.objects.create(
        ref="BALCAO-1",
        first_name="Ana",
        last_name="Prado",
        phone=NUMERO_DO_BALCAO,
        email=EMAIL_DO_BALCAO,
        source_system="pdv",
    )
    assert not customer.contact_points.filter(is_verified=True).exists()
    return customer


def _codigo_valido(numero: str) -> str:
    raw_code, digest = generate_raw_code()
    VerificationCode.objects.create(
        code_hash=digest,
        target_value=numero,
        purpose=VerificationCode.Purpose.LOGIN,
        delivery_method=VerificationCode.DeliveryMethod.SMS,
        status=VerificationCode.Status.SENT,
    )
    return raw_code


def test_codigo_no_numero_digitado_no_balcao_nao_abre_a_conta(cadastro_do_balcao):
    """S4: quem passa o código no número sem prova não entra na conta do balcão."""
    clientes_antes = Customer.objects.count()

    assert IdentityResolver().resolve("phone", NUMERO_DO_BALCAO) is None

    pedido = AuthService.request_code(NUMERO_DO_BALCAO, delivery_method="sms")
    assert pedido.success is True
    codigo_emitido = VerificationCode.objects.filter(target_value=NUMERO_DO_BALCAO).latest("created_at")
    # O código não nasce preso ao cadastro do balcão.
    assert codigo_emitido.customer_id is None

    entrada = AuthService.verify_for_login(NUMERO_DO_BALCAO, _codigo_valido(NUMERO_DO_BALCAO))

    assert entrada.success is False
    assert entrada.error_code == ErrorCode.IDENTITY_CONFLICT
    # Nem abriu a conta existente nem nasceu outra por cima do mesmo número.
    assert Customer.objects.count() == clientes_antes
    contato = ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=NUMERO_DO_BALCAO)
    assert contato.customer_id == cadastro_do_balcao.pk
    assert contato.is_verified is False


def test_pedir_codigo_para_numero_sem_prova_responde_como_numero_desconhecido(cadastro_do_balcao):
    """A loja não vira oráculo de "este telefone é cliente"."""
    do_balcao = AuthService.request_code(NUMERO_DO_BALCAO, delivery_method="sms")
    desconhecido = AuthService.request_code(NUMERO_QUE_NINGUEM_TEM, delivery_method="sms")

    assert (do_balcao.success, do_balcao.error_code) == (desconhecido.success, desconhecido.error_code)


def test_depois_da_confirmacao_o_numero_abre_a_conta(cadastro_do_balcao):
    """O toque no WhatsApp grava a prova; daí em diante o código abre a conta do balcão."""
    contato = ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=NUMERO_DO_BALCAO)
    contato.mark_verified(ContactPoint.VerificationMethod.CHANNEL_ASSERTED)

    resolvido = IdentityResolver().resolve("phone", NUMERO_DO_BALCAO)
    assert resolvido is not None
    assert resolvido.subject_id == cadastro_do_balcao.uuid

    entrada = AuthService.verify_for_login(NUMERO_DO_BALCAO, _codigo_valido(NUMERO_DO_BALCAO))

    assert entrada.success is True, entrada.error
    assert entrada.customer.subject_id == cadastro_do_balcao.uuid


def test_email_digitado_sem_prova_tambem_nao_abre_a_conta(cadastro_do_balcao):
    assert IdentityResolver().resolve("email", EMAIL_DO_BALCAO, purpose="access_link") is None

    ContactPoint.objects.get(type=ContactPoint.Type.EMAIL, value_normalized=EMAIL_DO_BALCAO).mark_verified(
        ContactPoint.VerificationMethod.OTP_EMAIL,
    )

    resolvido = IdentityResolver().resolve("email", EMAIL_DO_BALCAO, purpose="access_link")
    assert resolvido.subject_id == cadastro_do_balcao.uuid


def test_numero_novo_continua_criando_a_conta_de_quem_provou():
    """A trava é do contato sem prova de OUTRO cadastro: quem chega com número livre entra."""
    entrada = AuthService.verify_for_login(NUMERO_QUE_NINGUEM_TEM, _codigo_valido(NUMERO_QUE_NINGUEM_TEM))

    assert entrada.success is True, entrada.error
    contato = ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=NUMERO_QUE_NINGUEM_TEM)
    assert contato.is_verified is True
    assert IdentityResolver().resolve("phone", NUMERO_QUE_NINGUEM_TEM).subject_id == entrada.customer.subject_id
