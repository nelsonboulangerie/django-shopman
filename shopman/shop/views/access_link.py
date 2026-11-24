"""As duas rotas do doorman que o deployment monta, com a régua da loja (OC-09).

- ``POST /api/auth/access/create/``: a ponte do ManyChat (``StoreAccessLinkCreateView``).
- ``GET /auth/access/?t=``: a entrada de reserva quando a loja não está configurada
  (``StoreAccessLinkExchangeView``); a mesma régua de audiência da porta da loja.

A view do doorman cunha o link com o prazo e a audiência que o chamador pedir: prazo
sem teto e qualquer audiência. A régua do deployment mora no orquestrador
(``services.access.s2s_link_request_error``) e é aplicada aqui, antes de a view do
doorman fazer o resto (identidade, código NB, liberação da aba de origem, entrega).

A régua só roda para quem passou pela chave: quem não se autentica recebe a recusa do
próprio doorman (401, ou 503 sem chave configurada), e a régua não vira oráculo para
quem está de fora.
"""

from __future__ import annotations

import json
import secrets

from django.conf import settings as django_settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from shopman.doorman.conf import get_doorman_settings
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.views.access_link import AccessLinkCreateView, AccessLinkExchangeView

from shopman.shop.services import access as access_service


def _passes_the_key(request) -> bool:
    """A mesma conferência de chave da view do doorman, sem a resposta."""
    api_key = get_doorman_settings().ACCESS_LINK_API_KEY
    if not api_key:
        return bool(django_settings.DEBUG)
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    provided = auth_header[7:] if auth_header.startswith("Bearer ") else request.META.get("HTTP_X_API_KEY", "")
    return bool(provided) and secrets.compare_digest(provided, api_key)


@method_decorator(csrf_exempt, name="dispatch")
class StoreAccessLinkCreateView(AccessLinkCreateView):
    def post(self, request):
        if _passes_the_key(request):
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                error = access_service.s2s_link_request_error(
                    ttl_minutes=data.get("ttl_minutes"),
                    audience=data.get("audience"),
                )
                if error:
                    return JsonResponse({"error": error, "error_code": ErrorCode.INVALID_INPUT}, status=400)
        return super().post(request)


class StoreAccessLinkExchangeView(AccessLinkExchangeView):
    def get(self, request):
        audience = access_service.token_audience(request.GET.get("t") or "")
        if audience and audience not in access_service.STORE_ENTRY_AUDIENCES:
            return render(request, self.get_template_name(), {"error": "Link inválido."})
        return super().get(request)
