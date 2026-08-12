"""Access-link session service for customer-facing entry points."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SOURCE_TO_ORIGIN = {
    "manychat": "whatsapp",
    "api": "web",
    "internal": "web",
}


def exchange_token(token_str: str, request):
    from shopman.doorman import get_access_link_service

    AccessLinkService = get_access_link_service()
    return AccessLinkService.exchange(
        token_str=token_str,
        request=request,
        preserve_session_keys=["cart_session_key"],
    )


def token_metadata(token_str: str) -> dict:
    """Return AccessLink metadata for a raw token without exposing token data."""
    if not token_str:
        return {}
    try:
        from shopman.doorman.models import AccessLink

        token = AccessLink.get_by_token(token_str)
        if token is None:
            return {}
        return token.metadata if isinstance(token.metadata, dict) else {}
    except Exception:
        logger.exception("access_link_token_metadata_failed")
        return {}


def token_source(token_str: str) -> str:
    """A ORIGEM do token (`manychat` | `internal` | `api`), lida antes do resgate.

    ⚠️ É esta a distinção que autoriza confiar no aparelho, e ela é semântica, não técnica:

    - `manychat` — o link nasceu porque a pessoa MANDOU mensagem no WhatsApp. Enviar de um
      número prova posse dele, e é a mesma prova que o OTP dá (o código também chega naquele
      número). Então confiar no aparelho aqui é coerente com o que já fazemos no login.
    - `internal` — nós empurramos o link (campanha). Prova que sabemos o número, não que
      quem tocou é a dona: mensagem se encaminha.

    Sem isto, ou nenhuma confirmação valeria para sempre (pedágio semanal), ou toda campanha
    passaria a confiar no aparelho de quem tocasse primeiro.
    """
    if not token_str:
        return ""
    try:
        from shopman.doorman.models import AccessLink

        token = AccessLink.get_by_token(token_str)
        return getattr(token, "source", "") or "" if token else ""
    except Exception:
        logger.exception("access_link_token_source_failed")
        return ""


def resolve_origin(result) -> str:
    """Determine origin_channel from exchange result metadata."""
    source = "web"
    try:
        from shopman.doorman.models import AccessLink

        token = (
            AccessLink.objects.filter(
                customer_id=result.customer.uuid,
            )
            .order_by("-created_at")
            .first()
        )
        if token:
            source = token.source
            meta = token.metadata or {}
            if meta.get("channel") == "instagram":
                return "instagram"
            if meta.get("channel") == "whatsapp":
                return "whatsapp"
    except Exception:
        logger.exception("access_link_resolve_origin_failed")

    return SOURCE_TO_ORIGIN.get(source, "web")
