"""Transporte do concierge: falar com o ManyChat.

Fina de propósito. O adapter ``notification_manychat`` é quem sabe autenticar,
declarar o canal WhatsApp e ficar inerte em dev; aqui só se escolhe o verbo.

Dois verbos, e só dois:

- ``send_text``   — a resposta do turno. A janela de 24 h está aberta por
                    construção (o cliente acabou de falar), então é texto livre
                    por ``sendContent``, sem template.
- ``set_handoff`` — liga/desliga o campo personalizado que o flow do ManyChat
                    consulta ANTES de chamar a casa. Não existe API para pausar
                    a automação; o campo é o combinado entre o flow e a casa.

Falha de envio nunca é exceção: devolve ``False`` e quem chamou decide (registrar,
alertar, tentar de novo na próxima mensagem). O log do adapter já grita.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _config() -> dict:
    return getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}


def send_text(subscriber_id: str, text: str) -> bool:
    """Envia ``text`` ao assinante. ``True`` se o ManyChat aceitou."""
    if not text or not text.strip():
        return False
    from shopman.shop.adapters import notification_manychat

    try:
        return bool(notification_manychat.send_text(str(subscriber_id), text))
    except Exception:
        logger.exception("concierge.transport.send_text falhou subscriber=%s", subscriber_id)
        return False


def set_handoff(subscriber_id: str, on: bool) -> bool:
    """Grava o campo de handoff no assinante (``"1"`` ligado, ``""`` desligado)."""
    field = str(_config().get("handoff_field") or "concierge_handoff")
    from shopman.shop.adapters import notification_manychat

    try:
        return bool(
            notification_manychat.set_custom_field(str(subscriber_id), field, "1" if on else "")
        )
    except Exception:
        logger.exception("concierge.transport.set_handoff falhou subscriber=%s", subscriber_id)
        return False
