"""Webhook do concierge: a mensagem do cliente entra por aqui.

O flow do ManyChat faz um External Request para cá a cada mensagem de WhatsApp
que não é tratada por outro flow (e só quando o campo de handoff está vazio).
A view guarda a mensagem via ``service.receive_inbound`` e responde em
milissegundos: o turno com o modelo roda na diretiva ``concierge.turn``, no
worker. O ManyChat corta a chamada em 10 s, então NADA de trabalho aqui.

Autenticação por chave S2S (``SHOPMAN_CONCIERGE["api_key"]``), em
``Authorization: Bearer`` ou ``X-Api-Key``, como no access link. Sem chave
configurada fora de DEBUG, a porta falha FECHADA (503).
"""

from __future__ import annotations

import json
import logging
import secrets

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.core import is_ratelimited

from shopman.shop.concierge import service

logger = logging.getLogger(__name__)

RATE_LIMIT_GROUP = "concierge_inbound"
RATE_LIMIT_RATE = "120/m"

#: Chaves de perfil que o flow pode mandar junto e que ajudam a identificar o
#: cliente sem uma ida extra ao ``getInfo``.
_PROFILE_KEYS = ("first_name", "last_name", "whatsapp_id", "whatsapp_phone")


def _config() -> dict:
    return getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}


def _subscriber_id_from_payload(data: dict) -> str:
    """O ``subscriber_id`` do ManyChat, venha ele aninhado ou no topo."""
    subscriber = data.get("subscriber") or data.get("manychat_subscriber") or {}
    value = (
        (subscriber.get("id") if isinstance(subscriber, dict) else None)
        or data.get("manychat_id")
        or data.get("subscriber_id")
    )
    return str(value).strip() if value else ""


def _looks_unrendered(text: str) -> bool:
    """Variável do ManyChat digitada à mão chega literal: ``{{last_input_text}}``."""
    return "{{" in text


def _text_from_payload(data: dict, subscriber_id: str) -> str:
    """O texto da mensagem: do corpo, ou do ``getInfo`` quando o corpo não trouxe.

    Pedir ao ManyChat tira do flow a obrigação de saber QUAL variável carrega a
    mensagem (nome que muda por canal e por conta). Falha da API vira texto
    vazio, e ``receive_inbound`` responde ``empty`` sem derrubar o flow.
    """
    text = str(data.get("text") or data.get("message") or data.get("last_input_text") or "").strip()
    if text and not _looks_unrendered(text):
        return text
    if text:
        logger.warning("concierge.webhook: variável não renderizada no corpo: %r", text[:60])
    from shopman.guestman.adapters.auth import CustomerResolver

    try:
        return str(CustomerResolver().manychat_last_input_text(subscriber_id) or "").strip()
    except Exception:
        logger.warning("concierge.webhook: getInfo falhou subscriber=%s", subscriber_id, exc_info=True)
        return ""


def _profile_from_payload(data: dict) -> dict:
    subscriber = data.get("subscriber") or data.get("manychat_subscriber") or {}
    if not isinstance(subscriber, dict):
        subscriber = {}
    profile: dict = {}
    for key in _PROFILE_KEYS:
        value = data.get(key) if data.get(key) is not None else subscriber.get(key)
        if isinstance(value, str) and value.strip() and not _looks_unrendered(value):
            profile[key] = value.strip()
    return profile


@method_decorator(csrf_exempt, name="dispatch")
class ConciergeInboundView(View):
    """POST /api/webhooks/manychat/conversation/

    Corpo (JSON), tudo além do assinante é opcional::

        {"subscriber_id": "123", "text": "quero 2 baguetes", "message_id": "...",
         "first_name": "Ana", "whatsapp_phone": "+5543..."}

    ``subscriber_id`` também é aceito em ``subscriber.id`` ou ``manychat_id``.

    Com o concierge DESLIGADO a resposta é 200 ``{"status": "disabled"}``: o
    flow do ManyChat não pode quebrar porque a casa desligou a IA; ele segue
    para o próximo bloco (a mensagem fica para a equipe).
    """

    http_method_names = ["post"]

    def post(self, request: HttpRequest):
        denied = self._authenticate(request)
        if denied is not None:
            return denied

        if is_ratelimited(
            request=request,
            group=RATE_LIMIT_GROUP,
            key="ip",
            rate=RATE_LIMIT_RATE,
            method="POST",
            increment=True,
        ):
            return JsonResponse({"detail": "Muitas requisições. Tente de novo em instantes."}, status=429)

        if not _config().get("enabled"):
            return JsonResponse({"status": "disabled"}, status=200)

        try:
            data = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"detail": "JSON inválido"}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({"detail": "Corpo precisa ser um objeto JSON"}, status=400)

        subscriber_id = _subscriber_id_from_payload(data)
        if not subscriber_id or _looks_unrendered(subscriber_id):
            return JsonResponse({"detail": "subscriber_id obrigatório", "field": "subscriber_id"}, status=400)

        try:
            text = _text_from_payload(data, subscriber_id)
            external_id = str(data.get("message_id") or data.get("external_id") or "").strip()
            if _looks_unrendered(external_id):
                external_id = ""
            result = service.receive_inbound(
                subscriber_id=subscriber_id,
                text=text,
                external_id=external_id,
                profile=_profile_from_payload(data),
            )
        except Exception:
            logger.exception("concierge.webhook: falha inesperada subscriber=%s", subscriber_id)
            return JsonResponse({"detail": "Erro interno"}, status=500)

        return JsonResponse(
            {
                "status": result.reason,
                "conversation_id": result.conversation_id,
                "queued": bool(result.queued),
            },
            status=202 if result.queued else 200,
        )

    @staticmethod
    def _authenticate(request: HttpRequest) -> JsonResponse | None:
        api_key = str(_config().get("api_key") or "")
        if not api_key:
            if settings.DEBUG:
                return None
            logger.error("concierge.webhook: CONCIERGE_API_KEY não configurada, recusando (falha fechada).")
            return JsonResponse({"detail": "Concierge não configurado"}, status=503)

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        provided = ""
        if auth_header.startswith("Bearer "):
            provided = auth_header[7:].strip()
        elif request.META.get("HTTP_X_API_KEY"):
            provided = str(request.META["HTTP_X_API_KEY"]).strip()
        if not provided or not secrets.compare_digest(provided, api_key):
            return JsonResponse({"detail": "Não autorizado"}, status=401)
        return None
