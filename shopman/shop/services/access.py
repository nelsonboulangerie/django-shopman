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

    from shopman.shop.services.customer_sign_in import mark_method

    AccessLinkService = get_access_link_service()
    mark_method(request, "access_link")
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
                customer_id=result.customer.subject_id,
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


# ⚠️ A escada sem fricção do Doorman (decisão do dono, 23/10): a resposta do WhatsApp traz
# o botão de volta, e ONDE a entrada acontece depende de onde o login começou.
#
# - No CELULAR, a entrada acontece no navegador que o botão "Voltar à loja" abrir, e nunca
#   é liberada para outra aba. Liberar a aba de origem por conta própria era abrir uma
#   porta que a pessoa não via: quem convence alguém a enviar a mensagem com o código dele
#   entrava sem ela tocar em nada.
# - No COMPUTADOR, a mensagem chega no celular e a aba fica do outro lado da mesa. O botão
#   nomeia o que libera ("Liberar o Chrome no Windows"), e só o toque nele solta a aba.
#
# Agente de usuário desconhecido conta como celular: na dúvida, nada é liberado à distância.
_PHONE_USER_AGENT_MARKERS = ("iphone", "ipod", "mobi", "windows phone")
_KNOWN_BROWSERS = ("Chrome", "Firefox", "Safari", "Edge")
_RELEASE_CONFIRM_KEY = "shopman:site-release-offer:{}"


def site_origin_is_phone(request) -> bool:
    """O login começou num celular? Decide se a mensagem libera a aba ou só a loja."""
    user_agent = str(request.META.get("HTTP_USER_AGENT", "") or "").lower()
    if not user_agent:
        return True
    return any(marker in user_agent for marker in _PHONE_USER_AGENT_MARKERS)


def _origin_parts(origin_label: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(origin_label or "").split("/") if part.strip()]
    browser = next((part for part in parts if part in _KNOWN_BROWSERS), "")
    system = next((part for part in parts if part not in _KNOWN_BROWSERS), "")
    return browser, system


def release_target(origin_label: str) -> str:
    """"o Chrome no Windows": o que o botão da mensagem libera, dito como a pessoa diria."""
    browser, system = _origin_parts(origin_label)
    if browser and system:
        return f"o {browser} no {system}"
    if browser:
        return f"o {browser}"
    if system:
        return f"o navegador no {system}"
    return "o navegador do computador"


def release_caption(origin_label: str) -> str:
    """O rótulo do botão, dentro do limite de 20 caracteres do botão do WhatsApp."""
    from shopman.shop.notification_copy import ACCESS_BUTTON_COPY, ACCESS_BUTTON_MAX_CHARS

    template = ACCESS_BUTTON_COPY["release"]
    full = template.format(target=release_target(origin_label))
    if len(full) <= ACCESS_BUTTON_MAX_CHARS:
        return full
    browser, _system = _origin_parts(origin_label)
    if browser:
        short = template.format(target=f"o {browser}")
        if len(short) <= ACCESS_BUTTON_MAX_CHARS:
            return short
    return ACCESS_BUTTON_COPY["release_fallback"]


def offer_site_release(revoke_ref: str) -> str:
    """A referência do botão "Liberar o Chrome no Windows" (vai no fragmento do link).

    É separada da referência do "Não foi você?": quem tem o link de liberar não ganha,
    só por isso, o poder de derrubar a conta inteira, e vice-versa.
    """
    import secrets

    from django.core.cache import cache
    from shopman.doorman.conf import get_doorman_settings

    if not revoke_ref:
        return ""
    release_ref = secrets.token_urlsafe(24)
    cache.set(
        _RELEASE_CONFIRM_KEY.format(release_ref),
        revoke_ref,
        timeout=get_doorman_settings().LINK_STATE_TTL_SECONDS,
    )
    return release_ref


def confirm_site_release(release_ref: str) -> str | None:
    """O toque no botão: a aba de origem pode entrar. Devolve o rótulo da origem
    ("Chrome / Windows"), ou None se a oferta venceu ou foi encerrada.

    Repetir o toque não estraga nada: a confirmação já está lá, e a resposta é a mesma.
    """
    from django.core.cache import cache
    from django.utils import timezone
    from shopman.doorman.services.link_state import get_revocation, store_revocation

    if not release_ref:
        return None
    revoke_ref = cache.get(_RELEASE_CONFIRM_KEY.format(release_ref))
    if not revoke_ref:
        return None
    record = get_revocation(str(revoke_ref))
    if record is None:
        # O "Não foi você?" chegou antes: não há mais o que liberar.
        return None
    if not record.get("confirmed_at"):
        record["confirmed_at"] = timezone.now().isoformat()
        store_revocation(str(revoke_ref), record)
    return str(record.get("origin_label") or "")


