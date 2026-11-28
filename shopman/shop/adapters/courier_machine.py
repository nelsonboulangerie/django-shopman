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

from shopman.shop.protocols import DeliveryCapabilities, RideState

logger = logging.getLogger(__name__)

#: Letras de status terminais — a corrida não muda mais depois delas.
TERMINAL_STATUSES = frozenset({"F", "N", "C"})

#: Fases em que a corrida ainda pode ser cancelada (antes da coleta). O ``T``
#: (a central trocando de entregador) é procura, como o ``D``.
CANCELLABLE_STATUSES = frozenset({"D", "G", "P", "T", "A", "S"})

# ── Motivo do cancelamento, por fase ────────────────────────────────
#
# ``POST /cancelar`` exige ``motivo_id``, e o motivo aceito depende da letra da
# corrida (OpenAPI v1 da TaOn, usuário de empresa): antes do aceite só o 10;
# depois do aceite, a lista abaixo; fora disso a central devolve o erro 102.
# Um motivo fixo por deployment fazia o cancelamento antes do aceite falhar
# sempre (issue #2463): o motivo é da fase, não da configuração.

#: Letras em que ninguém aceitou a corrida ainda.
BEFORE_ACCEPT_STATUSES = frozenset({"D", "T", "P", "G"})

#: O único motivo que a central aceita antes do aceite.
CANCEL_REASON_BEFORE_ACCEPT = 10

#: Os motivos que a central aceita depois do aceite (``A``/``S``).
CANCEL_REASONS_AFTER_ACCEPT = frozenset({1, 2, 6, 12, 18, *range(32, 42)})

#: O que o operador escolhe na confirmação, depois do aceite (os rótulos moram
#: na projeção, ``order_queue.COURIER_CANCEL_REASONS``): 12 o entregador não
#: está vindo, 37 está demorando demais, 40 não consegui falar com o entregador.
CANCEL_REASON_OPERATOR_DEFAULT = 12
CANCEL_REASONS_OPERATOR = (12, 37, 40)

#: O pedido foi cancelado pela casa e a corrida já tinha entregador.
CANCEL_REASON_ORDER_CANCELLED = 33

#: Código de erro da central para "este motivo não vale nesta fase".
CANCEL_REASON_REFUSED_CODE = 102

#: Quem pede o cancelamento, quando não é o operador escolhendo um motivo.
CANCEL_INTENT_OPERATOR = "operator"
CANCEL_INTENT_ORDER_CANCELLED = "order_cancelled"


def cancel_reason_for(status: str, intent=CANCEL_INTENT_OPERATOR) -> int:
    """O ``motivo_id`` que a central aceita para cancelar a corrida nesta letra.

    ``intent`` é o motivo escolhido pelo operador (inteiro da lista de depois do
    aceite) ou quem pede (``"operator"``, ``"order_cancelled"``). Antes do
    aceite a escolha não importa: a central só aceita o 10.
    """
    if (status or "").strip().upper() in BEFORE_ACCEPT_STATUSES:
        return CANCEL_REASON_BEFORE_ACCEPT
    if type(intent) is int and intent in CANCEL_REASONS_AFTER_ACCEPT:
        return intent
    if intent == CANCEL_INTENT_ORDER_CANCELLED:
        return CANCEL_REASON_ORDER_CANCELLED
    return CANCEL_REASON_OPERATOR_DEFAULT

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

    def __init__(self, message: str, *, transient: bool, outcome_unknown: bool | None = None,
                 codes: tuple[int, ...] = ()):
        super().__init__(message)
        self.transient = transient
        self.outcome_unknown = transient if outcome_unknown is None else outcome_unknown
        #: Os códigos de erro que a central devolveu no envelope (``errors[].code``).
        self.codes = tuple(codes)


#: Espera quando a TaOn limita as chamadas (HTTP 429) e não diz por quanto tempo.
RATE_LIMIT_DEFAULT_SECONDS = 30

#: Teto da espera pedida pela TaOn: um ``Retry-After`` absurdo não some com a corrida.
RATE_LIMIT_MAX_SECONDS = 300


class CourierRateLimited(CourierError):
    """A TaOn limitou as chamadas (HTTP 429): a chamada NÃO foi aplicada.

    Transitório e de resultado conhecido (nada aconteceu do lado de lá): quem
    chama espera ``retry_after`` segundos e tenta de novo. Não é falha de
    leitura nem de despacho, e por isso não vira aviso ao operador.
    """

    def __init__(self, message: str, *, retry_after: int):
        super().__init__(message, transient=True, outcome_unknown=False)
        self.retry_after = retry_after


def _retry_after_seconds(value) -> int:
    """``Retry-After`` em segundos (número ou data HTTP), dentro do teto."""
    text = str(value or "").strip()
    seconds: float | None = None
    try:
        seconds = float(text)
    except ValueError:
        from datetime import UTC
        from email.utils import parsedate_to_datetime

        from django.utils import timezone

        try:
            moment = parsedate_to_datetime(text) if text else None
        except (TypeError, ValueError):
            moment = None
        if moment is not None:
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
            seconds = (moment - timezone.now()).total_seconds()
    if seconds is None or seconds != seconds:  # sem cabeçalho, ilegível ou NaN
        return RATE_LIMIT_DEFAULT_SECONDS
    return int(min(max(seconds, 1), RATE_LIMIT_MAX_SECONDS))


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


