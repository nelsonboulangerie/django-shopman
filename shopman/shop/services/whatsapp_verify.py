"""Login por WhatsApp via access link (start leve).

O botão do site traz o cliente para o fluxo de access link do doorman: guardamos o
contexto ({cart_session_key, next}) sob um código ``NB-XxXx`` de uso único no cache e
devolvemos um deep link ``wa.me`` já preenchido. O cliente envia a mensagem; o ManyChat
casa a intenção ``#menu`` e cria o access link (``AccessLinkCreateView``), que loga a
sessão e adota a sacola quando a mensagem também traz um código ``NB-*``. A identidade é
o número que ENVIA a mensagem (zero-telefone) — sem handshake, sem bind de sessão, sem
polling/SSE. Ver ACCESS-LINK-UNIFICATION-PLAN.md.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

from django.conf import settings

logger = logging.getLogger(__name__)


def _config() -> dict:
    return getattr(settings, "SHOPMAN_WA_VERIFY", {}) or {}


def _wa_number() -> str:
    """Número (só dígitos, E.164 sem '+') do WhatsApp da loja para o deep link."""
    num = re.sub(r"\D", "", str(_config().get("number") or ""))
    if num:
        return num
    try:
        from shopman.shop.models import Shop

        shop = Shop.objects.first()
        if shop and getattr(shop, "phone", ""):
            return re.sub(r"\D", "", shop.phone)
    except Exception:
        logger.debug("wa_verify: fallback para Shop.phone degradado", exc_info=True)
    return ""


def _safe_next(raw: str) -> str:
    """Destino pós-login. Só caminhos internos (guard de open-redirect): começa com
    '/' e não '//' (protocol-relative). Caso contrário, vazio."""
    value = (raw or "").strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    return ""


def _is_checkout_next(path: str) -> bool:
    return bool(re.search(r"/(?:checkout|finalizar)(?:/|$)", path))


def _access_message_text(code: str) -> str:
    """Mensagem pré-preenchida do botão do site.

    ``#menu`` é o gatilho público no ManyChat. O ``NB-XxXx`` é payload técnico para
    recuperar contexto, não um segundo gatilho operacional.
    """
    template = str(_config().get("access_message_template") or "#menu {code}")
    try:
        return template.format(code=code)
    except (KeyError, IndexError, ValueError):
        return f"#menu {code}"


def _access_deep_link(code: str) -> str:
    number = _wa_number()
    query = urllib.parse.quote(_access_message_text(code))
    if number:
        return f"https://wa.me/{number}?text={query}"
    return f"https://wa.me/?text={query}"


def start_access_link(*, cart_session_key: str = "", next_path: str = "") -> dict:
    """Guarda o contexto do site ({cart_session_key, next}) sob um código NB-XxXx
    (uso único, no cache) e devolve o deep link com o código pré-preenchido.

    Sem token de handshake, sem bind de sessão, sem polling/SSE: a identidade é o
    número que envia a mensagem no WhatsApp; o código só carrega contexto (destino
    + sacola), consumido na criação do access link (``AccessLinkCreateView``).
    """
    from shopman.doorman.services.link_state import store_state

    state: dict = {}
    if cart_session_key:
        state["cart_session_key"] = str(cart_session_key)
    safe_next = _safe_next(next_path)
    if safe_next and (cart_session_key or not _is_checkout_next(safe_next)):
        state["next"] = safe_next

    code = store_state(state)
    has_cart_context = bool(cart_session_key)
    logger.info(
        "wa_access.start code_issued has_cart=%s has_next=%s",
        has_cart_context,
        bool(state.get("next")),
    )
    return {
        "code": code,
        "message": _access_message_text(code),
        "deep_link": _access_deep_link(code),
        "wa_number": _wa_number(),
        "has_context": has_cart_context,
        "has_cart_context": has_cart_context,
    }
