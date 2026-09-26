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

    ⚠️ É esta a distinção que autoriza confiar no dispositivo, e ela é semântica, não técnica:

    - `manychat` — o link nasceu porque a pessoa MANDOU mensagem no WhatsApp. Enviar de um
      número prova posse dele, e é a mesma prova que o OTP dá (o código também chega naquele
      número). Então confiar no dispositivo aqui é coerente com o que já fazemos no login.
    - `internal` — nós empurramos o link (campanha). Prova que sabemos o número, não que
      quem tocou é a dona: mensagem se encaminha.

    Sem isto, ou nenhuma confirmação valeria para sempre (pedágio semanal), ou toda campanha
    passaria a confiar no dispositivo de quem tocasse primeiro.
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


# ── Login do site pelo WhatsApp: a aba de origem entra sozinha ──────────────────


def site_origin(request) -> str:
    """Impressão digital da sessão deste navegador, criando a sessão se preciso.

    Visitante anônimo pode ainda não ter sessão gravada — e sem chave não há o que
    amarrar. Gravar agora faz o cookie sair nesta mesma resposta.
    """
    from shopman.doorman.services.link_state import origin_fingerprint

    session = getattr(request, "session", None)
    if session is None:
        return ""
    if not session.session_key:
        session.save()
    return origin_fingerprint(session.session_key or "")


def site_origin_label(request) -> str:
    """"Safari / iPhone": o nome que a mensagem usa para dizer onde a pessoa entrou."""
    from shopman.doorman.services.device_trust import describe_user_agent

    return describe_user_agent(str(request.META.get("HTTP_USER_AGENT", "") or ""))[:60]


def pop_site_release(request) -> dict | None:
    """A liberação pendente para ESTE navegador (uso único), se a mensagem já chegou."""
    from shopman.doorman.services.link_state import origin_fingerprint, pop_release

    session = getattr(request, "session", None)
    if session is None or not session.session_key:
        return None
    return pop_release(origin_fingerprint(session.session_key))


def record_site_release_login(revoke_ref: str, *, request, response) -> None:
    """Depois da troca: guarda a sessão e o dispositivo nascidos dela, para o
    "Não foi você?" da mensagem poder derrubar os dois."""
    from shopman.doorman.conf import get_doorman_settings
    from shopman.doorman.models import TrustedDevice
    from shopman.doorman.services.link_state import get_revocation, store_revocation

    record = get_revocation(revoke_ref)
    if record is None:
        return
    record["session_key"] = getattr(getattr(request, "session", None), "session_key", "") or ""
    cookie = response.cookies.get(get_doorman_settings().DEVICE_TRUST_COOKIE_NAME)
    if cookie is not None and cookie.value:
        device = TrustedDevice.verify_token(cookie.value)
        if device is not None:
            record["device_id"] = str(device.id)
    store_revocation(revoke_ref, record)


def revoke_site_release(ref: str) -> bool:
    """"Não foi você?": cancela a liberação pendente ou derruba o acesso que ela abriu.

    Quem tem a referência é quem recebeu a mensagem — o dono do número. Idempotente
    do ponto de vista dele: a segunda vez só não encontra mais nada.
    """
    from importlib import import_module

    from django.conf import settings
    from shopman.doorman.models import TrustedDevice
    from shopman.doorman.services.link_state import pop_release, pop_revocation

    record = pop_revocation(ref)
    if record is None:
        return False

    pop_release(str(record.get("origin") or ""))

    session_key = str(record.get("session_key") or "")
    if session_key:
        store = import_module(settings.SESSION_ENGINE).SessionStore
        store(session_key=session_key).delete()

    device_id = str(record.get("device_id") or "")
    if device_id:
        device = TrustedDevice.objects.filter(id=device_id).first()
        if device is not None:
            device.revoke()

    logger.warning(
        "access_link.site_release_revoked tinha_sessao=%s tinha_dispositivo=%s",
        bool(session_key), bool(device_id),
    )
    return True
