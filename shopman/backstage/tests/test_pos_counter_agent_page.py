"""A tela do Admin que entrega o agente do balcão.

O dono já está no Admin configurando o terminal. O que se prova aqui é que ele
consegue terminar a tarefa sem sair dali: baixar o arquivo e ler o comando já
preenchido — e que o token deixou de ser transcrito à mão.
"""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Terminal

from shopman.backstage.admin.print_jobs import PrintAgentCredentialAdmin
from shopman.backstage.admin.terminal import TerminalForm
from shopman.backstage.models import PrintAgentCredential
from shopman.backstage.projections.pos_agent import build_agent_install
from shopman.backstage.services.pos_hardware import CashDrawerConfig

pytestmark = pytest.mark.django_db


def _terminal(drawer=None, ref="pdv-agente") -> Terminal:
    metadata = {"hardware": {"cash_drawer": drawer}} if drawer else {}
    return Terminal.objects.create(ref=ref, label="Balcão", metadata=metadata)


AGENT = {
    "adapter": "agent",
    "agent_url": "http://127.0.0.1:47811",
    "token": "token-do-balcao-com-tamanho",
}


def _relay_terminal(ref="pdv-agente") -> Terminal:
    terminal = _terminal(AGENT, ref=ref)
    hardware = terminal.metadata["hardware"]
    hardware["printer"] = {
        "enabled": True,
        "adapter": "driver",
        "model": "epson-tm-t20",
        "role": "preparation",
        "roll_width_mm": 80,
        "label_width_mm": 60,
        "label_height_mm": 40,
        "label_print_width_mm": 52,
        "label_cut_mode": "none",
    }
    terminal.save(update_fields=("metadata",))
    return terminal


def _credential_version(credential: PrintAgentCredential) -> str:
    return f"{credential.ref}:{credential.rotated_at.isoformat()}"


def _bearer_from_response(response) -> str:
    match = re.search(
        r"([0-9a-f-]{36}\.[A-Za-z0-9_-]{20,})",
        response.content.decode(),
    )
    assert match, response.content.decode()
    return match.group(1)


@pytest.fixture
def manager(client):
    # Sem Shop o OnboardingMiddleware manda todo mundo para o setup e o teste
    # mede o redirect, não a tela.
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    user = get_user_model().objects.create_user(username="dono", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Terminal)
    user.user_permissions.add(
        Permission.objects.get(content_type=ct, codename="change_terminal"),
        Permission.objects.get(content_type__app_label="cashman", codename="manage_operators"),
    )
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
        "counter_agent_url": "http://127.0.0.1:47811",
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
    form = TerminalForm(_form_data(), instance=terminal)

    assert form.is_valid(), form.errors
    form.save()

    config = CashDrawerConfig.from_terminal(Terminal.objects.get(pk=terminal.pk))
    assert len(config.token) >= 16
    assert config.kicks_by_software is True
    assert config.misconfigured_reason == ""


def test_salvar_de_novo_NAO_troca_o_token():
    """Trocar sozinho deixaria o balcão levando 401 sem ninguém ter pedido."""
    terminal = _terminal(AGENT)
    TerminalForm(_form_data(), instance=terminal).save()

    assert CashDrawerConfig.from_terminal(Terminal.objects.get(pk=terminal.pk)).token == AGENT["token"]


def test_marcar_gerar_novo_troca_o_token():
    terminal = _terminal(AGENT)
    form = TerminalForm(_form_data(drawer_rotate_token="on"), instance=terminal)

    assert form.is_valid(), form.errors
    form.save()

    assert CashDrawerConfig.from_terminal(Terminal.objects.get(pk=terminal.pk)).token != AGENT["token"]


def test_editar_geometria_da_etiqueta_preserva_a_fila_e_o_modelo_aferidos():
    terminal = _terminal(AGENT)
    terminal.metadata["hardware"]["printer"] = {
        "enabled": True,
        "adapter": "driver",
        "model": "epson-tm-t20",
        "queue": "TM-T20",
        "role": "preparation",
    }
    terminal.save(update_fields=("metadata",))
    form = TerminalForm(
        _form_data(
            printer_enabled="on",
            printer_role="preparation",
            printer_roll_width_mm="80",
            printer_label_width_mm="60",
            printer_label_height_mm="40",
            printer_cut_mode="none",
        ),
        instance=terminal,
    )

    assert form.is_valid(), form.errors
    form.save()
    printer = Terminal.objects.get(pk=terminal.pk).metadata["hardware"]["printer"]

    assert printer["adapter"] == "driver"
    assert printer["model"] == "epson-tm-t20"
    assert printer["queue"] == "TM-T20"
    assert (printer["label_width_mm"], printer["label_height_mm"]) == (60, 40)


