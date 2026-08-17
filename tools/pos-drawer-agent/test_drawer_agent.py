"""Testes do agente da gaveta.

O que estes testes travam é o que ninguém consegue conferir no balcão às 6h da
manhã: os bytes exatos, o `-o raw` que impede o CUPS de imprimir o comando em
vez de executá-lo, e a recusa de quem não tem token.
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import drawer_agent  # noqa: E402
from drawer_agent import AgentConfig, DrawerHandler, kick_bytes  # noqa: E402

TOKEN = "token-de-teste-com-tamanho-suficiente"
ORIGIN = "https://pdv.boulangerie.com.br"


# ── Bytes ─────────────────────────────────────────────────────────────────


CANONICAL_KICK = bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])


def test_kick_bytes_sao_os_cinco_do_manual():
    """50ms/500ms → `1B 70 00 19 FA`, a sequência canônica da TM-T20.

    `0x19`/`0xFA` são 25 e 250 **unidades** de 2ms. Chamar isso de "pulso
    25/250ms" é o atalho que erra por metade — e é o default que este teste
    protege.
    """
    assert kick_bytes(pin=0, on_ms=50, off_ms=500) == CANONICAL_KICK


def test_o_default_do_agente_e_a_sequencia_canonica():
    """Quem não configura pulso nenhum tem que sair com os bytes do manual."""
    assert kick_bytes() == CANONICAL_KICK


def test_kick_bytes_aceita_o_segundo_pino():
    assert kick_bytes(pin=1, on_ms=50, off_ms=500)[2] == 1


def test_kick_bytes_recusa_pino_inexistente():
    with pytest.raises(ValueError, match="pino"):
        kick_bytes(pin=2)


def test_kick_bytes_recusa_pulso_que_cozinha_o_solenoide():
    """Acima de 510ms o byte satura — e o solenoide não é feito para carga contínua."""
    with pytest.raises(ValueError, match="longo demais"):
        kick_bytes(on_ms=600)


def test_kick_bytes_recusa_pulso_curto_demais():
    with pytest.raises(ValueError, match="curto demais"):
        kick_bytes(on_ms=1)


# ── Spooler ───────────────────────────────────────────────────────────────


def test_send_raw_usa_o_flag_raw(monkeypatch):
    """Sem `-o raw` o CUPS IMPRIME os cinco bytes em vez de executá-los."""
    captured = {}

    class Done:
        returncode = 0
        stdout = b"request id is TM-T20-7 (1 file(s))"
        stderr = b""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return Done()

    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(drawer_agent.subprocess, "run", fake_run)

    job = drawer_agent.send_raw(b"\x1b\x70\x00\x19\xfa", queue="TM-T20")

    assert "-o" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-o") + 1] == "raw"
    assert "-d" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-d") + 1] == "TM-T20"
    assert captured["input"] == b"\x1b\x70\x00\x19\xfa"
    assert job == "TM-T20-7"


def test_send_raw_propaga_a_falha_do_cups(monkeypatch):
    class Failed:
        returncode = 1
        stdout = b""
        stderr = b"lp: The printer or class does not exist."

    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(drawer_agent.subprocess, "run", lambda *a, **k: Failed())

    with pytest.raises(drawer_agent.SpoolerError, match="does not exist"):
        drawer_agent.send_raw(b"\x1b", queue="fantasma")


# ── Config ────────────────────────────────────────────────────────────────


def test_config_recusa_token_fraco():
    with pytest.raises(SystemExit, match="token"):
        AgentConfig.from_dict({"queue": "TM-T20", "token": "curto"})


def test_config_recusa_sem_fila():
    with pytest.raises(SystemExit, match="queue"):
        AgentConfig.from_dict({"token": TOKEN})


def test_config_sem_allowlist_aceita_qualquer_origem():
    config = AgentConfig.from_dict({"queue": "q", "token": TOKEN})
    assert config.allows("https://qualquer.coisa")


def test_config_com_allowlist_ignora_barra_final():
    config = AgentConfig.from_dict({"queue": "q", "token": TOKEN, "allowed_origins": [ORIGIN + "/"]})
    assert config.allows(ORIGIN)
    assert not config.allows("https://intruso.example")


# ── HTTP ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent(monkeypatch):
    """Sobe o agente de verdade numa porta efêmera, com o spooler dublado."""
    sent = []

    def fake_send_raw(payload, *, queue, title="cash-drawer"):
        sent.append({"payload": payload, "queue": queue, "title": title})
        return "TM-T20-1"

    monkeypatch.setattr(drawer_agent, "send_raw", fake_send_raw)
    monkeypatch.setattr(
        drawer_agent, "probe_queue",
        lambda queue: {"ok": True, "accepting": True, "reason": ""},
    )

    config = AgentConfig.from_dict(
        {"queue": "TM-T20", "token": TOKEN, "port": 0, "allowed_origins": [ORIGIN]}
    )
    handler = type("Bound", (DrawerHandler,), {"config": config})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base, sent
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post(base, path, body, origin=ORIGIN):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read()), dict(response.headers)


def test_kick_com_token_valido_manda_os_bytes(agent):
    base, sent = agent
    status, body, _ = _post(base, "/kick", {"token": TOKEN, "reason": "cash_sale"})

    assert status == 200
    assert body["ok"] is True
    assert sent[0]["payload"] == bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])
    assert sent[0]["title"] == "gaveta:cash_sale"


def test_kick_aplica_o_pulso_que_o_django_mandou(agent):
    """O pulso é do terminal, não do agente — senão haveria dois donos."""
    base, sent = agent
    _post(base, "/kick", {"token": TOKEN, "pulse": {"pin": 1, "on_ms": 100, "off_ms": 100}})

    assert sent[0]["payload"] == bytes([0x1B, 0x70, 0x01, 0x32, 0x32])


def test_kick_sem_token_e_recusado_e_nao_toca_no_spooler(agent):
    base, sent = agent
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/kick", {"reason": "cash_sale"})

    assert exc.value.code == 401
    assert sent == []


def test_kick_de_origem_estranha_e_recusado(agent):
    """A aba que o operador abriu por engano não abre a gaveta."""
    base, sent = agent
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/kick", {"token": TOKEN}, origin="https://intruso.example")

    assert exc.value.code == 403
    assert sent == []


def test_kick_com_pulso_invalido_e_recusado(agent):
    base, sent = agent
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/kick", {"token": TOKEN, "pulse": {"on_ms": 9000}})

    assert exc.value.code == 400
    assert sent == []


def test_falha_do_spooler_vira_502_e_nao_500(agent, monkeypatch):
    """A tela precisa saber que a gaveta NÃO abriu, com o motivo do CUPS."""
    base, _ = agent

    def boom(*a, **k):
        raise drawer_agent.SpoolerError("fila 'TM-T20' não existe")

    monkeypatch.setattr(drawer_agent, "send_raw", boom)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/kick", {"token": TOKEN})

    assert exc.value.code == 502
    assert "não existe" in json.loads(exc.value.read())["error"]


def test_preflight_responde_o_header_de_private_network(agent):
    """Inerte hoje; é o que evita uma visita ao balcão se o PNA voltar."""
    base, _ = agent
    request = urllib.request.Request(
        base + "/kick",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        method="OPTIONS",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 204
        assert response.headers.get("Access-Control-Allow-Private-Network") == "true"
        assert response.headers.get("Access-Control-Allow-Origin") == ORIGIN


def test_health_devolve_a_sonda_da_fila(agent):
    base, _ = agent
    with urllib.request.urlopen(base + "/health", timeout=5) as response:
        body = json.loads(response.read())

    assert body["ok"] is True
    assert body["queue"] == "TM-T20"
    assert body["version"] == drawer_agent.VERSION


# ── Instalação ────────────────────────────────────────────────────────────


def test_instalar_gera_config_utilizavel(tmp_path):
    path = tmp_path / "agent.json"
    config, created = drawer_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo/")

    assert created is True
    assert config["queue"] == "TM-T20"
    # A allowlist guarda a origem sem barra final, senão o `allows()` erra por
    # um caractere e a gaveta para de abrir sem ninguém entender por quê.
    assert config["allowed_origins"] == ["https://pos.exemplo"]
    # O token nasce forte o bastante para o próprio agente aceitar.
    assert AgentConfig.from_dict(config).token == config["token"]


def test_reinstalar_PRESERVA_o_token(tmp_path):
    """Trocar o token numa reinstalação deixaria o PDV levando 401 até alguém
    colar o novo no Admin — descoberto no meio do sábado."""
    path = tmp_path / "agent.json"
    first, _ = drawer_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo")
    second, created = drawer_agent.write_config(path, queue="OUTRA", origin="https://outra.exemplo")

    assert created is False
    assert second["token"] == first["token"]
    assert second["queue"] == "TM-T20"


def test_token_do_admin_manda_na_primeira_instalacao(tmp_path):
    """O Admin é o dono do par — o agente não inventa um por cima."""
    path = tmp_path / "agent.json"
    config, _ = drawer_agent.write_config(
        path, queue="TM-T20", origin="https://pos.exemplo", token=TOKEN
    )
    assert config["token"] == TOKEN


def test_token_novo_do_admin_ROTACIONA_a_config_existente(tmp_path):
    """Rotação é a única razão para mexer num token já instalado."""
    path = tmp_path / "agent.json"
    drawer_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo", token=TOKEN)
    config, written = drawer_agent.write_config(
        path, queue="TM-T20", origin="https://pos.exemplo", token="token-rotacionado-pelo-admin"
    )

    assert written is True
    assert config["token"] == "token-rotacionado-pelo-admin"
    assert json.loads(path.read_text())["token"] == "token-rotacionado-pelo-admin"


def test_reinstalar_com_o_MESMO_token_nao_reescreve(tmp_path):
    path = tmp_path / "agent.json"
    drawer_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo", token=TOKEN)
    _, written = drawer_agent.write_config(
        path, queue="TM-T20", origin="https://pos.exemplo", token=TOKEN
    )
    assert written is False


def test_sem_origem_a_allowlist_fica_vazia_em_vez_de_chutar_um_dominio(tmp_path):
    """A primeira versão cravava um domínio inventado aqui.

    Ele não correspondia a nada no deployment (o PDV é `pdv.boulangerie.com.br`),
    então instalar sem `--origin` daria 403 calado na gaveta. Vazio é mais
    frouxo, mas é honesto e o instalador avisa.
    """
    path = tmp_path / "agent.json"
    config, _ = drawer_agent.write_config(path, queue="TM-T20", origin="", token=TOKEN)

    assert config["allowed_origins"] == []
    assert AgentConfig.from_dict(config).allows("https://pdv.boulangerie.com.br")


def test_nenhum_dominio_de_deployment_cravado_no_agente():
    """O agente é genérico. Quem sabe a origem é o Django, e ele a injeta."""
    source = (Path(__file__).parent / "drawer_agent.py").read_text(encoding="utf-8")
    for invented in ("nelsonboulangerie.com.br", "boulangerie.com.br"):
        assert invented not in source, f"domínio de deployment cravado no agente: {invented}"


def test_config_nasce_ilegivel_para_outros_usuarios(tmp_path):
    path = tmp_path / "agent.json"
    drawer_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo")
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_a_unit_aponta_para_o_arquivo_instalado_e_reergue_sozinha():
    unit = drawer_agent._unit_text(Path("/home/pdv/.local/share/nelson-pos-drawer/drawer_agent.py"))
    assert "ExecStart=/usr/bin/env python3 /home/pdv/.local/share/nelson-pos-drawer/drawer_agent.py" in unit
    assert "Restart=always" in unit
    # O balcão abre antes do CUPS estar de pé se a ordem não for dita.
    assert "After=cups.service" in unit


def test_instalar_com_fila_inexistente_para_antes_de_mexer_em_nada(monkeypatch, capsys):
    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(drawer_agent, "list_queues", lambda: ["OUTRA"])

    assert drawer_agent.install(["--install", "--queue", "TM-T20"]) == 1
    assert "não está entre as" in capsys.readouterr().err


def test_instalar_sem_cups_diz_o_que_falta(monkeypatch, capsys):
    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: None)

    assert drawer_agent.install(["--install"]) == 1
    assert "CUPS" in capsys.readouterr().err


# ── Multiplataforma ───────────────────────────────────────────────────────
#
# Linux é o SO oficial do balcão. Windows existe porque a máquina do caixa
# ainda roda Windows e a troca não dá para ser feita com a loja aberta; macOS
# existe para o Pablo testar do Mac dele.
#
# ⚠️ O caminho Windows NÃO foi executado em Windows nenhum — não há máquina
# aqui. O que estes testes travam é o despacho e o contrato; o kick de verdade
# só o balcão confirma.


def test_linux_e_macos_usam_o_MESMO_comando(monkeypatch):
    """O macOS quase virou um terceiro caminho por um erro de leitura meu.

    `lpadmin -m raw` é que foi removido (o DRIVER raw). A opção de job `-o raw`
    continua entregando os bytes intactos — medido em CUPS 2.3.4 do macOS.
    """
    captured = {}

    class Done:
        returncode = 0
        stdout = b"request id is TM-T20-1 (1 file(s))"
        stderr = b""

    monkeypatch.setattr(drawer_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        drawer_agent.subprocess, "run", lambda cmd, **k: (captured.update(cmd=cmd), Done())[1]
    )

    drawer_agent.send_raw(CANONICAL_KICK, queue="TM-T20")
    assert captured["cmd"][:5] == ["/usr/bin/lp", "-d", "TM-T20", "-o", "raw"]


def test_windows_despacha_para_o_spooler_proprio(monkeypatch):
    """No Windows não existe `lp`; quem entrega é o winspool."""
    chamado = {}
    monkeypatch.setattr(drawer_agent, "IS_WINDOWS", True)
    monkeypatch.setattr(
        drawer_agent, "_send_raw_windows",
        lambda payload, *, queue, title: chamado.update(payload=payload, queue=queue) or "42",
    )

    assert drawer_agent.send_raw(CANONICAL_KICK, queue="TM-T20") == "42"
    assert chamado["payload"] == CANONICAL_KICK


def test_a_sonda_tambem_despacha_por_plataforma(monkeypatch):
    monkeypatch.setattr(drawer_agent, "IS_WINDOWS", True)
    monkeypatch.setattr(drawer_agent, "_probe_queue_windows", lambda q: {"ok": True, "accepting": True, "reason": q})
    assert drawer_agent.probe_queue("TM-T20")["reason"] == "TM-T20"


def test_o_launchagent_do_macos_reergue_sozinho():
    plist = drawer_agent._plist_text(Path("/Users/pdv/agente/drawer_agent.py"))
    assert "<string>/Users/pdv/agente/drawer_agent.py</string>" in plist
    # KeepAlive é o Restart=always do launchd: ninguém confere se o agente caiu.
    assert "<key>KeepAlive</key><true/>" in plist
    assert drawer_agent.LAUNCH_AGENT_LABEL in plist


def test_o_plist_do_macos_e_xml_valido():
    """Plist malformado o launchd recusa em silêncio, e a gaveta some no boot."""
    import plistlib

    parsed = plistlib.loads(drawer_agent._plist_text(Path("/tmp/x.py")).encode())
    assert parsed["Label"] == drawer_agent.LAUNCH_AGENT_LABEL
    assert parsed["RunAtLoad"] is True
    assert parsed["ProgramArguments"][1] == "/tmp/x.py"


# ── O instalador confere o que afirma ─────────────────────────────────────


def test_o_launcher_do_windows_da_UM_caminho_ao_schtasks(monkeypatch, tmp_path):
    """Aspas aninhadas em `/tr` fazem o schtasks gravar comando mutilado.

    Foi o defeito real do balcão: a tarefa nasceu quebrada, o agente não subiu,
    e o `--kick` da linha de comando continuou funcionando — então nada gritou.
    """
    monkeypatch.setattr(drawer_agent, "INSTALL_DIR", tmp_path)
    monkeypatch.setattr(drawer_agent, "LOG_PATH", tmp_path / "drawer-agent.log")

    launcher = drawer_agent._windows_launcher(tmp_path / "drawer_agent.py")

    assert launcher.suffix == ".cmd"
    conteudo = launcher.read_text(encoding="utf-8")
    assert "drawer_agent.py" in conteudo
    assert "--log-file" in conteudo


def test_instalador_reprova_quando_o_agente_nao_sobe(monkeypatch, capsys, tmp_path):
    """Dizer 'instalado' sem medir foi o que mandou o defeito para o balcão."""
    monkeypatch.setattr(drawer_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(drawer_agent, "IS_MACOS", False)
    monkeypatch.setattr(drawer_agent, "INSTALL_DIR", tmp_path / "inst")
    monkeypatch.setattr(drawer_agent, "DEFAULT_CONFIG_PATH", tmp_path / "agent.json")
    monkeypatch.setattr(drawer_agent, "list_queues", lambda: ["TM-T20"])
    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(drawer_agent, "_autostart_linux", lambda target: None)
    monkeypatch.setattr(drawer_agent, "_wait_until_listening", lambda config, **k: None)

    codigo = drawer_agent.install(["--install", "--queue", "TM-T20", "--token", TOKEN])

    saida = capsys.readouterr().out
    assert codigo == 1, "instalação que não sobe o agente não pode sair com sucesso"
    assert "NÃO está respondendo" in saida
    assert "botão do PDV vai falhar" in saida


def test_instalador_aprova_quando_o_agente_responde(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(drawer_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(drawer_agent, "IS_MACOS", False)
    monkeypatch.setattr(drawer_agent, "INSTALL_DIR", tmp_path / "inst")
    monkeypatch.setattr(drawer_agent, "DEFAULT_CONFIG_PATH", tmp_path / "agent.json")
    monkeypatch.setattr(drawer_agent, "list_queues", lambda: ["TM-T20"])
    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(drawer_agent, "_autostart_linux", lambda target: None)
    monkeypatch.setattr(drawer_agent, "_wait_until_listening", lambda config, **k: {"ok": True, "build": drawer_agent.build_id()})

    assert drawer_agent.install(["--install", "--queue", "TM-T20", "--token", TOKEN]) == 0
    saida = capsys.readouterr().out
    assert "respondendo" in saida
    # A versão sai na mensagem porque é o que o operador compara com o Admin
    # quando desconfia de que o balcão está atrasado.
    assert drawer_agent.build_id() in saida


def test_no_windows_config_programa_e_log_ficam_na_MESMA_pasta():
    """Programa num lugar e config em outro fez o dono procurar o token e não achar.

    A primeira versão mandava o agente para `%LOCALAPPDATA%\\NelsonPosDrawer` e a
    config para uma `.config` de estilo Linux escondida na pasta do usuário.
    """
    home = Path(r"C:/Users/pdv")
    appdata = r"C:/Users/pdv/AppData/Local"

    pasta = drawer_agent.install_dir_for(home, windows=True, localappdata=appdata)
    config = drawer_agent.config_path_for(home, windows=True, localappdata=appdata)

    assert config.parent == pasta
    assert pasta.name == "NelsonPosDrawer"


def test_fora_do_windows_a_config_segue_a_convencao_do_sistema():
    """No Linux/macOS quem administra a máquina espera achar em `~/.config`."""
    config = drawer_agent.config_path_for(Path("/home/pdv"), windows=False)
    assert config.parts[-3:] == (".config", "nelson-pos-drawer", "agent.json")


# ── Página de teste ESC/POS ───────────────────────────────────────────────
#
# Ela existe para o PAPEL responder o que ninguém sabe de cabeça, antes de
# alguém compor recibo — e muito antes de compor DANFE, que tem leiaute exigido
# por lei.


def test_o_qr_declara_o_comprimento_certo():
    """`GS ( k` conta `cn`, `fn` e `m` ALÉM dos dados: três bytes a mais.

    Errar isso é o defeito clássico do comando — a impressora lê menos do que
    existe e imprime lixo, ou nada.
    """
    dados = b"https://pdv.boulangerie.com.br"
    saida = drawer_agent._qr_code(dados.decode())

    marcador = bytes([0x1D, 0x28, 0x6B])
    i = saida.index(marcador + bytes([(len(dados) + 3) % 256]))
    pL, pH = saida[i + 3], saida[i + 4]
    assert pL + pH * 256 == len(dados) + 3
    assert saida[i + 5:i + 8] == bytes([0x31, 0x50, 0x30])  # cn, fn, m
    assert dados in saida


def test_o_qr_sobrevive_a_dado_maior_que_255_bytes():
    """Acima de 255 o comprimento passa a usar os dois bytes; é onde se erra."""
    dados = "x" * 400
    saida = drawer_agent._qr_code(dados)
    tamanho = 403
    assert bytes([tamanho % 256, tamanho // 256]) in saida


def test_a_pagina_compara_tabelas_em_vez_de_chutar_uma():
    """Escolher página de código no escuro é como "PÃO" vira "PÎO" no balcão."""
    saida = drawer_agent.test_print_bytes()
    for code, _ in drawer_agent._CODE_PAGES:
        assert bytes([0x1B, ord("t"), code]) in saida
    assert len(drawer_agent._CODE_PAGES) >= 2, "comparar exige mais de uma tabela"


def test_a_amostra_de_acento_DISCRIMINA_as_tabelas():
    """A primeira versão não discriminava e o teste no balcão não decidiu nada.

    As maiúsculas iam SEM acento no código-fonte (saíam iguais em qualquer
    tabela) e entre as minúsculas só o "ã" separava — um caractere. A amostra
    precisa diferir em VÁRIOS bytes entre as três tabelas.
    """
    amostra = drawer_agent._ACCENT_SAMPLE
    codificacoes = {
        nome: amostra.encode(enc, "replace")
        for nome, enc in (("cp860", "cp860"), ("cp850", "cp850"), ("cp1252", "cp1252"))
    }
    assert len(set(codificacoes.values())) == 3, "as três tabelas têm que produzir bytes diferentes"

    diferencas = sum(
        1 for a, b in zip(codificacoes["cp860"], codificacoes["cp850"], strict=True) if a != b
    )
    assert diferencas >= 4, f"só {diferencas} byte(s) separam CP860 de CP850 — fácil de não notar"

    assert any(c.isupper() and not c.isascii() for c in amostra), "faltam maiúsculas acentuadas"
    assert any(c.islower() and not c.isascii() for c in amostra), "faltam minúsculas acentuadas"


def test_a_regua_vai_ALEM_da_largura_assumida():
    """Régua que para onde eu chutei não descobre largura nenhuma.

    O primeiro teste no balcão voltou "coube e sobrou espaço": a impressora era
    mais larga que as 48 colunas assumidas, e a régua não tinha como mostrar
    quanto.
    """
    assert drawer_agent._RULER_MAX > drawer_agent._COLUMNS
    regua = drawer_agent._ruler(drawer_agent._RULER_MAX)
    assert len(regua) == drawer_agent._RULER_MAX
    assert regua.encode("cp860") in drawer_agent.test_print_bytes()
    # Dezenas marcadas: quem lê diz o último número inteiro que apareceu.
    # Índice 39 é a COLUNA 40 — a dezena. A coluna 48 não é dezena nenhuma.
    assert regua[9] == "1" and regua[19] == "2" and regua[39] == "4"
    assert regua[4] == "+", "as meias-dezenas ajudam a contar sem perder a conta"


def test_as_duas_colunas_encostam_nas_bordas():
    linha = drawer_agent._two_columns("Pao frances", "R$ 0,90", 48)
    assert len(linha) == 48
    assert linha.startswith("Pao frances")
    assert linha.endswith("R$ 0,90")


def test_coluna_com_nome_gigante_nao_estoura_a_linha():
    linha = drawer_agent._two_columns("N" * 60, "R$ 9,99", 48)
    assert len(linha) == 48


def test_a_pagina_termina_cortando_o_papel():
    saida = drawer_agent.test_print_bytes()
    assert saida.startswith(bytes([0x1B, ord("@")])), "sem reset, herda estado do job anterior"
    assert saida.endswith(bytes([0x1D, ord("V"), 1]))


# ── /print: o agente é um cano ────────────────────────────────────────────


def _print_req(base, body, origin=ORIGIN):
    return _post(base, "/print", body, origin=origin)


def test_print_entrega_os_bytes_que_o_servidor_compos(agent):
    """O agente não sabe o que é sangria — quem compõe é o servidor."""
    base, sent = agent
    import base64

    papel = b"\x1b@\x1bt\x03NELSON\n"
    status, body, _ = _print_req(base, {
        "token": TOKEN, "title": "sangria", "payload_b64": base64.b64encode(papel).decode(),
    })

    assert status == 200 and body["ok"] is True
    assert sent[0]["payload"] == papel
    assert sent[0]["title"] == "sangria"


def test_print_sem_token_e_recusado(agent):
    base, sent = agent
    with pytest.raises(urllib.error.HTTPError) as exc:
        _print_req(base, {"payload_b64": "AAAA"})
    assert exc.value.code == 401
    assert sent == []


def test_print_de_origem_estranha_e_recusado(agent):
    base, sent = agent
    with pytest.raises(urllib.error.HTTPError) as exc:
        _print_req(base, {"token": TOKEN, "payload_b64": "AAAA"}, origin="https://intruso.example")
    assert exc.value.code == 403
    assert sent == []


@pytest.mark.parametrize("payload", ["nao-e-base64!!", "", None])
def test_print_com_payload_invalido_nao_manda_lixo_para_a_impressora(agent, payload):
    """Lixo no spooler vira papel rasgado de caracteres aleatórios."""
    base, sent = agent
    with pytest.raises(urllib.error.HTTPError) as exc:
        _print_req(base, {"token": TOKEN, "payload_b64": payload})
    assert exc.value.code == 400
    assert sent == []


def test_print_aceita_documento_grande(agent):
    """Comprovante em base64 passa de 8 KB; a DANFE passa mais."""
    import base64

    base, sent = agent
    grande = b"X" * 60_000
    status, _, _ = _print_req(base, {
        "token": TOKEN, "title": "danfe", "payload_b64": base64.b64encode(grande).decode(),
    })
    assert status == 200
    assert sent[0]["payload"] == grande


def test_falha_do_spooler_na_impressao_vira_502(agent, monkeypatch):
    """A tela precisa saber que NÃO imprimiu, para registrar como falha."""
    import base64

    base, _ = agent

    def boom(*a, **k):
        raise drawer_agent.SpoolerError("fila parada")

    monkeypatch.setattr(drawer_agent, "send_raw", boom)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _print_req(base, {"token": TOKEN, "payload_b64": base64.b64encode(b"x").decode()})
    assert exc.value.code == 502


def test_reinstalar_no_linux_REINICIA_o_servico(monkeypatch):
    """`enable --now` não reinicia serviço que já está de pé.

    Este é o bug que fez o balcão baixar o agente novo, reinstalar, e continuar
    respondendo "rota desconhecida": o arquivo era trocado, mas o processo velho
    seguia servindo o código velho. macOS (bootout+bootstrap) e Windows
    (schtasks /run) já reiniciavam de fato; só o Linux ficava para trás.
    """
    chamadas = []

    def fake_run(cmd, *args, **kwargs):
        chamadas.append(list(cmd))

        class R:
            returncode = 0
            stderr = b""
        return R()

    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(drawer_agent.subprocess, "run", fake_run)
    monkeypatch.setattr(drawer_agent, "UNIT_PATH", drawer_agent.Path("/tmp/nao-usado.service"))
    monkeypatch.setattr(drawer_agent.Path, "write_text", lambda self, *a, **k: None)
    monkeypatch.setattr(drawer_agent.Path, "mkdir", lambda self, *a, **k: None)

    drawer_agent._autostart_linux(drawer_agent.Path("/tmp/drawer_agent.py"))

    systemctl = [c for c in chamadas if c and c[0] == "systemctl"]
    verbos = [c[2] for c in systemctl if len(c) > 2]
    assert "restart" in verbos, f"faltou reiniciar; chamou apenas {verbos}"
    # `enable` sem `--now` continua sendo necessário (sobreviver ao reboot), mas
    # ele não pode ser o único jeito de o processo novo entrar no ar.
    assert "enable" in verbos


def test_instalador_reprova_quando_quem_atende_e_outra_versao(monkeypatch, capsys, tmp_path):
    """Responder não é ser — e foi por isso que reinstalar não adiantou no balcão.

    O processo ANTIGO nunca morria, seguia segurando a porta, e o instalador só
    perguntava "alguém responde?". Dizia pronto com a versão velha no ar; o PDV
    continuava acusando agente desatualizado, e estava certo. A prova de
    identidade é o `build` — sha256 do próprio arquivo.
    """
    monkeypatch.setattr(drawer_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(drawer_agent, "IS_MACOS", False)
    monkeypatch.setattr(drawer_agent, "INSTALL_DIR", tmp_path / "inst")
    monkeypatch.setattr(drawer_agent, "DEFAULT_CONFIG_PATH", tmp_path / "agent.json")
    monkeypatch.setattr(drawer_agent, "list_queues", lambda: ["TM-T20"])
    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(drawer_agent, "_autostart_linux", lambda target: None)
    monkeypatch.setattr(
        drawer_agent, "_wait_until_listening", lambda config, **k: {"ok": True, "build": "deadbeef"}
    )

    codigo = drawer_agent.install(["--install", "--queue", "TM-T20", "--token", TOKEN])

    saida = capsys.readouterr().out
    assert codigo == 1, "instalação que não trocou o processo não pode sair com sucesso"
    assert "NÃO pegou" in saida
    assert "deadbeef" in saida, "tem que mostrar a versão que está no ar"
    assert drawer_agent.build_id() in saida, "e a que deveria estar"
