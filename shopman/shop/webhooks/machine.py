"""Machine webhook — push de status/posição das corridas de entrega.

Cadastrado na Machine via ``manage.py machine_register_webhook`` (tipos
``status`` e ``posicao``, responsabilidade ``solicitante``). Autenticação por
token compartilhado (``SHOPMAN_MACHINE["webhook_token"]``) no header
``X-Machine-Webhook-Token`` ou no query param ``?token=`` — a URL cadastrada
na Machine leva o token no query param. Token ausente/errado → 401 fail-closed
em qualquer ambiente (mesmo contrato do EFI, ver ``efi.py``).

Payload documentado em docs.machine.global (v1, entregas, "Webhooks > Sobre"):

- **status** (um POST por evento): ``{datetime, event_id, company_id,
  request_id, status_code, status_label, stop_id?, links{request, driver?,
  enterprise?}}``. ``status_code`` traz a letra da corrida (D/G/P/S/N/A/E/C/F/U)
  ou um evento que não é estado: ``AP`` (chegou ao local), ``ER`` (parada
  finalizada), ``L`` (aguardando liberação), ``R`` (aguardando pagamento).
  Só a letra de estado entra no funil; o evento é aceito e logado.
- **posicao** (lote a cada 10 s, sem reenvio): ``{event_id, datetime,
  data: [{timestamp, company_id, request_id, driver_id,
  coordinates{latitude, longitude}}]}``, até 500 itens por POST.
- O formato antigo (``id_mch``/``status_solicitacao`` e ``id_mch``/
  ``lat_cond``/``lng_cond``) está DEPRECADO na doc, mas continua aceito.

A Machine assina com ``Signature-V2`` (HMAC-SHA-512 com a chave da API); esta
borda autentica pelo token na URL e ainda não confere a assinatura. O corpo cru
é SEMPRE logado e o polling (``courier.sync``) segue como via garantida.
Payload não reconhecido → 202 (nada é perdido: o polling converge).

Status converge no funil ``courier.apply_status`` (idempotente — replay do
mesmo status é no-op). Posição não toca o Order: vai para o cache
(``courier:pos:{id_mch}``, TTL 120s), lida pela projection do gestor.
"""

from __future__ import annotations

import hmac
import logging

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import webhook_idempotency

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

POSITION_CACHE_SECONDS = 120


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

        raw = request.body[:2000] if isinstance(request.body, bytes) else b""
        logger.info("machine.webhook raw=%s", raw.decode("utf-8", errors="replace"))

        event = request.data if isinstance(request.data, dict) else {}
        if isinstance(event.get("data"), list):
            # Lote de posição (formato documentado atual).
            stored = sum(_cache_position(item) for item in event["data"] if isinstance(item, dict))
            return Response(
                {"status": "ok", "kind": "position_batch", "positions": stored},
                status=http.HTTP_200_OK,
            )

        ride_ref = _first(event, _ID_KEYS)
        if not ride_ref:
            # Formato desconhecido: aceito (202) + logado; o polling converge.
            return Response({"status": "unrecognized"}, status=http.HTTP_202_ACCEPTED)

        lat = _first(event, ("lat", "lat_condutor", "lat_cond"))
        lng = _first(event, ("lng", "lng_condutor", "lng_cond"))
        if lat and lng:
            _store_position(ride_ref, lat, lng)

        ride_status = _first(event, _STATUS_KEYS).upper()
        if not ride_status:
            # Evento só de posição: cache atualizado acima, nada mais a fazer.
            return Response({"status": "ok", "kind": "position"}, status=http.HTTP_200_OK)
        if ride_status not in _RIDE_STATUSES:
            # Chegada ao local, parada finalizada etc.: fato registrado no log
            # acima, sem mexer na letra da corrida.
            return Response({"status": "ok", "kind": "event", "code": ride_status}, status=http.HTTP_200_OK)

        from shopman.orderman.models import Order

        order = Order.objects.filter(data__courier__id_mch=str(ride_ref)).first()
        if order is None:
            logger.warning("machine.webhook: corrida sem pedido id_mch=%s", ride_ref)
            return Response({"status": "ok", "kind": "unknown_ride"}, status=http.HTTP_200_OK)

        claim = webhook_idempotency.claim(
            "webhook:machine",
            webhook_idempotency.stable_webhook_key(ride_ref, ride_status),
        )
        if claim.replayed:
            return Response({"status": "ok", "kind": "replay"}, status=http.HTTP_200_OK)
        if claim.in_progress:
            return Response(claim.response_body, status=http.HTTP_409_CONFLICT)

        try:
            from shopman.shop.services import courier

            courier.apply_status(order, ride_status, source="webhook", details=event)
            webhook_idempotency.mark_done(
                claim,
                response_body={"status": "processed", "id_mch": str(ride_ref), "ride_status": ride_status},
            )
        except Exception as exc:
            logger.exception("MachineWebhook: error processing id_mch=%s", ride_ref)
            webhook_idempotency.mark_failed(claim)
            from shopman.shop.services import observability

            observability.record_webhook_failure(
                provider="machine",
                reason="processing_failed",
                status_code=http.HTTP_500_INTERNAL_SERVER_ERROR,
                external_ref=str(ride_ref),
                exc=exc,
                context={"id_mch": str(ride_ref), "ride_status": ride_status},
            )
            # 5xx → a Machine (se reentregar) tenta de novo; o polling cobre se não.
            return Response({"status": "retry"}, status=http.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": "ok", "kind": "status"}, status=http.HTTP_200_OK)

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


def _store_position(ride_ref: str, lat, lng) -> None:
    cache.set(
        f"courier:pos:{ride_ref}",
        {"lat": str(lat), "lng": str(lng)},
        POSITION_CACHE_SECONDS,
    )


def _cache_position(item: dict) -> bool:
    """Um item do lote de posição: ``request_id`` + ``coordinates``."""
    ride_ref = _first(item, ("request_id", "id_mch"))
    coordinates = item.get("coordinates") if isinstance(item.get("coordinates"), dict) else {}
    lat, lng = coordinates.get("latitude"), coordinates.get("longitude")
    if not ride_ref or lat is None or lng is None:
        return False
    _store_position(ride_ref, lat, lng)
    return True


def _first(event: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = event.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""
