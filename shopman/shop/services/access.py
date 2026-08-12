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


def mint_handoff_link(
    *, customer_uuid, next_path: str, identity_strength: str,
    cart_session_key: str = "", ttl_minutes: int = 3,
) -> str:
    """Link de uso único para a MESMA pessoa abrir no navegador do sistema.

    A travessia existe porque pote de cookie de webview não é pote de navegador — ver
    `storefront/api/auth.py::BrowserHandoffView`. A força da identidade viaja no metadata e é
    **reposta** do outro lado: a travessia carrega, nunca promove.

    A sacola viaja junto pelo mesmo motivo de sempre: sessão nova sem sacola é a pior surpresa
    possível para quem estava no meio de um pedido.
    """
    from datetime import timedelta

    from django.utils import timezone
    from shopman.doorman.models import AccessLink

    from shopman.shop.services import storefront_links

    metadata = {
        "next": next_path,
        "login_source": "handoff",
        "identity_strength": identity_strength,
    }
    if cart_session_key:
        metadata["cart_session_key"] = cart_session_key

    _link, raw_token = AccessLink.create_with_token(
        customer_id=customer_uuid,
        audience=AccessLink.Audience.WEB_GENERAL,
        source=AccessLink.Source.INTERNAL,
        expires_at=timezone.now() + timedelta(minutes=max(1, int(ttl_minutes))),
        metadata=metadata,
    )
    base = storefront_links.storefront_url(storefront_links.path_access())
    return f"{base}?t={raw_token}"


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
