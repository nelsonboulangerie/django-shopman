"""Ponte servidor-a-servidor com o Google Drive — o cofre vira UMA planilha viva.

Sem navegador e sem upload manual: uma *service account* do Google assina um
JWT (RS256, PyJWT + cryptography — ambos já no lock), troca por um access
token e fala com a API do Drive por HTTPS. O push converte o XLSX do cofre em
Google Sheets NATIVO e atualiza sempre o MESMO arquivo (URL estável para quem
cura); o pull exporta a planilha curada de volta como XLSX, pronta para o
``import_backup``.

Credenciais são dado do deployment, nunca do repositório:

- ``SHOPMAN_GOOGLE_SERVICE_ACCOUNT_FILE`` — caminho do JSON da service account;
- ``SHOPMAN_BACKUP_DRIVE_FOLDER`` — id da pasta do Drive compartilhada com o
  e-mail da service account (papel Editor).

Sem as duas, os comandos falham fechado com a instrução de setup — nunca um
fallback silencioso (a lei da casa para credencial: docs/plans/fallbacks).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import jwt
import requests
from django.conf import settings
from django.core.management.base import CommandError

_DRIVE_API = "https://www.googleapis.com/drive/v3/files"
_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
_SCOPE = "https://www.googleapis.com/auth/drive"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_GSHEET = "application/vnd.google-apps.spreadsheet"
_TIMEOUT = 60


def _config() -> tuple[dict, str]:
    """Credencial + pasta, ou a instrução completa de como criá-las."""
    creds_path = getattr(settings, "SHOPMAN_GOOGLE_SERVICE_ACCOUNT_FILE", "")
    folder = getattr(settings, "SHOPMAN_BACKUP_DRIVE_FOLDER", "")
    if not creds_path or not folder:
        raise CommandError(
            "Ponte com o Drive não configurada. Defina "
            "SHOPMAN_GOOGLE_SERVICE_ACCOUNT_FILE (JSON da service account) e "
            "SHOPMAN_BACKUP_DRIVE_FOLDER (id da pasta compartilhada com ela). "
            "Passo a passo: docs/guides/backup-and-restore.md, seção 'Camada 3'."
        )
    path = Path(creds_path)
    if not path.is_file():
        raise CommandError(f"Arquivo de credencial não encontrado: {path}")
    return json.loads(path.read_text()), folder


def _access_token(creds: dict) -> str:
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": creds["client_email"],
            "scope": _SCOPE,
            "aud": creds["token_uri"],
            "iat": now,
            "exp": now + 3600,
        },
        creds["private_key"],
        algorithm="RS256",
    )
    response = requests.post(
        creds["token_uri"],
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=_TIMEOUT,
    )
    if response.status_code != 200:
        raise CommandError(f"Google recusou a credencial: {response.status_code} {response.text[:300]}")
    return response.json()["access_token"]


def _find_by_name(token: str, name: str, folder: str) -> dict | None:
    query = f"name = '{name}' and '{folder}' in parents and trashed = false"
    response = requests.get(
        _DRIVE_API,
        params={"q": query, "fields": "files(id, name, mimeType, webViewLink)", "pageSize": 2},
        headers={"Authorization": f"Bearer {token}"},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    files = response.json().get("files", [])
    return files[0] if files else None


def push_workbook(name: str, xlsx_bytes: bytes) -> str:
    """Sobe (ou atualiza no lugar) a planilha do cofre. Devolve a URL."""
    creds, folder = _config()
    token = _access_token(creds)
    existing = _find_by_name(token, name, folder)
    headers = {"Authorization": f"Bearer {token}"}

    if existing:
        response = requests.patch(
            f"{_UPLOAD_API}/{existing['id']}",
            params={"uploadType": "media", "fields": "id, webViewLink"},
            data=xlsx_bytes,
            headers={**headers, "Content-Type": _XLSX},
            timeout=_TIMEOUT,
        )
    else:
        metadata = {"name": name, "parents": [folder], "mimeType": _GSHEET}
        response = requests.post(
            _UPLOAD_API,
            params={"uploadType": "multipart", "fields": "id, webViewLink"},
            files={
                "metadata": (None, json.dumps(metadata), "application/json; charset=UTF-8"),
                "file": (name, xlsx_bytes, _XLSX),
            },
            headers=headers,
            timeout=_TIMEOUT,
        )
    if response.status_code not in (200, 201):
        raise CommandError(f"Drive recusou o upload: {response.status_code} {response.text[:300]}")
    payload = response.json()
    return payload.get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{payload['id']}"


def pull_workbook(name_or_id: str) -> bytes:
    """Baixa a planilha curada como XLSX (por nome na pasta, ou por id)."""
    creds, folder = _config()
    token = _access_token(creds)
    existing = _find_by_name(token, name_or_id, folder)
    file_id = existing["id"] if existing else name_or_id
    response = requests.get(
        f"{_DRIVE_API}/{file_id}/export",
        params={"mimeType": _XLSX},
        headers={"Authorization": f"Bearer {token}"},
        timeout=_TIMEOUT,
    )
    if response.status_code != 200:
        raise CommandError(
            f"Drive recusou o export de {name_or_id!r}: {response.status_code} {response.text[:300]}"
        )
    return response.content
