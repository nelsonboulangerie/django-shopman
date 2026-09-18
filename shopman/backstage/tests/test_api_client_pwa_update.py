"""Telemetria da troca de versão do app instalado (api/v1/backstage/client-pwa-update/).

O relato chega no boot seguinte ao ``updateServiceWorker(true)``: quem o envia é o
``operator-kit`` (``reportPwaUpdateApplied``), com a versão de antes lida do disco e a
versão de agora vinda do bundle que acabou de subir. É essa linha de log que permite
provar no ar que o PDV instalado saiu do bundle antigo — o que, em 17/09/2026, depois
dos deploys das PRs #783 e #789, só dava para afirmar olhando a tela.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from shopman.backstage.api.telemetry import sanitize_pwa_update


def _post(client, payload):
    return client.post(
        reverse("api-backstage-client-pwa-update"),
        data=payload,
        content_type="application/json",
    )


@pytest.mark.django_db
def test_troca_aplicada_vira_evento_com_as_duas_versoes(client):
    with patch("shopman.backstage.api.telemetry.operational_event") as event:
        response = _post(
            client,
            {"app": "pos", "trigger": "idle", "from_version": "abc1234", "to_version": "def5678"},
        )

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    event.assert_called_once_with(
        "pwa.update_applied",
        app="pos",
        trigger="idle",
        from_version="abc1234",
        to_version="def5678",
    )


@pytest.mark.django_db
def test_sem_sessao_de_operador_o_relato_passa(client):
    # O POST sai de uma página que acabou de nascer: exigir sessão trocaria a prova
    # por um silêncio, exatamente quando a prova interessa.
    with patch("shopman.backstage.api.telemetry.operational_event") as event:
        assert _post(client, {"app": "kds", "trigger": "prompt"}).status_code == 202
    event.assert_called_once_with("pwa.update_applied", app="kds", trigger="prompt")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"app": "pdv", "trigger": "idle"},  # app fora do conjunto (é "pos")
        {"app": "pos", "trigger": "sozinho"},  # gatilho inventado
        {"app": "pos"},  # sem gatilho
        {"trigger": "idle"},  # sem app
        [{"app": "pos", "trigger": "idle"}],  # JSON válido que não é um objeto
    ],
)
def test_payload_fora_do_contrato_nao_vira_log(client, payload):
    with patch("shopman.backstage.api.telemetry.operational_event") as event:
        response = _post(client, payload)
    # Aceita e cala: telemetria nunca devolve erro para a tela do operador.
    assert response.status_code == 202
    event.assert_not_called()


def test_versao_fora_do_formato_e_descartada_sem_derrubar_o_evento():
    # Versão ausente é fato comum (bundle sem SOURCE_VERSION); versão com espaço,
    # barra ou tamanho de texto livre é entrada arbitrária e não entra no log.
    assert sanitize_pwa_update(
        {"app": "pos", "trigger": "idle", "from_version": "a b", "to_version": "ok-1.2_3"}
    ) == {"app": "pos", "trigger": "idle", "to_version": "ok-1.2_3"}
    assert sanitize_pwa_update({"app": "pos", "trigger": "idle", "to_version": "x" * 61}) == {
        "app": "pos",
        "trigger": "idle",
    }


def test_corpo_que_nao_e_objeto_nao_vira_log():
    assert sanitize_pwa_update("não é um objeto") == {}
    assert sanitize_pwa_update(None) == {}


def test_todo_app_de_operador_com_pwa_e_aceito():
    for app in ("pos", "kds", "production", "orders", "hub", "marketing", "purchase", "bi"):
        assert sanitize_pwa_update({"app": app, "trigger": "prompt"})["app"] == app
