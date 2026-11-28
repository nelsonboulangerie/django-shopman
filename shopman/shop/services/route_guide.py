"""A manobra da tela "Dirigindo" do entregador da casa, pelo Routes API do Google (#2509).

Aprovado pelo dono (21/11/2026: "Em tese, vamos usar 'pouco', acho que compensa ativar
sim"), com o desenho econômico da coordenação:

- a rota por ruas é calculada UMA vez, na saída ("Saí da loja"), e de novo só quando o
  entregador sai dela (a posição dele passa de ``reroute_meters`` da linha), nunca por
  tempo;
- o pedido vai só com o que a manobra usa (``FIELD_MASK``): os passos, a instrução de
  cada um e a linha. Sem tráfego e com menos de 11 paradas, a chamada fica no SKU
  Essentials do Compute Routes (``COST_USD_MICROS`` é o preço de tabela dele);
- o teto de chamadas por dia é da loja, no Admin (``Shop.integrations["google_routes"]``,
  ADR-042), nunca no env. Sem chave, desligado, no teto ou com erro, a página volta à
  linha reta e ao "Abrir no Waze", sem quebrar a tela;
- cada chamada, inclusive a recusada pelo teto, vira uma linha de ``PaidApiCall``
  (DEV-2026-067), para o B.I. de uso.

A rota mora no cache (como a posição, ``courier_position``): é da corrida viva, não é
história da venda. A coordenada do entregador nunca vai para o log.
"""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.request

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

PROVIDER = "google_routes"
PURPOSE = "courier_maneuver"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
#: Só o que a manobra usa: a linha de cada passo, onde ele começa e a instrução.
FIELD_MASK = ",".join((
    "routes.legs.steps.polyline.encodedPolyline",
    "routes.legs.steps.startLocation",
    "routes.legs.steps.navigationInstruction",
))
#: Compute Routes Essentials: US$ 5 por mil chamadas (tabela pública do Google, 2026).
COST_USD_MICROS = 5_000
REQUEST_TIMEOUT_SECONDS = 6
#: A rota vale enquanto a corrida está na rua; seis horas cobre o dia mais comprido.
KEEP_SECONDS = 6 * 60 * 60

#: Os padrões da loja, sobrescritos por ``Shop.integrations["google_routes"]``.
DEFAULTS = {"enabled": True, "calls_per_day": 100, "reroute_meters": 80}
#: Nenhum teto passa disto sem mudança no código (o mesmo freio da IA).
MAX_CALLS_PER_DAY = 1_000


def _key(ride_ref: str) -> str:
    return f"courier:route:{ride_ref}"


def settings_for_shop() -> dict:
    """O que a loja decidiu no Admin, com os padrões e o freio do código."""
    from shopman.shop.models import Shop

    shop = Shop.objects.first()
    chosen = ((getattr(shop, "integrations", None) or {}).get(PROVIDER) or {}) if shop else {}
    merged = {**DEFAULTS, **(chosen if isinstance(chosen, dict) else {})}
    try:
        per_day = max(0, min(int(merged["calls_per_day"]), MAX_CALLS_PER_DAY))
    except (TypeError, ValueError):
        per_day = DEFAULTS["calls_per_day"]
    try:
        reroute = max(30, int(merged["reroute_meters"]))
    except (TypeError, ValueError):
        reroute = DEFAULTS["reroute_meters"]
    return {"enabled": merged["enabled"] is not False, "calls_per_day": per_day, "reroute_meters": reroute}


def _meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    phi1, phi2 = math.radians(a[0]), math.radians(b[0])
    dphi, dlmb = phi2 - phi1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(min(1.0, h)))


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """A linha codificada do Google (precisão 5) em pontos (lat, lng)."""
    points: list[tuple[float, float]] = []
    index = lat = lng = 0
    while index < len(encoded):
        for is_lng in (False, True):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
            else:
                lat += delta
        points.append((lat / 1e5, lng / 1e5))
    return points


def _record(outcome: str, *, error_type: str = "", latency_ms: int = 0) -> None:
    from shopman.shop.models import PaidApiCall, PaidApiOutcome

    PaidApiCall.objects.create(
        provider=PROVIDER, purpose=PURPOSE, outcome=outcome, error_type=error_type[:80],
        cost_usd_micros=COST_USD_MICROS if outcome == PaidApiOutcome.OK else 0, latency_ms=latency_ms,
    )


def _spend_today(limit: int) -> bool:
    """Ainda cabe uma chamada hoje? Conta as chamadas de verdade do dia (as recusadas não)."""
    from shopman.shop.models import PaidApiCall, PaidApiOutcome

    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    used = PaidApiCall.objects.filter(
        provider=PROVIDER, created_at__gte=start,
    ).exclude(outcome=PaidApiOutcome.DENIED).count()
    return used < limit


