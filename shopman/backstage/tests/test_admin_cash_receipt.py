"""A tela de conferência de comprovante.

O que precisa ficar travado: ela **exige login** (é dinheiro), o código
assinado resolve para o movimento certo, e um papel forjado é recusado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from shopman.backstage.models import CashMovement, CashShift, POSTerminal
from shopman.backstage.projections.cash_receipt import build_receipt_verification
from shopman.backstage.services.receipt_verify import code_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _shop():
    """Sem Shop o OnboardingMiddleware desvia todo /admin/ para o cadastro da loja."""
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Nelson")


@pytest.fixture
def movement():
    terminal = POSTerminal.objects.create(ref="balcao", label="Balcão")
    operator = get_user_model().objects.create_user("marina", password="x")
    shift = CashShift.objects.create(terminal=terminal, operator=operator, opening_amount_q=10000)
    return CashMovement.objects.create(
        shift=shift,
        movement_type=CashMovement.MovementType.SANGRIA,
        amount_q=15000,
        reason="Depósito no cofre",
        created_by="marina",
        approved_by="admin",
    )


def test_codigo_valido_resolve_para_o_movimento(movement):
    resultado = build_receipt_verification(code_for(movement.pk))

    assert resultado.valid
    assert resultado.amount == "R$ 150,00"
    assert resultado.movement_type == "Sangria"
    assert resultado.approved_by == "admin"
    assert resultado.reason == "Depósito no cofre"
    # Ninguém confirmou impressão neste movimento: a tela não pode dizer que
    # imprimiu.
    assert resultado.receipt_status == "Sem confirmação"


def test_codigo_forjado_nao_confere(movement):
    # O id existe; a assinatura, não. É exatamente o papel que alguém escreve à
    # mão sabendo que a sangria de ontem foi a de número N.
    resultado = build_receipt_verification(f"SG-{movement.pk}-AAAAAAAA")

    assert not resultado.valid
    assert "não confere" in resultado.verdict


@pytest.mark.parametrize("lixo", ["", "SG-42", "banana", "XX-1-AAAAAAAA"])
def test_codigo_malformado_nao_explode(lixo):
    resultado = build_receipt_verification(lixo)

    assert not resultado.valid
    assert resultado.verdict


def test_movimento_apagado_e_dito_com_todas_as_letras(movement):
    codigo = code_for(movement.pk)
    movement.delete()

    resultado = build_receipt_verification(codigo)

    assert not resultado.valid
    # A distinção importa: "código legítimo, registro sumiu" é uma denúncia;
    # "não confere" esconderia o apagamento.
    assert "legítimo" in resultado.verdict


def test_pagina_exige_login(client, movement):
    resposta = client.get(reverse("admin_console_cash_receipt", args=[code_for(movement.pk)]))

    assert resposta.status_code == 302
    assert "/admin/login/" in resposta["Location"]


def test_pagina_mostra_o_movimento_para_quem_entrou(client, movement):
    get_user_model().objects.create_superuser("chefe", "c@x.com", "senha")
    client.login(username="chefe", password="senha")

    resposta = client.get(reverse("admin_console_cash_receipt", args=[code_for(movement.pk)]))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "R$ 150,00" in corpo
    assert "Depósito no cofre" in corpo


def test_qr_do_comprovante_aponta_para_a_pagina(settings, movement):
    from shopman.backstage.services.pos import cash_movement_receipt_payload

    settings.SHOPMAN_ADMIN_HOST = "admin.exemplo.test"
    payload = cash_movement_receipt_payload(
        operator=movement.shift.operator, movement_id=movement.pk
    )

    import base64

    bytes_do_papel = base64.b64decode(payload["payload_b64"])
    # O QR tem que levar para a MESMA rota que o Django serve. Se divergirem, o
    # papel manda o conferente para um 404 e a conferência morre no balcão.
    caminho = reverse("admin_console_cash_receipt", args=[payload["verify_code"]])
    assert f"https://admin.exemplo.test{caminho}".encode() in bytes_do_papel


def test_comprovante_antigo_confere_depois_de_girar_a_chave(settings, movement):
    """Girar a SECRET_KEY não pode invalidar o papel que já está na gaveta."""
    settings.SECRET_KEY = "chave-antiga"
    papel_impresso_ontem = code_for(movement.pk)

    # Vazamento → o operador gira a chave e guarda a antiga em fallbacks, que é
    # a receita do próprio Django.
    settings.SECRET_KEY = "chave-nova"
    settings.SECRET_KEY_FALLBACKS = ["chave-antiga"]

    assert build_receipt_verification(papel_impresso_ontem).valid
    # E o papel novo já sai assinado com a chave de hoje.
    assert build_receipt_verification(code_for(movement.pk)).valid


def test_chave_descartada_para_de_conferir(settings, movement):
    """Quando a chave antiga sai dos fallbacks, o papel dela deixa de valer."""
    settings.SECRET_KEY = "chave-antiga"
    papel_velho = code_for(movement.pk)

    settings.SECRET_KEY = "chave-nova"
    settings.SECRET_KEY_FALLBACKS = []

    assert not build_receipt_verification(papel_velho).valid
