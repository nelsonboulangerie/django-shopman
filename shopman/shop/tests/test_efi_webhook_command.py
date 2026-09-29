"""O webhook do Pix na Efí aponta para ESTE deployment — cadastrado no release.

Nenhum teste aqui fala com a Efí: o transporte (``urlopen``) é substituído e as
requisições que sairiam são inspecionadas.
"""

from __future__ import annotations

import io
import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework.test import APIClient

from shopman.shop.adapters import payment_efi

pytestmark = pytest.mark.django_db

TOKEN = "segredo-do-webhook"
PIX_KEY = "pix@nelson.example"
API_HOST = "api.boulangerie.example"
CANONICAL = f"https://{API_HOST}/api/webhooks/efi/pix/?token={TOKEN}&ignorar="

EFI_ON = {
    "SHOPMAN_PAYMENT_ADAPTERS": {"pix": "shopman.shop.adapters.payment_efi"},
    "SHOPMAN_EFI": {
        "sandbox": True,
        "client_id": "cid",
        "client_secret": "csecret",
        "certificate_path": "/nao/existe.pem",
        "pix_key": PIX_KEY,
    },
    "SHOPMAN_EFI_WEBHOOK": {"webhook_token": TOKEN},
    "SHOPMAN_OPERATOR_API_HOST": API_HOST,
}


class FakeEfi:
    """Guarda o webhook por chave como a Efí faria e registra cada chamada."""

    def __init__(self, registered: str | None = None, *, put_status: int | None = None):
        self.registered = registered
        self.put_status = put_status
        self.calls: list[tuple[str, str, dict, dict]] = []

    def urlopen(self, request, context=None, timeout=None):
        body = json.loads(request.data.decode()) if request.data else {}
        headers = {k.lower(): v for k, v in request.header_items()}
        self.calls.append((request.get_method(), request.full_url, headers, body))
        method = request.get_method()
        if method == "GET":
            if self.registered is None:
                raise HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b'{"nome":"webhook_nao_encontrado"}'))
            return _response({"webhookUrl": self.registered, "chave": PIX_KEY})
        if method == "PUT":
            if self.put_status:
                raise HTTPError(request.full_url, self.put_status, "Erro", {}, io.BytesIO(b'{"nome":"acesso_negado"}'))
            self.registered = body["webhookUrl"]
            return _response(None)
        raise AssertionError(f"verbo inesperado {method}")

    @property
    def puts(self):
        return [call for call in self.calls if call[0] == "PUT"]


def _response(payload):
    raw = b"" if payload is None else json.dumps(payload).encode()
    response = MagicMock()
    response.read.return_value = raw
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


@contextmanager
def efi(fake: FakeEfi):
    with (
        patch.object(payment_efi, "_get_access_token", return_value="tok"),
        patch.object(payment_efi.ssl, "create_default_context"),
        patch.object(payment_efi, "urlopen", side_effect=fake.urlopen),
    ):
        yield fake


def _run(*args):
    out, err = io.StringIO(), io.StringIO()
    call_command("efi_webhook", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


@override_settings(**EFI_ON)
def test_registers_canonical_url_with_skip_mtls_when_missing():
    with efi(FakeEfi(registered=None)) as fake:
        out, _ = _run()

    assert len(fake.puts) == 1
    method, url, headers, body = fake.puts[0]
    assert url == "https://pix-h.api.efipay.com.br/v2/webhook/pix%40nelson.example"
    assert headers["x-skip-mtls-checking"] == "true"
    assert body == {"webhookUrl": CANONICAL}
    assert fake.registered == CANONICAL
    assert "cadastrado" in out and "homologação" in out
    assert TOKEN not in out


@override_settings(**EFI_ON)
def test_replaces_webhook_that_points_to_a_dead_host():
    dead = "https://api.staging.nelsonboulangerie.com.br/api/webhooks/efi/pix/?token=velho"
    with efi(FakeEfi(registered=dead)) as fake:
        out, _ = _run()

    assert fake.registered == CANONICAL
    assert "api.staging.nelsonboulangerie.com.br" in out  # o "antes" aparece


@override_settings(**EFI_ON)
def test_is_idempotent_when_already_canonical():
    with efi(FakeEfi(registered=CANONICAL)) as fake:
        out, _ = _run()

    assert fake.puts == []
    assert "já cadastrado" in out


@override_settings(**EFI_ON)
def test_check_reports_divergence_without_writing():
    with efi(FakeEfi(registered=None)) as fake, pytest.raises(CommandError, match="diverge"):
        _run("--check")
    assert fake.puts == []


@override_settings(**EFI_ON)
def test_soft_failure_is_visible_but_does_not_break_release():
    with efi(FakeEfi(registered=None, put_status=403)):
        out, err = _run("--soft")

    assert "recusou o cadastro" in err
    assert "acesso_negado" in err
    assert TOKEN not in err + out


@override_settings(**EFI_ON)
def test_hard_failure_raises_without_soft():
    with efi(FakeEfi(registered=None, put_status=403)), pytest.raises(CommandError):
        _run()


@override_settings(**{**EFI_ON, "SHOPMAN_EFI_WEBHOOK": {"webhook_token": ""}})
def test_missing_token_is_an_error_not_a_silent_skip():
    with efi(FakeEfi()) as fake, pytest.raises(CommandError, match="EFI_WEBHOOK_TOKEN"):
        _run()
    assert fake.calls == []


@override_settings(**{**EFI_ON, "SHOPMAN_PAYMENT_ADAPTERS": {"pix": "shopman.shop.adapters.payment_mock"}})
def test_does_nothing_when_pix_is_not_efi():
    with efi(FakeEfi()) as fake:
        out, _ = _run()
    assert fake.calls == []
    assert "nada a cadastrar" in out


# ── O porquê do ``&ignorar=``: a Efí acrescenta ``/pix`` ao fim da URL ──


@override_settings(SHOPMAN_EFI_WEBHOOK={"webhook_token": TOKEN, "ip_allowlist": ()})
def test_canonical_url_survives_efi_appending_pix_suffix():
    client = APIClient()
    # O que a Efí chama com a URL canônica cadastrada: ``...&ignorar=`` + ``/pix``.
    ok = client.post(
        f"/api/webhooks/efi/pix/?token={TOKEN}&ignorar=/pix",
        {"evento": "teste_webhook"},
        format="json",
    )
    assert ok.status_code == 200

    # Sem o ``ignorar=``, o acréscimo cairia dentro do token — e todo webhook morreria.
    broken = client.post(
        f"/api/webhooks/efi/pix/?token={TOKEN}/pix",
        {"evento": "teste_webhook"},
        format="json",
    )
    assert broken.status_code == 401
