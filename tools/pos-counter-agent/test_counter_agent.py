"""Testes do agente do balcão.

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

import counter_agent  # noqa: E402
from counter_agent import AgentConfig, CounterAgentHandler, kick_bytes  # noqa: E402

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

    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent.subprocess, "run", fake_run)

    job = counter_agent.send_raw(b"\x1b\x70\x00\x19\xfa", queue="TM-T20")

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

    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent.subprocess, "run", lambda *a, **k: Failed())

    with pytest.raises(counter_agent.SpoolerError, match="does not exist"):
        counter_agent.send_raw(b"\x1b", queue="fantasma")


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

    monkeypatch.setattr(counter_agent, "send_raw", fake_send_raw)
    monkeypatch.setattr(
        counter_agent, "probe_queue",
        lambda queue: {"ok": True, "accepting": True, "reason": ""},
    )

    config = AgentConfig.from_dict(
        {"queue": "TM-T20", "token": TOKEN, "port": 0, "allowed_origins": [ORIGIN]}
    )
    handler = type("Bound", (CounterAgentHandler,), {"config": config})
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
        raise counter_agent.SpoolerError("fila 'TM-T20' não existe")

    monkeypatch.setattr(counter_agent, "send_raw", boom)
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
    assert body["version"] == counter_agent.VERSION


# ── Instalação ────────────────────────────────────────────────────────────


def test_instalar_gera_config_utilizavel(tmp_path):
    path = tmp_path / "agent.json"
    config, created = counter_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo/")

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
    first, _ = counter_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo")
    second, created = counter_agent.write_config(path, queue="OUTRA", origin="https://outra.exemplo")

    assert created is False
    assert second["token"] == first["token"]
    assert second["queue"] == "TM-T20"


def test_token_do_admin_manda_na_primeira_instalacao(tmp_path):
    """O Admin é o dono do par — o agente não inventa um por cima."""
    path = tmp_path / "agent.json"
    config, _ = counter_agent.write_config(
        path, queue="TM-T20", origin="https://pos.exemplo", token=TOKEN
    )
    assert config["token"] == TOKEN


def test_token_novo_do_admin_ROTACIONA_a_config_existente(tmp_path):
    """Rotação é a única razão para mexer num token já instalado."""
    path = tmp_path / "agent.json"
    counter_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo", token=TOKEN)
    config, written = counter_agent.write_config(
        path, queue="TM-T20", origin="https://pos.exemplo", token="token-rotacionado-pelo-admin"
    )

    assert written is True
    assert config["token"] == "token-rotacionado-pelo-admin"
    assert json.loads(path.read_text())["token"] == "token-rotacionado-pelo-admin"


def test_reinstalar_com_o_MESMO_token_nao_reescreve(tmp_path):
    path = tmp_path / "agent.json"
    counter_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo", token=TOKEN)
    _, written = counter_agent.write_config(
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
    config, _ = counter_agent.write_config(path, queue="TM-T20", origin="", token=TOKEN)

    assert config["allowed_origins"] == []
    assert AgentConfig.from_dict(config).allows("https://pdv.boulangerie.com.br")


def test_nenhum_dominio_de_deployment_cravado_no_agente():
    """O agente é genérico. Quem sabe a origem é o Django, e ele a injeta."""
    source = (Path(__file__).parent / "counter_agent.py").read_text(encoding="utf-8")
    for invented in ("nelsonboulangerie.com.br", "boulangerie.com.br"):
        assert invented not in source, f"domínio de deployment cravado no agente: {invented}"


def test_config_nasce_ilegivel_para_outros_usuarios(tmp_path):
    path = tmp_path / "agent.json"
    counter_agent.write_config(path, queue="TM-T20", origin="https://pos.exemplo")
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_a_unit_aponta_para_o_arquivo_instalado_e_reergue_sozinha():
    unit = counter_agent._unit_text(Path("/home/pdv/.local/share/nelson-pos-counter/counter_agent.py"))
    assert "ExecStart=/usr/bin/env python3 /home/pdv/.local/share/nelson-pos-counter/counter_agent.py" in unit
    assert "Restart=always" in unit
    # O balcão abre antes do CUPS estar de pé se a ordem não for dita.
    assert "After=cups.service" in unit


def test_instalar_com_fila_inexistente_para_antes_de_mexer_em_nada(monkeypatch, capsys):
    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent, "list_queues", lambda: ["OUTRA"])

    assert counter_agent.install(["--install", "--queue", "TM-T20"]) == 1
    assert "não está entre as" in capsys.readouterr().err


def test_instalar_sem_cups_diz_o_que_falta(monkeypatch, capsys):
    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: None)

    assert counter_agent.install(["--install"]) == 1
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

    monkeypatch.setattr(counter_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        counter_agent.subprocess, "run", lambda cmd, **k: (captured.update(cmd=cmd), Done())[1]
    )

    counter_agent.send_raw(CANONICAL_KICK, queue="TM-T20")
    assert captured["cmd"][:5] == ["/usr/bin/lp", "-d", "TM-T20", "-o", "raw"]


def test_windows_despacha_para_o_spooler_proprio(monkeypatch):
    """No Windows não existe `lp`; quem entrega é o winspool."""
    chamado = {}
    monkeypatch.setattr(counter_agent, "IS_WINDOWS", True)
    monkeypatch.setattr(
        counter_agent, "_send_raw_windows",
        lambda payload, *, queue, title: chamado.update(payload=payload, queue=queue) or "42",
    )

    assert counter_agent.send_raw(CANONICAL_KICK, queue="TM-T20") == "42"
    assert chamado["payload"] == CANONICAL_KICK


def test_a_sonda_tambem_despacha_por_plataforma(monkeypatch):
    monkeypatch.setattr(counter_agent, "IS_WINDOWS", True)
    monkeypatch.setattr(counter_agent, "_probe_queue_windows", lambda q: {"ok": True, "accepting": True, "reason": q})
    assert counter_agent.probe_queue("TM-T20")["reason"] == "TM-T20"


def test_o_launchagent_do_macos_reergue_sozinho():
    plist = counter_agent._plist_text(Path("/Users/pdv/agente/counter_agent.py"))
    assert "<string>/Users/pdv/agente/counter_agent.py</string>" in plist
    # KeepAlive é o Restart=always do launchd: ninguém confere se o agente caiu.
    assert "<key>KeepAlive</key><true/>" in plist
    assert counter_agent.LAUNCH_AGENT_LABEL in plist


def test_o_plist_do_macos_e_xml_valido():
    """Plist malformado o launchd recusa em silêncio, e a gaveta some no boot."""
    import plistlib

    parsed = plistlib.loads(counter_agent._plist_text(Path("/tmp/x.py")).encode())
    assert parsed["Label"] == counter_agent.LAUNCH_AGENT_LABEL
    assert parsed["RunAtLoad"] is True
    assert parsed["ProgramArguments"][1] == "/tmp/x.py"


# ── O instalador confere o que afirma ─────────────────────────────────────


def test_o_launcher_do_windows_da_UM_caminho_ao_schtasks(monkeypatch, tmp_path):
    """Aspas aninhadas em `/tr` fazem o schtasks gravar comando mutilado.

    Foi o defeito real do balcão: a tarefa nasceu quebrada, o agente não subiu,
    e o `--kick` da linha de comando continuou funcionando — então nada gritou.
    """
    monkeypatch.setattr(counter_agent, "INSTALL_DIR", tmp_path)
    monkeypatch.setattr(counter_agent, "LOG_PATH", tmp_path / "counter-agent.log")

    launcher = counter_agent._windows_launcher(tmp_path / "counter_agent.py")

    assert launcher.suffix == ".cmd"
    conteudo = launcher.read_text(encoding="utf-8")
    assert "counter_agent.py" in conteudo
    assert "--log-file" in conteudo


def test_instalador_reprova_quando_o_agente_nao_sobe(monkeypatch, capsys, tmp_path):
    """Dizer 'instalado' sem medir foi o que mandou o defeito para o balcão."""
    monkeypatch.setattr(counter_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(counter_agent, "IS_MACOS", False)
    monkeypatch.setattr(counter_agent, "INSTALL_DIR", tmp_path / "inst")
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", tmp_path / "agent.json")
    monkeypatch.setattr(counter_agent, "list_queues", lambda: ["TM-T20"])
    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent, "_autostart_linux", lambda target: None)
    monkeypatch.setattr(counter_agent, "_wait_until_listening", lambda config, **k: None)

    codigo = counter_agent.install(["--install", "--queue", "TM-T20", "--token", TOKEN])

    saida = capsys.readouterr().out
    assert codigo == 1, "instalação que não sobe o agente não pode sair com sucesso"
    assert "NÃO está respondendo" in saida
    assert "botão do PDV vai falhar" in saida


def test_instalador_aprova_quando_o_agente_responde(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(counter_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(counter_agent, "IS_MACOS", False)
    monkeypatch.setattr(counter_agent, "INSTALL_DIR", tmp_path / "inst")
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", tmp_path / "agent.json")
    monkeypatch.setattr(counter_agent, "list_queues", lambda: ["TM-T20"])
    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent, "_autostart_linux", lambda target: None)
    monkeypatch.setattr(counter_agent, "_wait_until_listening", lambda config, **k: {"ok": True, "build": counter_agent.build_id()})

    assert counter_agent.install(["--install", "--queue", "TM-T20", "--token", TOKEN]) == 0
    saida = capsys.readouterr().out
    assert "respondendo" in saida
    # A versão sai na mensagem porque é o que o operador compara com o Admin
    # quando desconfia de que o balcão está atrasado.
    assert counter_agent.build_id() in saida


def test_no_windows_config_programa_e_log_ficam_na_MESMA_pasta():
    """Programa num lugar e config em outro fez o dono procurar o token e não achar.

    A primeira versão mandava o agente para `%LOCALAPPDATA%\\NelsonPosCounter` e a
    config para uma `.config` de estilo Linux escondida na pasta do usuário.
    """
    home = Path(r"C:/Users/pdv")
    appdata = r"C:/Users/pdv/AppData/Local"

    pasta = counter_agent.install_dir_for(home, windows=True, localappdata=appdata)
    config = counter_agent.config_path_for(home, windows=True, localappdata=appdata)

    assert config.parent == pasta
    assert pasta.name == "NelsonPosCounter"


def test_fora_do_windows_a_config_segue_a_convencao_do_sistema():
    """No Linux/macOS quem administra a máquina espera achar em `~/.config`."""
    config = counter_agent.config_path_for(Path("/home/pdv"), windows=False)
    assert config.parts[-3:] == (".config", "nelson-pos-counter", "agent.json")


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
    saida = counter_agent._qr_code(dados.decode())

    marcador = bytes([0x1D, 0x28, 0x6B])
    i = saida.index(marcador + bytes([(len(dados) + 3) % 256]))
    pL, pH = saida[i + 3], saida[i + 4]
    assert pL + pH * 256 == len(dados) + 3
    assert saida[i + 5:i + 8] == bytes([0x31, 0x50, 0x30])  # cn, fn, m
    assert dados in saida


def test_o_qr_sobrevive_a_dado_maior_que_255_bytes():
    """Acima de 255 o comprimento passa a usar os dois bytes; é onde se erra."""
    dados = "x" * 400
    saida = counter_agent._qr_code(dados)
    tamanho = 403
    assert bytes([tamanho % 256, tamanho // 256]) in saida


def test_a_pagina_compara_tabelas_em_vez_de_chutar_uma():
    """Escolher página de código no escuro é como "PÃO" vira "PÎO" no balcão."""
    saida = counter_agent.test_print_bytes()
    for code, _ in counter_agent._CODE_PAGES:
        assert bytes([0x1B, ord("t"), code]) in saida
    assert len(counter_agent._CODE_PAGES) >= 2, "comparar exige mais de uma tabela"


def test_a_amostra_de_acento_DISCRIMINA_as_tabelas():
    """A primeira versão não discriminava e o teste no balcão não decidiu nada.

    As maiúsculas iam SEM acento no código-fonte (saíam iguais em qualquer
    tabela) e entre as minúsculas só o "ã" separava — um caractere. A amostra
    precisa diferir em VÁRIOS bytes entre as três tabelas.
    """
    amostra = counter_agent._ACCENT_SAMPLE
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
    assert counter_agent._RULER_MAX > counter_agent._COLUMNS
    regua = counter_agent._ruler(counter_agent._RULER_MAX)
    assert len(regua) == counter_agent._RULER_MAX
    assert regua.encode("cp860") in counter_agent.test_print_bytes()
    # Dezenas marcadas: quem lê diz o último número inteiro que apareceu.
    # Índice 39 é a COLUNA 40 — a dezena. A coluna 48 não é dezena nenhuma.
    assert regua[9] == "1" and regua[19] == "2" and regua[39] == "4"
    assert regua[4] == "+", "as meias-dezenas ajudam a contar sem perder a conta"


def test_as_duas_colunas_encostam_nas_bordas():
    linha = counter_agent._two_columns("Pao frances", "R$ 0,90", 48)
    assert len(linha) == 48
    assert linha.startswith("Pao frances")
    assert linha.endswith("R$ 0,90")


def test_coluna_com_nome_gigante_nao_estoura_a_linha():
    linha = counter_agent._two_columns("N" * 60, "R$ 9,99", 48)
    assert len(linha) == 48


def test_a_pagina_termina_cortando_o_papel():
    saida = counter_agent.test_print_bytes()
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
        raise counter_agent.SpoolerError("fila parada")

    monkeypatch.setattr(counter_agent, "send_raw", boom)
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

    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent.subprocess, "run", fake_run)
    monkeypatch.setattr(counter_agent, "UNIT_PATH", counter_agent.Path("/tmp/nao-usado.service"))
    monkeypatch.setattr(counter_agent.Path, "write_text", lambda self, *a, **k: None)
    monkeypatch.setattr(counter_agent.Path, "mkdir", lambda self, *a, **k: None)

    counter_agent._autostart_linux(counter_agent.Path("/tmp/counter_agent.py"))

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
    monkeypatch.setattr(counter_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(counter_agent, "IS_MACOS", False)
    monkeypatch.setattr(counter_agent, "INSTALL_DIR", tmp_path / "inst")
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", tmp_path / "agent.json")
    monkeypatch.setattr(counter_agent, "list_queues", lambda: ["TM-T20"])
    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent, "_autostart_linux", lambda target: None)
    monkeypatch.setattr(
        counter_agent, "_wait_until_listening", lambda config, **k: {"ok": True, "build": "deadbeef"}
    )

    codigo = counter_agent.install(["--install", "--queue", "TM-T20", "--token", TOKEN])

    saida = capsys.readouterr().out
    assert codigo == 1, "instalação que não trocou o processo não pode sair com sucesso"
    assert "NÃO pegou" in saida
    assert "deadbeef" in saida, "tem que mostrar a versão que está no ar"
    assert counter_agent.build_id() in saida, "e a que deveria estar"


def test_escolha_de_fila_por_numero(monkeypatch, capsys):
    """Ninguém deveria precisar digitar `EPSON_TM-T20X_Receipt5` sem errar.

    Nome de fila do CUPS é comprido e cheio de underscore. Quem instala no balcão
    erra um caractere, o instalador recusa, e a pessoa conclui que a impressora
    está com problema — quando o defeito é o instalador exigir transcrição.
    """
    monkeypatch.setattr("builtins.input", lambda _: "2")

    escolhida = counter_agent._escolher_fila(["TM-T20", "EPSON_TM-T20X_Receipt5"], "filas")

    assert escolhida == "EPSON_TM-T20X_Receipt5"
    assert "2) EPSON_TM-T20X_Receipt5" in capsys.readouterr().out


def test_escolha_aceita_o_nome_tambem(monkeypatch):
    """Quem já sabe o nome não precisa procurar o número dele na lista."""
    monkeypatch.setattr("builtins.input", lambda _: "TM-T20")

    assert counter_agent._escolher_fila(["TM-T20", "outra"], "filas") == "TM-T20"


def test_fila_unica_so_pede_confirmacao(monkeypatch, capsys):
    """Perguntar "qual das 1?" é cerimônia. Enter aceita."""
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert counter_agent._escolher_fila(["TM-T20"], "filas") == "TM-T20"
    assert "1)" not in capsys.readouterr().out, "lista numerada não faz sentido com uma só"


def test_fila_unica_pode_ser_recusada(monkeypatch):
    """Recusar devolve vazio, e o instalador para em vez de assumir a errada."""
    monkeypatch.setattr("builtins.input", lambda _: "n")

    assert counter_agent._escolher_fila(["TM-T20"], "filas") == ""


# ── O nome antigo não pode continuar servindo ─────────────────────────────
#
# O agente nasceu chutando só a gaveta e se chamava por isso; hoje ele também
# imprime (comprovante de caixa, e a DANFE NFC-e depois). Trocar o nome é de
# graça no repositório e caro no balcão: a máquina do caixa continua com o
# serviço antigo instalado, e ele SEGURA a porta 47811.


def test_instalador_DERRUBA_o_servico_antigo_ANTES_de_subir_o_novo(monkeypatch, tmp_path):
    """Ordem importa: com o velho de pé, o novo nem chega a ouvir.

    Dois agentes não dividem a 47811, e quem chegou primeiro ganha. Se o
    instalador subisse o novo antes da faxina, o serviço novo falharia calado, o
    `/health` continuaria respondendo (o velho atende), e o operador levaria uma
    instalação "concluída" com o código antigo no ar — que foi exatamente o que
    custou duas reinstalações no balcão.
    """
    chamadas = []

    def fake_run(cmd, *args, **kwargs):
        chamadas.append(list(cmd))

        class R:
            returncode = 0
            stdout = b""
            stderr = b""
        return R()

    unit_antiga = tmp_path / "nelson-pos-drawer.service"
    unit_antiga.write_text("[Unit]\n", encoding="utf-8")

    monkeypatch.setattr(counter_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(counter_agent, "IS_MACOS", False)
    monkeypatch.setattr(counter_agent, "INSTALL_DIR", tmp_path / "inst")
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", tmp_path / "agent.json")
    monkeypatch.setattr(counter_agent, "LEGACY_CONFIG_PATHS", ())
    monkeypatch.setattr(counter_agent, "LEGACY_UNIT_PATH", unit_antiga)
    monkeypatch.setattr(counter_agent, "UNIT_PATH", tmp_path / "nelson-pos-counter.service")
    monkeypatch.setattr(counter_agent, "list_queues", lambda: ["TM-T20"])
    monkeypatch.setattr(counter_agent.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(counter_agent.subprocess, "run", fake_run)
    monkeypatch.setattr(
        counter_agent,
        "_wait_until_listening",
        lambda config, **k: {"ok": True, "build": counter_agent.build_id()},
    )

    codigo = counter_agent.install(["--install", "--queue", "TM-T20", "--token", TOKEN])
    assert codigo == 0

    systemctl = [c for c in chamadas if c and c[0] == "systemctl"]
    verbos = [(c[2], c[3]) for c in systemctl if len(c) > 3]
    parou = verbos.index(("stop", counter_agent.LEGACY_SERVICE_NAME))
    subiu = verbos.index(("restart", counter_agent.SERVICE_NAME))
    assert parou < subiu, f"o novo subiu antes da faxina: {verbos}"
    assert ("disable", counter_agent.LEGACY_SERVICE_NAME) in verbos, (
        "parar sem desabilitar deixa o antigo voltar no próximo boot"
    )
    assert not unit_antiga.exists(), "a unit antiga tem que sair, senão ela ressuscita"


def test_a_faxina_do_antigo_e_TOLERANTE_em_maquina_nova(monkeypatch, tmp_path):
    """Máquina que nunca teve o agente antigo não tem nada para parar.

    Sem isto, o primeiro caixa novo receberia um traceback do instalador por
    causa de um serviço que ele nunca deveria ter tido.
    """

    def sem_comando(*args, **kwargs):
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(counter_agent, "IS_WINDOWS", False)
    monkeypatch.setattr(counter_agent, "IS_MACOS", False)
    monkeypatch.setattr(counter_agent, "LEGACY_UNIT_PATH", tmp_path / "nao-existe.service")
    monkeypatch.setattr(counter_agent.subprocess, "run", sem_comando)

    counter_agent.stop_legacy_service()  # não pode levantar


def test_a_config_do_nome_antigo_e_MOVIDA_com_o_token_dentro(monkeypatch, tmp_path):
    """O token é metade de um par que o Admin guarda do outro lado.

    Gerar um novo em vez de mover deixaria os dois lados diferentes, e o balcão
    passaria a levar 401 no meio do troco — falha que só aparece com cliente na
    frente.
    """
    antiga = tmp_path / "antigo" / "agent.json"
    antiga.parent.mkdir()
    antiga.write_text(json.dumps({"queue": "TM-T20", "token": TOKEN}), encoding="utf-8")
    nova = tmp_path / "novo" / "agent.json"

    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", nova)
    monkeypatch.setattr(counter_agent, "LEGACY_CONFIG_PATHS", (antiga,))

    counter_agent.migrate_legacy_config()

    assert not antiga.exists(), "duas configs na mesma máquina é como os tokens divergem"
    assert json.loads(nova.read_text(encoding="utf-8"))["token"] == TOKEN


def test_config_atual_MANDA_sobre_a_do_nome_antigo(monkeypatch, tmp_path):
    """Sobra do nome antigo não pode sobrescrever o que já está valendo."""
    antiga = tmp_path / "antigo" / "agent.json"
    antiga.parent.mkdir()
    antiga.write_text(json.dumps({"queue": "VELHA", "token": TOKEN}), encoding="utf-8")
    nova = tmp_path / "novo" / "agent.json"
    nova.parent.mkdir()
    nova.write_text(json.dumps({"queue": "TM-T20", "token": TOKEN}), encoding="utf-8")

    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", nova)
    monkeypatch.setattr(counter_agent, "LEGACY_CONFIG_PATHS", (antiga,))

    counter_agent.migrate_legacy_config()

    assert json.loads(nova.read_text(encoding="utf-8"))["queue"] == "TM-T20"
    assert antiga.exists(), "sem migração para fazer, não se mexe em nada"


def test_o_nome_antigo_so_existe_para_ser_derrubado():
    """Nome velho vivo em qualquer outro lugar é o agente se reinstalando velho.

    A faxina precisa dele escrito; o resto do arquivo, não. Sem esta trava, um
    caminho esquecido com o nome antigo volta a criar serviço, pasta ou log
    fantasma na máquina do balcão — e a próxima pessoa acha que é do agente
    atual.
    """
    fonte = Path(counter_agent.__file__).read_text(encoding="utf-8")
    sobras = [
        linha
        for linha in fonte.splitlines()
        if ("pos-drawer" in linha or "PosDrawer" in linha)
        and "LEGACY" not in linha
        and "antigas" not in linha
    ]
    assert not sobras, f"nome antigo fora da faxina: {sobras}"


def test_doctor_nao_morre_no_primeiro_problema(monkeypatch, capsys, tmp_path):
    """Diagnóstico que aborta no primeiro achado obriga a consertar às cegas.

    A primeira versão saía com SystemExit quando faltava config e nem chegava a
    olhar o serviço ou a impressora — a pessoa consertava um item, rodava de
    novo, descobria o seguinte. Um relatório inteiro por execução.
    """
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", tmp_path / "nao-existe.json")

    codigo = counter_agent.doctor()

    saida = capsys.readouterr().out
    assert codigo == 1
    assert "config" in saida
    assert "Reinstale" in saida


def test_doctor_acusa_versao_diferente_no_ar(monkeypatch, capsys, tmp_path):
    """Versão no ar diferente da do arquivo = a última instalação não pegou."""
    cfg = tmp_path / "agent.json"
    cfg.write_text('{"queue": "TM-T20", "token": "token-de-teste-longo", "port": 47811}')
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", cfg)
    monkeypatch.setattr(counter_agent, "_wait_until_listening", lambda c, **k: {"build": "deadbeef"})
    monkeypatch.setattr(counter_agent, "probe_queue", lambda q: {"ok": True})
    monkeypatch.setattr(counter_agent, "_servico_ativo", lambda n: n == counter_agent.SERVICE_NAME)

    codigo = counter_agent.doctor()

    saida = capsys.readouterr().out
    assert codigo == 1
    assert "deadbeef" in saida
    assert counter_agent.build_id() in saida
    assert "não pegou" in saida


def test_doctor_acusa_o_servico_antigo_de_pe(monkeypatch, capsys, tmp_path):
    """O antigo segura a porta — é o fantasma que custou duas reinstalações."""
    if not sys.platform.startswith("linux"):
        pytest.skip("a checagem de serviço só roda no Linux")
    cfg = tmp_path / "agent.json"
    cfg.write_text('{"queue": "TM-T20", "token": "token-de-teste-longo", "port": 47811}')
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", cfg)
    monkeypatch.setattr(counter_agent, "_wait_until_listening", lambda c, **k: {"build": counter_agent.build_id()})
    monkeypatch.setattr(counter_agent, "probe_queue", lambda q: {"ok": True})
    monkeypatch.setattr(counter_agent, "_servico_ativo", lambda n: True)  # os DOIS de pé

    codigo = counter_agent.doctor()

    saida = capsys.readouterr().out
    assert codigo == 1
    assert "AINDA EXISTE" in saida


def test_leitura_do_pino_sem_permissao_explica_o_grupo(monkeypatch, tmp_path):
    """Erro de permissão vira instrução, não `PermissionError` cru na tela."""
    def nega(*a, **k):
        raise PermissionError("negado")

    monkeypatch.setattr(counter_agent.os, "open", nega)

    byte, motivo = counter_agent._ler_pino(tmp_path / "lp0")

    assert byte is None
    assert "grupo 'lp'" in motivo


def test_veredito_bytes_iguais_e_honesto(capsys):
    """Responder e distinguir são coisas diferentes — e o texto tem que separar."""
    assert counter_agent._veredito_do_pino(0x12, 0x12) == 1
    saida = capsys.readouterr().out
    assert "iguais" in saida
    assert "fisico" in saida, "sem alternativa, o operador fica sem saída"


def test_veredito_bytes_diferentes_mostra_o_bit(capsys):
    """O bit que mudou é o dado que eu preciso para ligar o alerta."""
    assert counter_agent._veredito_do_pino(0x12, 0x16) == 0
    saida = capsys.readouterr().out
    assert "0x12" in saida and "0x16" in saida
    assert "0x04" in saida, "o bit que mudou tem que aparecer"


def test_windows_tenta_ler_em_vez_de_recusar(monkeypatch):
    """A recusa anterior era limitação do MEU código, não do Windows.

    O agente já fala com o `winspool.drv` para imprimir; a mesma biblioteca tem
    `ReadPrinter`. Dizer "não implementado" mandava o dono achar que o sistema
    dele é que não servia.
    """
    monkeypatch.setattr(counter_agent, "IS_WINDOWS", True)
    chamou = []
    monkeypatch.setattr(counter_agent, "_drawer_status_windows", lambda: chamou.append(1) or 0)

    assert counter_agent.drawer_status([]) == 0
    assert chamou, "no Windows tem que tentar pelo spooler"


def test_windows_tenta_o_usb_quando_o_spooler_nao_devolve(monkeypatch, capsys, tmp_path):
    """Spooler mudo não é o fim: o aparelho ainda pode responder direto.

    A fila de impressão perde a bidirecionalidade em muitas instalações; o
    `usbprint.sys` fala com o aparelho e a preserva. Desistir no primeiro
    "não devolveu nada" mandaria instalar driver sem necessidade.
    """
    cfg = tmp_path / "agent.json"
    cfg.write_text('{"queue": "TM-T20", "token": "token-de-teste-longo", "port": 47811}')
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", cfg)
    monkeypatch.setattr(counter_agent, "_ler_pino_windows", lambda q, **k: (None, "porta nao bidirecional"))

    # A gaveta muda só o bit 0x04 do `DLE EOT 1`, que é onde o manual diz que
    # ele vive. Os outros status ficam iguais — é assim no aparelho real.
    estado = {"aberta": False}
    def usb(*, query, **k):
        n = query[2]
        if n == 1:
            return (0x16 if estado["aberta"] else 0x12), ""
        return 0x00, ""
    monkeypatch.setattr(counter_agent, "_ler_pino_usb_windows", usb)

    # O PRIMEIRO Enter é com a gaveta fechada; a partir do segundo, aberta.
    enters = {"n": 0}
    def enter(_):
        enters["n"] += 1
        estado["aberta"] = enters["n"] > 1
        return ""
    monkeypatch.setattr("builtins.input", enter)

    codigo = counter_agent._drawer_status_windows()

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "DLE EOT 1" in saida and "MUDOU" in saida
    assert "0x04" in saida, "o bit que mudou é o dado que eu preciso"


def test_windows_so_manda_instalar_driver_quando_os_DOIS_falham(monkeypatch, capsys, tmp_path):
    """Mandar instalar driver cedo demais é fazer o dono trabalhar à toa."""
    cfg = tmp_path / "agent.json"
    cfg.write_text('{"queue": "TM-T20", "token": "token-de-teste-longo", "port": 47811}')
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", cfg)
    monkeypatch.setattr(counter_agent, "_ler_pino_windows", lambda q, **k: (None, "porta nao bidirecional"))
    monkeypatch.setattr(counter_agent, "_ler_pino_usb_windows", lambda **k: (None, "aparelho mudo"))
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert counter_agent._drawer_status_windows() == 1
    saida = capsys.readouterr().out
    assert "OPOS/APD" in saida, "aí sim, o caminho que resta"
    assert "NAO e defeito da impressora" in saida


def test_toda_chamada_do_windows_declara_argtypes():
    """Sem `argtypes`, o ctypes assume int de 32 bits — e o handle não cabe.

    Foi exatamente assim que a leitura da gaveta quebrou no balcão:
    `SetupDiGetClassDevs` devolve um handle de 64 bits, as funções seguintes
    receberam como int, e o Windows respondeu "int too long to convert" — erro
    que parece problema do GUID e não é.

    Este teste lê o PRÓPRIO código, então pega a regressão num Mac, sem Windows.
    Toda função de DLL usada nos blocos do Windows precisa de `argtypes`.
    """
    import re

    fonte = Path(counter_agent.__file__).read_text(encoding="utf-8")
    usadas = set(re.findall(r"\b(?:setupapi|kernel32|winspool|ole32)\.([A-Z]\w+)\(", fonte))
    declaradas = set(re.findall(r"\b(?:setupapi|kernel32|winspool|ole32)\.(\w+)\.argtypes\s*=", fonte))

    faltando = sorted(usadas - declaradas)
    assert not faltando, (
        f"sem argtypes (handle de 64 bits vira int de 32 e a chamada morre): {faltando}"
    )


def test_varredura_pergunta_os_QUATRO_status():
    """Perguntar só o que eu acho ser o certo já custou uma noite do dono.

    A primeira versão usou `DLE EOT 3` (status de ERRO) e o balcão devolveu 0x12
    com a gaveta fechada E aberta: o byte estava certo, a pergunta é que era
    outra. Perguntar os quatro custa milissegundos e dispensa eu estar certo —
    quem responde qual muda é a impressora.
    """
    perguntas = []
    counter_agent._varre_status(lambda q: (perguntas.append(bytes(q)), (0x12, ""))[1])

    assert perguntas == [bytes([0x10, 0x04, n]) for n in (1, 2, 3, 4)]


def test_varredura_ignora_o_status_que_nao_responde():
    """Nem todo status responde em toda impressora — e isso não é erro."""
    def so_o_primeiro(q):
        return (0x12, "") if q[2] == 1 else (None, "sem resposta")

    assert counter_agent._varre_status(so_o_primeiro) == {1: 0x12}


def test_veredito_aponta_QUAL_status_muda_e_o_bit(capsys):
    """O dado que eu preciso para ligar o alerta é o `n` e o bit, não 'funcionou'."""
    codigo = counter_agent._veredito_da_varredura(
        {1: 0x12, 2: 0x00, 3: 0x12, 4: 0x00},
        {1: 0x16, 2: 0x00, 3: 0x12, 4: 0x00},
    )

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "DLE EOT 1" in saida and "MUDOU" in saida
    assert "0x04" in saida, "o bit que mudou tem que aparecer"
    # E os que NÃO mudaram continuam listados: é assim que se vê que a varredura
    # foi completa, em vez de ter parado no primeiro.
    assert "DLE EOT 3" in saida


def test_veredito_quando_nenhum_status_muda(capsys):
    """O caso do balcão: responde, mas não reporta o pino nesta montagem."""
    iguais = {1: 0x12, 2: 0x00, 3: 0x12, 4: 0x00}

    assert counter_agent._veredito_da_varredura(iguais, dict(iguais)) == 1
    saida = capsys.readouterr().out
    assert "Nenhum dos quatro" in saida
    assert "OPOS/APD" in saida, "tem que dizer o que resta"
    assert "fisico" in saida, "e a saída final, se nem o driver resolver"


class TestPolaridadeDaGaveta:
    """A polaridade é MEDIDA, nunca constante.

    No balcão da Nelson: fechada 0x16 (bit ligado), aberta 0x12 (desligado) —
    o INVERSO do que a leitura ingênua do manual sugere. Cravar a constante
    faria o alerta gritar o dia todo com a gaveta fechada, a pessoa aprenderia
    a ignorar, e o aviso legítimo morreria junto.
    """

    def _config(self, drawer_status=None):
        return counter_agent.AgentConfig(
            queue="TM-T20", token="token-de-teste-longo", drawer_status=drawer_status
        )

    def test_a_medicao_do_balcao_da_nelson(self):
        # mask 0x04, fechada com o bit LIGADO
        cfg = self._config({"query": 1, "mask": 4, "closed_value": 4})

        assert cfg.estado_da_gaveta(0x16) is False, "0x16 é FECHADA nesta gaveta"
        assert cfg.estado_da_gaveta(0x12) is True, "0x12 é ABERTA nesta gaveta"

    def test_a_polaridade_inversa_tambem_funciona(self):
        """Outra montagem pode ligar ao contrário — e aí é a config que mando."""
        cfg = self._config({"query": 1, "mask": 4, "closed_value": 0})

        assert cfg.estado_da_gaveta(0x12) is False
        assert cfg.estado_da_gaveta(0x16) is True

    def test_sem_medicao_responde_NAO_SEI(self):
        """Palpite aqui é pior que silêncio: alerta invertido ensina a ignorar."""
        assert self._config(None).estado_da_gaveta(0x16) is None
        assert self._config({}).estado_da_gaveta(0x16) is None
        # Medição pela metade também não vale palpite.
        assert self._config({"mask": 4}).estado_da_gaveta(0x16) is None


def test_veredito_grava_a_polaridade_medida(monkeypatch, capsys, tmp_path):
    """O que a gaveta respondeu tem que sobreviver ao fim do comando."""
    cfg = tmp_path / "agent.json"
    cfg.write_text('{"queue": "TM-T20", "token": "token-de-teste-longo"}')
    monkeypatch.setattr(counter_agent, "DEFAULT_CONFIG_PATH", cfg)

    counter_agent._veredito_da_varredura({1: 0x16, 3: 0x12}, {1: 0x12, 3: 0x12})

    import json as _json
    salvo = _json.loads(cfg.read_text())["drawer_status"]
    assert salvo == {"query": 1, "mask": 4, "closed_value": 4}
    assert "gravado" in capsys.readouterr().out
