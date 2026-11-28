"""Ensaio do botão "Confirmar pedido" no WhatsApp do ManyChat (#2926, WP-11, ADR-050).

O dono escolheu confirmar o pedido por um botão. A documentação do ManyChat só garante o
``dynamic_block_callback`` (o botão que leva um payload ao nosso servidor) no Messenger.
Este ensaio responde, no número do dono, três perguntas antes de qualquer cliente:

1. o botão aparece no WhatsApp;
2. o clique chega ao nosso servidor com o ``payload`` íntegro;
3. o clique diz QUEM tocou (o contato), para ligar o código ao orçamento certo.

Nada de pedido: o resumo é de teste, e o clique só é gravado e respondido.

- ``send(subscriber_id)`` manda a mensagem de teste com o botão;
- ``ProbeCallbackView`` recebe o clique, grava tudo numa nota da conversa (ou no log, se
  não achar a conversa) e responde no formato do ManyChat;
- ``recorded()`` devolve o que chegou, para o ``manage.py concierge_button_probe --show``.

O cabeçalho que autentica o clique sai do ``SECRET_KEY`` (HMAC do id do ensaio): nada
novo no env nem no ``settings`` (ADR-042).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

HEADER = "X-Concierge-Probe"
NOTE_PREFIX = "Ensaio do botão Confirmar pedido"
TEST_TEXT = (
    "Teste da casa, sem pedido nenhum: toque no botão abaixo para a gente conferir se ele "
    "chega até nós. Código deste teste: {code}."
)
REPLY_TEXT = "Recebi o seu toque no botão. Era só um teste da casa, obrigada! 💛"


def _token(probe_id: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"button-probe:{probe_id}".encode(), hashlib.sha256).hexdigest()


def button(probe_id: str, code: str, url: str) -> dict:
    return {
        "type": "dynamic_block_callback",
        "caption": "Confirmar pedido",
        "url": url,
        "method": "post",
        "headers": {HEADER: f"{probe_id}.{_token(probe_id)}"},
        "payload": {"probe": probe_id, "code": code, "kind": "confirm_order_probe"},
    }


#: Mensagem livre no WhatsApp só dentro de 24 horas da última fala do contato.
WINDOW = timedelta(hours=24)


def _subscriber_info(subscriber_id: str) -> dict | None:
    from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

    return ManychatSubscriberResolver.fetch_subscriber_info(subscriber_id)


def window_open(subscriber_id: str, *, now: datetime | None = None) -> tuple[bool, str]:
    """(aberta, última interação): fora da janela o ManyChat recusa, e o ensaio não prova nada."""
    info = _subscriber_info(subscriber_id) or {}
    raw = str(info.get("last_interaction") or "").strip()
    try:
        last = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
    except ValueError:
        last = None
    if last is None:
        return False, raw
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return (now or timezone.now()) - last <= WINDOW, raw


def explain(result: dict) -> str:
    """Uma linha para quem roda o ensaio: o que aconteceu, com o código do ManyChat."""
    if result.get("success"):
        return f"Enviado. Ensaio {result.get('probe')}, código {result.get('code')}: toque no botão e rode --show."
    if result.get("error") == "outside_window":
        return f"Não enviado: fora da janela de 24 horas (última interação: {result.get('last_interaction') or 'desconhecida'}). Mande um oi pelo WhatsApp e rode de novo."
    parts = [f"Recusado pelo ManyChat: {result.get('error')}"]
    if result.get("provider_http_status"):
        parts.append(f"HTTP {result['provider_http_status']}")
    if result.get("provider_code"):
        parts.append(f"código {result['provider_code']}")
    if result.get("probe"):
        parts.append(f"ensaio {result['probe']}")
    return ", ".join(parts) + "."


def send(subscriber_id: str, *, callback_url: str, check_window: bool = True) -> dict:
    """Manda a mensagem de teste com o botão. Devolve o resultado do ``sendContent``."""
    from shopman.shop.adapters import notification_manychat as mc

    if check_window:
        is_open, last = window_open(subscriber_id)
        if not is_open:
            return {"success": False, "error": "outside_window", "last_interaction": last}
    probe_id = secrets.token_hex(6)
    code = f"{secrets.randbelow(10_000):04d}"
    config, subscriber = mc._prepare_call(subscriber_id, "button_probe")
    if config is None:
        return {"success": False, "error": "not_configured"}
    payload = {
        "subscriber_id": subscriber,
        "data": {
            "version": "v2",
            "content": {
                "type": "whatsapp",
                "messages": [
                    {"type": "text", "text": TEST_TEXT.format(code=code), "buttons": [button(probe_id, code, callback_url)]}
                ],
            },
        },
    }
    result = mc._api_call("/sending/sendContent", payload, config)
    return {**result, "probe": probe_id, "code": code}


def _subject_from(body) -> str:
    """O contato que tocou, onde quer que o ManyChat o ponha (id do assinante)."""
    if not isinstance(body, dict):
        return ""
    for key in ("subscriber_id", "id", "user_id", "contact_id"):
        value = body.get(key)
        if value:
            return str(value)
    for nest in ("subscriber", "contact", "user"):
        found = _subject_from(body.get(nest))
        if found:
            return found
    return ""


def record(body, headers: dict, *, authenticated: bool) -> dict:
    """Grava o clique: corpo, nomes dos cabeçalhos, contato e se o payload veio íntegro."""
    from shopman.shop.models import ConversationBinding, ConversationMessage

    payload = body.get("payload") if isinstance(body, dict) else None
    subject = _subject_from(body)
    entry = {
        "at": timezone.now().isoformat(),
        "authenticated": authenticated,
        "subject": subject,
        "payload": payload,
        "body_keys": sorted(body) if isinstance(body, dict) else [],
        "header_names": sorted(headers),
        "body": body,
    }
    binding = ConversationBinding.objects.filter(provider="manychat", subject=subject).order_by("-pk").first() if subject else None
    if binding is not None:
        ConversationMessage.objects.create(
            conversation=binding.conversation, binding=binding, role=ConversationMessage.Role.ASSISTANT,
            kind=ConversationMessage.Kind.NOTE, text=f"{NOTE_PREFIX}: clique recebido.",
            envelope={"button_probe": entry},
        )
    logger.warning("concierge.button_probe.click %s", json.dumps(entry, ensure_ascii=False, default=str)[:4000])
    return entry


def recorded(limit: int = 5) -> list[dict]:
    from shopman.shop.models import ConversationMessage

    rows = ConversationMessage.objects.filter(envelope__has_key="button_probe").order_by("-pk")[:limit]
    return [{"conversation": row.conversation_id, **row.envelope["button_probe"]} for row in rows]


@method_decorator(csrf_exempt, name="dispatch")
class ProbeCallbackView(View):
    """O clique do botão de teste. Grava e responde; nunca muda pedido nem conversa."""

    def post(self, request: HttpRequest):
        raw = request.headers.get(HEADER, "")
        probe_id, _, token = raw.partition(".")
        authenticated = bool(probe_id and token and hmac.compare_digest(token, _token(probe_id)))
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            body = {"_unparsed": request.body[:2000].decode("utf-8", "replace")}
        headers = dict.fromkeys(request.headers, "")  # só os nomes: o valor pode ser segredo
        record(body, headers, authenticated=authenticated)
        if not authenticated:
            return JsonResponse({"detail": "não autorizado"}, status=403)
        return JsonResponse({
            "version": "v2",
            "content": {"type": "whatsapp", "messages": [{"type": "text", "text": REPLY_TEXT}]},
        })
