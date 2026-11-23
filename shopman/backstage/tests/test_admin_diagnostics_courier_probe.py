"""A sonda da central de entregas no Diagnóstico do Admin (#2489).

O console da DigitalOcean não recebe as variáveis SECRET e o token de deploy não
tem ``exec``: a rodada da TaOn só lê onde está a credencial, que é o processo do
Admin. A tela chama os MESMOS comandos; estes testes provam que ela passa as
opções certas, que nenhuma opção de escrita chega ao comando, e que é de
superusuário.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

pytestmark = pytest.mark.django_db

CALL = "shopman.backstage.services.courier_probe.call_command"
WRITE_OPTIONS = {"write", "confirm", "cancel", "attach", "remove_stop", "boost"}


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
    assert not WRITE_OPTIONS & set(kwargs)
    assert b"data-courier-probe-result" in response.content
    assert "12 chamadas" in response.content.decode()


def test_no_maximo_tres_corridas(dono, url):
    with mock.patch(CALL, side_effect=_fake()) as call:
        _post(dono, url, action="read", rides="1,2,3,4,5")
    assert call.call_args.kwargs["ride"] == ["1", "2", "3"]


def test_ler_os_avisos_usa_a_base_publica_deste_admin_e_so_lista(dono, url):
    with mock.patch(CALL, side_effect=_fake()) as call:
        _post(dono, url, action="webhooks")
    args, kwargs = call.call_args
    assert args == ("machine_register_webhook", "https://testserver")
    assert kwargs["list"] is True


def test_o_comando_de_verdade_recusa_na_tela_sem_credencial(dono, url, settings):
    """Sem mock: o erro do comando (aqui, sem credencial) aparece inteiro, e nada vai à rede."""
    settings.SHOPMAN_MACHINE = {"username": "", "password": "", "api_key": ""}
    with mock.patch("requests.request") as rede:
        response = _post(dono, url, action="read", rides="1")
    rede.assert_not_called()
    body = response.content.decode()
    assert "Credenciais da TaOn ausentes" in body
    assert "Recusou ou falhou" in body


def test_a_projecao_diz_se_a_central_esta_configurada_sem_ir_a_rede(settings):
    from shopman.backstage.projections.diagnostics import build_diagnostics

    settings.SHOPMAN_MACHINE = {"username": "u", "password": "p", "api_key": "k", "base_url": "https://api.taximachine.com.br/api/integracao"}
    with mock.patch("requests.request") as rede:
        courier = build_diagnostics().courier
    rede.assert_not_called()
    assert courier.configured is True
    assert courier.environment == "produção"
    settings.SHOPMAN_MACHINE = {"base_url": "https://api-vendas.taximachine.com.br/api/integracao"}
    courier = build_diagnostics().courier
    assert courier.configured is False
    assert courier.environment == "homologação"
