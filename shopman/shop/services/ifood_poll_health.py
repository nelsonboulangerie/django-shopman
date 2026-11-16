"""Sinal de vida do polling do iFood (DEV-2026-017, issue #2325).

A integração direta do iFood entra só por polling (``ifood_poll --watch``, a cada
30 s, componente ``ifood-poll-worker``): não há webhook. Se o polling para, os
pedidos não entram e o iFood cancela cada um depois de 8 minutos sem aceite. Até
aqui, nada percebia: o único vigia (``check_ifood_store``) depende do módulo
Merchant, desligado.

O registro é a hora do último poll que o iFood RESPONDEU (200 com lista, ou 204
sem eventos), gravada no mesmo lugar dos outros workers
(``shopman.orderman.worker_heartbeat``: Redis compartilhado em produção, sem
migração e sem componente novo). Quem lê:

* a sonda ``ifood_polling`` do Watchman (``shopman.shop.watchman_checks``);
* o ``check_ifood_polling`` do maintenance-worker, que vira ``OperatorAlert``.

O limiar é 2 minutos: quatro polls seguidos sem resposta. Ainda sobram seis
minutos dos oito do iFood para alguém aceitar o pedido pelo Portal.

Cache locmem (dev/CI) é por processo: o batimento de outro processo é invisível,
e a ausência de registro ali é "desconhecido", nunca alarme. Com cache
compartilhado e a integração configurada, ausência de registro é worker que
nunca respondeu, e alarma.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

#: Nome do batimento em ``worker_heartbeat``.
POLL_HEARTBEAT = "ifood_poll"

#: Quatro polls de 30 s sem resposta do iFood.
STALE_AFTER = timedelta(minutes=2)

_LOCMEM_BACKEND = "django.core.cache.backends.locmem.LocMemCache"

DISABLED = "disabled"
UNKNOWN = "unknown"
FRESH = "fresh"
STALE = "stale"
MISSING = "missing"


@dataclass(frozen=True, slots=True)
class PollHealth:
    state: str
    last_success: datetime | None = None
    age_seconds: int | None = None

    @property
    def failing(self) -> bool:
        return self.state in {STALE, MISSING}


def record_success() -> None:
    """Grava a hora do poll que o iFood respondeu (200 ou 204)."""
    from shopman.orderman import worker_heartbeat

    worker_heartbeat.beat(POLL_HEARTBEAT)


def last_success() -> datetime | None:
    from shopman.orderman import worker_heartbeat

    return worker_heartbeat.last_beat(POLL_HEARTBEAT)


def _shared_cache() -> bool:
    return settings.CACHES.get("default", {}).get("BACKEND", "") != _LOCMEM_BACKEND


def current(now: datetime | None = None) -> PollHealth:
    """Estado do polling agora."""
    from shopman.shop.services import ifood_events

    if not ifood_events.polling_configured():
        return PollHealth(DISABLED)
    now = now or timezone.now()
    last = last_success()
    if last is None:
        return PollHealth(MISSING if _shared_cache() else UNKNOWN)
    age = max(0, int((now - last).total_seconds()))
    state = STALE if now - last > STALE_AFTER else FRESH
    return PollHealth(state, last_success=last, age_seconds=age)


__all__ = [
    "DISABLED",
    "FRESH",
    "MISSING",
    "POLL_HEARTBEAT",
    "STALE",
    "STALE_AFTER",
    "UNKNOWN",
    "PollHealth",
    "current",
    "last_success",
    "record_success",
]
