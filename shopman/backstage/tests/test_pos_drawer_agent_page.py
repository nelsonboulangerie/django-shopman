"""A tela do Admin que entrega o agente da gaveta.

O dono já está no Admin configurando o terminal. O que se prova aqui é que ele
consegue terminar a tarefa sem sair dali: baixar o arquivo e ler o comando já
preenchido — e que o token deixou de ser transcrito à mão.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from shopman.backstage.admin.cash_register import POSTerminalForm
from shopman.backstage.models import POSTerminal
from shopman.backstage.projections.pos_agent import build_agent_install
from shopman.backstage.services.pos_hardware import CashDrawerConfig

pytestmark = pytest.mark.django_db


def _terminal(drawer=None, ref="pdv-agente") -> POSTerminal:
    metadata = {"hardware": {"cash_drawer": drawer}} if drawer else {}
    return POSTerminal.objects.create(ref=ref, label="Balcão", metadata=metadata)


AGENT = {
    "adapter": "agent",
    "agent_url": "http://127.0.0.1:47811",
    "token": "token-do-balcao-com-tamanho",
}


@pytest.fixture
def manager(client):
    # Sem Shop o OnboardingMiddleware manda todo mundo para o setup e o teste
    # mede o redirect, não a tela.
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    user = get_user_model().objects.create_user(username="dono", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(POSTerminal)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="change_posterminal"))
    client.force_login(user)
    return user


# ── O token nasce no Admin ────────────────────────────────────────────────


def _form_data(**overrides) -> dict:
    data = {
        "ref": "pdv-agente",
        "label": "Balcão",
        "channel_ref": "pdv",
        "location_ref": "",
        "is_active": "on",
        "drawer_adapter": "agent",
        "drawer_agent_url": "http://127.0.0.1:47811",
        "drawer_pulse_pin": "0",
        "drawer_pulse_on_ms": "50",
        "drawer_pulse_off_ms": "500",
        "drawer_open_on_cash_sale": "on",
    }
    data.update(overrides)
    return data


def test_escolher_o_agente_ja_gera_o_token():
    """Ninguém transcreve 43 caracteres de um terminal Linux para cá."""
    terminal = _terminal()
    form = POSTerminalForm(_form_data(), instance=terminal)

    assert form.is_valid(), form.errors
    form.save()

    config = CashDrawerConfig.from_terminal(POSTerminal.objects.get(pk=terminal.pk))
    assert len(config.token) >= 16
    assert config.kicks_by_software is True
    assert config.misconfigured_reason == ""


def test_salvar_de_novo_NAO_troca_o_token():
    """Trocar sozinho deixaria o balcão levando 401 sem ninguém ter pedido."""
    terminal = _terminal(AGENT)
    POSTerminalForm(_form_data(), instance=terminal).save()

    assert CashDrawerConfig.from_terminal(POSTerminal.objects.get(pk=terminal.pk)).token == AGENT["token"]


def test_marcar_gerar_novo_troca_o_token():
    terminal = _terminal(AGENT)
    form = POSTerminalForm(_form_data(drawer_rotate_token="on"), instance=terminal)

    assert form.is_valid(), form.errors
    form.save()

    assert CashDrawerConfig.from_terminal(POSTerminal.objects.get(pk=terminal.pk)).token != AGENT["token"]


# ── A projection das instruções ───────────────────────────────────────────


def test_o_comando_ja_vem_com_o_token_daquele_balcao(settings):
    settings.SHOPMAN_POS_BASE_URL = "https://pos.staging.exemplo/"
    guide = build_agent_install(_terminal(AGENT), download_url="/baixar/")

    install = next(step for step in guide.steps if step.command.startswith("python3"))
    assert f"--token {AGENT['token']}" in install.command
    # A origem sai da config do deployment, não de um chute no código.
    assert "--origin https://pos.staging.exemplo" in install.command


def test_sem_pos_base_url_o_comando_nao_inventa_origem(settings):
    """Melhor o instalador usar o default dele do que escrever endereço errado."""
    settings.SHOPMAN_POS_BASE_URL = ""
    guide = build_agent_install(_terminal(AGENT), download_url="/baixar/")

    install = next(step for step in guide.steps if step.command.startswith("python3"))
    assert "--origin" not in install.command


def test_terminal_de_gaveta_manual_explica_em_vez_de_oferecer_download():
    guide = build_agent_install(_terminal({"adapter": "manual"}), download_url="/baixar/")

    assert guide.configured is False
    assert "chave" in guide.blocker
    assert guide.steps == ()


# ── A tela ────────────────────────────────────────────────────────────────


def test_a_pagina_mostra_o_comando_pronto(client, manager):
    terminal = _terminal(AGENT)
    response = client.get(reverse("admin_console_pos_drawer_agent", args=[terminal.ref]))

    assert response.status_code == 200
    body = response.content.decode()
    assert AGENT["token"] in body
    assert "Baixar drawer_agent.py" in body


def test_o_download_entrega_o_agente_de_verdade(client, manager):
    terminal = _terminal(AGENT)
    response = client.get(reverse("admin_console_pos_drawer_agent_download", args=[terminal.ref]))

    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    assert "drawer_agent.py" in response["Content-Disposition"]
    body = b"".join(response.streaming_content).decode()
    # É o agente mesmo, não um arquivo qualquer com o nome certo.
    assert "def kick_bytes(" in body
    assert "--install" in body


def test_quem_nao_configura_terminal_nao_baixa_o_agente(client):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    terminal = _terminal(AGENT)
    user = get_user_model().objects.create_user(username="curioso", password="x", is_staff=True)
    client.force_login(user)

    response = client.get(reverse("admin_console_pos_drawer_agent_download", args=[terminal.ref]))
    assert response.status_code in (302, 403, 404)


def test_terminal_inexistente_nao_serve_arquivo(client, manager):
    response = client.get(reverse("admin_console_pos_drawer_agent_download", args=["fantasma"]))
    assert response.status_code == 404


def test_a_config_do_terminal_linka_para_a_tela(client, manager):
    terminal = _terminal(AGENT)
    response = client.get(reverse("admin:backstage_posterminal_change", args=[terminal.pk]))

    assert response.status_code == 200
    assert reverse("admin_console_pos_drawer_agent", args=[terminal.ref]) in response.content.decode()
