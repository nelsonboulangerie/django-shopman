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
ORIGIN = "https://pos.staging.nelsonboulangerie.com.br"


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
    monkeypatch.setattr(drawer_agent, "_cups_queues", lambda: ["OUTRA"])

    assert drawer_agent.install(["--install", "--queue", "TM-T20"]) == 1
    assert "não existe no CUPS" in capsys.readouterr().err


def test_instalar_sem_cups_diz_o_que_falta(monkeypatch, capsys):
    monkeypatch.setattr(drawer_agent.shutil, "which", lambda name: None)

    assert drawer_agent.install(["--install"]) == 1
    assert "CUPS" in capsys.readouterr().err
