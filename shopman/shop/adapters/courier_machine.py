"""
Machine courier adapter — despacho de entregadores via API da Machine (Gaudium).

A Machine (api.taximachine.com.br) é a plataforma por trás da central de
entregas usada pelo estabelecimento. Este adapter é a ÚNICA borda HTTP com a
Machine: dinheiro entra/sai daqui já convertido para centavos (`_q`) — a API
fala float em reais (`estimativa_valor`, `final_value`) e nenhum float de
dinheiro cruza esta borda.

Auth: HTTP Basic (usuário de integração) + header `api-key`. Permissão
"API - Entrega" no usuário. Config em settings.SHOPMAN_MACHINE.

Contrato: API de Integração **v1, entregas** (OpenAPI em
docs.machine.global/pages/v1/openapi-entregas.json). Base de produção
``https://api.taximachine.com.br/api/integracao``; homologação
``https://api-vendas.taximachine.com.br/api/integracao`` (mesma API Key). Os
detalhes moram em ``<base>/v1/request/{id}``. Tabela endereço a endereço em
docs/plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md.

Status de solicitação (letra crua; labels só na projection):
  D distribuindo · G aguardando aceite · P pendente · A aceita · S em espera ·
  E em andamento (coletou) · F finalizada · N não atendida · C cancelada ·
  U agrupada. Terminais: F, N, C.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

#: Letras de status terminais — a corrida não muda mais depois delas.
TERMINAL_STATUSES = frozenset({"F", "N", "C"})

#: Fases em que a corrida ainda pode ser cancelada (antes da coleta).
CANCELLABLE_STATUSES = frozenset({"D", "G", "P", "A", "S"})

#: User-Agent próprio. A borda da Machine recusa o padrão do `requests`
#: (`python-requests/x.y`) com 403 e uma página HTML, nos dois ambientes; com qualquer
#: outro, a chamada chega à API. Medido em 01/10/2026 com a chave de produção: o mesmo
#: pedido devolveu 403 HTML como `python-requests/2.32.3` e JSON como `curl/8`.
#: O endereço de contato é o da loja deste deployment (``SHOPMAN_STOREFRONT_BASE_URL``),
#: nunca um domínio escrito aqui.
USER_AGENT_PRODUCT = "Shopman/1.0"


def user_agent() -> str:
    base = (getattr(settings, "SHOPMAN_STOREFRONT_BASE_URL", "") or "").strip()
    return f"{USER_AGENT_PRODUCT} (+{base})" if base else USER_AGENT_PRODUCT


class CourierError(Exception):
    """Falha na chamada à Machine.

    ``transient=True`` (timeout, rede, 5xx) → o chamador pode re-tentar
    (Directive re-agenda). ``transient=False`` (4xx) → erro de dados/config,
    re-tentar não resolve.
    """

    def __init__(self, message: str, *, transient: bool, outcome_unknown: bool | None = None):
        super().__init__(message)
        self.transient = transient
        self.outcome_unknown = transient if outcome_unknown is None else outcome_unknown


@dataclass(frozen=True)
class CourierEstimate:
    value_q: int
    minutes: float
    km: float


@dataclass(frozen=True)
class CourierDispatchResult:
    courier_ref: str
    inert: bool = False


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_MACHINE", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("base_url") or "https://api.taximachine.com.br/api/integracao").rstrip("/")


def _details_base() -> str:
    return str(_cfg().get("details_base") or "https://api.taximachine.com.br/api/integracao/v1").rstrip("/")


def _to_q(value) -> int:
    """Converte valor decimal em reais (float da API) para centavos int."""
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


def _inert() -> bool:
    from ._external import inert

    if inert("SHOPMAN_MACHINE_ALLOW_IN_DEBUG"):
        logger.info("Machine externo inerte (trava dev/seed)")
        return True
    return False


def is_configured() -> bool:
    cfg = _cfg()
    return bool(cfg.get("username") and cfg.get("password") and cfg.get("api_key"))


def _request(method: str, path: str, *, base: str | None = None, params: dict | None = None,
             json_body: dict | None = None) -> dict:
    """Chamada autenticada à Machine. Retorna o dict `response` do envelope.

    Envelope da API: `{"success": true, "response": {...}}` ou
    `{"success": false, "errors": [{code, message}]}`.
    """
    cfg = _cfg()
    if not is_configured():
        raise CourierError("Machine não configurada (username/password/api_key)", transient=False)

    url = f"{base or _base_url()}{path}"
    try:
        resp = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            auth=(cfg["username"], cfg["password"]),
            headers={"api-key": cfg["api_key"], "User-Agent": user_agent()},
            timeout=int(cfg.get("timeout") or 15),
        )
    except requests.RequestException as exc:
        raise CourierError(f"Machine indisponível: {exc}", transient=True) from exc

    if resp.status_code >= 500:
        raise CourierError(
            f"Machine HTTP {resp.status_code}: {resp.text[:200]}", transient=True
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise CourierError(
            f"Machine HTTP {resp.status_code}: resposta não-JSON: {resp.text[:200]}",
            transient=resp.status_code >= 500, outcome_unknown=resp.status_code < 400 or resp.status_code >= 500,
        ) from exc

    # O endpoint de detalhes (/api/integracao/v1) responde o objeto direto, sem envelope.
    if "success" not in payload:
        if resp.status_code >= 400:
            raise CourierError(
                f"Machine HTTP {resp.status_code}: {resp.text[:200]}", transient=False
            )
        return payload

    if not payload.get("success"):
        errors = payload.get("errors") or []
        detail = "; ".join(
            f"[{e.get('code')}] {e.get('message')}" for e in errors if isinstance(e, dict)
        ) or resp.text[:200]
        raise CourierError(f"Machine recusou ({resp.status_code}): {detail}", transient=False)

    response = payload.get("response")
    return response if isinstance(response, (dict, list)) else {}


#: Campo do endereço no nosso lado → sufixo do parâmetro da Machine no
#: GET /estimarSolicitacao (``endereco_partida``, ``bairro_desejado``...). Na
#: API de entregas v1 os quatro são obrigatórios nos dois pontos; a coordenada
#: é opcional e só refina.
_ESTIMATE_ADDRESS_FIELDS = (
    ("street", "endereco"),
    ("neighborhood", "bairro"),
    ("city", "cidade"),
    ("state", "estado"),
)


def _estimate_params(point: dict, suffix: str) -> dict:
    params = {f"lat_{suffix}": point["lat"], f"lng_{suffix}": point["lng"]}
    for ours, theirs in _ESTIMATE_ADDRESS_FIELDS:
        value = str(point.get(ours) or "").strip()
        if value:
            params[f"{theirs}_{suffix}"] = value
    return params


def estimate(*, pickup: dict, dropoff: dict) -> CourierEstimate | None:
    """Cota a corrida (GET /estimarSolicitacao).

    ``pickup``/``dropoff``: dicts com ``lat``/``lng`` e o endereço
    (``street``, ``neighborhood``, ``city``, ``state``), que a API de entregas
    exige. Retorna None quando inerte ou sem coordenadas: a cotação é sempre
    best-effort.
    """
    if _inert():
        return None
    if not all([pickup.get("lat"), pickup.get("lng"), dropoff.get("lat"), dropoff.get("lng")]):
        return None
    response = _request(
        "GET",
        "/estimarSolicitacao",
        params={**_estimate_params(pickup, "partida"), **_estimate_params(dropoff, "desejado")},
    )
    return CourierEstimate(
        value_q=_to_q(response.get("estimativa_valor")),
        minutes=float(response.get("estimativa_minutos") or 0),
        km=float(response.get("estimativa_km") or 0),
    )


def dispatch(payload: dict) -> CourierDispatchResult:
    """Abre a corrida (POST /abrirSolicitacao). Retorna o ``id_mch``.

    ``payload`` é o corpo pronto da Machine (montado por
    ``shopman.shop.services.courier.build_machine_payload``).
    """
    if _inert():
        return CourierDispatchResult(courier_ref="", inert=True)
    response = _request("POST", "/abrirSolicitacao", json_body=payload)
    courier_ref = str(response.get("id_mch") or "")
    if not courier_ref:
        raise CourierError("Machine abriu a solicitação mas não devolveu id_mch", transient=False, outcome_unknown=True)
    return CourierDispatchResult(courier_ref=courier_ref)


def get_status(courier_ref: str) -> str:
    """Status atual da corrida (GET /solicitacaoStatus) — letra crua ("" se inerte)."""
    if _inert():
        return ""
    response = _request("GET", "/solicitacaoStatus", params={"id_mch": courier_ref})
    return str(response.get("status") or "")


def get_details(courier_ref: str) -> dict:
    """Detalhes da corrida (GET /api/integracao/v1/request/:id): driver, progress, finished."""
    if _inert():
        return {}
    return _request("GET", f"/request/{courier_ref}", base=_details_base())


# ── Leitura da corrida (o que o polling aplica) ─────────────────────

#: ``status_label``/``full_code`` da Machine → letra de estado. Os eventos
#: (``ARRIVED_AT_LOCATION``, ``STOP_FINISHED``...) não são estado e ficam de fora.
_LABEL_TO_STATUS = {
    "DISTRIBUTING": "D",
    "WAITING_ACCEPTANCE": "G",
    "PENDING": "P",
    "ON_HOLD": "S",
    "NOT_SERVED": "N",
    "ACCEPTED": "A",
    "IN_PROGRESS": "E",
    "CANCELLED": "C",
    "FINISHED": "F",
    "GROUPED": "U",
}

RIDE_STATUSES = frozenset(_LABEL_TO_STATUS.values())

#: Ordem da leitura. Medido no alpha em 13/10/2026: ``/solicitacaoStatus``
#: devolveu 400 ``[67] O usuário informado não pode realizar essa operação.``
#: em toda batida da primeira corrida real, e o status ficou parado em D. As
#: outras duas vias leem a mesma corrida; a que responder vence e é lembrada.
READ_VIAS = ("details", "listing", "status")

_READ_VIA_CACHE_KEY = "courier:machine:read_via"


def _text(value) -> str:
    return "" if value in (None, "") else str(value).strip()


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_plus_seconds(iso: str, seconds: float | None) -> str:
    if not iso or seconds is None:
        return ""
    from datetime import timedelta

    from django.utils.dateparse import parse_datetime

    moment = parse_datetime(iso.replace("Z", "+00:00")) if isinstance(iso, str) else None
    if moment is None:
        return ""
    return (moment + timedelta(seconds=seconds)).isoformat()


def _status_letter(*candidates) -> str:
    for candidate in candidates:
        code = _text(candidate).upper()
        if code in RIDE_STATUSES:
            return code
        if code in _LABEL_TO_STATUS:
            return _LABEL_TO_STATUS[code]
    return ""


def _driver(name, phone, plate, model, color="") -> dict | None:
    driver = {
        "name": _text(name),
        "phone": _text(phone),
        "vehicle_plate": _text(plate),
        "vehicle_model": _text(model),
        "vehicle_color": _text(color),
    }
    return driver if driver["name"] else None


def snapshot_from_details(payload: dict) -> dict:
    """``GET /v1/request/{id}`` → a leitura normalizada da corrida.

    ``progress.accept_eta_seconds`` é o "tempo até o local de coleta" do painel
    da TaOn no aceite; ``pickup_arrival`` é a chegada à loja;
    ``start_trip`` é a coleta; ``estimated_duration_minutes`` é a viagem.
    """
    payload = payload if isinstance(payload, dict) else {}
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    finished = payload.get("finished") if isinstance(payload.get("finished"), dict) else {}
    raw_driver = payload.get("driver") if isinstance(payload.get("driver"), dict) else {}
    cancellations = [c for c in payload.get("cancellation") or [] if isinstance(c, dict)]

    status = _status_letter(payload.get("short_code"), payload.get("full_code"))
    if not status:
        # Código de evento (chegada, parada) no lugar do estado: o progresso diz qual é.
        if _text(finished.get("finished_at")):
            status = "F"
        elif cancellations:
            status = "C"
        elif _text(progress.get("start_trip")):
            status = "E"
        elif _text(progress.get("accepted_at")):
            status = "A"

    accepted_at = _text(progress.get("accepted_at"))
    eta_seconds = _number(progress.get("accept_eta_seconds"))
    final_value = finished.get("final_value")
    cancelled = cancellations[-1] if cancellations else {}
    return {
        "status": status,
        "driver": _driver(raw_driver.get("name"), raw_driver.get("phone"),
                          raw_driver.get("vehicle_plate"), raw_driver.get("vehicle_model")),
        "progress": {
            "accepted_at": accepted_at,
            "pickup_eta_at": _iso_plus_seconds(accepted_at, eta_seconds),
            "pickup_eta_minutes": round(eta_seconds / 60) if eta_seconds is not None else None,
            "pickup_km": _number(progress.get("accept_eta_km")),
            "near_pickup_at": _text(progress.get("arrival_at_surroundings")),
            "arrived_pickup_at": _text(progress.get("pickup_arrival")),
            "picked_up_at": _text(progress.get("start_trip")),
            "trip_minutes": _number(progress.get("estimated_duration_minutes")),
            "trip_km": _number(progress.get("estimated_distance_km")),
            "finished_at": _text(finished.get("finished_at")),
            "cancelled_at": _text(cancelled.get("cancelled_at")),
            "cancelled_reason": _text(cancelled.get("cancelled_reason")),
        },
        "final_value_q": _to_q(final_value) if final_value not in (None, "") else None,
    }


def snapshot_from_listing(row: dict) -> dict:
    """Uma linha de ``GET /solicitacao?id=`` → a mesma leitura normalizada.

    A listagem não traz a estimativa de chegada à coleta; traz o aceite, a
    chegada ao local, o início, o entregador e o valor.
    """
    row = row if isinstance(row, dict) else {}
    final = row.get("valor_corrida")
    finished_at = _text(row.get("data_hora_finalizacao_utc"))
    return {
        "status": _status_letter(row.get("status_solicitacao")),
        "driver": _driver(row.get("nome_condutor"), row.get("telefone_condutor"),
                          row.get("placa_veiculo"), row.get("veiculo"), row.get("cor_veiculo")),
        "progress": {
            "accepted_at": _text(row.get("data_hora_aceite_utc")),
            "pickup_eta_at": "",
            "pickup_eta_minutes": None,
            "pickup_km": _number(row.get("distancia_coleta_km")),
            "near_pickup_at": "",
            "arrived_pickup_at": _text(row.get("data_hora_chegada_local_utc")),
            "picked_up_at": _text(row.get("data_hora_inicio")),
            "trip_minutes": None,
            "trip_km": None,
            "finished_at": finished_at,
            "cancelled_at": _text(row.get("data_hora_cancelamento_utc")),
            "cancelled_reason": "",
        },
        "final_value_q": _to_q(final) if finished_at and final not in (None, "") else None,
    }


def _read_via(via: str, courier_ref: str) -> dict:
    if via == "details":
        return snapshot_from_details(get_details(courier_ref))
    if via == "listing":
        rows = _request("GET", "/solicitacao", params={"id": courier_ref})
        rows = rows if isinstance(rows, list) else [rows]
        row = next((r for r in rows if isinstance(r, dict) and _text(r.get("id")) == str(courier_ref)), None)
        if row is None:
            raise CourierError(f"A listagem não trouxe a corrida {courier_ref}", transient=False)
        return snapshot_from_listing(row)
    return {"status": _status_letter(get_status(courier_ref)), "driver": None, "progress": {}, "final_value_q": None}


def read_ride(courier_ref: str) -> dict:
    """Lê a corrida pela primeira via que responder (só GET).

    Devolve ``{status, driver, progress, final_value_q, via}``; ``{}`` quando
    inerte. Levanta :class:`CourierError` só quando as três vias falham, com o
    erro de cada uma: é esse fato que o polling mostra ao operador.
    """
    if _inert():
        return {}
    from django.core.cache import cache

    preferred = cache.get(_READ_VIA_CACHE_KEY)
    order = [preferred, *[v for v in READ_VIAS if v != preferred]] if preferred in READ_VIAS else list(READ_VIAS)
    errors: list[CourierError] = []
    for via in order:
        try:
            snapshot = _read_via(via, courier_ref)
        except CourierError as exc:
            errors.append(exc)
            continue
        if not snapshot.get("status"):
            errors.append(CourierError(f"{via}: resposta sem status", transient=False))
            continue
        cache.set(_READ_VIA_CACHE_KEY, via, 3600)
        if errors:
            logger.warning("courier.read_fallback id_mch=%s via=%s antes=%s", courier_ref, via,
                           " | ".join(str(e) for e in errors))
        return {**snapshot, "via": via}
    raise CourierError(
        " | ".join(str(e) for e in errors) or "Nenhuma leitura da corrida respondeu.",
        transient=any(e.transient for e in errors),
    )


def get_position(courier_ref: str) -> dict | None:
    """Posição do entregador (GET /posicaoCondutor). None fora da fase ativa."""
    if _inert():
        return None
    response = _request("GET", "/posicaoCondutor", params={"id_mch": courier_ref})
    lat, lng = response.get("lat_condutor"), response.get("lng_condutor")
    if lat is None or lng is None:
        return None
    return {"lat": float(lat), "lng": float(lng)}


def cancel(courier_ref: str, *, reason_id: int | None = None) -> bool:
    """Cancela a corrida (POST /cancelar). Só antes de F/N/C."""
    if _inert():
        return True
    _request(
        "POST",
        "/cancelar",
        json_body={
            "id_mch": courier_ref,
            "motivo_id": reason_id if reason_id is not None else int(_cfg().get("cancel_reason_id") or 1),
        },
    )
    return True


def tracking_links(courier_ref: str) -> list[dict]:
    """Links de rastreio por parada (GET /obterLinkRastreio/:id).

    Retorna ``[{parada_id, link_rastreio, codigo_confirmacao}]`` (lista vazia
    se inerte ou indisponível). O OpenAPI v1 de entregas documenta a resposta
    como um objeto só, ``{"link": ...}``; a coleção original trazia a lista por
    parada. Os dois formatos viram a mesma lista até a homologação dizer qual é.
    """
    if _inert():
        return []
    response = _request("GET", f"/obterLinkRastreio/{courier_ref}")
    if isinstance(response, dict) and response.get("link"):
        return [{"parada_id": "", "link_rastreio": str(response["link"]), "codigo_confirmacao": None}]
    return response if isinstance(response, list) else []


def list_webhooks() -> list[dict]:
    """Webhooks cadastrados (GET /listarWebhook, só leitura).

    Em 01/10/2026 a produção respondeu ``{"webhooks": [], "quantidade_webhooks": 0}``.
    """
    if _inert():
        return []
    response = _request("GET", "/listarWebhook")
    items = response.get("webhooks") if isinstance(response, dict) else response
    return [item for item in (items or []) if isinstance(item, dict)]


def register_webhook(url: str, *, kind: str) -> bool:
    """Cadastra a URL de webhook na Machine (POST /cadastrarWebhook).

    ``kind``: "status" ou "posicao". Usado só na homologação, via
    ``manage.py machine_register_webhook``.
    """
    if kind not in ("status", "posicao"):
        raise ValueError(f"kind inválido: {kind!r} (use 'status' ou 'posicao')")
    _request(
        "POST",
        "/cadastrarWebhook",
        json_body={"tipo": kind, "url": url, "responsabilidade": "solicitante"},
    )
    return True
