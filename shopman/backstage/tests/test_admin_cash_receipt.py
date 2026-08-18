"""A tela de conferência de comprovante.

O que precisa ficar travado: ela **exige login** (é dinheiro), o código
assinado resolve para a linha certa do livro, e um papel forjado é recusado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Terminal

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
    terminal = Terminal.objects.create(ref="balcao", label="Balcão")
    operator = get_user_model().objects.create_user("marina", password="x")
    admin = get_user_model().objects.create_user("admin", password="x", is_staff=True)
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=10000)
    return cash.record(
        Entry.Kind.CASH_OUT,
        shift=shift,
        operator=operator,
        approved_by=admin,
        amount_q=-15000,
        reason="Depósito no cofre",
    )


def test_codigo_valido_resolve_para_o_movimento(movement):
    resultado = build_receipt_verification(code_for(movement.pk))

    assert resultado.valid
    assert resultado.amount == "R$ 150,00"
    assert resultado.movement_type == "Saída de caixa"
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


def test_confirmacao_de_impressao_aparece_na_conferencia(movement):
    """O ÚLTIMO ``receipt_result`` filho é o que a tela mostra."""
    cash.record(
        Entry.Kind.RECEIPT_RESULT, shift=movement.shift, operator=movement.operator,
        parent=movement, payload={"status": "failed", "detail": "sem papel"},
    )
    cash.record(
        Entry.Kind.RECEIPT_RESULT, shift=movement.shift, operator=movement.operator,
        parent=movement, payload={"status": "printed", "detail": ""},
    )

    resultado = build_receipt_verification(code_for(movement.pk))

    assert resultado.receipt_status == "Impresso"
    assert resultado.receipt_detail == ""


def test_movimento_apagado_e_dito_com_todas_as_letras(movement):
    codigo = code_for(movement.pk)
    # O livro não apaga pelo app (a guarda levanta); só quem tem acesso ao
    # banco consegue — e é exatamente esse cenário que a tela denuncia.
    Entry.objects.filter(pk=movement.pk)._raw_delete(Entry.objects.db)

    resultado = build_receipt_verification(codigo)

    assert not resultado.valid
    # A distinção importa: "código legítimo, registro sumiu" é uma denúncia;
    # "não confere" esconderia o apagamento.
    assert "legítimo" in resultado.verdict


def test_pagina_exige_login(client, movement):
    resposta = client.get(reverse("admin_console_cash_receipt", args=[code_for(movement.pk)]))

    assert resposta.status_code == 302
    assert "/admin/login/" in resposta["Location"]


def test_pagina_exige_auditar_turnos(client, movement):
    """Staff sem ``cashman.audit_shift`` não confere: é a planta de uma retirada."""
    user = get_user_model().objects.create_user("curioso", password="senha", is_staff=True)
    client.force_login(user)

    resposta = client.get(reverse("admin_console_cash_receipt", args=[code_for(movement.pk)]))

    assert resposta.status_code in (302, 403)


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
        operator=movement.shift.operator, entry_id=movement.pk
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


def _reload_settings_com_env(**env):
    """Reexecuta o `settings.py` com `env` e devolve o módulo.

    ⚠️ Recarregar o módulo mexe num objeto GLOBAL — outro teste que importe
    `config.settings` direto veria o estado do último reload. Por isso o
    ambiente volta ao que era e o módulo é reexecutado limpo antes de sair.
    """
    import importlib
    import os
    from contextlib import contextmanager

    import config.settings as s

    @contextmanager
    def _ctx():
        original = {chave: os.environ.get(chave) for chave in env}
        try:
            for chave, valor in env.items():
                if valor is None:
                    os.environ.pop(chave, None)
                else:
                    os.environ[chave] = valor
            importlib.reload(s)
            yield s
        finally:
            for chave, valor in original.items():
                if valor is None:
                    os.environ.pop(chave, None)
                else:
                    os.environ[chave] = valor
            importlib.reload(s)

    return _ctx()


class TestAdminHostSetting:
    """O host que vai IMPRESSO no QR.

    Estes testes existem porque a suíte inteira do comprovante passava com
    `settings.SHOPMAN_ADMIN_HOST` sobrescrito — nenhum perguntava o que o setting
    vale de verdade. Um valor com esquema teria gerado `https://https://…` e
    ninguém perceberia até alguém apontar o celular para um papel.
    """

    def test_o_setting_existe(self):
        from django.conf import settings

        assert hasattr(settings, "SHOPMAN_ADMIN_HOST")

    def test_perde_esquema_e_barra_final(self):
        # É comparado com `request.get_host()` (que nunca traz esquema) e
        # concatenado em `https://{host}{caminho}`. Lixo quebra os dois usos.
        with _reload_settings_com_env(SHOPMAN_ADMIN_HOST="https://admin.exemplo.test/") as s:
            assert s.SHOPMAN_ADMIN_HOST == "admin.exemplo.test"

    def test_vazio_continua_vazio(self):
        # Vazio desliga o redirect da raiz; o setting não inventa host nenhum.
        with _reload_settings_com_env(SHOPMAN_ADMIN_HOST=None) as s:
            assert s.SHOPMAN_ADMIN_HOST == ""


class TestQRFallback:
    """De onde o QR tira o host quando o canônico não está configurado."""

    def test_cai_no_host_da_api(self, settings, movement):
        from shopman.backstage.services.pos import cash_movement_receipt_payload

        settings.SHOPMAN_ADMIN_HOST = ""
        settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"

        payload = cash_movement_receipt_payload(
            operator=movement.shift.operator, entry_id=movement.pk
        )

        import base64

        # `api.` também serve /admin/, então o papel leva a algum lugar em vez de
        # sair mudo.
        assert b"https://api.exemplo.test/admin/cash/receipt/" in base64.b64decode(
            payload["payload_b64"]
        )

    def test_sem_nenhum_host_o_qr_leva_so_o_codigo(self, settings, movement):
        from shopman.backstage.services.pos import cash_movement_receipt_payload

        settings.SHOPMAN_ADMIN_HOST = ""
        settings.SHOPMAN_OPERATOR_API_HOST = ""

        payload = cash_movement_receipt_payload(
            operator=movement.shift.operator, entry_id=movement.pk
        )

        import base64

        papel = base64.b64decode(payload["payload_b64"])
        # Sem URL o QR ainda carrega o código — conferível digitando.
        assert b"https://" not in papel
        assert payload["verify_code"].encode() in papel
