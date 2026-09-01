"""Ponte do cofre com o Drive — contrato dos comandos, sem rede.

O que se prova: sem credencial falha FECHADO com a instrução; o JWT assinado
carrega a identidade e o escopo certos; planilha nova nasce com conversão para
Sheets nativo; planilha existente é atualizada NO LUGAR (mesmo id, mesma URL);
o pull exporta como XLSX e não importa nada.
"""

from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.management import CommandError, call_command

from shopman.shop.backup import drive


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def creds_file(tmp_path, rsa_key):
    pem = rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    path = tmp_path / "sa.json"
    path.write_text(json.dumps({
        "client_email": "cofre@teste.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.googleapis.com/token",
    }))
    return path


@pytest.fixture
def bridge(settings, creds_file):
    settings.SHOPMAN_GOOGLE_SERVICE_ACCOUNT_FILE = str(creds_file)
    settings.SHOPMAN_BACKUP_DRIVE_FOLDER = "pasta123"


class _FakeHTTP:
    """Captura chamadas do módulo drive e responde o roteiro combinado."""

    def __init__(self, existing_file=None):
        self.calls = []
        self.existing_file = existing_file

    def _response(self, status, payload=None, content=b""):
        return SimpleNamespace(
            status_code=status,
            content=content,
            text=json.dumps(payload or {}),
            json=lambda: payload or {},
            raise_for_status=lambda: None,
        )

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if "oauth2" in url:
            return self._response(200, {"access_token": "token-fake"})
        return self._response(200, {"id": "novo1", "webViewLink": "https://sheets/novo1"})

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if url.endswith("/export"):
            return self._response(200, content=b"PK-xlsx-fake")
        files = [self.existing_file] if self.existing_file else []
        return self._response(200, {"files": files})

    def patch(self, url, **kwargs):
        self.calls.append(("patch", url, kwargs))
        return self._response(200, {"id": "velho1", "webViewLink": "https://sheets/velho1"})


def test_unconfigured_fails_closed_with_setup_pointer(db, settings):
    settings.SHOPMAN_GOOGLE_SERVICE_ACCOUNT_FILE = ""
    settings.SHOPMAN_BACKUP_DRIVE_FOLDER = ""
    with pytest.raises(CommandError, match="backup-and-restore"):
        call_command("push_backup_drive", stdout=StringIO())
    with pytest.raises(CommandError, match="backup-and-restore"):
        call_command("pull_backup_drive", stdout=StringIO())


def test_push_new_creates_native_sheet_with_signed_jwt(db, bridge, rsa_key, monkeypatch):
    fake = _FakeHTTP()
    monkeypatch.setattr(drive, "requests", fake)
    out = StringIO()
    call_command("push_backup_drive", stdout=out)

    token_call = next(c for c in fake.calls if "oauth2" in c[1])
    assertion = token_call[2]["data"]["assertion"]
    claims = jwt.decode(
        assertion,
        rsa_key.public_key(),
        algorithms=["RS256"],
        audience="https://oauth2.googleapis.com/token",
    )
    assert claims["iss"] == "cofre@teste.iam.gserviceaccount.com"
    assert claims["scope"] == "https://www.googleapis.com/auth/drive"

    upload = next(c for c in fake.calls if c[0] == "post" and "upload" in c[1])
    metadata = json.loads(upload[2]["files"]["metadata"][1])
    assert metadata["mimeType"] == "application/vnd.google-apps.spreadsheet"
    assert metadata["parents"] == ["pasta123"]
    assert "https://sheets/novo1" in out.getvalue()


def test_push_existing_updates_in_place(db, bridge, monkeypatch):
    fake = _FakeHTTP(existing_file={"id": "velho1", "name": "shopman-backup"})
    monkeypatch.setattr(drive, "requests", fake)
    out = StringIO()
    call_command("push_backup_drive", stdout=out)
    patch_call = next(c for c in fake.calls if c[0] == "patch")
    assert patch_call[1].endswith("/velho1")
    assert not any(c[0] == "post" and "upload" in c[1] for c in fake.calls)
    assert "https://sheets/velho1" in out.getvalue()


def test_pull_exports_xlsx_and_imports_nothing(db, bridge, monkeypatch, tmp_path):
    fake = _FakeHTTP(existing_file={"id": "velho1", "name": "shopman-backup"})
    monkeypatch.setattr(drive, "requests", fake)
    out = StringIO()
    call_command("pull_backup_drive", "--out", str(tmp_path), stdout=out)
    export_call = next(c for c in fake.calls if c[1].endswith("/export"))
    assert export_call[2]["params"]["mimeType"].endswith("spreadsheetml.sheet")
    saved = next(tmp_path.glob("drive-*.xlsx"))
    assert saved.read_bytes() == b"PK-xlsx-fake"
    assert "import_backup" in out.getvalue()
