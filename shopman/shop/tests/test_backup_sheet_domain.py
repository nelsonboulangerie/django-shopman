"""Atalho de domínio para a planilha viva do cofre — contrato do middleware.

O host de atalho redireciona (302) para a planilha SEM depender de
ALLOWED_HOSTS (o middleware lê o Host cru e responde antes de qualquer
validação) — de propósito, para o atalho não exigir mais configuração do que
as duas envs. Sem URL configurada, falha fechado em 404. Qualquer outro host
passa intocado.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

_HOST = "backup.boulangerie.com.br"
_SHEET = "https://docs.google.com/spreadsheets/d/abc123/edit"


def test_backup_host_redirects_to_sheet(client, settings):
    settings.SHOPMAN_BACKUP_SHEET_HOST = _HOST
    settings.SHOPMAN_BACKUP_SHEET_URL = _SHEET
    response = client.get("/", HTTP_HOST=_HOST)
    assert response.status_code == 302
    assert response["Location"] == _SHEET


def test_backup_host_without_url_fails_closed(client, settings):
    settings.SHOPMAN_BACKUP_SHEET_HOST = _HOST
    settings.SHOPMAN_BACKUP_SHEET_URL = ""
    assert client.get("/qualquer/", HTTP_HOST=_HOST).status_code == 404


def test_other_hosts_are_untouched(client, settings):
    settings.SHOPMAN_BACKUP_SHEET_HOST = _HOST
    settings.SHOPMAN_BACKUP_SHEET_URL = _SHEET
    assert client.get("/health/").status_code == 200


def test_port_is_ignored_when_matching(client, settings):
    settings.SHOPMAN_BACKUP_SHEET_HOST = _HOST
    settings.SHOPMAN_BACKUP_SHEET_URL = _SHEET
    response = client.get("/", HTTP_HOST=f"{_HOST}:443")
    assert response.status_code == 302
