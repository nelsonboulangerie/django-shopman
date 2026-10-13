"""Cadastro do aviso da TaOn (webhook): só lê com --list, não duplica, não mostra o token."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

MACHINE = {"username": "u", "password": "p", "api_key": "k", "webhook_token": "segredo-longo-123"}
BASE = "https://api.boulangerie.com.br"
URL = f"{BASE}/api/webhooks/machine/?token=segredo-longo-123"


def _run(*args):
    out = StringIO()
    call_command("machine_register_webhook", BASE, *args, stdout=out)
    return out.getvalue()


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_list_only_reads():
    with patch("shopman.shop.adapters.courier_machine.list_webhooks", return_value=[]) as listing, \
            patch("shopman.shop.adapters.courier_machine.register_webhook") as register:
        output = _run("--list")
    listing.assert_called_once()
    register.assert_not_called()
    assert "Nenhum webhook cadastrado" in output


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_registers_both_kinds_without_printing_the_token():
    with patch("shopman.shop.adapters.courier_machine.list_webhooks", return_value=[]), \
            patch("shopman.shop.adapters.courier_machine.register_webhook") as register:
        output = _run()
    assert [call.kwargs["kind"] for call in register.call_args_list] == ["status", "posicao"]
    assert register.call_args_list[0].args[0] == URL
    assert "segredo-longo-123" not in output


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_rerun_does_not_duplicate():
    existing = [{"id": 7, "tipo": "status", "url": URL}]
    with patch("shopman.shop.adapters.courier_machine.list_webhooks", return_value=existing), \
            patch("shopman.shop.adapters.courier_machine.register_webhook") as register:
        output = _run()
    assert [call.kwargs["kind"] for call in register.call_args_list] == ["posicao"]
    assert "já cadastrado" in output
    assert "segredo-longo-123" not in output


@override_settings(SHOPMAN_MACHINE={**MACHINE, "webhook_token": ""})
def test_refuses_without_token():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        _run()
