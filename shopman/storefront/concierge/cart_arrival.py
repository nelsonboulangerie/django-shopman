"""A sacola da loja chega à conversa pelo código ``NB-`` (OC-16, C02, J7).

A loja oferece "Continuar pelo WhatsApp": guarda a oferta da sacola sob um código
``NB-`` (``session_transfer.offer_to_conversation``) e abre o WhatsApp com a
mensagem pronta. Quando a mensagem chega aqui, este módulo lê o código, consome o
estado e pede o aceite ao serviço (``tools.receive_site_cart`` →
``session_transfer.accept``). A Nice diz numa frase que a sacola chegou e, uma por
linha, o que chegou diferente; depois mostra a sacola como ela está.

O código não autentica ninguém: quem aceita é o número que ENVIA, pelo vínculo
``verified_customer`` da conversa. Mensagens do fluxo de login ("quero entrar no
site", ``#menu``) não são desta porta: são do ManyChat, que cria o access link.

O mesmo código outra vez (a cliente mandou duas vezes, o provedor repetiu) não abre
uma segunda sacola: a conversa guarda a última oferta aceita em
``Conversation.flags["cart_arrival"]``, e o serviço devolve o mesmo recibo (X4).
"""

from __future__ import annotations

import logging

from shopman.shop.models import Conversation
from shopman.shop.services.session_transfer import CONVERSATION_MESSAGE_MARKER, CONVERSATION_STATE_KEY

from . import metrics
from .turn_outcome import TurnOutcome

logger = logging.getLogger(__name__)

FLAG = "cart_arrival"
#: As palavras do fluxo de login no ManyChat: a mensagem com elas não é desta porta.
_LOGIN_MARKERS = ("quero entrar no site", "#menu")
#: O corpo de um código ``NB-`` cunhado pelo doorman (``link_state.new_code``).
_CODE_BODY_LENGTH = 6

ARRIVED = "Sua sacola do site chegou aqui na conversa."
ARRIVED_AGAIN = "Sua sacola do site já está aqui na conversa."
CHANGED = "Chegou com estas mudanças:"
REFUSED = {
    "not_authorized": (
        "Recebi o código da sacola do site, mas ela é de outra conta, ou este número ainda não foi "
        "verificado. A sacola continua no site, como estava."
    ),
    "source_changed": (
        "A sacola do site mudou depois que você tocou em Continuar pelo WhatsApp. Para trazer a versão "
        "nova, toque de novo nesse botão, no site."
    ),
    "destination_conflict": (
        "Você já tem uma sacola aqui na conversa, então a do site continua lá, sem mudança. Para trazer "
        "a do site, esvazie esta sacola e toque de novo em Continuar pelo WhatsApp, no site."
    ),
    "nothing_available": "Nenhum item da sacola do site está disponível aqui agora. Ela continua no site.",
    "no_cart": "A sacola do site já não está aberta. Monte de novo por aqui ou no site.",
}
EXPIRED = (
    "Esse código de sacola venceu ou já foi usado. No site, toque de novo em Continuar pelo WhatsApp "
    "para gerar outro."
)
UNAVAILABLE = "Não consegui trazer a sacola do site agora. Ela continua no site, como estava."


def _fold(text: str) -> str:
    from .house_rules import fold

    return fold(text)


def _code_in(text: str) -> str:
    from shopman.doorman.services.link_state import contains_code, extract_code

    if not contains_code(text or ""):
        return ""
    code = extract_code(text)
    prefix, _, body = code.rpartition("-")
    return code if prefix and len(body) == _CODE_BODY_LENGTH else ""


def _remembered(conversation: Conversation, code: str):
    remembered = (conversation.flags or {}).get(FLAG)
    if isinstance(remembered, dict) and remembered.get("code") == code:
        return remembered.get("offer")
    return None


def _remember(conversation: Conversation, code: str, offer: dict) -> None:
    fence = getattr(conversation, "_turn_fence", conversation.turn_fence)
    locked = Conversation.objects.filter(pk=conversation.pk, turn_fence=fence).first()
    if locked is None:
        return
    flags = dict(locked.flags or {})
    flags[FLAG] = {"code": code, "offer": offer}
    Conversation.objects.filter(pk=conversation.pk, turn_fence=fence).update(flags=flags)
    conversation.flags = flags


def receive(conversation: Conversation, binding, text: str) -> TurnOutcome | None:
    """A resposta do turno quando a mensagem traz o código de uma sacola da loja; ``None`` se não traz.

    ``None`` deixa o turno seguir pelo caminho de sempre: mensagem sem código, mensagem
    do fluxo de login, ou código que não é de sacola (um ref de pedido citado na fala).
    """
    code = _code_in(text)
    if not code:
        return None
    folded = _fold(text)
    if any(marker in folded for marker in _LOGIN_MARKERS):
        return None
    from shopman.doorman.services.link_state import pop_state

    state = pop_state(code) or {}
    offer = state.get(CONVERSATION_STATE_KEY)
    if not isinstance(offer, dict):
        offer = _remembered(conversation, code)
    if not isinstance(offer, dict):
        if _fold(CONVERSATION_MESSAGE_MARKER) in folded:
            return TurnOutcome(reply_text=EXPIRED, layer=metrics.LAYER_CONTEXT)
        return None

    from . import tools
    from .service import config

    ctx = tools.ToolContext(
        conversation=conversation,
        channel_ref=str(conversation.channel_ref or config().get("channel_ref") or ""),
        provider=str(getattr(binding, "provider", "") or ""),
        account=str(getattr(binding, "account", "") or ""),
        transport_channel=str(getattr(binding, "transport_channel", "") or ""),
        connection_key=str(getattr(binding, "connection_key", "") or ""),
        customer_text=text,
    )
    result = tools.receive_site_cart(ctx, offer)
    if not result.get("ok"):
        logger.info("concierge.cart_arrival.refused code=%s", result.get("error"))
        return TurnOutcome(
            reply_text=REFUSED.get(str(result.get("error") or ""), UNAVAILABLE), layer=metrics.LAYER_CONTEXT
        )
    _remember(conversation, code, offer)
    return TurnOutcome(
        reply_text=arrival_text(result, cart_text=tools.render_result("view_cart", tools.view_cart(ctx))),
        layer=metrics.LAYER_CONTEXT,
        tool_events=[{"name": "receive_site_cart", "ok": True, "replayed": bool(result.get("replayed"))}],
    )


def arrival_text(result: dict, *, cart_text: str = "") -> str:
    """A frase de chegada, as diferenças uma por linha, e a sacola como está."""
    from shopman.shop.projections.cart import transfer_difference_lines

    if result.get("replayed"):
        return "\n".join(part for part in (ARRIVED_AGAIN, cart_text) if part)
    differences = transfer_difference_lines(result.get("differences") or ())
    parts = [ARRIVED]
    if differences:
        parts.append("\n".join([CHANGED, *(f"• {line}" for line in differences)]))
    if cart_text:
        parts.append(cart_text)
    return "\n\n".join(parts)