def pop_site_release(request) -> dict | None:
    """A liberação para ESTE navegador (uso único), se o botão da mensagem já foi tocado.

    A mensagem deixa a liberação esperando; sem o toque em "Liberar o Chrome no Windows"
    ela volta para a espera e a aba continua do lado de fora.
    """
    from shopman.doorman.services.link_state import (
        get_revocation,
        origin_fingerprint,
        pop_release,
        release_to_origin,
    )

    session = getattr(request, "session", None)
    if session is None or not session.session_key:
        return None
    origin = origin_fingerprint(session.session_key)
    release = pop_release(origin)
    if not release:
        return None
    revoke_ref = str(release.get("revoke_ref") or "")
    record = get_revocation(revoke_ref) if revoke_ref else None
    if record is None:
        return None
    if not record.get("confirmed_at"):
        release_to_origin(origin, token=str(release.get("token") or ""), revoke_ref=revoke_ref)
        return None
    return release


def record_site_release_login(revoke_ref: str, *, request, response) -> None:
    """Depois da troca: guarda a sessão e o dispositivo nascidos dela, para o
    "Não foi você?" da mensagem poder derrubar os dois."""
    from django.utils import timezone
    from shopman.doorman.conf import get_doorman_settings
    from shopman.doorman.models import TrustedDevice
    from shopman.doorman.services.link_state import get_revocation, store_revocation

    record = get_revocation(revoke_ref)
    if record is None:
        return
    # A hora do login marca a janela: passkey criada depois dela pode ser de quem
    # entrou no lugar da dona, e o "Não foi você?" a derruba junto.
    record["logged_in_at"] = timezone.now().isoformat()
    record["session_key"] = getattr(getattr(request, "session", None), "session_key", "") or ""
    cookie = response.cookies.get(get_doorman_settings().DEVICE_TRUST_COOKIE_NAME)
    if cookie is not None and cookie.value:
        device = TrustedDevice.verify_token(cookie.value)
        if device is not None:
            record["device_id"] = str(device.id)
    store_revocation(revoke_ref, record)


def revoke_site_release(ref: str) -> bool:
    """"Não foi você?": cancela a liberação pendente e derruba TUDO o que ela pode ter aberto.

    Quem tem a referência é quem recebeu a mensagem — o dono do número. Idempotente
    do ponto de vista dele: a segunda vez só não encontra mais nada.

    Derrubar só a sessão e o dispositivo nascidos da liberação não basta: na janela entre
    o login e o toque, quem entrou pode ter aberto outra sessão, confiado outro navegador
    ou cadastrado uma passkey, e cada um desses sobrevive sozinho. Por isso o toque
    encerra todas as sessões e todos os dispositivos lembrados da conta, e apaga as
    passkeys criadas depois daquele login. A dona volta a entrar com um código, que só
    chega no número dela.
    """
    from datetime import datetime
    from importlib import import_module

    from django.conf import settings
    from shopman.doorman.models import CustomerUser, Passkey, TrustedDevice
    from shopman.doorman.services.link_state import pop_release, pop_revocation

    from shopman.shop.services import customer_sign_in
    from shopman.shop.services import devices as device_service

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

    # Todas as sessões e dispositivos lembrados do cliente; passkeys desde o login. Sem
    # hora de login (a liberação ainda não tinha sido trocada quando a dona tocou), nenhuma
    # passkey nasceu daquele acesso, e as dela ficam.
    customer_id = str(record.get("customer_id") or "")
    sessions = devices = passkeys = 0
    if customer_id:
        link = CustomerUser.objects.filter(customer_id=customer_id).select_related("user").first()
        if link is not None:
            sessions = customer_sign_in.revoke_other_sessions(user=link.user, current_session_key="")
        devices = device_service.revoke_all(customer_id=customer_id)
        try:
            since = datetime.fromisoformat(str(record.get("logged_in_at") or ""))
        except ValueError:
            since = None
        if since is not None:
            passkeys, _ = Passkey.objects.filter(customer_id=customer_id, created_at__gte=since).delete()

    logger.warning(
        "access_link.site_release_revoked tinha_sessao=%s tinha_dispositivo=%s "
        "sessoes=%s dispositivos=%s passkeys=%s",
        bool(session_key), bool(device_id), sessions, devices, passkeys,
    )
    return True
