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


# ── Seletor de sistema operacional ────────────────────────────────────────
#
# Linux é o oficial. Windows existe porque o caixa ainda roda Windows e a troca
# não pode ser feita com a loja aberta; macOS existe para o dono testar.


@pytest.mark.parametrize("os_key,esperado", [("linux", "python3"), ("macos", "python3"), ("windows", "python ")])
def test_o_comando_usa_o_interpretador_do_sistema(os_key, esperado):
    guide = build_agent_install(_terminal(AGENT), download_url="/baixar/", os_key=os_key)
    install = next(s for s in guide.steps if "--install" in s.command)
    assert install.command.startswith(esperado)
    assert AGENT["token"] in install.command


def test_o_token_e_o_mesmo_em_qualquer_sistema():
    """O par vive no Admin; o SO só muda como se digita, não o segredo."""
    terminal = _terminal(AGENT)
    tokens = {
        next(s for s in build_agent_install(terminal, download_url="/x/", os_key=k).steps
             if "--install" in s.command).command.split("--token ")[1].split()[0]
        for k in ("linux", "windows", "macos")
    }
    assert tokens == {AGENT["token"]}


@pytest.mark.parametrize("os_key,marca", [
    ("linux", "journalctl"),
    ("macos", "drawer-agent.log"),
    ("windows", "LOCALAPPDATA"),
])
def test_cada_sistema_diz_onde_ver_o_registro(os_key, marca):
    """Prometo na tela que 'o agente registra cada abertura' — em todos eles."""
    guide = build_agent_install(_terminal(AGENT), download_url="/x/", os_key=os_key)
    assert any(marca in s.command for s in guide.steps)


def test_so_desconhecido_cai_no_oficial():
    """`?so=haiku` não pode virar uma tela sem passos."""
    guide = build_agent_install(_terminal(AGENT), download_url="/x/", os_key="haiku")
    assert guide.os_key == "linux"
    assert guide.steps


def test_o_padrao_e_linux_e_ele_nao_tem_ressalva():
    guide = build_agent_install(_terminal(AGENT), download_url="/x/")
    assert guide.os_key == "linux"
    assert guide.os_caveat == ""


def test_windows_e_macos_dizem_que_nao_sao_o_oficial():
    terminal = _terminal(AGENT)
    for key in ("windows", "macos"):
        guide = build_agent_install(terminal, download_url="/x/", os_key=key)
        assert guide.os_caveat, key
        assert "Linux" in guide.os_caveat


def test_o_windows_avisa_que_pode_faltar_python():
    """Linux e macOS já trazem; o Windows não, e descobrir isso no balcão custa caro."""
    guide = build_agent_install(_terminal(AGENT), download_url="/x/", os_key="windows")
    assert any("Microsoft Store" in s.detail for s in guide.steps)


def test_a_tela_oferece_os_tres_sistemas(client, manager):
    terminal = _terminal(AGENT)
    response = client.get(reverse("admin_console_pos_drawer_agent", args=[terminal.ref]) + "?so=windows")

    assert response.status_code == 200
    body = response.content.decode()
    for rotulo in ("Linux", "Windows", "macOS"):
        assert rotulo in body
    assert "?so=linux" in body and "?so=macos" in body


def test_a_tela_nao_vaza_comentario_de_template(client, manager):
    """`{# … #}` do Django é de UMA linha; em várias ele VIRA TEXTO na tela.

    Aconteceu: um comentário meu sobre a fonte apareceu para o usuário, entre o
    passo e o comando. Teste de conteúdo por palavra-chave não pega isso —
    quem pegou foi olhar a tela.
    """
    terminal = _terminal(AGENT)
    body = client.get(reverse("admin_console_pos_drawer_agent", args=[terminal.ref])).content.decode()

    assert "U+002D" not in body
    assert "{#" not in body and "#}" not in body


def test_terminal_sem_gaveta_mostra_NAO_CONFIGURADA_selecionada():
    """Sem opção vazia o navegador marca a primeira ("Com a chave") sozinho.

    O formulário então exibia um estado que o banco não tinha, e salvar sem
    tocar no campo gravava `manual`. Estado real e exibido divergindo é como a
    config da gaveta some sem ninguém ter pedido.
    """
    form = POSTerminalForm(instance=_terminal())
    html = str(form["drawer_adapter"])

    assert 'value=""' in html, "falta a opção vazia"
    assert html.index('value=""') < html.index('value="manual"'), "a vazia tem que vir primeiro"


def test_terminal_com_agente_abre_o_formulario_com_agente_marcado():
    form = POSTerminalForm(instance=_terminal(AGENT))
    assert form["drawer_adapter"].value() == "agent"


def test_a_tela_carimba_a_versao_do_arquivo_que_entrega():
    """O balcão só se atualiza pelo download daqui — sem rede, sem pendrive.

    Sem carimbo ninguém sabe se a máquina está com o agente atual, e
    "reinstalei e continua igual" vira meia hora perdida.
    """
    import hashlib

    from shopman.backstage.projections.pos_agent import AGENT_SOURCE

    guide = build_agent_install(_terminal(AGENT), download_url="/x/")
    esperado = hashlib.sha256(AGENT_SOURCE.read_bytes()).hexdigest()[:8]

    assert guide.source_build == esperado


def test_o_carimbo_da_tela_bate_com_o_que_o_agente_calcula_de_si():
    """Dois carimbos que não batem seriam pior que carimbo nenhum."""
    import sys

    from shopman.backstage.projections.pos_agent import AGENT_SOURCE

    sys.path.insert(0, str(AGENT_SOURCE.parent))
    try:
        import drawer_agent
    finally:
        sys.path.pop(0)

    guide = build_agent_install(_terminal(AGENT), download_url="/x/")
    assert guide.source_build == drawer_agent.build_id()
