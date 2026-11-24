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

Com sacola dos dois lados (``destination_conflict``), a Nice pergunta o mesmo que o
site ("Qual quer usar?") e guarda a oferta em ``Conversation.flags["pending_cart_arrival"]``
até a resposta: "a do site" aceita com ``replace_existing=True`` (a daqui é descartada
inteira, nunca mesclada); "a daqui" mantém, e a do site continua lá.
"""

from __future__ import annotations

import logging

from shopman.shop.models import Conversation
from shopman.shop.services.session_transfer import CONVERSATION_MESSAGE_MARKER, CONVERSATION_STATE_KEY

from . import metrics
from .turn_outcome import TurnOutcome

logger = logging.getLogger(__name__)

FLAG = "cart_arrival"
#: A pergunta "qual sacola quer usar?" esperando a resposta (``destination_conflict``).
PENDING_FLAG = "pending_cart_arrival"
#: Quanto tempo a pergunta espera; depois, a resposta já não se refere a ela.
PENDING_MINUTES = 30
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
    "nothing_available": "Nenhum item da sacola do site está disponível aqui agora. Ela continua no site.",
    "no_cart": "A sacola do site já não está aberta. Monte de novo por aqui ou no site.",
}
#: A mesma pergunta do site ("Qual sacola você quer usar aqui?"), com as duas respostas.
ASK = (
    "Você já tem uma sacola aqui, com {here}. A do site tem {there}. Qual quer usar?\n"
    "Responda “a do site” para trazer a do site (a daqui é descartada) ou “a daqui” para ficar com "
    "esta (a do site continua lá)."
)
KEPT = "Combinado: fica a sacola daqui. A do site continua lá, como estava."
EXPIRED = (
    "Esse código de sacola venceu ou já foi usado. No site, toque de novo em Continuar pelo WhatsApp "
    "para gerar outro."
)
UNAVAILABLE = "Não consegui trazer a sacola do site agora. Ela continua no site, como estava."

#: As respostas à pergunta. Só vale a resposta que aponta UMA das duas.
_REPLACE_ANSWERS = ("a do site", "do site", "trazer", "substituir", "substitui", "troca")
_KEEP_ANSWERS = ("a daqui", "daqui", "manter", "mantem", "mantenha", "ficar com esta", "fico com esta")
_ANSWER_MAX_WORDS = 6


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


def _write_flags(conversation: Conversation, **changes) -> None:
    """Grava as chaves com o fence do turno (``None`` apaga), como ``_remember_unclear``."""
    fence = getattr(conversation, "_turn_fence", conversation.turn_fence)
    locked = Conversation.objects.filter(pk=conversation.pk, turn_fence=fence).first()
    if locked is None:
        return
    flags = dict(locked.flags or {})
    for key, value in changes.items():
        if value is None:
            flags.pop(key, None)
        else:
            flags[key] = value
    Conversation.objects.filter(pk=conversation.pk, turn_fence=fence).update(flags=flags)
    conversation.flags = flags


def _pending(conversation: Conversation) -> dict | None:
    from datetime import timedelta

    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    pending = (conversation.flags or {}).get(PENDING_FLAG)
    if not isinstance(pending, dict) or not isinstance(pending.get("offer"), dict):
        return None
    at = parse_datetime(str(pending.get("at") or ""))
    if at is None or timezone.now() - at > timedelta(minutes=PENDING_MINUTES):
        return None
    return pending


def _answer(folded: str) -> str:
    """``replace``, ``keep`` ou vazio: só vale a resposta curta que aponta uma das duas sacolas.

    Frase longa ("pode trazer 2 croissants") é pedido, não resposta: segue pelo turno
    de sempre, e a pergunta continua esperando.
    """
    if len(folded.split()) > _ANSWER_MAX_WORDS:
        return ""
    replace = any(word in folded for word in _REPLACE_ANSWERS)
    keep = any(word in folded for word in _KEEP_ANSWERS)
    if replace == keep:
        return ""
    return "replace" if replace else "keep"


def _context(conversation: Conversation, binding, text: str):
    from . import tools
    from .service import config

    return tools.ToolContext(
        conversation=conversation,
        channel_ref=str(conversation.channel_ref or config().get("channel_ref") or ""),
        provider=str(getattr(binding, "provider", "") or ""),
        account=str(getattr(binding, "account", "") or ""),
        transport_channel=str(getattr(binding, "transport_channel", "") or ""),
        connection_key=str(getattr(binding, "connection_key", "") or ""),
        customer_text=text,
    )


def _summary(channel_ref: str, session_key: str) -> str:
    """"2 itens (R$ 1,80)": a sacola contada como a loja conta, sem abrir as linhas."""
    from shopman.shop.projections.cart import items_phrase, offered_cart

    from .tools import _money

    entry = offered_cart(channel_ref, session_key)
    if entry is None:
        return ""
    return f"{items_phrase(entry)} ({_money(entry.subtotal_q)})"


def receive(conversation: Conversation, binding, text: str) -> TurnOutcome | None:
    """A resposta do turno quando a mensagem traz o código de uma sacola da loja; ``None`` se não traz.

    Também responde à pergunta "qual sacola quer usar?" que ela mesma fez num turno
    anterior. ``None`` deixa o turno seguir pelo caminho de sempre: mensagem sem código
    nem resposta, mensagem do fluxo de login, ou código que não é de sacola (um ref de
    pedido citado na fala).
    """
    folded = _fold(text)
    code = _code_in(text)
    pending = _pending(conversation)
    if not code:
        answer = _answer(folded) if pending else ""
        if not answer:
            return None
        return _answered(conversation, binding, text, pending, answer)
    if any(marker in folded for marker in _LOGIN_MARKERS):
        return None
    from shopman.doorman.services.link_state import pop_state

    state = pop_state(code) or {}
    offer = state.get(CONVERSATION_STATE_KEY)
    if not isinstance(offer, dict):
        offer = _remembered(conversation, code)
    if not isinstance(offer, dict) and pending and pending.get("code") == code:
        offer = pending["offer"]  # a mesma mensagem outra vez com a pergunta no ar: pergunta de novo
    if not isinstance(offer, dict):
        if _fold(CONVERSATION_MESSAGE_MARKER) in folded:
            return TurnOutcome(reply_text=EXPIRED, layer=metrics.LAYER_CONTEXT)
        return None
    return _accept(conversation, binding, text, code, offer, replace_existing=False)


def _answered(conversation: Conversation, binding, text: str, pending: dict, answer: str) -> TurnOutcome:
    if answer == "keep":
        _write_flags(conversation, **{PENDING_FLAG: None})
        return TurnOutcome(reply_text=KEPT, layer=metrics.LAYER_CONTEXT)
    code = str(pending.get("code") or "")
    return _accept(conversation, binding, text, code, pending["offer"], replace_existing=True)


def _accept(conversation, binding, text: str, code: str, offer: dict, *, replace_existing: bool) -> TurnOutcome:
    from . import tools

    ctx = _context(conversation, binding, text)
    result = tools.receive_site_cart(ctx, offer, replace_existing=replace_existing)
    if not result.get("ok"):
        error = str(result.get("error") or "")
        logger.info("concierge.cart_arrival.refused code=%s", error)
        if error == "destination_conflict":
            here = _summary(ctx.channel_ref, ctx.conversation.session_key)
            there = _summary(str(offer.get("source_channel") or ""), str(offer.get("source_key") or ""))
            if here and there:
                from django.utils import timezone

                _write_flags(
                    conversation,
                    **{PENDING_FLAG: {"code": code, "offer": offer, "at": timezone.now().isoformat()}},
                )
                return TurnOutcome(reply_text=ASK.format(here=here, there=there), layer=metrics.LAYER_CONTEXT)
        _write_flags(conversation, **{PENDING_FLAG: None})
        return TurnOutcome(reply_text=REFUSED.get(error, UNAVAILABLE), layer=metrics.LAYER_CONTEXT)
    _write_flags(conversation, **{FLAG: {"code": code, "offer": offer}, PENDING_FLAG: None})
    return TurnOutcome(
        reply_text=arrival_text(result, cart_text=tools.render_result("view_cart", tools.view_cart(ctx))),
        layer=metrics.LAYER_CONTEXT,
        tool_events=[{"name": "receive_site_cart", "ok": True, "replayed": bool(result.get("replayed"))}],
    )


def arrival_text(result: dict, *, cart_text: str = "") -> str:
    """A frase de chegada, as diferenças uma por linha, e a sacola como está."""
    from shopman.storefront.presentation.cart import transfer_difference_lines

    if result.get("replayed"):
        return "\n".join(part for part in (ARRIVED_AGAIN, cart_text) if part)
    differences = transfer_difference_lines(result.get("differences") or ())
    parts = [ARRIVED]
    if differences:
        parts.append("\n".join([CHANGED, *(f"• {line}" for line in differences)]))
    if cart_text:
        parts.append(cart_text)
    return "\n\n".join(parts)
