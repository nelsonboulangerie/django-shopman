"""iFood signed event webhook (WP-5, optional push path).

Polling (:mod:`shopman.shop.services.ifood_events`) is the primary, recommended
mechanism. This endpoint is the optional *push* alternative: iFood POSTs the
same lightweight events, signed with an HMAC. We validate the signature and run
the events through the exact same :func:`process_events` path as polling — so a
pushed event and a polled event produce identical orders.

Authentication
--------------

``X-IFood-Signature`` = ``HMAC-SHA256(raw_body, secret)`` in hex, compared with
:func:`hmac.compare_digest`. The secret is ``SHOPMAN_IFOOD['webhook_hmac_secret']``
(defaults to ``client_secret``). A missing/invalid signature — or an unconfigured
secret — returns **401**, in every environment.

⚠️ The exact signature scheme must be confirmed against the iFood portal's
webhook docs during homologação (the portal blocks bots, so it was not verified
live). Until then this endpoint stays unregistered unless a secret is set.

Response contract
-----------------

The push path has **no separate acknowledgement call**: the HTTP status *is* the
ack. iFood treats ``202 Accepted`` as "delivered, stop retrying" and any other
status (or a response slower than 5s) as a failed delivery, retrying for up to
15 minutes before discarding the event for good. So the status has to tell the
truth:

- **202** — every event in the batch was handled (ingested, deduped or an
  ignorable code). This is the success code for *all* events, not only presence.
- **500** — at least one event failed. Answering 200/202 here would consume the
  delivery and lose the order forever, since there is no second chance on push.

Presence (``KEEPALIVE``)
------------------------

iFood probes the endpoint with a ``KEEPALIVE`` event to decide whether the
merchant is *online* — i.e. able to receive orders in real time. It is a
presence probe, not an order event, so it never reaches ``process_events``:
answering it is the whole job. The reply lists, in ``merchantIds``, the
merchants this deployment declares online; iFood generates a heartbeat only for
those. A reply that omits a merchant takes that store offline on the platform,
so the list is built conservatively — see :func:`_presence_body`.

This is distinct from the legacy :class:`~shopman.shop.webhooks.ifood.IFoodWebhookView`
(dev simulation / normalized hub payload), which is left untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import ifood_events

logger = logging.getLogger(__name__)

# Presença: o iFood sonda o endpoint com este código para saber se a loja está
# apta a receber pedido. Não é evento de pedido — não passa por process_events.
_KEEPALIVE_CODE = "KEEPALIVE"


def _hmac_secret() -> str:
    cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
    return str(cfg.get("webhook_hmac_secret") or "").strip()


def _merchant_id() -> str:
    cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
    return str(cfg.get("merchant_id") or "").strip()


def _valid_signature(raw_body: bytes, presented: str) -> bool:
    secret = _hmac_secret()
    if not secret:
        logger.error(
            "ifood_events_webhook: SHOPMAN_IFOOD['webhook_hmac_secret'] not set — rejecting"
        )
        return False
    if not presented:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, presented)


def _event_code(event: dict) -> str:
    """Normalized event code. iFood sends both a short ``code`` and a ``fullCode``."""
    if not isinstance(event, dict):
        return ""
    return str(event.get("fullCode") or event.get("code") or "").upper()


def _requested_merchant_ids(keepalives: list[dict]) -> list[str]:
    """The merchants iFood is asking about, de-duplicated, order preserved."""
    seen: list[str] = []
    for event in keepalives:
        raw = event.get("merchantIds") or []
        if not isinstance(raw, list):
            continue
        for candidate in raw:
            value = str(candidate or "").strip()
            if value and value not in seen:
                seen.append(value)
    return seen


def _presence_body(keepalives: list[dict]) -> dict:
    """Which merchants this deployment declares online.

    Responder é a própria prova de presença: se a requisição chegou e foi
    assinada, a integração está de pé. O que se decide aqui é apenas *por quem*
    a casa responde, e o critério é o mesmo isolamento de merchant que
    ``process_events`` aplica — rejeitar divergência explícita, tolerar
    ausência:

    - sonda sem ``merchantIds`` → corpo vazio, que o iFood lê como "todos os
      merchants do app estão online" (era o comportamento pedido para
      integrações sem controle fino de presença);
    - sonda com ``merchantIds`` e ``merchant_id`` configurado → interseção, para
      nunca afirmar presença de loja que não é nossa;
    - sonda com ``merchantIds`` e nada configurado → devolve o que foi pedido.
      Omitir aqui derrubaria a loja no iFood por falta de configuração local, o
      que é pior que o risco de responder a mais num app de uma loja só.
    """
    requested = _requested_merchant_ids(keepalives)
    configured = _merchant_id()

    if not requested:
        # Corpo vazio = todos online. Uma lista vazia diria o oposto.
        return {}

    if not configured:
        logger.warning(
            "ifood_events_webhook: presence probe for %s with no SHOPMAN_IFOOD['merchant_id'] "
            "configured — declaring the requested merchants online",
            requested,
        )
        return {"merchantIds": requested}

    online = [merchant_id for merchant_id in requested if merchant_id == configured]
    if not online:
        logger.warning(
            "ifood_events_webhook: presence probe for %s does not include the configured "
            "merchant %s — declaring nobody online",
            requested,
            configured,
        )
    return {"merchantIds": online}


@extend_schema(exclude=True)
class IFoodEventsWebhookView(APIView):
    """Signed push endpoint for iFood Order Module events."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        raw_body = request.body  # read raw bytes before parsing (needed for HMAC)
        signature = request.META.get("HTTP_X_IFOOD_SIGNATURE", "")

        if not _valid_signature(raw_body, signature):
            return Response(
                {"detail": "Invalid or missing iFood signature.", "error_code": "invalid_signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            parsed = json.loads(raw_body or b"null")
        except ValueError:
            return Response(
                {"detail": "Body must be JSON.", "error_code": "invalid_payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # iFood may deliver a single event or a list.
        events = parsed if isinstance(parsed, list) else [parsed] if isinstance(parsed, dict) else []
        if not events:
            return Response(
                {"detail": "No events in body.", "error_code": "no_events"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        keepalives = [e for e in events if _event_code(e) == _KEEPALIVE_CODE]
        order_events = [e for e in events if _event_code(e) != _KEEPALIVE_CODE]

        summary: dict = {}
        if order_events:
            from shopman.shop.services import observability

            try:
                summary = ifood_events.process_events(order_events)
            # O traceback é a única pista do que derrubou a entrega, e o alerta
            # abaixo já é consequência dele: o log vem primeiro, sempre.
            except Exception as exc:
                logger.exception("ifood_events_webhook: unexpected error processing events")
                observability.record_webhook_failure(
                    provider="ifood",
                    reason="processing_failed",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    severity="critical",
                    exc=exc,
                )
                return Response(
                    {
                        "detail": "Unexpected webhook processing error.",
                        "error_code": "processing_failed",
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            if summary.get("failed"):
                # Sem ack separado no push: 2xx aqui encerraria a entrega e o
                # evento sumiria. O 500 é o que faz o iFood reentregar.
                observability.record_webhook_failure(
                    provider="ifood",
                    reason="processing_failed",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    severity="critical",
                    context={"summary": summary},
                )
                logger.error(
                    "ifood_events_webhook: %s event(s) failed; answering 500 for redelivery — %s",
                    summary.get("failed"),
                    summary,
                )
                return Response(
                    {
                        "detail": "One or more events could not be processed.",
                        "error_code": "processing_failed",
                        **summary,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if keepalives:
            body = _presence_body(keepalives)
            logger.info("ifood_events_webhook: presence probe answered with %s", body)
            return Response(body, status=status.HTTP_202_ACCEPTED)

        return Response({"status": "processed", **summary}, status=status.HTTP_202_ACCEPTED)
