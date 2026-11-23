"""As escritas da sonda da central de entregas: prévia, confirmação na página e registro (#2489).

Cada escrita muda a conta da casa na TaOn de verdade. Estes testes provam as
três portas: a prévia não chama a rede, o envio só sai com a confirmação (a
trava do próprio comando), e toda chamada fica no histórico da Loja.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.urls import reverse

pytestmark = pytest.mark.django_db

CALL = "shopman.backstage.services.courier_probe.call_command"


@pytest.fixture(autouse=True)
def shop():
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


def _fake(report="HTTP 200"):
    def run(command, *args, stdout, stderr, **options):
        stdout.write(report)

    return run


def _preview(client, url, **data):
    return client.post(url, {"probe": "courier", **data})


def _send(client, url, **data):
    return client.post(url, {"probe": "courier", "step": "send", **data})


def test_a_previa_mostra_o_que_vai_sair_e_o_custo_sem_ir_a_rede(dono, url):
    with mock.patch(CALL) as call, mock.patch("requests.request") as rede:
        response = _preview(dono, url, action="boost", rides="776722699", value="2,00")
    call.assert_not_called()
    rede.assert_not_called()
    body = response.content.decode()
    assert "data-courier-probe-preview" in body
    assert "/api/v2/integracao/entregas/776722699/impulsionar com valor=2.00" in body
    assert "Gasta o valor do impulso" in body
    assert response.context["courier_confirm_form"].initial == {"action": "boost", "rides": "776722699", "value": "2,00"}
    assert not LogEntry.objects.exists()


@pytest.mark.parametrize(
    ("action", "value", "problem"),
    [
        ("cancel", "dez", "O valor precisa ser"),
        ("boost", "1,50", "O valor precisa ser"),
        ("attach", "", "O valor precisa ser"),
    ],
)
def test_a_previa_recusa_valor_errado(dono, url, action, value, problem):
    with mock.patch(CALL) as call:
        response = _preview(dono, url, action=action, rides="1", value=value)
    call.assert_not_called()
    assert "courier_confirm_form" not in response.context
    assert problem in response.content.decode()


def test_a_previa_recusa_duas_corridas(dono, url):
    response = _preview(dono, url, action="cancel", rides="1,2", value="10")
    assert "exatamente uma corrida" in response.content.decode()


def test_mandar_passa_pelas_travas_do_comando_e_registra(dono, url, shop):
    with mock.patch(CALL, side_effect=_fake("v1 cancelar com motivo 10 → HTTP 200")) as call:
        response = _send(dono, url, action="cancel", rides="776722699", value="10", confirm="776722699")
    args, kwargs = call.call_args
    assert args == ("courier_machine_probe",)
    assert kwargs["ride"] == ["776722699"] and kwargs["write"] is True
    assert kwargs["confirm"] == "776722699" and kwargs["cancel"] == 10
    assert "Escreveu na central" in response.content.decode()
    entry = LogEntry.objects.get()
    assert entry.user.username == "dono"
    assert entry.object_id == str(shop.pk)
    assert "Cancelar a corrida" in entry.change_message
    assert "motivo_id=10" in entry.change_message
    assert "HTTP 200" in entry.change_message


def test_a_recusa_tambem_fica_registrada(dono, url):
    def recusa(command, *args, stdout, stderr, **options):
        from django.core.management.base import CommandError

        raise CommandError("--confirm precisa repetir o id da corrida (1). Nada foi enviado.")

    with mock.patch(CALL, side_effect=recusa):
        response = _send(dono, url, action="cancel", rides="1", value="10", confirm="2")
    assert "Recusou ou falhou" in response.content.decode()
    assert "recusou ou falhou" in LogEntry.objects.get().change_message


def test_a_trava_do_comando_de_verdade_barra_a_confirmacao_errada(dono, url, settings):
    """Sem mock no comando: confirmação diferente do número da corrida não chega à rede."""
    settings.SHOPMAN_MACHINE = {"username": "u", "password": "p", "api_key": "k"}
    with mock.patch("shopman.shop.adapters.courier_machine._inert", return_value=False), \
            mock.patch("requests.request") as rede:
        response = _send(dono, url, action="boost", rides="776722699", value="2", confirm="776722690")
    rede.assert_not_called()
    assert "Nada foi enviado" in response.content.decode()


def test_cadastrar_avisos_pede_a_palavra(dono, url):
    with mock.patch(CALL, side_effect=_fake()) as call:
        recusado = _send(dono, url, action="register_webhooks", confirm="sim")
        call.assert_not_called()
        assert "Nada foi enviado" in recusado.content.decode()
        _send(dono, url, action="register_webhooks", confirm="cadastrar")
    args, kwargs = call.call_args
    assert args == ("machine_register_webhook", "https://testserver")
    assert "list" not in kwargs
    assert LogEntry.objects.count() == 1


def test_gerente_nao_manda_nada(gerente, url):
    with mock.patch(CALL) as call:
        response = _send(gerente, url, action="cancel", rides="1", value="10", confirm="1")
    assert response.status_code == 302
    call.assert_not_called()
    assert not LogEntry.objects.exists()


def test_o_registro_nao_leva_credencial(dono, url, settings):
    settings.SHOPMAN_MACHINE = {"username": "usuario-secreto", "password": "senha-secreta", "api_key": "chave-secreta"}
    with mock.patch(CALL, side_effect=_fake()):
        _send(dono, url, action="cancel", rides="1", value="10", confirm="1")
    message = LogEntry.objects.get().change_message
    for secret in ("usuario-secreto", "senha-secreta", "chave-secreta"):
        assert secret not in message
