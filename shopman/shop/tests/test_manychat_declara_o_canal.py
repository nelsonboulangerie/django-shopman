"""O envio diz ao ManyChat que o canal é WhatsApp.

02/09: um 400 com código 3011 — "Subscriber's last interaction was over 19521h
ago" — para alguém que tinha acabado de mandar mensagem. O payload nunca
declarava o canal, então o ManyChat avaliava a janela de 24h do MESSENGER, que
para um assinante de WhatsApp nunca abriu.

A pista estava na recusa: ela fala em "message tag", conceito do Messenger. O
WhatsApp tem template e janela, não tag.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _envia(**cfg):
    from shopman.shop.adapters import notification_manychat as mc

    base = {"api_token": "t", "timeout": 5, "flow_map": {}}
    base.update(cfg)
    with patch.object(mc, "_get_config", return_value=base):
        with patch.object(mc, "_resolve_subscriber", return_value=123):
            with patch.object(mc, "_load_db_flow_ns", return_value=None):
                with patch.object(mc, "_api_call", return_value={"success": True}) as api:
                    mc.send("123", "order_accepted", {"order_ref": "NB-1"})
    return api


@pytest.mark.django_db
def test_o_payload_declara_whatsapp():
    api = _envia()
    endpoint, payload, _cfg = api.call_args[0]
    assert endpoint == "/sending/sendContent"
    assert payload["data"]["content"]["type"] == "whatsapp", (
        "sem o canal, o ManyChat avalia a janela do Messenger e recusa com 3011"
    )


@pytest.mark.django_db
def test_a_mensagem_continua_sendo_texto():
    """O `type` do CANAL não pode ter comido o `type` da mensagem."""
    api = _envia()
    _e, payload, _c = api.call_args[0]
    mensagens = payload["data"]["content"]["messages"]
    assert mensagens[0]["type"] == "text"
    assert mensagens[0]["text"]
