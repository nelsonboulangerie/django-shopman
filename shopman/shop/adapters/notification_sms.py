"""SMS notification adapter — envia via Comtele (provedor BR, mesma conta do OTP).

Config em ``settings.SHOPMAN_SMS`` (env-driven, compartilhada com o OTP do
Doorman): ``api_key`` (header ``x-api-key``), ``route`` (ID da rota de envio da
conta — usar a transacional/Premium) e ``timeout``. Inerte (``is_available``
False) até api_key + route estarem setados.

API: POST https://api.comtele.com.br/messages/sms/send com JSON
``{receivers: [...], message, route, tag}``. Sucesso = HTTP 200 com
``{"hasError": false, ...}``.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from shopman.shop import notification_copy

from ._sms import to_digits

logger = logging.getLogger(__name__)

# ⚠️ ASCII de propósito: acento fora do GSM-7 (ã, ç, õ, á, í, ó, ú) força UCS-2 e o
# segmento cai de 160 para 70 caracteres — o SMS passa a custar o dobro. Estes são
# só o fallback: o template do Admin (NotificationTemplate) vale para todos os canais
# e ESSE é acentuado; aqui, sem acento é decisão de custo, não erro.
MESSAGE_TEMPLATES: dict[str, str] = {
    "announcement_published": "{body} {cta} {action_url}",
    "purchase_request": (
        "Ola, {supplier_greeting}! Pedido {purchase_ref} da {shop_name}: "
        "{material_name} {purchase_qty_display}. "
        "Pode confirmar disponibilidade e prazo?"
    ),
    "purchase_receipt_rejected": "Devolução {receipt_ref}: {supplier_name}. Motivo: {reason}",
    # Avisos ao cliente: fonte única em `shopman/shop/notification_copy.py`.
    **notification_copy.sms_bodies(),
}

_COMTELE_SEND_URL = "https://api.comtele.com.br/messages/sms/send"


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_SMS", {}) or {}


# O template do Admin é escrito pensando no WhatsApp e usa `*negrito*` de markdown.
# No SMS não existe formatação: o asterisco chega literal na tela do cliente
# ("pedido *NB-260901-M63*"). Tirar na SAÍDA do canal, e não no texto, é o que
# preserva o negrito onde ele funciona sem obrigar o lojista a escrever duas versões.
# Limite de 80 e sem quebra de linha: `*` solto no meio de uma frase não vira par.
_MARKDOWN_BOLD = re.compile(r"\*([^*\n]{1,80})\*")


def _strip_markdown_bold(text: str) -> str:
    return _MARKDOWN_BOLD.sub(r"\1", text)


def _build_message(template: str, context: dict) -> str:
    # O texto editado no Admin (NotificationTemplate) vale para SMS também.
    from shopman.shop.adapters._notification_templates import render_message

    return _strip_markdown_bold(render_message(template, context, MESSAGE_TEMPLATES))


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Send an SMS notification via Comtele.

    Args:
        recipient: Phone number (E.164 ou dígitos).
        template: Event template name (e.g. "order_accepted").
        context: Template variables.

    Returns:
        True if sent successfully, False otherwise.
    """
    cfg = _get_config()
    api_key = cfg.get("api_key")
    route = str(cfg.get("route") or "").strip()
    if not api_key or not route:
        logger.warning("SMS adapter: Comtele não configurado (api_key/route)")
        return False

    from ._external import inert

    if inert("SHOPMAN_SMS_ALLOW_IN_DEBUG"):
        logger.info(
            "SMS externo inerte (trava dev/seed): %s -> %s",
            template, recipient,
        )
        return True

    message = _build_message(template, context or {})
    payload = {
        "receivers": [to_digits(recipient)],
        "contactGroups": [],
        "message": message,
        "route": route,
        "tag": str(cfg.get("notification_tag") or "notification"),
    }
    request = Request(
        _COMTELE_SEND_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"x-api-key": api_key, "content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=cfg.get("timeout", 15)) as response:
            body = json.loads(response.read().decode("utf-8"))
            # Comtele responde HTTP 200 com {"hasError": true/false}; confiar na flag.
            if body.get("hasError") is False:
                logger.info("SMS accepted via Comtele: template=%s", template)
                return True
            if body.get("hasError") is not True:
                raise RuntimeError("acceptance_unconfirmed")
            logger.warning("Comtele SMS rejected: template=%s", template)
            return False
    except HTTPError as exc:
        if exc.code in {400, 401, 403, 404, 405, 413, 415, 422, 429}:
            return False
        raise RuntimeError("acceptance_unconfirmed") from exc
    except URLError as exc:
        raise RuntimeError("acceptance_unconfirmed") from exc
    except Exception as exc:
        raise RuntimeError("acceptance_unconfirmed") from exc



def is_available(recipient: str | None = None, **config) -> bool:
    """Check if SMS adapter is configured and available."""
    cfg = _get_config()
    return bool(cfg.get("api_key") and str(cfg.get("route") or "").strip())
