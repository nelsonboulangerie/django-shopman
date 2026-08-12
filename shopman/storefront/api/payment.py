"""Storefront Payment API — só o que sobrou da fusão PAYMENT-TRACKING-MERGE.

A tela de pagamento deixou de existir: o Pix/cartão viraram um degrau do próprio
acompanhamento (``GET /api/v1/tracking/{ref}/`` + SSE ``order-<ref>``). Os
antigos ``GET /payment/{ref}/`` e ``/status/`` sumiram com ela. O que fica é o
gatilho de captura simulada em DEBUG/staging, disparado de dentro do
acompanhamento.
"""

from __future__ import annotations

from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import remote_mutations
from shopman.storefront.api.actions import retry_after_action
from shopman.storefront.services import orders as order_service


def _tracking_url(ref: str) -> str:
    """URL de NAVEGAÇÃO do cliente — `pages/pedido/[ref]` no app Nuxt.

    Não confundir com o endpoint `/api/v1/tracking/{ref}/`: como rota de tela,
    `/tracking/{ref}` dá 404. Ver o mesmo cuidado no `next_url` do `views.py`.
    """
    return f"/pedido/{ref}"


PAYMENT_RATE_LIMIT_RETRY_SECONDS = 30


def mock_payment_enabled() -> bool:
    """"Simular pagamento" liberado em DEBUG ou com adapters mock (staging).

    Delega ao dono da pergunta em ``shop.services.payment`` — o mesmo que a
    projection do acompanhamento consulta para decidir se mostra o botão. Antes
    cada lado tinha a sua fórmula e elas divergiam em staging.
    """
    from shopman.shop.services import payment as payment_service

    return payment_service.mock_capture_allowed()


def _rate_limited_response() -> Response:
    return Response(
        {
            "detail": "Muitas tentativas. Aguarde um instante.",
            "error_code": "rate_limited",
            "retry_after_seconds": PAYMENT_RATE_LIMIT_RETRY_SECONDS,
            "actions": [retry_after_action(PAYMENT_RATE_LIMIT_RETRY_SECONDS)],
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(PAYMENT_RATE_LIMIT_RETRY_SECONDS)},
    )


@method_decorator(never_cache, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="30/m", method="POST", block=False), name="dispatch")
class OrderPaymentMockConfirmView(APIView):
    """POST /api/v1/payment/<ref>/mock-confirm/ — captura simulada (DEBUG/staging)."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request, ref: str):
        if getattr(request, "limited", False):
            return _rate_limited_response()

        if not mock_payment_enabled():
            raise Http404
        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Pedido não encontrado."}, status=404)

        key = remote_mutations.idempotency_key_from_request(
            request,
            fallback=f"mock-confirm:{ref}",
        )

        def execute_mock_confirm() -> tuple[dict, int]:
            order_service.resolve_timeouts_if_due(order)
            if not order_service.payment_is_sufficient(order):
                if order_service.ensure_payment_intent(order):
                    order_service.mock_confirm_payment(order)
                    order_service.resolve_confirmation_timeout_if_due(order)
            return {"redirect_url": _tracking_url(ref)}, status.HTTP_200_OK

        try:
            result = remote_mutations.run_idempotent_mutation(
                scope=f"payment-mock-confirm:{ref}",
                key=key,
                execute=execute_mock_confirm,
            )
        except remote_mutations.RemoteMutationInProgress:
            return Response(
                {"detail": "Confirmação teste já está em andamento.", "error_code": "mutation_in_progress"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(result.response_body, status=result.response_code)
