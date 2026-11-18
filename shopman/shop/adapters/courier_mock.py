"""
Mock courier adapter — dev e testes, sem rede.

Espelha a interface de :mod:`courier_machine`. O estado das corridas vive em
memória de processo e é controlável pelo teste/dev:

    from shopman.shop.adapters import courier_mock
    result = courier_mock.dispatch(payload)          # id determinístico
    courier_mock.set_status(result.courier_ref, "E") # simula coleta
    courier_mock.reset()                             # limpa entre testes
"""

from __future__ import annotations

from .courier_machine import (  # noqa: F401 — mesma semântica de status
    BEFORE_ACCEPT_STATUSES,
    CANCEL_REASON_BEFORE_ACCEPT,
    CANCEL_REASON_REFUSED_CODE,
    CANCEL_REASONS_AFTER_ACCEPT,
    CANCELLABLE_STATUSES,
    CAPABILITIES,
    TERMINAL_STATUSES,
    CourierDispatchResult,
    CourierError,
    CourierEstimate,
    ride_state,
)

_rides: dict[str, dict] = {}
_counter = 0


def reset() -> None:
    global _counter
    _rides.clear()
    _webhooks.clear()
    _counter = 0


def set_status(courier_ref: str, status: str) -> None:
    _rides.setdefault(courier_ref, {})["status"] = status


def set_driver(courier_ref: str, driver: dict) -> None:
    _rides.setdefault(courier_ref, {})["driver"] = driver


def set_progress(courier_ref: str, progress: dict) -> None:
    _rides.setdefault(courier_ref, {}).setdefault("progress", {}).update(progress)


def fail_reads(courier_ref: str, message: str = "[67] O usuário informado não pode realizar essa operação.") -> None:
    """Simula a central recusando a leitura da corrida (o que o alpha viu em 13/10)."""
    _rides.setdefault(courier_ref, {})["read_error"] = message


def set_tracking_links(courier_ref: str, links) -> None:
    """Simula a resposta de ``/obterLinkRastreio`` (lista fora de ordem, com ``id_externo``, formato único)."""
    _rides.setdefault(courier_ref, {})["tracking_links"] = links


def rides() -> dict[str, dict]:
    """Estado interno (payloads despachados) — para asserts em testes."""
    return _rides


def is_configured() -> bool:
    return True


def estimate(*, pickup: dict, dropoff: dict, with_return: bool = False,
             stops: list[dict] | None = None) -> CourierEstimate | None:
    if not all([pickup.get("lat"), pickup.get("lng"), dropoff.get("lat"), dropoff.get("lng")]):
        return None
    extra = len(stops or [])
    return CourierEstimate(value_q=1250 + 400 * extra, minutes=18.0 + 6 * extra, km=round(4.2 + 1.5 * extra, 1))


def dispatch(payload: dict) -> CourierDispatchResult:
    global _counter
    _counter += 1
    external = ""
    for parada in payload.get("paradas") or []:
        external = str(parada.get("id_externo") or "")
        if external:
            break
    courier_ref = f"MOCK-{external or _counter}"
    if courier_ref in _rides:
        courier_ref = f"{courier_ref}-{_counter}"
    _rides[courier_ref] = {"status": "D", "payload": payload, "driver": None}
    return CourierDispatchResult(courier_ref=courier_ref)


def get_status(courier_ref: str) -> str:
    ride = _rides.get(courier_ref)
    if ride is None:
        raise CourierError("Solicitação não encontrada.", transient=False)
    return ride.get("status") or "D"


def get_details(courier_ref: str) -> dict:
    ride = _rides.get(courier_ref) or {}
    driver = ride.get("driver") or {
        "name": "Entregador Mock",
        "phone": "(43) 99999-0000",
        "vehicle_plate": "MCK0A00",
        "vehicle_model": "Moto Mock",
    }
    return {"request_id": courier_ref, "driver": driver, "progress": {}, "finished": {}}


def read_ride(courier_ref: str) -> dict:
    ride = _rides.get(courier_ref)
    if ride is None:
        raise CourierError("Solicitação não encontrada.", transient=False)
    if ride.get("read_error"):
        raise CourierError(f"Machine recusou (400): {ride['read_error']}", transient=False)
    status = ride.get("status") or "D"
    driver = None
    if status in ("A", "S", "E", "F"):
        driver = {"vehicle_color": "", **get_details(courier_ref)["driver"]}
    progress = {
        "accepted_at": "", "pickup_eta_at": "", "pickup_eta_minutes": None, "pickup_km": None,
        "near_pickup_at": "", "arrived_pickup_at": "", "picked_up_at": "", "trip_minutes": None,
        "trip_km": None, "finished_at": "", "cancelled_at": "", "cancelled_reason": "",
        **(ride.get("progress") or {}),
    }
    return {"status": status, "driver": driver, "progress": progress,
            "final_value_q": ride.get("final_value_q"), "via": "details"}


def get_position(courier_ref: str) -> dict | None:
    ride = _rides.get(courier_ref) or {}
    if ride.get("status") in ("A", "S", "E"):
        return {"lat": -23.3045, "lng": -51.1696}
    return None


def cancel(courier_ref: str, *, reason_id: int) -> bool:
    """Cancela como a central: o motivo tem de ser o da fase, senão erro 102.

    Antes do aceite só o 10; depois do aceite, a lista de
    ``CANCEL_REASONS_AFTER_ACCEPT``. Os motivos recebidos ficam em
    ``rides()[ref]["cancel_reasons"]``, para o teste conferir o que foi enviado.
    """
    ride = _rides.get(courier_ref)
    if ride is None:
        raise CourierError("Solicitação não encontrada.", transient=False)
    if ride.get("status") in TERMINAL_STATUSES:
        raise CourierError("Solicitação já finalizada/cancelada.", transient=False)
    ride.setdefault("cancel_reasons", []).append(reason_id)
    before_accept = (ride.get("status") or "D") in BEFORE_ACCEPT_STATUSES
    accepted = reason_id == CANCEL_REASON_BEFORE_ACCEPT if before_accept else reason_id in CANCEL_REASONS_AFTER_ACCEPT
    if not accepted:
        raise CourierError(
            f"Machine recusou (400): [{CANCEL_REASON_REFUSED_CODE}] Motivo de cancelamento inválido para o status.",
            transient=False, codes=(CANCEL_REASON_REFUSED_CODE,),
        )
    ride["status"] = "C"
    return True


def tracking_links(courier_ref: str) -> list[dict]:
    """Uma entrada por parada, na ordem enviada (o formato da coleção original da TaOn).

    Corrida de uma parada mantém o link de sempre; com várias, cada parada tem o
    seu. ``set_tracking_links`` troca a resposta para o teste do casamento.
    """
    ride = _rides.get(courier_ref)
    if ride is None:
        return []
    if "tracking_links" in ride:
        return [dict(entry) for entry in ride["tracking_links"]]
    stops = (ride.get("payload") or {}).get("paradas") or [{}]
    base = f"https://rastreio.mock/pedido/{courier_ref}"
    return [
        {
            "parada_id": str(index),
            "link_rastreio": base if len(stops) == 1 else f"{base}/parada/{index}",
            "codigo_confirmacao": 1233 + index,
        }
        for index, _ in enumerate(stops, start=1)
    ]


_webhooks: list[dict] = []


def list_webhooks() -> list[dict]:
    return list(_webhooks)


def register_webhook(url: str, *, kind: str) -> bool:
    _webhooks.append({"id": len(_webhooks) + 1, "tipo": kind, "url": url})
    return True
