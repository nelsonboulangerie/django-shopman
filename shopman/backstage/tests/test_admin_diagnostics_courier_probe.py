"""A sonda da central de entregas no Diagnóstico do Admin (#2489).

O console da DigitalOcean não recebe as variáveis SECRET e o token de deploy não
tem ``exec``: a rodada da TaOn só roda onde está a credencial, que é o processo
do Admin. A tela chama os MESMOS comandos; estes testes provam que ela passa as
opções certas, que a escrita só sai com a confirmação, e que é de superusuário.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

pytestmark = pytest.mark.django_db

CALL = "shopman.backstage.services.courier_probe.call_command"


@pytest.fixture(autouse=True)
def _shop():
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Nelson")


@pytest.fixture
def url():
    return reverse("admin_console_diagnostics")


@pytest.fixture
def dono(client, django_user_model):
    user = django_user_model.objects.create_superuser(username="dono", email="dono@boulangerie.com.br", password="x")
    client.force_login(user)
    return client


@pytest.fixture
def gerente(client, django_user_model):
    user = django_user_model.objects.create_user(username="gerente", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_shop"))
    client.force_login(user)
    return client


def _post(client, url, **data):
    return client.post(url, {"probe": "courier", **data})


def _fake(report="laudo da sonda"):
    def run(command, *args, stdout, stderr, **options):
        stdout.write(report)
    return run


def test_o_cartao_so_aparece_para_superusuario(dono, url):
    assert b"data-courier-probe" in dono.get(url).content


def test_gerente_nao_ve_nem_roda_a_sonda(gerente, url):
    assert b"data-courier-probe" not in gerente.get(url).content
    with mock.patch(CALL) as call:
        response = _post(gerente, url, action="read")
    assert response.status_code == 302
    call.assert_not_called()


def test_ler_passa_corridas_janela_e_ultimas_ao_comando(dono, url):
    with mock.patch(CALL, side_effect=_fake("12 chamadas")) as call:
        response = _post(dono, url, action="read", rides="776722699, 776722700", window="30", recent="2")
    call.assert_called_once()
    args, kwargs = call.call_args
    assert args == ("courier_machine_probe",)
    assert kwargs["ride"] == ["776722699", "776722700"]
    assert kwargs["window"] == 30 and kwargs["recent"] == 2
    assert "write" not in kwargs
    assert b"data-courier-probe-result" in response.content
    assert "12 chamadas" in response.content.decode()


def test_ler_os_avisos_usa_a_base_publica_deste_admin(dono, url):
    with mock.patch(CALL, side_effect=_fake()) as call:
        _post(dono, url, action="webhooks")
    args, kwargs = call.call_args
    assert args == ("machine_register_webhook", "https://testserver")
    assert kwargs["list"] is True


def test_cancelar_passa_pelas_travas_do_comando(dono, url):
    with mock.patch(CALL, side_effect=_fake()) as call:
        response = _post(dono, url, action="cancel", rides="776722699", value="1", confirm="776722699")
    _args, kwargs = call.call_args
    assert kwargs["ride"] == ["776722699"]
    assert kwargs["write"] is True and kwargs["confirm"] == "776722699"
    assert kwargs["cancel"] == 1
    assert "Escreveu na central" in response.content.decode()


def test_impulsionar_aceita_virgula_decimal(dono, url):
    with mock.patch(CALL, side_effect=_fake()) as call:
        _post(dono, url, action="boost", rides="1", value="2,00", confirm="1")
    assert call.call_args.kwargs["boost"] == 2.0


def test_escrita_com_duas_corridas_nao_envia_nada(dono, url):
    with mock.patch(CALL) as call:
        response = _post(dono, url, action="cancel", rides="1,2", value="10", confirm="1")
    call.assert_not_called()
    assert "exatamente uma corrida" in response.content.decode()


def test_escrita_com_valor_errado_nao_envia_nada(dono, url):
    with mock.patch(CALL) as call:
        response = _post(dono, url, action="cancel", rides="1", value="dez", confirm="1")
    call.assert_not_called()
    assert "Nada foi enviado" in response.content.decode()


def test_cadastrar_avisos_pede_a_palavra(dono, url):
    with mock.patch(CALL, side_effect=_fake()) as call:
        recusado = _post(dono, url, action="register_webhooks", confirm="sim")
        call.assert_not_called()
        assert "Nada foi enviado" in recusado.content.decode()
        _post(dono, url, action="register_webhooks", confirm="cadastrar")
    args, kwargs = call.call_args
    assert args == ("machine_register_webhook", "https://testserver")
    assert "list" not in kwargs


def test_a_confirmacao_nao_volta_preenchida(dono, url):
    with mock.patch(CALL, side_effect=_fake()):
        response = _post(dono, url, action="cancel", rides="776722699", value="10", confirm="776722699")
    form = response.context["courier_form"]
    assert form.initial["confirm"] == ""
    assert form.initial["rides"] == "776722699"


def test_o_comando_de_verdade_recusa_na_tela_sem_credencial(dono, url, settings):
    """Sem mock: o erro do comando (aqui, sem credencial) aparece inteiro, e nada é chamado na rede."""
    settings.SHOPMAN_MACHINE = {"username": "", "password": "", "api_key": ""}
    with mock.patch("requests.request") as rede:
        response = _post(dono, url, action="cancel", rides="1", value="10", confirm="1")
    rede.assert_not_called()
    body = response.content.decode()
    assert "Credenciais da TaOn ausentes" in body
    assert "Recusou ou falhou" in body
