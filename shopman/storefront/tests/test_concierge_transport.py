"""Transporte do concierge: os dois verbos novos do adapter ManyChat.

``send_text`` precisa declarar o canal WhatsApp (sem isso o ManyChat avalia a
janela do Messenger) e ``set_custom_field`` grava o campo do handoff. Nada
sai de verdade: ``_api_call`` é substituído e o que se afirma é o payload.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from shopman.shop.adapters import notification_manychat as adapter

MANYCHAT = {"api_token": "tok-test", "base_url": "https://api.manychat.test/fb"}


@pytest.fixture
def calls(monkeypatch):
    """Captura as chamadas à API e responde sucesso."""
    seen: list[tuple[str, dict]] = []

    def fake_api_call(endpoint, payload, config):
        seen.append((endpoint, payload))
        return {"success": True, "message_id": "mc_1"}

    monkeypatch.setattr(adapter, "_api_call", fake_api_call)
    return seen


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=False)
def test_send_text_declara_o_canal_whatsapp(calls):
    assert adapter.send_text("12345", "Temos baguete sim!") is True
    assert len(calls) == 1
    endpoint, payload = calls[0]
    assert endpoint == "/sending/sendContent"
    assert payload == {
        "subscriber_id": 12345,
        "data": {
            "version": "v2",
            "content": {
                "type": "whatsapp",
                "messages": [{"type": "text", "text": "Temos baguete sim!"}],
            },
        },
    }


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=False)
def test_send_text_corta_em_4000_caracteres(calls, monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(adapter.logger, "warning", lambda msg, *args, **kw: warnings.append(msg % args))
    longo = "a" * 4500
    assert adapter.send_text(12345, longo) is True
    _, payload = calls[0]
    assert len(payload["data"]["content"]["messages"][0]["text"]) == adapter.TEXT_MAX_CHARS == 4000
    assert any("cortado" in w for w in warnings)


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=False)
def test_send_text_vazio_nao_chama_a_api(calls):
    assert adapter.send_text("12345", "   ") is False
    assert calls == []


@override_settings(SHOPMAN_MANYCHAT={}, DEBUG=False)
def test_send_text_sem_token_devolve_false(calls):
    assert adapter.send_text("12345", "oi") is False
    assert calls == []


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=True, SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG=False,
                   SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=False)
def test_send_text_inerte_em_dev_nao_chama_e_devolve_true(calls):
    assert adapter.send_text("12345", "oi") is True
    assert calls == []


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=False)
def test_set_custom_field_payload(calls):
    assert adapter.set_custom_field("777", "concierge_handoff", "1") is True
    assert calls == [
        ("/subscriber/setCustomFieldByName",
         {"subscriber_id": 777, "field_name": "concierge_handoff", "field_value": "1"}),
    ]


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=False)
def test_set_custom_field_recusa_da_api_devolve_false(monkeypatch):
    monkeypatch.setattr(adapter, "_api_call", lambda *a, **k: {"success": False, "error": "no field"})
    assert adapter.set_custom_field("777", "concierge_handoff", "") is False


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=True, SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG=False,
                   SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=False)
def test_set_custom_field_inerte_em_dev(calls):
    assert adapter.set_custom_field("777", "concierge_handoff", "1") is True
    assert calls == []


@override_settings(SHOPMAN_MANYCHAT=MANYCHAT, DEBUG=False)
def test_subscriber_id_nao_numerico_nao_chama(calls):
    assert adapter.send_text("+5543999990000", "oi") is False
    assert calls == []
