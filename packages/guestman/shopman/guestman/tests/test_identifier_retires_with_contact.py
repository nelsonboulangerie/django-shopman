"""A chave de login sai junto com o contato que ela espelha (A4-1)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.models import ContactPoint, Customer

pytestmark = pytest.mark.django_db

NUMERO = "+5543999997001"
EMAIL = "ana.antiga@example.com"


def _customer(ref: str = "CUS-IDR-01") -> Customer:
    return Customer.objects.create(ref=ref, first_name="Ana")


def _contact(customer, contact_type, value, *, primary=False) -> ContactPoint:
    return ContactPoint.objects.create(
        customer=customer,
        type=contact_type,
        value_normalized=value,
        is_primary=primary,
    )


def _identifier(customer, identifier_type, value) -> CustomerIdentifier:
    return CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=identifier_type,
        identifier_value=value,
        source_system="doorman",
    )


def _keys(customer) -> set[tuple[str, str]]:
    return set(
        CustomerIdentifier.objects.filter(customer=customer).values_list(
            "identifier_type", "identifier_value"
        )
    )


def test_apagar_o_telefone_apaga_a_chave_do_numero():
    customer = _customer()
    contato = _contact(customer, ContactPoint.Type.PHONE, NUMERO, primary=True)
    _identifier(customer, IdentifierType.PHONE, NUMERO)
    _identifier(customer, IdentifierType.WHATSAPP, NUMERO)

    contato.delete()

    assert _keys(customer) == set()


def test_apagar_por_queryset_tambem_apaga_a_chave():
    customer = _customer()
    _contact(customer, ContactPoint.Type.EMAIL, EMAIL, primary=True)
    _identifier(customer, IdentifierType.EMAIL, EMAIL)

    ContactPoint.objects.filter(customer=customer, value_normalized=EMAIL).delete()

    assert _keys(customer) == set()


def test_a_chave_fica_enquanto_o_mesmo_numero_segue_como_whatsapp():
    customer = _customer()
    voz = _contact(customer, ContactPoint.Type.PHONE, NUMERO, primary=True)
    _contact(customer, ContactPoint.Type.WHATSAPP, NUMERO, primary=True)
    _identifier(customer, IdentifierType.PHONE, NUMERO)

    voz.delete()

    assert _keys(customer) == {("phone", NUMERO)}


def test_chave_que_nao_e_de_login_nao_e_tocada():
    customer = _customer()
    contato = _contact(customer, ContactPoint.Type.PHONE, NUMERO, primary=True)
    _identifier(customer, IdentifierType.MANYCHAT, "mc-001")
    _identifier(customer, IdentifierType.CPF, "12345678909")

    contato.delete()

    assert _keys(customer) == {("manychat", "mc-001"), ("cpf", "12345678909")}


def test_chave_de_outro_valor_nao_e_tocada():
    customer = _customer()
    antigo = _contact(customer, ContactPoint.Type.PHONE, NUMERO, primary=True)
    _contact(customer, ContactPoint.Type.PHONE, "+5543999997002")
    _identifier(customer, IdentifierType.PHONE, NUMERO)
    _identifier(customer, IdentifierType.PHONE, "+5543999997002")

    antigo.delete()

    assert _keys(customer) == {("phone", "+5543999997002")}


def test_comando_lista_sem_apagar_e_apaga_com_apply():
    customer = _customer()
    _contact(customer, ContactPoint.Type.PHONE, NUMERO, primary=True)
    _identifier(customer, IdentifierType.PHONE, NUMERO)
    # Sobra de antes da correção: identificador sem contato nenhum.
    orfao = CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.EMAIL,
        identifier_value=EMAIL,
    )
    _identifier(customer, IdentifierType.MANYCHAT, "mc-002")

    out = StringIO()
    call_command("prune_unbacked_login_identifiers", stdout=out)
    texto = out.getvalue()
    assert "Simulação: 1 identificador(es)" in texto
    assert EMAIL not in texto
    assert CustomerIdentifier.objects.filter(pk=orfao.pk).exists()

    out = StringIO()
    call_command("prune_unbacked_login_identifiers", "--apply", stdout=out)
    assert "1 identificador(es) sem contato apagado(s)." in out.getvalue()
    assert _keys(customer) == {("phone", NUMERO), ("manychat", "mc-002")}
