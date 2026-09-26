"""Emissão do JSON e dos Bearers escopados do player de menuboard."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.doorman.models import TrustedDevice

from shopman.shop.menuboard_access import is_menuboard_player_device
from shopman.shop.tests._display import display_channel

pytestmark = pytest.mark.django_db


def test_emite_config_de_duas_telas_e_credenciais_separadas():
    display_channel("tv-cafe", "TV Café", collections=[])
    display_channel("tv-salao", "TV Salão", collections=[])
    stdout = StringIO()

    call_command(
        "issue_menuboard_player_credential",
        "tv-cafe",
        "tv-salao",
        server_url="https://gestor.example/",
        stdout=stdout,
        stderr=StringIO(),
    )

    config = json.loads(stdout.getvalue())
    assert config["server_url"] == "https://gestor.example"
    assert [screen["cec_adapter"] for screen in config["screens"]] == ["/dev/cec0", "/dev/cec1"]
    assert [screen["window_position"] for screen in config["screens"]] == ["0,0", "1920,0"]
    assert config["screens"][0]["token"] != config["screens"][1]["token"]
    devices = list(TrustedDevice.objects.order_by("subject_id"))
    assert [device.subject_id for device in devices] == ["tv-cafe", "tv-salao"]
    assert all(is_menuboard_player_device(device) for device in devices)


def test_ref_invalida_nao_emite_credencial():
    display_channel("tv-cafe", "TV Café", collections=[])

    with pytest.raises(CommandError, match="não encontrado"):
        call_command(
            "issue_menuboard_player_credential",
            "tv-cafe",
            "tv-inexistente",
            server_url="https://gestor.example",
        )

    assert not TrustedDevice.objects.exists()
