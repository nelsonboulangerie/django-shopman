"""Telemetria da troca de versão da loja instalada (api/v1/storefront/client-pwa-update/, #2379).

O relato chega no boot seguinte ao ``updateServiceWorker(true)``: quem o envia é o
plugin ``pwaUpdateReport.client.ts`` da loja, com a versão de antes lida do disco e a
de agora vinda do bundle que acabou de subir. É o gêmeo do relato do ``operator-kit``
(``test_api_client_pwa_update`` no backstage): o mesmo evento, com ``app="storefront"``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from shopman.storefront.api.telemetry import sanitize_pwa_update


def _post(client, payload):
    return client.post(
        reverse("api-storefront-client-pwa-update"),
        data=payload,
        content_type="application/json",
    )


@pytest.mark.django_db
def test_troca_aplicada_vira_evento_com_as_duas_versoes(client):
    with patch("shopman.storefront.api.telemetry.operational_event") as event:
        response = _post(
            client,
            {"trigger": "prompt", "from_version": "abc1234", "to_version": "def5678"},
        )

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    event.assert_called_once_with(
        "pwa.update_applied",
        app="storefront",
        trigger="prompt",
        from_version="abc1234",
        to_version="def5678",
    )


@pytest.mark.django_db
def test_gatilho_fora_do_conjunto_nao_vira_evento(client):
    with patch("shopman.storefront.api.telemetry.operational_event") as event:
        # A loja nunca aplica sozinha, parada: "idle" é do kit de operador.
        response = _post(client, {"trigger": "idle", "to_version": "def5678"})

    assert response.status_code == 202
    event.assert_not_called()


def test_app_e_fixo_o_cliente_nao_escolhe():
    report = sanitize_pwa_update({"app": "pos", "trigger": "navigation", "to_version": "abc"})

    assert report == {"app": "storefront", "trigger": "navigation", "to_version": "abc"}


def test_versao_fora_do_formato_fica_de_fora():
    report = sanitize_pwa_update(
        {"trigger": "prompt", "from_version": "<script>", "to_version": "a" * 80}
    )

    assert report == {"app": "storefront", "trigger": "prompt"}


def test_payload_que_nao_e_objeto_nao_vira_relato():
    assert sanitize_pwa_update(["prompt"]) == {}
    assert sanitize_pwa_update(None) == {}
