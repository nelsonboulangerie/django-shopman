"""Onde o entregador está, desde quando e quem disse (revisão das Entregas, F7b).

Um lugar só grava a posição (:func:`store_position`) e um só a lê (:func:`read`). A
posição mora no cache, nunca no pedido: muda a cada 10 s e não é história da venda.
Cada registro leva a hora da posição (``at``) e de onde ela veio (``source``), para a
tela dizer "Posição agora" ou "Última posição há 3 min" em vez de mostrar uma moto
parada como se estivesse viva.

As vias, por ordem de preferência:

- ``webhook``: o lote de posição da TaOn, a cada 10 s (a própria TaOn descarta a
  posição com mais de 15 s). É a via normal desde 17/11/2026;
- ``poll``: ``get_position`` do serviço da corrida, na batida do ``courier.sync``,
  SÓ quando o webhook está calado há mais de :data:`WEBHOOK_SILENT_SECONDS`;
- ``own_fleet``: o entregador da casa (DEV-2026-030), se o celular dele mandar.

Cada posição nova avisa o Gestor pelo SSE (evento ``backstage-courier-position`` no
canal ``backstage-orders-main``), no máximo uma vez a cada
:data:`PUSH_THROTTLE_SECONDS` por corrida. O aviso leva só a corrida: a tela refaz o
fetch canônico (ADR-016), e a coordenada não vai para o histórico do SSE.

**A posição do entregador é dado pessoal: nunca vai para o log.** O log diz a corrida,
a via e o desfecho; a coordenada, nunca.

O fim da corrida e a troca de entregador apagam a mesma chave
(``courier._forget_driver_caches``): a posição era de quem saiu.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

#: De onde veio a posição.
SOURCE_WEBHOOK = "webhook"
SOURCE_POLL = "poll"
SOURCE_OWN_FLEET = "own_fleet"
SOURCES = frozenset({SOURCE_WEBHOOK, SOURCE_POLL, SOURCE_OWN_FLEET})

#: Quanto tempo a última posição fica guardada. Passados 2 min ela continua na tela,
#: esmaecida e com a idade; passado isto, some.
KEEP_SECONDS = 30 * 60

#: Sem posição pelo webhook há mais que isto, a batida do ``courier.sync`` pergunta.
#: A TaOn manda um lote a cada 10 s: três lotes perdidos é webhook calado.
WEBHOOK_SILENT_SECONDS = 30

#: No máximo um aviso de posição por corrida neste intervalo.
PUSH_THROTTLE_SECONDS = 10

#: Relógio do serviço adiantado em relação ao nosso: até isto, vale a hora dele;
#: além disso, a hora de chegada (posição "do futuro" não ordena nada).
FUTURE_TOLERANCE_SECONDS = 60

#: Estados em que a corrida tem alguém na rua (``delivery_services.ride_state``).
_STATES_WITH_DRIVER = frozenset({"assigned", "at_store", "on_route"})


def _key(ride_ref: str) -> str:
    return f"courier:pos:{ride_ref}"


def _push_key(ride_ref: str) -> str:
    return f"courier:pos:push:{ride_ref}"


def _coordinate(value, limit: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) > limit:
        return None
    return number


def _instant(value) -> datetime | None:
    """A hora da posição: epoch (s ou ms, como a TaOn manda) ou ISO com fuso."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int | float) or (isinstance(value, str) and value.strip().isdigit()):
        number = float(value)
        if number > 1e12:  # milissegundos
            number /= 1000
        try:
            return datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    from shopman.shop.services.courier import provider_instant

    return provider_instant(str(value).strip())


