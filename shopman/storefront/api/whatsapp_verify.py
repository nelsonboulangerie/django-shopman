"""Endpoints do login por WhatsApp (fluxo access-link): start, claim e revoke.

``start`` — guarda o contexto do site (sacola anônima + destino + a sessão que apertou
o botão) sob um código NB-XxXx e devolve o deep link ``wa.me`` pré-preenchido.
``claim`` — a aba que apertou o botão pergunta se a mensagem já chegou; se chegou, entra.
``revoke`` — o "Não foi você?" da mensagem desfaz essa entrada.

A mensagem continua trazendo o access link (``AccessLinkCreateView``), agora como
reserva. Ver o serviço em ``shopman.shop.services.whatsapp_verify`` e o guia do Flow
ManyChat em docs/guides/whatsapp-access-link.md.
"""

from __future__ import annotations

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import whatsapp_verify as wa

logger = logging.getLogger(__name__)


@method_decorator(
    ratelimit(key="ip", rate="10/m", method="POST", block=False), name="dispatch"
)
class WhatsAppVerifyStartView(APIView):
    """POST /api/v1/auth/whatsapp/start/ — start leve do login por WhatsApp.

    Guarda o contexto do site (sacola anônima + destino) sob um código NB-XxXx e
    devolve o deep link pré-preenchido. Sem handshake/poll/SSE — o login acontece
    pelo access link que o ManyChat devolve. Ver ACCESS-LINK-UNIFICATION-PLAN.md.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Start WhatsApp login (access-link handoff)")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        payload = request.data if hasattr(request, "data") else {}
        next_path = str((payload or {}).get("next") or "").strip()
        cart_key = ""
        if hasattr(request, "session"):
            try:
                from shopman.storefront.cart import CartService

                if CartService.has_items(request):
                    cart_key = str(request.session.get("cart_session_key") or "")
            except Exception:
                logger.warning("wa_access.start_cart_context_check_failed", exc_info=True)

        from shopman.shop.services import access as access_service

        result = wa.start_access_link(
            cart_session_key=cart_key,
            next_path=next_path,
            origin=access_service.site_origin(request),
            origin_label=access_service.site_origin_label(request),
        )
        return Response(result)


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(
    ratelimit(key="ip", rate="40/m", method="POST", block=False), name="dispatch"
)
class WhatsAppVerifyClaimView(APIView):
    """POST /api/v1/auth/whatsapp/claim/ — "a mensagem já chegou? posso entrar?".

    A aba que apertou o botão pergunta ao voltar a ficar visível (e devagar, enquanto
    está na tela). Não manda nada: a liberação é procurada pela impressão digital da
    sessão DESTE navegador, então só quem gerou o código a encontra.

    ``status``: ``done`` (entrou — vem o payload da sessão, igual ao do link) ou
    ``pending`` (a mensagem ainda não chegou).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Claim the WhatsApp login released for this browser")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        from shopman.shop.services import access as access_service
        from shopman.storefront.api.auth import exchange_access_token

        release = access_service.pop_site_release(request)
        if not release:
            return Response({"status": "pending"})

        response = exchange_access_token(request, str(release.get("token") or ""))
        if response.status_code != status.HTTP_200_OK:
            logger.warning("wa_access.claim_exchange_failed status=%s", response.status_code)
            return Response({"status": "pending"})

        access_service.record_site_release_login(
            str(release.get("revoke_ref") or ""), request=request, response=response,
        )
        response.data = {**response.data, "status": "done"}
        logger.info("wa_access.claim_done")
        return response


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(
    ratelimit(key="ip", rate="10/m", method="POST", block=False), name="dispatch"
)
class WhatsAppVerifyRevokeView(APIView):
    """POST /api/v1/auth/whatsapp/revoke/ — o "Não foi você?" da mensagem.

    Quem tem a referência é quem recebeu a mensagem no WhatsApp: o dono do número.
    Cancela a entrada que ainda não aconteceu ou derruba a que já aconteceu (sessão e
    dispositivo lembrado).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Revoke a site login released by a WhatsApp message")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        from shopman.shop.services import access as access_service

        payload = request.data if hasattr(request, "data") else {}
        ref = str((payload or {}).get("ref") or "").strip()
        if not ref or not access_service.revoke_site_release(ref):
            return Response(
                {"detail": "Este aviso já expirou ou o acesso já foi encerrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"revoked": True})
