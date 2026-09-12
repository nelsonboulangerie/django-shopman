"""Fronteira HTTP provider-agnostic para eventos do concierge."""

from __future__ import annotations

import hashlib
import logging

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.core import is_ratelimited

from shopman.storefront.concierge import service, transport
from shopman.storefront.concierge.contracts import InboundEvent, IngressRejected

logger = logging.getLogger(__name__)

RATE_LIMIT_GROUP = "concierge_inbound"
RATE_LIMIT_RATE = "1200/m"
MAX_BODY_BYTES = 32768


def _limited(request: HttpRequest, *, group: str, identity: str, rate: str) -> bool:
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return is_ratelimited(
        request=request,
        group=f"{RATE_LIMIT_GROUP}:{group}",
        key=lambda _group, _request: digest,
        rate=rate,
        method="POST",
        increment=True,
    )


@method_decorator(csrf_exempt, name="dispatch")
class ConciergeEventView(View):
    """POST /api/webhooks/concierge/<connection_key>/events/."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, connection_key: str):
        connection = transport.connection_for_key(connection_key)
        if connection is None:
            return JsonResponse({"detail": "Connection não encontrada"}, status=404)
        adapter = transport.adapter_for_connection(connection)
        if adapter is None:
            return JsonResponse({"detail": "Connection indisponível"}, status=503)
        if request.content_type != "application/json":
            return JsonResponse({"detail": "Content-Type precisa ser application/json"}, status=415)
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"detail": "Corpo muito grande"}, status=413)
        if is_ratelimited(
            request=request,
            group=RATE_LIMIT_GROUP,
            key="ip",
            rate=RATE_LIMIT_RATE,
            method="POST",
            increment=True,
        ):
            return JsonResponse({"detail": "Muitas requisições. Tente de novo em instantes."}, status=429)

        try:
            event = adapter.authenticate_and_normalize(request, timezone.now())
        except IngressRejected as exc:
            body = {"detail": exc.detail, "code": exc.code}
            if exc.field:
                body["field"] = exc.field
            return JsonResponse(body, status=exc.status)
        if not isinstance(event, InboundEvent) or (
            event.scope.connection_key,
            event.scope.provider,
            event.scope.account,
            event.scope.channel,
        ) != (connection.key, connection.provider, connection.account, connection.channel):
            logger.error("concierge.webhook.adapter_scope_mismatch")
            return JsonResponse({"detail": "Connection indisponível"}, status=503)

        if _limited(request, group="connection", identity=event.scope.connection_key, rate="1200/m") or _limited(
            request,
            group="subject",
            identity=f"{event.scope.connection_key}:{event.scope.subject}",
            rate="60/m",
        ):
            return JsonResponse({"detail": "Muitas requisições. Tente de novo em instantes."}, status=429)

        reason = service.disabled_reason()
        if reason:
            if reason != "switch_off":
                logger.error("concierge.webhook: concierge ligado mas inoperante (%s)", reason)
            return JsonResponse({"status": "disabled", "reason": reason}, status=200)
        try:
            result = service.receive_inbound(event)
        except Exception:
            logger.exception("concierge.webhook: falha inesperada")
            return JsonResponse({"detail": "Erro interno"}, status=500)
        return JsonResponse(
            {"status": result.reason, "queued": bool(result.queued)},
            status=409 if result.reason in {"intent_conflict", "scope_conflict"} else 200,
        )
