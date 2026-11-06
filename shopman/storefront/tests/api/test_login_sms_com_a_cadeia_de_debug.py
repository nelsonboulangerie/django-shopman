"""Beta 05/11 (LOJA-01): ninguém entrava por SMS na loja local.

Em DEBUG a cadeia é ``sms,console``: o Comtele fica inerte, devolve False e o
``ConsoleSender`` entrega. O código ficava gravado com ``delivery_method =
"console"`` e o vínculo do telefone no Guestman recusava essa prova
(``unsupported_verification_proof``), que a loja traduzia como cadastro
duplicado. Os testes de login passavam um sender explícito e nunca exercitavam
a cadeia de verdade; este passa pela cadeia inteira, sem sender custom.
"""

from __future__ import annotations

import json
import re

import pytest
from django.test import Client
from shopman.doorman.conf import reset_adapter
from shopman.doorman.models import VerificationCode

pytestmark = pytest.mark.django_db

PHONE = "+5543991374682"


@pytest.fixture(autouse=True)
def _cadeia_de_debug(settings, monkeypatch):
    settings.RATELIMIT_ENABLE = False
    settings.DEBUG = True  # a cadeia ``sms,console`` só existe em DEBUG
    settings.DOORMAN = {
        **settings.DOORMAN,
        "DELIVERY_CHAIN": ["sms", "console"],
        "DELIVERY_SENDERS": {
            **settings.DOORMAN.get("DELIVERY_SENDERS", {}),
            "sms": "shopman.shop.adapters.otp_sms_comtele.ComteleSMSSender",
            "console": "shopman.doorman.senders.ConsoleSender",
        },
    }
    # A trava de dev do Comtele: o SMS externo fica inerte e a cadeia cai no console.
    from shopman.shop.adapters import _external

    monkeypatch.setattr(_external, "_suppressed_reason", "teste: SMS inerte como em DEBUG")
    reset_adapter()
    yield
    reset_adapter()


def _post(client: Client, path: str, payload: dict):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def test_codigo_entregue_pelo_console_entra_como_sms(client: Client, capsys):
    resp = _post(client, "/api/v1/auth/request-code/", {"phone": PHONE, "delivery_method": "sms"})
    assert resp.status_code == 200, resp.content
    assert resp.json()["delivery_method"] == "sms"

    code = VerificationCode.objects.filter(target_value=PHONE).latest("created_at")
    assert code.delivery_method == "sms"

    out = capsys.readouterr().out
    found = re.findall(r"Code: (\d+)", out)
    assert found, out
    resp = _post(client, "/api/v1/auth/verify-code/", {"phone": PHONE, "code": found[-1]})
    assert resp.status_code == 200, resp.content


def _verify_fails_with(monkeypatch, *, error: str, error_code, attempts_remaining=None) -> None:
    from types import SimpleNamespace

    from shopman.shop.services import auth as auth_service

    monkeypatch.setattr(
        auth_service,
        "verify_for_login",
        lambda **_: SimpleNamespace(
            success=False, error=error, error_code=error_code, attempts_remaining=attempts_remaining,
        ),
    )


def test_conflito_de_identidade_tem_codigo_proprio_e_nao_aponta_o_campo_do_codigo(client: Client, monkeypatch):
    """LOJA-03: o código estava certo; a tela precisa saber que o problema é o número."""
    from shopman.doorman.error_codes import ErrorCode

    _verify_fails_with(
        monkeypatch, error="This handle belongs to another account.", error_code=ErrorCode.IDENTITY_CONFLICT,
    )
    resp = _post(client, "/api/v1/auth/verify-code/", {"phone": PHONE, "code": "123456"})

    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "identity_conflict"
    assert body["field"] is None
    assert body["errors"] == {}
    assert "mais de um cadastro" in body["detail"]


def test_codigo_errado_segue_apontando_o_campo_do_codigo(client: Client, monkeypatch):
    from shopman.doorman.error_codes import ErrorCode

    _verify_fails_with(monkeypatch, error="Incorrect code.", error_code=ErrorCode.CODE_INVALID, attempts_remaining=2)
    resp = _post(client, "/api/v1/auth/verify-code/", {"phone": PHONE, "code": "123456"})

    body = resp.json()
    assert body["field"] == "code"
    assert "error_code" not in body