# ── A projection das instruções ───────────────────────────────────────────


def test_o_comando_ja_vem_com_o_token_daquele_balcao(settings):
    settings.SHOPMAN_POS_BASE_URL = "https://pos.staging.exemplo/"
    settings.SHOPMAN_PRODUCTION_BASE_URL = "https://prod.staging.exemplo/mise-en-place"
    guide = build_agent_install(_terminal(AGENT), download_url="/baixar/")

    install = next(step for step in guide.steps if step.command.startswith("python3"))
    assert f"--token {AGENT['token']}" in install.command
    # A origem sai da config do deployment, não de um chute no código.
    assert "--origin https://pos.staging.exemplo" in install.command
    assert "--origin https://prod.staging.exemplo" in install.command


def test_sem_pos_base_url_o_comando_nao_inventa_origem(settings):
    """Melhor o instalador usar o default dele do que escrever endereço errado."""
    settings.SHOPMAN_POS_BASE_URL = ""
    settings.SHOPMAN_ORDERS_BASE_URL = ""
    settings.SHOPMAN_KDS_BASE_URL = ""
    settings.SHOPMAN_PRODUCTION_BASE_URL = ""
    settings.SHOPMAN_MARKETING_BASE_URL = ""
    settings.SHOPMAN_BI_BASE_URL = ""
    settings.SHOPMAN_PURCHASE_BASE_URL = ""
    guide = build_agent_install(_terminal(AGENT), download_url="/baixar/")

    install = next(step for step in guide.steps if step.command.startswith("python3"))
    assert "--origin" not in install.command


