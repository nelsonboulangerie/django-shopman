"""Machine webhook — push de status/posição das corridas de entrega.

Cadastrado na Machine via ``manage.py machine_register_webhook`` (tipos
``status`` e ``posicao``, responsabilidade ``solicitante``). Autenticação por
token compartilhado (``SHOPMAN_MACHINE["webhook_token"]``) no header
``X-Machine-Webhook-Token`` ou no query param ``?token=`` — a URL cadastrada
na Machine leva o token no query param. Token ausente/errado → 401 fail-closed
em qualquer ambiente (mesmo contrato do EFI, ver ``efi.py``).

Payload documentado em docs.machine.global (v1, entregas, "Webhooks > Sobre"):

- **status** (um POST por evento): ``{datetime, event_id, company_id,
  request_id, status_code, status_label, stop_id?, will_reopen?, links{request,
  driver?, enterprise?}}``. ``status_code`` traz a letra da corrida
  (D/G/P/S/N/A/E/C/F/U) ou um evento que não é estado: ``AP`` (chegou ao local),
  ``AN`` (nas redondezas), ``AW`` (esperando no local), ``T`` (trocando de
  entregador), ``ER`` (parada finalizada), ``L`` (aguardando liberação), ``R``
  (aguardando pagamento). Só a letra de estado entra no funil; AP/AN/AW gravam
  o andamento e T reabre a mesma corrida; o resto é aceito e logado.
- **will_reopen** (seção "Campo will_reopen" da doc): no ``C`` em que o
  entregador desistiu, ``true`` diz que a TaOn vai redistribuir a MESMA corrida:
  "não abra outra solicitação". Aqui o ``C`` não cancela nada
  (``courier.record_reopen``): a corrida segue chamada, sem entregador.
- **posicao** (lote a cada 10 s, sem reenvio): ``{event_id, datetime,
  data: [{timestamp, company_id, request_id, driver_id,
  coordinates{latitude, longitude}}]}``, até 500 itens por POST.
- O formato antigo (``id_mch``/``status_solicitacao`` e ``id_mch``/
  ``lat_cond``/``lng_cond``) está DEPRECADO na doc, mas continua aceito.

Além do token, todo POST tem de trazer o header ``Signature-V2``: HMAC-SHA-512
do corpo cru inteiro, com a chave da API. A doc não diz a codificação: aceita
hexadecimal (o exemplo da doc) e base64 (o que a produção mandou em 19/11, com
caracteres fora do hexadecimal), sempre a mesma conta com a mesma chave
(``SHOPMAN_MACHINE["api_key"]``, env ``MACHINE_API_KEY``), conferido em tempo
constante. Assinatura ausente ou que não confere → 401. Chave da API vazia →
401 em TODO POST, com log de erro e alerta ao operador (falha fechada e
gritando: nunca aceitar sem conferir). O ``GET`` de verificação do cadastro não
tem corpo e fica só no token. O polling (``courier.sync``) segue como via
garantida. Payload não reconhecido → 202 (nada é perdido: o polling converge).

**O corpo cru nunca vai para o log.** Ele traz dado pessoal do entregador
(nome, telefone, CPF, ``pix_key``, ``photo_url``, que a doc da TaOn manda não
logar) e a posição dele a cada 10 s. O log é de lista fechada, depois da
assinatura conferida: os ids, a letra, ``event_id``, ``stop_id``,
``will_reopen``, o tamanho e o começo do SHA-256 do corpo; do formato
desconhecido, só os nomes das chaves. Assinatura que não confere loga o mesmo
resumo do corpo e os 8 primeiros caracteres da assinatura recebida (o bastante
para ver se a conta da TaOn é outra, sem guardar o corpo).

Status converge no funil ``courier.apply_status``: a mesma letra de novo é
no-op e a letra fora de ordem é recusada (``stale``). A idempotência é pelo
``event_id`` do aviso: dois avisos com a mesma letra (o aceite do segundo
entregador, depois de uma desistência) são dois fatos. Só o formato deprecado,
sem ``event_id``, cai na chave antiga (corrida + letra). Posição não toca o
Order: vai para ``courier_position.store_position``, com a hora da posição
(``timestamp`` do item do lote) e a via ``webhook``, lida pela projection do
Gestor.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import courier_position, webhook_idempotency

logger = logging.getLogger(__name__)

#: Chaves do id da corrida: ``request_id`` no formato documentado atual,
#: ``id_mch`` no deprecado; as demais são tolerância.
_ID_KEYS = ("id_mch", "id", "solicitacao_id", "id_solicitacao", "request_id")

#: Chaves do status: ``status_code`` no formato atual, ``status_solicitacao``
#: no deprecado.
_STATUS_KEYS = ("status", "status_solicitacao", "status_code", "situacao")

#: Letras que são ESTADO da corrida. ``AP``/``ER``/``L``/``R`` chegam pelo
#: mesmo webhook mas são eventos (chegada, parada, liberação, pagamento):
#: gravá-los como status apagaria a letra verdadeira.
_RIDE_STATUSES = frozenset({"D", "G", "P", "S", "N", "A", "E", "C", "F", "U"})

#: Header da assinatura documentada (``Signature`` é o antigo, deprecado).
SIGNATURE_HEADER = "HTTP_SIGNATURE_V2"


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_MACHINE", {}) or {}


@extend_schema(exclude=True)
class MachineWebhookView(APIView):
    """Endpoint para eventos de corrida (status/posição) da Machine."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        # Health probe do cadastro; a autenticação vale igual.
        if not self._check_auth(request):
            return Response({"error": "Unauthorized"}, status=http.HTTP_401_UNAUTHORIZED)
        return Response(status=http.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        if not self._check_auth(request):
            return Response({"error": "Unauthorized"}, status=http.HTTP_401_UNAUTHORIZED)
        body = request.body if isinstance(request.body, bytes) else b""
        if not _check_signature(request, body):
            return Response({"error": "Unauthorized"}, status=http.HTTP_401_UNAUTHORIZED)

        event = request.data if isinstance(request.data, dict) else {}
        if isinstance(event.get("data"), list):
            # Lote de posição (formato documentado atual).
            stored = sum(_store_batch_item(item) for item in event["data"] if isinstance(item, dict))
            logger.info("machine.webhook kind=position_batch items=%d stored=%d %s",
                        len(event["data"]), stored, _body_digest(body))
            return Response(
                {"status": "ok", "kind": "position_batch", "positions": stored},
                status=http.HTTP_200_OK,
            )

        ride_ref = _first(event, _ID_KEYS)
        if not ride_ref:
            # Formato desconhecido: aceito (202) + logado (só os nomes das
            # chaves, nunca os valores); o polling converge.
            logger.info("machine.webhook kind=unrecognized keys=%s %s",
                        ",".join(sorted(str(key) for key in event)[:40]), _body_digest(body))
            return Response({"status": "unrecognized"}, status=http.HTTP_202_ACCEPTED)

        lat = _first(event, ("lat", "lat_condutor", "lat_cond"))
        lng = _first(event, ("lng", "lng_condutor", "lng_cond"))
        if lat and lng:
            courier_position.store_position(ride_ref, lat, lng, source=courier_position.SOURCE_WEBHOOK,
                                            at=_first(event, ("datetime",)) or None)

        ride_status = _first(event, _STATUS_KEYS).upper()
        if not ride_status:
            # Evento só de posição: gravada acima, nada mais a fazer.
            return Response({"status": "ok", "kind": "position"}, status=http.HTTP_200_OK)
        event_id = _first(event, ("event_id",))
        will_reopen = _truthy(event.get("will_reopen"))
        at = _first(event, ("datetime",)) or None
        logger.info(
            "machine.webhook kind=status request=%s code=%s event=%s stop=%s will_reopen=%s company=%s %s",
            ride_ref, ride_status, event_id or "-", _first(event, ("stop_id",)) or "-",
            "yes" if will_reopen else "no", _first(event, ("company_id",)) or "-", _body_digest(body),
        )
        from shopman.orderman.models import Order

        if ride_status not in _RIDE_STATUSES:
            # Chegada ao local, parada finalizada etc.: não é a letra da corrida.
            # A chegada (AP) entra no progresso (na loja antes da coleta, no
            # cliente depois) e pede uma leitura completa já.
            orders = list(Order.objects.filter(data__courier__ride_ref=str(ride_ref)).order_by("pk"))
            from shopman.shop.services import courier

            if orders and ride_status == "AP":
                for order in orders:
                    courier.record_arrival(order, at=at)
                courier.schedule_sync(orders[0], delay_seconds=0)
            elif orders and ride_status in courier.PICKUP_EVENTS:
                # Nas redondezas (AN) ou esperando na loja além do combinado (AW):
                # o relógio da espera no balcão conta daqui (TAON-12).
                for order in orders:
                    courier.record_pickup_event(order, ride_status, at=at)
            elif orders and ride_status == "T":
                # A TaOn está trocando o entregador: a MESMA corrida segue, sem
                # dono por um instante. Nunca é falha nem "chame de novo".
                for order in orders:
                    courier.record_reopen(order, at=at, source="webhook", reason=courier.REOPEN_TRANSFER)
                courier.schedule_sync(orders[0], delay_seconds=0)
            return Response({"status": "ok", "kind": "event", "code": ride_status}, status=http.HTTP_200_OK)

        from shopman.shop.adapters.courier_machine import TERMINAL_STATUSES
        from shopman.shop.services import courier

        # Corrida com várias paradas: o mesmo id em cada pedido dela.
        orders = list(Order.objects.filter(data__courier__ride_ref=str(ride_ref)).order_by("pk"))
        # Corrida que consta como encerrada (N/C) e dá sinal de vida: a TaOn
        # retomou a mesma corrida (uma desistência que virou "cancelada" aqui).
        archived = [] if orders or ride_status in TERMINAL_STATUSES else courier.orders_with_archived_ride(str(ride_ref))
        if not orders and not archived:
            logger.warning("machine.webhook: corrida sem pedido ride_ref=%s", ride_ref)
            return Response({"status": "ok", "kind": "unknown_ride"}, status=http.HTTP_200_OK)

        # Um aviso é um fato (``event_id``). A chave antiga (corrida + letra)
        # descartava como repetição o aceite do segundo entregador.
        claim = webhook_idempotency.claim(
            "webhook:machine",
            webhook_idempotency.stable_webhook_key("event", event_id) if event_id
            else webhook_idempotency.stable_webhook_key(ride_ref, ride_status),
        )
        if claim.replayed:
            # Repetição não reaplica, mas pede a leitura completa: se o primeiro
            # envio se perdeu no meio, a batida converge agora, não em 1 min.
            if orders:
                courier.schedule_sync(orders[0], delay_seconds=0)
            return Response({"status": "ok", "kind": "replay"}, status=http.HTTP_200_OK)
        if claim.in_progress:
            return Response(claim.response_body, status=http.HTTP_409_CONFLICT)

        try:
            kind = "status"
            if archived:
                orders, kind = _revive_archived(archived, str(ride_ref), ride_status, at=at)
            if kind == "status" and ride_status == "C" and will_reopen:
                # O entregador desistiu e a TaOn redistribui a mesma corrida:
                # nada de cancelar, arquivar ou chamar de novo.
                outcomes = [courier.record_reopen(order, at=at, source="webhook") for order in orders]
                kind = "stale" if outcomes and all(outcome == "stale" for outcome in outcomes) else "reopened"
            elif kind in ("status", "restored"):
                details = event
                if len(orders) > 1 and ride_status in ("A", "F"):
                    # Corrida com várias paradas: os detalhes (entregador, valor final)
                    # vêm da central UMA vez, não uma consulta por pedido.
                    from shopman.shop.services import delivery_services

                    adapter = delivery_services.courier_backend()
                    try:
                        details = {**event, **(adapter.get_details(str(ride_ref)) if adapter else {})}
                    except Exception:  # silêncio-deliberado: cada pedido busca sozinho, como antes
                        logger.warning("machine.webhook: detalhes da corrida ride_ref=%s", ride_ref, exc_info=True)
                outcomes = [courier.apply_status(order, ride_status, source="webhook", details=details, at=at)
                            for order in orders]
                if kind == "status" and outcomes and all(outcome == "stale" for outcome in outcomes):
                    # Letra fora de ordem (um aceite atrasado depois da coleta):
                    # recusada, e o 200 evita a reentrega de algo que não muda nada.
                    kind = "stale"
            if orders:
                # O aviso traz só a letra; a leitura completa (entregador, previsão
                # de chegada, coleta, viagem) vem da batida, agora, não daqui a 1 min.
                courier.schedule_sync(orders[0], delay_seconds=0)
            webhook_idempotency.mark_done(
                claim,
                response_body={"status": "processed", "ride_ref": str(ride_ref), "ride_status": ride_status, "kind": kind},
            )
        except Exception as exc:
            logger.exception("MachineWebhook: error processing ride_ref=%s", ride_ref)
            webhook_idempotency.mark_failed(claim)
            from shopman.shop.services import observability

            observability.record_webhook_failure(
                provider="machine",
                reason="processing_failed",
                status_code=http.HTTP_500_INTERNAL_SERVER_ERROR,
                external_ref=str(ride_ref),
                exc=exc,
                context={"ride_ref": str(ride_ref), "ride_status": ride_status},
            )
            # 5xx → a Machine (se reentregar) tenta de novo; o polling cobre se não.
            return Response({"status": "retry"}, status=http.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": "ok", "kind": kind}, status=http.HTTP_200_OK)

    def _check_auth(self, request: Request) -> bool:
        expected = _cfg().get("webhook_token") or ""
        if not expected:
            logger.error(
                "MachineWebhook: SHOPMAN_MACHINE['webhook_token'] não configurado — "
                "rejeitando. Defina MACHINE_WEBHOOK_TOKEN (inclusive em dev)."
            )
            return False
        token = request.META.get("HTTP_X_MACHINE_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")
        if not token:
            logger.warning("MachineWebhook: token ausente — rejeitando")
            return False
        if not hmac.compare_digest(token, expected):
            logger.warning("MachineWebhook: token não confere — rejeitando")
            return False
        return True


def signature_for(body: bytes, key: str) -> str:
    """``Signature-V2`` esperada: HMAC-SHA-512 do corpo cru, em hexadecimal."""
    return hmac.new(key.encode("utf-8"), body, hashlib.sha512).hexdigest()


def _check_signature(request: Request, body: bytes) -> bool:
    """Confere ``Signature-V2`` contra o corpo cru. Falha fechada sempre."""
    key = _cfg().get("api_key") or ""
    if not key:
        # Sem a chave não há como conferir: rejeita e grita (log + alerta).
        logger.error(
            "MachineWebhook: SHOPMAN_MACHINE['api_key'] não configurado; sem ela a "
            "Signature-V2 não pode ser conferida e todo POST é rejeitado. "
            "Defina MACHINE_API_KEY."
        )
        _alert_signature_failure("signature_key_missing")
        return False
    received = (request.META.get(SIGNATURE_HEADER) or "").strip()
    if not received:
        logger.warning("MachineWebhook: Signature-V2 ausente, rejeitando %s", _body_digest(body))
        _alert_signature_failure("signature_missing")
        return False
    encoding = _signature_encoding(received, body, key)
    if not encoding:
        # O resumo do corpo e a forma da assinatura recebida (tamanho, alfabeto e
        # começo) dizem se a chave é outra ou se a codificação é outra; o corpo
        # cru não entra no log.
        logger.warning(
            "MachineWebhook: Signature-V2 não confere, rejeitando %s signature=%s... len=%d alphabet=%s",
            _body_digest(body), "".join(ch for ch in received[:8].lower() if ch in "0123456789abcdef"),
            len(received), _alphabet(received),
        )
        _alert_signature_failure("signature_mismatch")
        return False
    logger.info("machine.webhook signature=ok encoding=%s", encoding)
    return True


def _signature_encoding(received: str, body: bytes, key: str) -> str:
    """Qual codificação do HMAC-SHA-512 confere (``hex``/``base64``), ou ``""``.

    A conta é uma só (HMAC-SHA-512 do corpo cru com a chave da API); muda só a
    forma de escrever o resultado. Aceitar as duas não abre nada: sem a chave
    não se forja nenhuma. Prefixo ``sha512=`` é tolerado.
    """
    if received.lower().startswith("sha512="):
        received = received[7:]
    digest = hmac.new(key.encode("utf-8"), body, hashlib.sha512).digest()
    candidates = (
        ("hex", received.lower(), digest.hex()),
        ("base64", received, base64.b64encode(digest).decode("ascii")),
        ("base64url", received.rstrip("="), base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")),
    )
    matched = ""
    for name, got, expected in candidates:
        # Compara todas, sem sair cedo: o tempo não diz qual chegou perto.
        if hmac.compare_digest(got.encode("ascii", "replace"), expected.encode("ascii")) and not matched:
            matched = name
    return matched


def _alphabet(value: str) -> str:
    """O alfabeto da assinatura recebida, sem ela: diz a codificação no log."""
    if all(ch in "0123456789abcdefABCDEF" for ch in value):
        return "hex"
    if all(ch.isalnum() or ch in "+/=" for ch in value):
        return "base64"
    if all(ch.isalnum() or ch in "-_=" for ch in value):
        return "base64url"
    return "other"


def _body_digest(body: bytes) -> str:
    """O corpo, sem o corpo: tamanho e começo do SHA-256 (casa o log com o envio da TaOn)."""
    return f"size={len(body)} sha256={hashlib.sha256(body).hexdigest()[:12]}"


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "s", "sim", "yes"}
    return value is True or value == 1


def _revive_archived(archived: list, ride_ref: str, ride_status: str, *, at: str | None) -> tuple[list, str]:
    """Aviso de corrida viva para um id que consta como encerrado (N/C) no pedido.

    Só retoma com prova de que o aviso é mais novo que o encerramento: a hora
    do evento ou, sem ela, uma leitura da corrida na central que não esteja em
    letra final. Sem prova, é aviso atrasado (``stale``) e nada muda. Devolve os
    pedidos que voltaram a ter a corrida e o que aconteceu.
    """
    from shopman.shop.adapters.courier_machine import TERMINAL_STATUSES
    from shopman.shop.services import courier, delivery_services

    event_at = courier.provider_instant(at)
    ended = [courier.archived_ride_ended_at(order, ride_ref) for order in archived]
    proven = event_at is not None and all(moment is not None and event_at > moment for moment in ended)
    if not proven:
        adapter = delivery_services.courier_backend()
        read_ride = getattr(adapter, "read_ride", None) if adapter else None
        try:
            reading = read_ride(ride_ref) if read_ride else {}
        except Exception:  # silêncio-deliberado: sem leitura não há prova, e sem prova não retoma
            logger.warning("machine.webhook: leitura da corrida arquivada ride_ref=%s", ride_ref, exc_info=True)
            reading = {}
        letter = str(reading.get("status") or "")
        proven = bool(letter) and letter not in TERMINAL_STATUSES
    if not proven:
        logger.info("courier_status_ignored ride_ref=%s received=%s reason=archived_ride_without_proof", ride_ref, ride_status)
        return [], "stale"
    restored = [order for order in archived if courier.restore_archived_ride(order, ride_ref, source="webhook") == "restored"]
    for order in restored:
        order.refresh_from_db()
    return restored, "restored" if restored else "conflict"


def _alert_signature_failure(reason: str) -> None:
    """O token da URL bateu e a assinatura não: é config ou é vazamento do token."""
    from shopman.shop.services import observability

    try:
        observability.record_webhook_failure(
            provider="machine",
            reason=reason,
            status_code=http.HTTP_401_UNAUTHORIZED,
        )
    except Exception:
        logger.exception("MachineWebhook: falha ao registrar o alerta de assinatura (%s)", reason)


def _store_batch_item(item: dict) -> bool:
    """Um item do lote de posição: ``request_id`` + ``coordinates`` + ``timestamp``."""
    ride_ref = _first(item, ("request_id", "id_mch"))
    coordinates = item.get("coordinates") if isinstance(item.get("coordinates"), dict) else {}
    if not ride_ref:
        return False
    return courier_position.store_position(
        ride_ref, coordinates.get("latitude"), coordinates.get("longitude"),
        source=courier_position.SOURCE_WEBHOOK, at=item.get("timestamp"),
    )


def _first(event: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = event.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""