def _error_codes(errors) -> tuple[int, ...]:
    codes = []
    for error in errors if isinstance(errors, list) else []:
        try:
            codes.append(int(error.get("code")))
        except (AttributeError, TypeError, ValueError):
            continue
    return tuple(codes)


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

    if resp.status_code == 429:
        retry_after = _retry_after_seconds(resp.headers.get("Retry-After"))
        logger.warning(
            "courier.rate_limited path=%s retry_after=%s remaining=%s reset=%s",
            path, retry_after, resp.headers.get("X-RateLimit-Remaining"), resp.headers.get("X-RateLimit-Reset"),
        )
        raise CourierRateLimited(
            f"A TaOn limitou as chamadas (HTTP 429). Nova tentativa em {retry_after} s.", retry_after=retry_after,
        )

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
        raise CourierError(f"Machine recusou ({resp.status_code}): {detail}", transient=False,
                           codes=_error_codes(errors))

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


def estimate(*, pickup: dict, dropoff: dict, with_return: bool = False,
             stops: list[dict] | None = None) -> CourierEstimate | None:
    """Cota a corrida (GET /estimarSolicitacao).

    ``pickup``/``dropoff``: dicts com ``lat``/``lng`` e o endereço
    (``street``, ``neighborhood``, ``city``, ``state``), que a API de entregas
    exige. ``with_return``: a corrida volta à loja (``com_retorno``), o mesmo
    ``retorno`` que a abertura vai pedir. ``stops``: as paradas ANTES do
    destino, na ordem do percurso (``lat``/``lng``), para a corrida com várias
    entregas (``latlng_paradas``: "lat,lng|lat,lng"; o separador entre latitude
    e longitude não está na documentação e espera a homologação). Retorna None
    quando inerte ou sem coordenadas: a cotação é sempre best-effort.
    """
    if _inert():
        return None
    if not all([pickup.get("lat"), pickup.get("lng"), dropoff.get("lat"), dropoff.get("lng")]):
        return None
    params = {**_estimate_params(pickup, "partida"), **_estimate_params(dropoff, "desejado")}
    if with_return:
        params["com_retorno"] = "true"
    if stops:
        params["latlng_paradas"] = "|".join(f"{stop['lat']},{stop['lng']}" for stop in stops)
    response = _request("GET", "/estimarSolicitacao", params=params)
    return CourierEstimate(
        value_q=_to_q(response.get("estimativa_valor")),
        minutes=float(response.get("estimativa_minutos") or 0),
        km=float(response.get("estimativa_km") or 0),
    )