def test_o_comando_de_uso_unico_inclui_o_relay_sem_expor_segredo_no_argv(settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    settings.SHOPMAN_POS_BASE_URL = "https://pdv.exemplo.test"
    settings.SHOPMAN_PRODUCTION_BASE_URL = "https://prod.exemplo.test"
    guide = build_agent_install(
        _relay_terminal(),
        download_url="/baixar/",
        relay_bearer="credencial.um-segredo",
    )

    assert "--origin https://pdv.exemplo.test" in guide.relay_install_command
    assert "--origin https://prod.exemplo.test" in guide.relay_install_command
    assert "--server-url https://api.exemplo.test" in guide.relay_install_command
    assert "--station pdv-agente" in guide.relay_install_command
    assert "--relay-token-prompt" in guide.relay_install_command
    assert "credencial.um-segredo" not in guide.relay_install_command
    assert guide.relay_secret_once == "credencial.um-segredo"


def test_projection_nao_entrega_bearer_se_o_relay_estiver_bloqueado(settings):
    settings.SHOPMAN_OPERATOR_API_HOST = ""
    guide = build_agent_install(
        _relay_terminal(),
        download_url="/baixar/",
        relay_bearer="credencial.que-nao-pode-vazar",
    )

    assert guide.relay_can_issue is False
    assert guide.relay_install_command == ""
    assert guide.relay_secret_once == ""


def test_sem_bearer_a_projection_nunca_reconstroi_o_segredo(settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    credential, bearer = PrintAgentCredential.issue(terminal=terminal, label="relay")

    guide = build_agent_install(terminal, download_url="/baixar/")

    assert guide.relay_active is True
    assert guide.relay_install_command == ""
    assert bearer not in repr(guide)
    assert credential.token_digest not in repr(guide)


def test_terminal_de_gaveta_manual_explica_em_vez_de_oferecer_download():
    guide = build_agent_install(_terminal({"adapter": "manual"}), download_url="/baixar/")

    assert guide.configured is False
    assert "Ative a impressora" in guide.blocker
    assert guide.steps == ()


# ── A tela ────────────────────────────────────────────────────────────────


def test_a_pagina_mostra_o_comando_pronto(client, manager):
    terminal = _terminal(AGENT)
    response = client.get(reverse("admin_console_pos_counter_agent", args=[terminal.ref]))

    assert response.status_code == 200
    body = response.content.decode()
    assert AGENT["token"] in body
    assert "Baixar counter_agent.py" in body


def test_a_pagina_exige_confirmacao_antes_de_emitir_o_relay(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    url = reverse("admin_console_pos_counter_agent", args=[terminal.ref])

    response = client.post(url, {"action": "prepare_relay_issue"})

    assert response.status_code == 200
    assert "Confirmar novo pareamento" in response.content.decode()
    assert PrintAgentCredential.objects.count() == 0


def test_emitir_relay_mostra_um_comando_uma_vez_sem_cache(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    settings.SHOPMAN_POS_BASE_URL = "https://pdv.exemplo.test"
    settings.SHOPMAN_PRODUCTION_BASE_URL = "https://prod.exemplo.test"
    terminal = _relay_terminal()
    url = reverse("admin_console_pos_counter_agent", args=[terminal.ref])

    response = client.post(
        url,
        {"action": "issue_relay", "expected_credential_version": ""},
    )

    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    assert response["Referrer-Policy"] == "no-referrer"
    body = response.content.decode()
    bearer = _bearer_from_response(response)
    credential = PrintAgentCredential.authenticate(bearer)
    assert credential is not None and credential.terminal_id == terminal.pk
    assert bearer not in credential.token_digest
    assert "--server-url https://api.exemplo.test" in body
    assert "--station pdv-agente" in body
    assert "--relay-token-prompt" in body
    assert f"--relay-token {bearer}" not in body
    assert bearer not in response.get("Location", "")

    # Um GET posterior conhece o estado, nunca o segredo exibido uma vez.
    reopened = client.get(url)
    assert reopened.status_code == 200
    assert bearer not in reopened.content.decode()
    assert "Aguardando o agente" in reopened.content.decode()


def test_reparear_rotaciona_o_mesmo_par_e_audita_sem_segredo(client, manager, settings):
    from django.contrib.admin.models import LogEntry

    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    old, old_bearer = PrintAgentCredential.issue(terminal=terminal, label="antigo")
    url = reverse("admin_console_pos_counter_agent", args=[terminal.ref])

    response = client.post(
        url,
        {
            "action": "issue_relay",
            "expected_credential_version": _credential_version(old),
        },
    )

    assert response.status_code == 200
    old.refresh_from_db()
    assert old.is_active is True and old.revoked_at is None
    assert PrintAgentCredential.authenticate(old_bearer) is None
    assert PrintAgentCredential.objects.filter(terminal=terminal, is_active=True).count() == 1
    assert PrintAgentCredential.objects.filter(terminal=terminal).count() == 1
    new_bearer = _bearer_from_response(response)
    assert PrintAgentCredential.authenticate(new_bearer) == old
    log = LogEntry.objects.get(object_id=str(terminal.pk))
    assert "Credencial do relay" in log.change_message
    assert "--relay-token" not in log.change_message


def test_reparear_limpa_presenca_do_bearer_anterior(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    credential, _ = PrintAgentCredential.issue(terminal=terminal, label="antigo")
    credential.last_seen_at = timezone.now()
    credential.last_build = "build-antigo"
    credential.last_remote_addr = "192.0.2.10"
    credential.save(update_fields=("last_seen_at", "last_build", "last_remote_addr"))

    response = client.post(
        reverse("admin_console_pos_counter_agent", args=[terminal.ref]),
        {
            "action": "issue_relay",
            "expected_credential_version": _credential_version(credential),
        },
    )

    assert response.status_code == 200
    credential.refresh_from_db()
    assert credential.last_seen_at is None
    assert credential.last_build == ""
    assert credential.last_remote_addr is None


def test_replay_do_mesmo_formulario_nao_rotaciona_duas_vezes(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    credential, old_bearer = PrintAgentCredential.issue(terminal=terminal, label="atual")
    stale_version = _credential_version(credential)
    url = reverse("admin_console_pos_counter_agent", args=[terminal.ref])
    payload = {"action": "issue_relay", "expected_credential_version": stale_version}

    first = client.post(url, payload)
    first_bearer = _bearer_from_response(first)
    credential.refresh_from_db()
    version_after_first = _credential_version(credential)
    second = client.post(url, payload)

    credential.refresh_from_db()
    assert first.status_code == 200 and second.status_code == 302
    assert PrintAgentCredential.authenticate(old_bearer) is None
    assert PrintAgentCredential.authenticate(first_bearer) == credential
    assert _credential_version(credential) == version_after_first


def test_emitir_relay_preserva_token_local_fila_e_origens(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    terminal.metadata["hardware"]["printer"]["queue"] = "TM-T20 aferida"
    terminal.metadata["hardware"]["cash_drawer"]["allowed_origins"] = ["https://pdv.exemplo.test"]
    terminal.save(update_fields=("metadata",))
    metadata_before = terminal.metadata

    response = client.post(
        reverse("admin_console_pos_counter_agent", args=[terminal.ref]),
        {"action": "issue_relay", "expected_credential_version": ""},
    )

    assert response.status_code == 200
    terminal.refresh_from_db()
    assert terminal.metadata == metadata_before
    assert terminal.metadata["hardware"]["cash_drawer"]["token"] == AGENT["token"]


def test_get_nunca_emite_nem_rotaciona_credencial(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    credential, bearer = PrintAgentCredential.issue(terminal=terminal, label="atual")
    rotated_at = credential.rotated_at

    response = client.get(reverse("admin_console_pos_counter_agent", args=[terminal.ref]))

    credential.refresh_from_db()
    assert response.status_code == 200
    assert credential.rotated_at == rotated_at
    assert PrintAgentCredential.authenticate(bearer) == credential


def test_admin_generico_nao_reativa_credencial_revogada():
    assert "is_active" in PrintAgentCredentialAdmin.readonly_fields


def test_cas_recusa_substituir_um_pareamento_que_mudou(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    current, bearer = PrintAgentCredential.issue(terminal=terminal, label="atual")
    url = reverse("admin_console_pos_counter_agent", args=[terminal.ref])

    response = client.post(
        url,
        {"action": "issue_relay", "expected_credential_version": "ref-antiga"},
    )

    assert response.status_code == 302
    current.refresh_from_db()
    assert current.is_active is True
    assert PrintAgentCredential.authenticate(bearer) == current
    assert PrintAgentCredential.objects.filter(terminal=terminal).count() == 1


def test_credencial_conectada_aparece_como_ativa(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    credential, _ = PrintAgentCredential.issue(terminal=terminal)
    credential.last_seen_at = timezone.now() - timedelta(seconds=1)
    credential.save(update_fields=("last_seen_at",))

    response = client.get(reverse("admin_console_pos_counter_agent", args=[terminal.ref]))

    assert response.status_code == 200
    assert "Relay conectado" in response.content.decode()


def test_relay_fica_bloqueado_sem_perfil_de_impressora(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _terminal(AGENT)
    url = reverse("admin_console_pos_counter_agent", args=[terminal.ref])

    response = client.post(
        url,
        {"action": "issue_relay", "expected_credential_version": ""},
    )

    assert response.status_code == 302
    assert PrintAgentCredential.objects.count() == 0


def test_quem_nao_configura_terminal_nao_emite_credencial_de_relay(client, settings):
    from shopman.shop.models import Shop

    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    Shop.objects.create(name="Loja")
    terminal = _relay_terminal()
    user = get_user_model().objects.create_user(username="curioso", password="x", is_staff=True)
    client.force_login(user)

    response = client.post(
        reverse("admin_console_pos_counter_agent", args=[terminal.ref]),
        {"action": "issue_relay", "expected_credential_version": ""},
    )

    assert response.status_code in (302, 403, 404)
    assert PrintAgentCredential.objects.count() == 0


def test_quem_so_edita_terminal_consulta_mas_nao_pareia(client, settings):
    from shopman.shop.models import Shop

    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    Shop.objects.create(name="Loja")
    terminal = _relay_terminal()
    user = get_user_model().objects.create_user(username="tecnico", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Terminal)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="change_terminal"))
    client.force_login(user)
    url = reverse("admin_console_pos_counter_agent", args=[terminal.ref])

    page = client.get(url)
    attempt = client.post(
        url,
        {"action": "issue_relay", "expected_credential_version": ""},
    )

    assert page.status_code == 200
    body = page.content.decode()
    assert "Um gerente habilitado faz o pareamento" in body
    assert "Ativar impressão por tablets" not in body
    assert attempt.status_code == 403
    assert PrintAgentCredential.objects.count() == 0


def test_post_de_pareamento_exige_csrf(manager, settings):
    from django.test import Client

    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(manager)

    response = csrf_client.post(
        reverse("admin_console_pos_counter_agent", args=[terminal.ref]),
        {"action": "issue_relay", "expected_credential_version": ""},
    )

    assert response.status_code == 403
    assert PrintAgentCredential.objects.count() == 0


def test_terminal_inativo_nao_recebe_credencial(client, manager, settings):
    settings.SHOPMAN_OPERATOR_API_HOST = "api.exemplo.test"
    terminal = _relay_terminal()
    terminal.is_active = False
    terminal.save(update_fields=("is_active",))

    response = client.post(
        reverse("admin_console_pos_counter_agent", args=[terminal.ref]),
        {"action": "issue_relay", "expected_credential_version": ""},
    )

    assert response.status_code == 404
    assert PrintAgentCredential.objects.count() == 0


def test_o_download_entrega_o_agente_de_verdade(client, manager):
    terminal = _terminal(AGENT)
    response = client.get(reverse("admin_console_pos_counter_agent_download", args=[terminal.ref]))

    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    assert "counter_agent.py" in response["Content-Disposition"]
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

    response = client.get(reverse("admin_console_pos_counter_agent_download", args=[terminal.ref]))
    assert response.status_code in (302, 403, 404)


def test_terminal_inexistente_nao_serve_arquivo(client, manager):
    response = client.get(reverse("admin_console_pos_counter_agent_download", args=["fantasma"]))
    assert response.status_code == 404


def test_a_config_do_terminal_linka_para_a_tela(client, manager):
    terminal = _terminal(AGENT)
    response = client.get(reverse("admin:cashman_terminal_change", args=[terminal.pk]))

    assert response.status_code == 200
    assert reverse("admin_console_pos_counter_agent", args=[terminal.ref]) in response.content.decode()


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
        next(s for s in build_agent_install(terminal, download_url="/x/", os_key=k).steps if "--install" in s.command)
        .command.split("--token ")[1]
        .split()[0]
        for k in ("linux", "windows", "macos")
    }
    assert tokens == {AGENT["token"]}


@pytest.mark.parametrize(
    "os_key,marca",
    [
        ("linux", "journalctl"),
        ("macos", "counter-agent.log"),
        ("windows", "LOCALAPPDATA"),
    ],
)
def test_cada_sistema_diz_onde_ver_o_registro(os_key, marca):
    """Prometo na tela que 'o agente registra cada abertura' — em todos eles."""
    # O log saiu do roteiro de instalação e virou comando do dia a dia: ver
    # registro se faz sempre, instalar se faz uma vez.
    guide = build_agent_install(_terminal(AGENT), download_url="/x/", os_key=os_key)
    assert any(marca in c.command for c in guide.commands)


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
    response = client.get(reverse("admin_console_pos_counter_agent", args=[terminal.ref]) + "?so=windows")

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
    body = client.get(reverse("admin_console_pos_counter_agent", args=[terminal.ref])).content.decode()

    assert "U+002D" not in body
    assert "{#" not in body and "#}" not in body


def test_terminal_sem_gaveta_mostra_NAO_CONFIGURADA_selecionada():
    """Sem opção vazia o navegador marca a primeira ("Com a chave") sozinho.

    O formulário então exibia um estado que o banco não tinha, e salvar sem
    tocar no campo gravava `manual`. Estado real e exibido divergindo é como a
    config da gaveta some sem ninguém ter pedido.
    """
    form = TerminalForm(instance=_terminal())
    html = str(form["drawer_adapter"])

    assert 'value=""' in html, "falta a opção vazia"
    assert html.index('value=""') < html.index('value="manual"'), "a vazia tem que vir primeiro"


def test_terminal_com_agente_abre_o_formulario_com_agente_marcado():
    form = TerminalForm(instance=_terminal(AGENT))
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
        import counter_agent
    finally:
        sys.path.pop(0)

    guide = build_agent_install(_terminal(AGENT), download_url="/x/")
    assert guide.source_build == counter_agent.build_id()


def test_a_tela_traz_TODO_comando_que_o_balcao_precisa():
    """Comando que só existe numa conversa é comando que alguém transcreve errado.

    O dono não tem terminal de desenvolvedor no balcão: cada caractere digitado à
    mão é uma chance de errar e concluir que o defeito é da impressora. A tela é
    o único lugar onde o comando pode estar certo por construção.
    """
    from shopman.backstage.projections.pos_agent import _commands

    for so in ("linux", "macos", "windows"):
        comandos = " ".join(c.command for c in _commands(so))
        for flag in ("--doctor", "--kick", "--test-print", "--drawer-status"):
            assert flag in comandos, f"{flag} ausente em {so}"
        assert all(c.command for c in _commands(so)), "todo comando desta lista tem que ser copiável"


def test_os_comandos_apontam_para_o_agente_INSTALADO():
    """O arquivo baixado é descartável — o instalador se copia sozinho.

    Rodar `--doctor` na pasta de downloads diagnostica uma cópia que não é a que
    está no ar, e o relatório sairia mentindo sobre a versão.
    """
    from shopman.backstage.projections.pos_agent import _commands

    for so, marca in (("linux", "nelson-pos-counter"), ("windows", "NelsonPosCounter")):
        for passo in _commands(so):
            if "--" in passo.command:  # os do agente, não o de log
                assert marca in passo.command, f"{so}: {passo.command} não aponta para o instalado"


def test_os_comandos_saem_mesmo_com_o_terminal_mal_configurado():
    """É justamente quando falta config que alguém precisa do `--doctor`."""
    guia = build_agent_install(_terminal(None), download_url="/x/")

    assert guia.blocker, "este terminal deveria estar bloqueado"
    assert guia.steps == (), "o roteiro de instalação não sai com blocker"
    assert guia.commands, "mas os comandos de diagnóstico saem"