def store_position(ride_ref, latitude, longitude, *, source: str, at=None) -> bool:
    """Grava a posição do entregador da corrida. False quando não grava.

    Não grava coordenada ilegível ou fora do globo, o ponto (0, 0) que o GPS sem sinal
    manda, nem a posição mais velha que a guardada (lote fora de ordem).
    """
    ride_ref = str(ride_ref or "").strip()
    if not ride_ref or source not in SOURCES:
        return False
    lat, lng = _coordinate(latitude, 90.0), _coordinate(longitude, 180.0)
    if lat is None or lng is None or (lat == 0.0 and lng == 0.0):
        return False
    now = timezone.now()
    moment = (_instant(at) or now).astimezone(UTC)
    if moment > now + timedelta(seconds=FUTURE_TOLERANCE_SECONDS):
        moment = now
    current = read(ride_ref)
    if current is not None and current["at"] > moment:
        return False
    cache.set(_key(ride_ref), {"lat": str(lat), "lng": str(lng), "at": moment.isoformat(), "source": source},
              KEEP_SECONDS)
    if cache.add(_push_key(ride_ref), 1, PUSH_THROTTLE_SECONDS):
        _push(ride_ref)
    return True


def _push(ride_ref: str) -> None:
    try:
        from shopman.shop.handlers._sse_emitters import emit_courier_position

        emit_courier_position(ride_ref)
    except Exception:
        logger.warning("courier.position_push_failed ride_ref=%s", ride_ref, exc_info=True)


def read(ride_ref) -> dict | None:
    """A última posição: ``{latitude, longitude, at, source}``, ou None."""
    ride_ref = str(ride_ref or "").strip()
    if not ride_ref:
        return None
    stored = cache.get(_key(ride_ref))
    if not isinstance(stored, dict):
        return None
    lat, lng = _coordinate(stored.get("lat"), 90.0), _coordinate(stored.get("lng"), 180.0)
    moment = _instant(stored.get("at"))
    source = stored.get("source")
    if lat is None or lng is None or moment is None or source not in SOURCES:
        return None
    return {"latitude": lat, "longitude": lng, "at": moment, "source": source}


def age_seconds(position: dict, *, now: datetime | None = None) -> float:
    return max(0.0, ((now or timezone.now()) - position["at"]).total_seconds())


def webhook_is_silent(ride_ref) -> bool:
    """Nenhuma posição pelo webhook nos últimos :data:`WEBHOOK_SILENT_SECONDS`."""
    position = read(ride_ref)
    return not (position and position["source"] == SOURCE_WEBHOOK
                and age_seconds(position) <= WEBHOOK_SILENT_SECONDS)


def poll_if_silent(block: dict) -> bool:
    """Pergunta a posição ao serviço da corrida, só quando o webhook está calado.

    Chamado pela batida do ``courier.sync``, nunca por uma leitura de tela: a tela
    só lê o cache. Serviço sem ``get_position`` (o entregador da casa) não é
    perguntado. Falha não derruba a batida: a posição só fica mais velha na tela.
    """
    from shopman.shop.services import delivery_services

    ride_ref = str((block or {}).get("ride_ref") or "")
    if not ride_ref:
        return False
    state = delivery_services.ride_state(block)
    if state is None or str(state) not in _STATES_WITH_DRIVER:
        return False
    get_position = getattr(delivery_services.courier_backend(block), "get_position", None)
    if get_position is None or not webhook_is_silent(ride_ref):
        return False
    try:
        answer = get_position(ride_ref)
    except Exception as exc:
        logger.warning("courier.position_poll_failed ride_ref=%s error=%s", ride_ref, type(exc).__name__)
        return False
    if not isinstance(answer, dict):
        return False
    stored = store_position(ride_ref, answer.get("lat"), answer.get("lng"), source=SOURCE_POLL)
    logger.info("courier.position_poll ride_ref=%s stored=%s", ride_ref, "yes" if stored else "no")
    return stored


__all__ = [
    "KEEP_SECONDS",
    "PUSH_THROTTLE_SECONDS",
    "SOURCES",
    "SOURCE_OWN_FLEET",
    "SOURCE_POLL",
    "SOURCE_WEBHOOK",
    "WEBHOOK_SILENT_SECONDS",
    "age_seconds",
    "poll_if_silent",
    "read",
    "store_position",
    "webhook_is_silent",
]