def dispatch(payload: dict) -> CourierDispatchResult:
    """Abre a corrida (POST /abrirSolicitacao). Retorna o identificador da corrida.

    A TaOn o chama ``id_mch`` (campo dela, que só vive aqui); dentro da casa ele é o
    ``ride_ref`` do bloco ``courier``.

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

#: O que a TaOn sabe fazer (DEV-2026-030, contrato em ``shopman.shop.protocols``).
CAPABILITIES = DeliveryCapabilities(
    quote=True,
    multi_stop=4,
    cancel_reasons=True,
    customer_tracking=True,
    push_status=True,
    door_charge=True,
    needs_return=True,
    assign=False,
)

#: Letra da TaOn → estado da casa. A letra crua continua no bloco (``status``); este é o
#: vocabulário que serve a qualquer serviço. ``S`` (em espera) é corrida aceita, ainda
#: sem coleta.
RIDE_STATES: dict[str, RideState] = {
    "D": RideState.SEARCHING,
    "G": RideState.SEARCHING,
    "P": RideState.SEARCHING,
    "U": RideState.GROUPED,
    "T": RideState.REASSIGNING,
    "A": RideState.ASSIGNED,
    "S": RideState.ASSIGNED,
    "E": RideState.ON_ROUTE,
    "F": RideState.DONE,
    "N": RideState.NOT_SERVED,
    "C": RideState.CANCELLED,
}


def ride_state(status: str) -> RideState | None:
    """O estado da casa para a letra da TaOn, ou None para letra desconhecida."""
    return RIDE_STATES.get(str(status or "").strip().upper())


#: O que a letra diz a mais que o estado da casa: ``G`` ainda procura, mas já ofereceu
#: a corrida a alguém; ``S`` já aceitou, mas termina outra entrega antes de vir. "Na
#: loja" é a chegada (``progress.arrived_pickup_at``), não o ``S``.
STATUS_DETAILS: dict[str, str] = {
    "G": "Aguardando aceite",
    "S": "Entregador vem após outra entrega",
}


def status_detail(status: str) -> str:
    """A nuance da letra da TaOn sobre o estado da casa, ou ""."""
    return STATUS_DETAILS.get(str(status or "").strip().upper(), "")

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


def driver_from(payload: dict) -> dict | None:
    """O entregador de um corpo da TaOn (aviso de aceite ou ``GET /request/{id}``).

    A doc manda o veículo à parte, em ``vehicle{model, color, vehicle_plate}``; o
    ``driver`` traz nome e telefone. Antes só se lia ``driver.vehicle_*``, que a
    TaOn não manda, e a placa e a cor se perdiam (revisão das Entregas, TAON-14).
    ``driver.vehicle_*`` segue como segunda via.
    """
    payload = payload if isinstance(payload, dict) else {}
    raw = payload.get("driver") if isinstance(payload.get("driver"), dict) else {}
    vehicle = payload.get("vehicle") if isinstance(payload.get("vehicle"), dict) else {}
    if not vehicle and isinstance(raw.get("vehicle"), dict):
        vehicle = raw["vehicle"]
    return _driver(
        raw.get("name"),
        raw.get("phone"),
        vehicle.get("vehicle_plate") or vehicle.get("plate") or raw.get("vehicle_plate"),
        vehicle.get("model") or raw.get("vehicle_model"),
        vehicle.get("color") or raw.get("vehicle_color"),
    )


def driver_photo_url(payload: dict) -> str:
    """O endereço da foto do entregador no corpo da TaOn (só ``https``), ou vazio."""
    payload = payload if isinstance(payload, dict) else {}
    raw = payload.get("driver") if isinstance(payload.get("driver"), dict) else {}
    url = _text(raw.get("photo_url") or payload.get("photo_url"))
    return url if url.startswith("https://") else ""


def snapshot_from_details(payload: dict) -> dict:
    """``GET /v1/request/{id}`` → a leitura normalizada da corrida.

    ``progress.accept_eta_seconds`` é o "tempo até o local de coleta" do painel
    da TaOn no aceite; ``pickup_arrival`` é a chegada à loja;
    ``start_trip`` é a coleta; ``estimated_duration_minutes`` é a viagem.
    """
    payload = payload if isinstance(payload, dict) else {}
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    finished = payload.get("finished") if isinstance(payload.get("finished"), dict) else {}
    cancellations = [c for c in payload.get("cancellation") or [] if isinstance(c, dict)]

    status = _status_letter(payload.get("short_code"), payload.get("full_code"))
    if not status:
        # Código de evento (chegada, parada) no lugar do estado: o progresso diz qual é.
        # ``cancellation[]`` NÃO prova corrida cancelada: a desistência de um
        # entregador entra ali e a TaOn segue procurando outro. Cancelada, só
        # quando a letra lida é C. E com desistência na lista o aceite do
        # andamento pode ser de quem saiu: sem letra, outra via responde.
        if _text(finished.get("finished_at")):
            status = "F"
        elif _text(progress.get("start_trip")):
            status = "E"
        elif _text(progress.get("accepted_at")) and not cancellations:
            status = "A"

    accepted_at = _text(progress.get("accepted_at"))
    eta_seconds = _number(progress.get("accept_eta_seconds"))
    final_value = finished.get("final_value")
    cancelled = cancellations[-1] if cancellations else {}
    return {
        "status": status,
        "driver": driver_from(payload),
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
        except CourierRateLimited:
            # Sob limite, tentar as outras vias só gasta mais cota: quem lê espera.
            raise
        except CourierError as exc:
            errors.append(exc)
            continue
        if not snapshot.get("status"):
            errors.append(CourierError(f"{via}: resposta sem status", transient=False))
            continue
        cache.set(_READ_VIA_CACHE_KEY, via, 3600)
        if errors:
            logger.warning("courier.read_fallback ride_ref=%s via=%s antes=%s", courier_ref, via,
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


def cancel(courier_ref: str, *, reason_id: int) -> bool:
    """Cancela a corrida (POST /cancelar). Só antes de F/N/C.

    ``reason_id`` é obrigatório e depende da letra da corrida
    (:func:`cancel_reason_for`); com o motivo da fase errada a central devolve
    o erro 102, que sobe em ``CourierError.codes``.
    """
    if _inert():
        return True
    _request("POST", "/cancelar", json_body={"id_mch": courier_ref, "motivo_id": int(reason_id)})
    return True


def tracking_links(courier_ref: str) -> list[dict]:
    """Links de rastreio por parada (GET /obterLinkRastreio/:id).

    Retorna ``[{parada_id, link_rastreio, codigo_confirmacao}]`` (lista vazia
    se inerte ou indisponível). O OpenAPI v1 de entregas documenta a resposta
    como um objeto só, ``{"link": ...}``; a coleção original trazia a lista por
    parada. O objeto único vira UMA entrada sem ``parada_id``: serve à corrida de
    um pedido e, numa corrida com várias paradas, não casa com nenhum
    (``courier.link_for_order``, falha fechada) até a homologação dizer qual é.
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