def _request(origin: tuple[float, float], stops: list[tuple[float, float]], api_key: str) -> dict:
    point = lambda p: {"location": {"latLng": {"latitude": p[0], "longitude": p[1]}}}  # noqa: E731
    body = {
        "origin": point(origin),
        "destination": point(stops[-1]),
        "intermediates": [point(p) for p in stops[:-1]],
        "travelMode": "TWO_WHEELER",
        "routingPreference": "TRAFFIC_UNAWARE",
        "languageCode": "pt-BR",
        "regionCode": "br",
        "units": "METRIC",
    }
    request = urllib.request.Request(
        ROUTES_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _guide(payload: dict) -> dict | None:
    """A rota numa forma que a página lê: a linha inteira e onde começa cada manobra."""
    path: list[tuple[float, float]] = []
    steps: list[dict] = []
    for route in (payload.get("routes") or [])[:1]:
        for leg in route.get("legs") or []:
            for step in leg.get("steps") or []:
                line = decode_polyline(((step.get("polyline") or {}).get("encodedPolyline")) or "")
                instruction = step.get("navigationInstruction") or {}
                if line:
                    steps.append({
                        "at": len(path),
                        "lat": line[0][0], "lng": line[0][1],
                        "instruction": str(instruction.get("instructions") or "").strip(),
                        "maneuver": str(instruction.get("maneuver") or "").strip(),
                    })
                    path.extend(line)
    if len(path) < 2:
        return None
    return {"path": [[round(lat, 5), round(lng, 5)] for lat, lng in path], "steps": steps}


def compute(ride_ref: str, origin: tuple[float, float], stops: list[tuple[float, float]]) -> bool:
    """Calcula e guarda a rota por ruas. Nunca levanta: sem rota, a página usa a linha reta."""
    from shopman.shop.google_maps_credentials import server_api_key
    from shopman.shop.models import PaidApiOutcome
    from shopman.shop.services.observability import record_integration_failure

    config = settings_for_shop()
    api_key = server_api_key()
    if not (ride_ref and stops and config["enabled"] and api_key):
        return False
    if not _spend_today(config["calls_per_day"]):
        _record(PaidApiOutcome.DENIED)
        return False
    started = time.monotonic()
    try:
        payload = _request(origin, stops, api_key)
    except Exception as exc:  # noqa: BLE001 — a tela volta à linha reta; o log leva só a classe
        latency = int((time.monotonic() - started) * 1000)
        logger.warning("route_guide_failed ride_ref=%s err=%s", ride_ref, exc.__class__.__name__)
        _record(PaidApiOutcome.ERROR, error_type=exc.__class__.__name__, latency_ms=latency)
        record_integration_failure(provider=PROVIDER, operation="compute_routes",
                                   detail=f"falha ({exc.__class__.__name__}); a página usa a linha reta", exc=exc)
        return False
    latency = int((time.monotonic() - started) * 1000)
    guide = _guide(payload)
    _record(PaidApiOutcome.OK if guide else PaidApiOutcome.ERROR,
            error_type="" if guide else "empty_route", latency_ms=latency)
    if guide is None:
        return False
    cache.set(_key(ride_ref), guide, KEEP_SECONDS)
    return True


def read(ride_ref: str) -> dict | None:
    stored = cache.get(_key(ride_ref)) if ride_ref else None
    return stored if isinstance(stored, dict) and stored.get("path") else None


def forget(ride_ref: str) -> None:
    if ride_ref:
        cache.delete(_key(ride_ref))


def _nearest(path: list, here: tuple[float, float]) -> tuple[int, float]:
    best, distance = 0, float("inf")
    for index, (lat, lng) in enumerate(path):
        meters = _meters(here, (lat, lng))
        if meters < distance:
            best, distance = index, meters
    return best, distance


def off_route(ride_ref: str, here: tuple[float, float]) -> bool:
    """Ele saiu da rota guardada? (mais longe da linha que ``reroute_meters``)."""
    guide = read(ride_ref)
    if guide is None:
        return False
    _, distance = _nearest(guide["path"], here)
    return distance > settings_for_shop()["reroute_meters"]


def view(ride_ref: str, here: tuple[float, float] | None) -> dict | None:
    """A linha e a próxima manobra para a página: ``{"path", "next"}``, ou None sem rota."""
    guide = read(ride_ref)
    if guide is None:
        return None
    steps = guide.get("steps") or []
    index = _nearest(guide["path"], here)[0] if here else -1
    upcoming = next((step for step in steps if step["at"] > index and step["instruction"]), None)
    following = None
    if upcoming is not None:
        meters = _meters(here, (upcoming["lat"], upcoming["lng"])) if here else None
        following = {
            "instruction": upcoming["instruction"],
            "maneuver": upcoming["maneuver"],
            "meters": int(round(meters / 10) * 10) if meters is not None else None,
        }
    return {"path": guide["path"], "next": following}
