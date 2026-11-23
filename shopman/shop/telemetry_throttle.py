"""Erro de provedor de IA vai ao Sentry uma vez por dia por causa, não a cada chamada.

A integração do Sentry com a Anthropic liga sozinha (o pacote ``anthropic`` está
instalado) e manda um evento a cada chamada que falha, mesmo quando o código já
trata a falha. Uma chave inválida é ESTADO: com a Concierge e os placares chamando
o tempo todo, viraram 610 eventos em 14 dias (SHOPMAN-1C, 401 ``invalid x-api-key``)
e ajudaram a esgotar a cota mensal do Sentry, que então para de registrar o erro
novo de verdade.

Fica um evento por causa (tipo da exceção e texto dela) a cada 24 h: a issue segue
viva no Sentry, com o "visto por último" em dia, sem gastar a cota.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: A marca que a integração do Sentry põe na exceção que ela mesma capturou.
PROVIDER_MECHANISMS = frozenset({"anthropic"})

#: De quanto em quanto tempo a mesma causa volta ao Sentry.
EVERY_SECONDS = 24 * 60 * 60


def _provider_exception(event: dict) -> dict | None:
    values = ((event.get("exception") or {}).get("values")) or []
    for value in reversed(values):
        if not isinstance(value, dict):
            continue
        mechanism = value.get("mechanism") or {}
        if isinstance(mechanism, dict) and mechanism.get("type") in PROVIDER_MECHANISMS:
            return value
    return None


def drop_repeated_provider_error(event: Any) -> Any:
    """``None`` (descarta) quando a mesma falha do provedor já foi ao Sentry hoje."""

    if not isinstance(event, dict):
        return event
    exception = _provider_exception(event)
    if exception is None:
        return event
    cause = f"{exception.get('type') or ''}|{str(exception.get('value') or '')[:200]}"
    key = "sentry:provider_error:" + hashlib.sha256(cause.encode()).hexdigest()[:32]
    try:
        from django.core.cache import cache

        first_today = cache.add(key, 1, timeout=EVERY_SECONDS)
    except Exception:
        # Sem cache, na dúvida o erro aparece.
        logger.debug("telemetry_throttle.cache_unavailable", exc_info=True)
        return event
    return event if first_today else None
