"""Webhook do concierge: a mensagem do cliente entra por aqui.

O flow do ManyChat faz um External Request para cá a cada mensagem de WhatsApp
que não é tratada por outro flow (e só quando o campo de handoff está vazio).
A view guarda a mensagem via ``service.receive_inbound`` e responde em
milissegundos: o turno com o modelo roda na diretiva ``concierge.turn``, no
worker. O ManyChat corta a chamada em 10 s, então NADA de trabalho aqui.

Autenticação por chave S2S (``SHOPMAN_CONCIERGE["api_key"]``), em
``Authorization: Bearer`` ou ``X-Api-Key``, como no access link. Sem chave
configurada, a porta falha FECHADA (503).
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.core import is_ratelimited

from shopman.storefront.concierge import service

logger = logging.getLogger(__name__)

RATE_LIMIT_GROUP = "concierge_inbound"
RATE_LIMIT_RATE = "1200/m"
MAX_DEPTH = 8


def _depth_ok(value, level=0):
    if level > MAX_DEPTH:
        return False
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return all(_depth_ok(child, level + 1) for child in children)


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
    return str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) and value else ""


#: Palavra-chave do piloto fechado no ManyChat: um gatilho de Keyword ("#c" no início)
#: chama a casa sem tocar no Default Reply dos clientes. A palavra é do gatilho, não
#: da conversa: sai do texto antes de chegar ao modelo.
_PILOT_PREFIXES = ("#concierge", "#c")


def strip_pilot_prefix(text: str) -> str:
    stripped = (text or "").strip()
    lowered = stripped.lower()
    for prefix in _PILOT_PREFIXES:
        if lowered == prefix or lowered.startswith(prefix + " "):
            return stripped[len(prefix) :].strip()
    return stripped


def _looks_unrendered(text: str) -> bool:
    """Variável do ManyChat digitada à mão chega literal: ``{{last_input_text}}``."""
    return "{{" in text


def _text_from_payload(data: dict, subscriber_id: str) -> str:
    """Somente o texto deste evento; getInfo não identifica mensagem."""
    text = data.get("text") or data.get("message") or data.get("last_input_text") or ""
    if not isinstance(text, str) or _looks_unrendered(text):
        return ""
    return strip_pilot_prefix(text)


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

    Corpo JSON v2 com identidade estável do evento e conta configurada::

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

        reason = service.disabled_reason()
        if reason:
            # O motivo sai no corpo: "disabled" sem explicação já mandou procurar a
            # chave errada. `switch_off` = SHOPMAN_CONCIERGE_ENABLED; `ai_key_missing` =
            # AI_ASSIST_API_KEY vazia no painel.
            if reason != "switch_off":
                logger.error("concierge.webhook: concierge ligado mas inoperante (%s)", reason)
            return JsonResponse({"status": "disabled", "reason": reason}, status=200)

        if request.content_type != "application/json":
            return JsonResponse({"detail": "Content-Type precisa ser application/json"}, status=415)
        if len(request.body) > 32768:
            return JsonResponse({"detail": "Corpo muito grande"}, status=413)
        try:
            data = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
            return JsonResponse({"detail": "JSON inválido"}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({"detail": "Corpo precisa ser um objeto JSON"}, status=400)

        if not _depth_ok(data):
            return JsonResponse({"detail": "JSON profundo demais"}, status=400)

        subscriber_id = _subscriber_id_from_payload(data)
        if not subscriber_id or _looks_unrendered(subscriber_id):
            return JsonResponse({"detail": "subscriber_id obrigatório", "field": "subscriber_id"}, status=400)

        account = str(_config().get("account_id") or "")
        transport = str(_config().get("transport_channel") or "whatsapp")
        if not account:
            return JsonResponse({"detail": "Conta do canal não configurada"}, status=503)
        if any(
            data.get(key, expected) != expected
            for key, expected in (("account_id", account), ("transport_channel", transport), ("provider", "manychat"))
        ):
            return JsonResponse({"detail": "Conta ou canal inválido"}, status=403)
        for group, identity, rate in (
            ("account", account, "1200/m"),
            ("subject", account + ":" + transport + ":" + subscriber_id, "60/m"),
        ):
            opaque = hashlib.sha256(identity.encode()).hexdigest()
            if is_ratelimited(
                request=request,
                group=RATE_LIMIT_GROUP + ":" + group,
                key=lambda g, r: opaque,
                rate=rate,
                method="POST",
                increment=True,
            ):
                return JsonResponse({"detail": "Muitas requisições. Tente de novo em instantes."}, status=429)
        event_id = next((data[key] for key in ("event_id", "message_id", "external_id") if key in data), "")
        if not isinstance(event_id, str) or len(event_id) > 4096:
            return JsonResponse({"detail": "Identidade de evento inválida"}, status=400)
        if len(subscriber_id) > 128 or any(
            not isinstance(data[key], str) for key in ("text", "message", "last_input_text") if key in data
        ):
            return JsonResponse({"detail": "Conteúdo inválido"}, status=400)
        if any(len(data.get(key, "")) > 16000 for key in ("text", "message", "last_input_text")):
            return JsonResponse({"detail": "Texto muito grande"}, status=413)
        if data.get("message_type", "text") not in ("text", "audio", "image", "video", "file"):
            return JsonResponse({"detail": "Tipo de mensagem inválido"}, status=400)
        for key in ("provider_timestamp", "correlation_ref"):
            if key in data and (not isinstance(data[key], str) or len(data[key]) > 256):
                return JsonResponse({"detail": "Metadado inválido", "field": key}, status=400)
        envelope = {
            "version": 2,
            "provider": "manychat",
            "account_id": account,
            "transport_channel": transport,
            "subject": subscriber_id,
            "event_id": event_id,
            "provider_timestamp": data.get("provider_timestamp", ""),
            "received_at": timezone.now().isoformat(),
            "message_type": data.get("message_type", "text"),
            "correlation_ref": data.get("correlation_ref", ""),
            "authentication": "api_key",
            "payload_hash": hashlib.sha256(
                json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        try:
            text = _text_from_payload(data, subscriber_id)
            external_id = event_id.strip()
            if _looks_unrendered(external_id):
                external_id = ""
            result = service.receive_inbound(
                subscriber_id=subscriber_id,
                text=text,
                external_id=external_id,
                profile=_profile_from_payload(data),
                envelope=envelope,
            )
        except Exception:
            logger.exception("concierge.webhook: falha inesperada")
            return JsonResponse({"detail": "Erro interno"}, status=500)

        return JsonResponse(
            {
                "status": result.reason,
                "queued": bool(result.queued),
            },
            status=409 if result.reason == "intent_conflict" else 200,
        )

    @staticmethod
    def _authenticate(request: HttpRequest) -> JsonResponse | None:
        keys = [str(_config().get("api_key") or ""), str(_config().get("api_key_previous") or "")]
        keys = [key for key in keys if key]
        if not keys:
            logger.error("concierge.webhook: chave ausente; ingresso contido.")
            return JsonResponse({"detail": "Concierge não configurado"}, status=503)
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        provided = (
            auth_header[7:].strip()
            if auth_header.startswith("Bearer ")
            else str(request.META.get("HTTP_X_API_KEY", "")).strip()
        )
        valid = False
        for key in keys:
            valid |= secrets.compare_digest(provided.encode(), key.encode())
        if not provided or not valid:
            return JsonResponse({"detail": "Não autorizado"}, status=401)
        return None
