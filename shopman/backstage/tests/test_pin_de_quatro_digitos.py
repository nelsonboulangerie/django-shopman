"""O PIN da casa tem exatamente 4 dígitos, e o de 4 fixos entra sozinho (#3223).

Decisão do dono (22/11/2026, opção 1): o teclado envia o PIN no quarto dígito,
sem o toque em Confirmar. Ele lembrou que já estava decidido que o PIN tem 4
dígitos, mas o doorman aceitava de 4 a 8. O desenho, acertado com a coordenação:

1. todo PIN que já existe passa a exigir troca no próximo uso (``backstage.0101``);
2. até a troca, o teclado mantém o Confirmar, e quem tem PIN de 6 ainda entra;
3. a troca e a criação só aceitam exatamente 4 dígitos;
4. a credencial de 4 fixos vem marcada no cartão (``pin_digits``), e com ela o
   teclado envia sozinho.

Nada disso toca o doorman: todo PIN gravado passa pelos serviços do shop.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.doorman.models import PinCredential, PinCredentialError

from shopman.backstage.services import operator as operator_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def fran():
    return get_user_model().objects.create_user(username="fran", password="x", is_staff=True, first_name="Fran")


def test_o_pin_novo_tem_exatamente_quatro_digitos():
    assert operator_service.validate_operator_pin(" 4821 ") == "4821"
    for wrong in ("482", "48213", "482135", "48a1", ""):
        with pytest.raises(PinCredentialError, match="4 dígitos"):
            operator_service.validate_operator_pin(wrong)


def test_a_troca_recusa_pin_que_nao_tem_quatro(fran):
    PinCredential.set_for(fran, "123456")

    with pytest.raises(PinCredentialError, match="4 dígitos"):
        operator_service.change_own_pin(fran, "123456", "654321")

    operator_service.change_own_pin(fran, "123456", "4821")
    fran.pin_credential.refresh_from_db()
    assert fran.pin_credential.verify("4821")


def test_o_reset_do_gerente_da_um_provisorio_de_quatro(fran):
    temp = operator_service.reset_operator_pin(fran)

    assert len(temp) == 4 and temp.isdigit()
    with pytest.raises(PinCredentialError, match="4 dígitos"):
        operator_service.reset_operator_pin(fran, temp_pin="123456")


def test_o_comando_recusa_pin_que_nao_tem_quatro(fran):
    with pytest.raises(CommandError, match="4 dígitos"):
        call_command("set_operator_pin", "fran", "--pin", "123456")

    call_command("set_operator_pin", "fran", "--pin", "4821")
    assert operator_service.pin_digits(fran) == 4


def test_o_cartao_marca_so_o_pin_de_quatro_fixos(fran):
    # Sem credencial: nada a marcar.
    assert operator_service.operator_card(fran)["pin_digits"] is None

    # PIN com troca pendente (o antigo, ou o provisório do gerente): Confirmar.
    PinCredential.set_for(fran, "123456", must_change=True)
    fran.refresh_from_db()
    assert operator_service.operator_card(fran)["pin_digits"] is None

    # Trocado para 4: o teclado envia sozinho.
    operator_service.change_own_pin(fran, "123456", "4821")
    fran.refresh_from_db()
    assert operator_service.operator_card(fran)["pin_digits"] == 4


def test_todo_pin_que_ja_existe_passa_a_exigir_troca(fran):
    """A migração: o hash não guarda o tamanho, então todo PIN antigo troca."""
    other = get_user_model().objects.create_user(username="joyce", password="x", is_staff=True)
    PinCredential.set_for(fran, "123456")
    PinCredential.set_for(other, "1234")
    badge_only = get_user_model().objects.create_user(username="cracha", password="x", is_staff=True)
    PinCredential.objects.create(user=badge_only, pin_hash="")

    migration = importlib.import_module("shopman.backstage.migrations.0101_pin_de_quatro_digitos_troca_obrigatoria")
    migration.force_pin_change(django_apps, None)

    assert PinCredential.objects.get(user=fran).must_change is True
    assert PinCredential.objects.get(user=other).must_change is True
    # Só crachá, sem PIN: não há o que trocar.
    assert PinCredential.objects.get(user=badge_only).must_change is False
    # O PIN antigo continua abrindo até a troca.
    assert PinCredential.objects.get(user=fran).verify("123456")
