"""Contrato local do player: duas janelas, atraso e CEC independente."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import player  # noqa: E402

TOKEN = "token-de-teste-longo-e-separado-123456"


def _config(delay=30):
    return player.PlayerConfig.from_dict(
        {
            "server_url": "https://gestor.example",
            "standby_delay_minutes": delay,
            "screens": [
                {
                    "ref": "tv-cafe",
                    "cec_adapter": "/dev/cec0",
                    "token": TOKEN,
                    "window_position": "0,0",
                    "window_size": "1920,1080",
                },
                {
                    "ref": "tv-salao",
                    "cec_adapter": "/dev/cec1",
                    "token": TOKEN + "-2",
                    "window_position": "1920,0",
                    "window_size": "1920,1080",
                },
            ],
        },
        home=Path("/tmp/home-player-test"),
    )


def test_duas_telas_recebem_perfis_urls_e_posicoes_independentes():
    config = _config()
    cafe = player.browser_command(config, config.screens[0])
    salao = player.browser_command(config, config.screens[1])

    assert "--window-position=0,0" in cafe
    assert "--window-position=1920,0" in salao
    assert cafe[-1].endswith("/menuboard/tv-cafe/")
    assert salao[-1].endswith("/menuboard/tv-salao/")
    assert cafe[5] != salao[5]


def test_descanso_mostra_marquee_antes_de_mandar_standby():
    clock = iter([100.0, 100.0, 100.0 + 29 * 60, 100.0 + 31 * 60])
    controller = player.Player(_config(delay=30), dry_run=True, monotonic=lambda: next(clock))
    runtime = controller.screens[0]
    intent = {"standby_allowed": True, "next_transition_at": "2026-09-28T08:45:00-03:00"}

    controller.apply_intent(runtime, intent)
    assert runtime.power_on is True
    controller.apply_intent(runtime, intent)
    assert runtime.power_on is True
    controller.apply_intent(runtime, intent)
    assert runtime.power_on is False


def test_conteudo_acorda_imediatamente_e_nao_repete_comando():
    controller = player.Player(_config(), dry_run=True)
    runtime = controller.screens[0]
    runtime.power_on = False

    controller.apply_intent(runtime, {"standby_allowed": False, "next_transition_at": None})
    assert runtime.power_on is True
    assert runtime.sleep_started_at is None


def test_chromium_que_cai_e_reaberto(monkeypatch):
    controller = player.Player(_config())
    runtime = controller.screens[0]
    started = []

    class Process:
        def __init__(self, code=None):
            self.code = code

        def poll(self):
            return self.code

    monkeypatch.setattr(player.subprocess, "Popen", lambda command: started.append(command) or Process())
    runtime.browser = Process(1)

    controller.ensure_browser(runtime)
    controller.ensure_browser(runtime)

    assert len(started) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"server_url": "ftp://errado"},
        {"standby_delay_minutes": -1},
        {"screens": []},
    ],
)
def test_config_recusa_valores_inseguros(change):
    raw = {
        "server_url": "https://gestor.example",
        "standby_delay_minutes": 30,
        "screens": [
            {
                "ref": "tv",
                "cec_adapter": "/dev/cec0",
                "token": TOKEN,
                "window_position": "0,0",
                "window_size": "1920,1080",
            }
        ],
    }
    raw.update(change)
    with pytest.raises(ValueError):
        player.PlayerConfig.from_dict(raw)
