"""Cadência de atualização das telas do cliente — configurável, não literal.

O acompanhamento e a tela de pagamento se atualizam por push (SSE) com poll de
fallback. As cadências desse poll estavam espalhadas como número mágico: uma
constante de módulo lida no import (exigia restart), um `setInterval(…, 8000)`
no Vue e um piso de 15s cravado no front. Nada disso chegava ao gestor.

Aqui vira dataclass — fonte da verdade do JSON, como as demais configs do
projeto — com cascata `Shop.realtime` ← `settings` ← default. Lida por
requisição, então mudar no Admin vale na próxima carga, sem reiniciar nada.

O piso é guarda de servidor, não preferência: por mais que se configure baixo,
ele impede que a tela vire um martelo contra a API.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

# Piso absoluto: nem config nem Admin descem abaixo disto.
ABSOLUTE_FLOOR_SECONDS = 3


@dataclass(frozen=True)
class RealtimeConfig:
    """Cadência do poll das telas do cliente, em segundos."""

    # Acompanhamento: o pedido muda de estado em minutos, não em segundos.
    tracking_poll_seconds: int = 30
    # Pagamento: o cliente está parado esperando o Pix cair — vale ser mais ágil.
    payment_poll_seconds: int = 8
    # Piso aplicado às duas telas (protege a API de config afobada).
    min_poll_seconds: int = 5

    @classmethod
    def load(cls) -> RealtimeConfig:
        """Cascata: Shop.realtime ← settings ← default da dataclass."""
        values = {
            "tracking_poll_seconds": _from_settings("STOREFRONT_TRACKING_POLL_SECONDS"),
            "payment_poll_seconds": _from_settings("STOREFRONT_PAYMENT_POLL_SECONDS"),
            "min_poll_seconds": _from_settings("STOREFRONT_MIN_POLL_SECONDS"),
        }
        values = {k: v for k, v in values.items() if v is not None}
        values.update(_from_shop())
        base = cls()
        cleaned = {}
        for field, default in asdict(base).items():
            raw = values.get(field, default)
            try:
                cleaned[field] = max(int(raw), ABSOLUTE_FLOOR_SECONDS)
            except (TypeError, ValueError):
                cleaned[field] = default
        return cls(**cleaned)

    def tracking_seconds(self) -> int:
        return max(self.tracking_poll_seconds, self.min_poll_seconds)

    def payment_seconds(self) -> int:
        return max(self.payment_poll_seconds, self.min_poll_seconds)


def _from_settings(name: str) -> int | None:
    value = getattr(settings, name, None)
    return value if value is not None else None


def _from_shop() -> dict:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        raw = getattr(shop, "realtime", None) if shop else None
        return dict(raw) if isinstance(raw, dict) else {}
    except Exception:
        # Base ainda não migrada / Shop ausente: cai no settings + default.
        logger.debug("realtime_config_shop_lookup_degraded", exc_info=True)
        return {}


__all__ = ["ABSOLUTE_FLOOR_SECONDS", "RealtimeConfig"]
