"""Contato gravado sem prova: o código certo o confirma (laudo S4; D4, OC-08; decisão D).

O telefone digitado no balcão nasce sem prova. O OC-08 fez o número sem prova não
resolver para a conta: pedir o código responde igual a um número que ninguém tem
(a loja não vira oráculo de "este telefone é cliente"). A decisão D (24/11/2026)
completa: o código CERTO prova a posse do número, como a mensagem pelo WhatsApp já
prova, então ele CONFIRMA o contato (prova ``sms``, gravada na transação do aceite)
e entra no cadastro do balcão. Código errado não muda nada. Número digitado errado
pela equipe é o D' (#3528).
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


def test_codigo_certo_no_numero_do_balcao_confirma_o_numero_e_entra(cadastro_do_balcao):
    """D: o código certo prova a posse, grava a prova ``sms`` e entra no cadastro do balcão."""
    clientes_antes = Customer.objects.count()

    assert IdentityResolver().resolve("phone", NUMERO_DO_BALCAO) is None

    pedido = AuthService.request_code(NUMERO_DO_BALCAO, delivery_method="sms")
    assert pedido.success is True
    codigo_emitido = VerificationCode.objects.filter(target_value=NUMERO_DO_BALCAO).latest("created_at")
    # O código não nasce preso ao cadastro do balcão: até o código certo, nada o distingue.
    assert codigo_emitido.customer_id is None

    entrada = AuthService.verify_for_login(NUMERO_DO_BALCAO, _codigo_valido(NUMERO_DO_BALCAO))

    assert entrada.success is True, entrada.error
    assert entrada.customer.subject_id == cadastro_do_balcao.uuid
    # Entrou no cadastro que existia: nenhuma conta nasceu por cima do mesmo número.
    assert Customer.objects.count() == clientes_antes
    contato = ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=NUMERO_DO_BALCAO)
    assert contato.customer_id == cadastro_do_balcao.pk
    assert contato.is_verified is True
    assert contato.verification_method == ContactPoint.VerificationMethod.OTP_SMS
    # Daí em diante o número resolve para o cadastro, como qualquer contato provado.
    assert IdentityResolver().resolve("phone", NUMERO_DO_BALCAO).subject_id == cadastro_do_balcao.uuid


def test_codigo_errado_no_numero_do_balcao_nao_muda_nada(cadastro_do_balcao):
    """Sem o código certo não há prova: o contato segue sem prova e ninguém entra."""
    codigo = _codigo_valido(NUMERO_DO_BALCAO)
    errado = "".join(str((int(d) + 1) % 10) for d in codigo)

    entrada = AuthService.verify_for_login(NUMERO_DO_BALCAO, errado)

    assert entrada.success is False
    assert entrada.error_code == ErrorCode.CODE_INVALID
    contato = ContactPoint.objects.get(type=ContactPoint.Type.PHONE, value_normalized=NUMERO_DO_BALCAO)
    assert contato.is_verified is False
    assert IdentityResolver().resolve("phone", NUMERO_DO_BALCAO) is None


def test_cadastro_inativo_nao_e_entregue_ao_codigo_certo(cadastro_do_balcao):
    """Cadastro desativado não é adotado: a entrada recusa com conflito, sem conta nova."""
    Customer.objects.filter(pk=cadastro_do_balcao.pk).update(is_active=False)
    clientes_antes = Customer.objects.count()

    entrada = AuthService.verify_for_login(NUMERO_DO_BALCAO, _codigo_valido(NUMERO_DO_BALCAO))

    assert entrada.success is False
    assert entrada.error_code == ErrorCode.IDENTITY_CONFLICT
    assert Customer.objects.count() == clientes_antes


def test_pedir_codigo_para_numero_sem_prova_responde_como_numero_desconhecido(cadastro_do_balcao):
    """A loja não vira oráculo de "este telefone é cliente"."""
    do_balcao = AuthService.request_code(NUMERO_DO_BALCAO, delivery_method="sms")
    desconhecido = AuthService.request_code(NUMERO_QUE_NINGUEM_TEM, delivery_method="sms")

    assert (do_balcao.success, do_balcao.error_code) == (desconhecido.success, desconhecido.error_code)
    # E o código errado também responde igual nos dois.
    respostas = []
    for numero in (NUMERO_DO_BALCAO, NUMERO_QUE_NINGUEM_TEM):
        errado = "".join(str((int(d) + 1) % 10) for d in _codigo_valido(numero))
        r = AuthService.verify_for_login(numero, errado)
        respostas.append((r.success, r.error_code, r.error, r.attempts_remaining))
    assert respostas[0] == respostas[1]


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


# ── O porto: quem recebe o contato recém-provado ────────────────────────────


def test_create_entrega_o_unico_cadastro_sem_prova_a_quem_provou_o_contato(cadastro_do_balcao):
    """O ``create`` só é chamado depois do código certo: o titular sem prova é quem provou."""
    clientes_antes = Customer.objects.count()

    for kind, valor in (("phone", NUMERO_DO_BALCAO), ("email", EMAIL_DO_BALCAO)):
        visto = IdentityResolver().create(kind, valor)
        assert visto.subject_id == cadastro_do_balcao.uuid

    assert Customer.objects.count() == clientes_antes


def test_create_com_dois_cadastros_no_mesmo_contato_continua_conflito(cadastro_do_balcao):
    from shopman.doorman.protocols.identity import IdentityConflict
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

    outra = Customer.objects.create(ref="BALCAO-2", first_name="Outra")
    CustomerIdentifier.objects.create(customer=outra, identifier_type="whatsapp", identifier_value=NUMERO_DO_BALCAO)
    clientes_antes = Customer.objects.count()

    with pytest.raises(IdentityConflict):
        IdentityResolver().create("phone", NUMERO_DO_BALCAO)

    assert Customer.objects.count() == clientes_antes
