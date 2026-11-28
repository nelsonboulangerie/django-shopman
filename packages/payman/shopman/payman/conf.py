"""Configuração do Payman.

``PAYMAN["REFUND_BACKEND"]``: caminho pontuado da classe que devolve dinheiro pelo
gateway (contrato ``shopman.payman.protocols.RefundBackend``). Vazio = o Admin de
cobranças não estorna.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string


def get_refund_backend():
    """O ``RefundBackend`` configurado, ou ``None`` quando não há."""
    path = (getattr(settings, "PAYMAN", None) or {}).get("REFUND_BACKEND") or ""
    if not path:
        return None
    return import_string(path)()
