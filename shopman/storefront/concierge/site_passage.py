"""A Nice e o site: o link quando a cliente pede, e onde a sacola está depois (OC-18, §4.4, J6).

Três momentos, todos pelo serviço de transferência (``shop.services.session_transfer``),
que decide dono, revisão, conflito e reserva. Aqui só se reconhece o pedido da
cliente, se chama a ferramenta e se diz o resultado com a frase da casa, sem modelo.

- **"Quero ver no site"** ("manda o link do site", "prefiro terminar pelo site"): a
  Nice manda o link (``tools.send_web_link``). Com sacola na conversa, o link leva a
  OFERTA da sacola, e a frase diz que ela vai junto (``tools.CART_GOES_ALONG``). Oferecer não tira a sacola daqui: quem leva é a
  troca do link.
- **A mensagem seguinte**: se a sacola da conversa foi aceita no site
  (``transferred_to``), a Nice diz, uma vez, onde ela está, antes da resposta do
  turno (``lead``). Se a cliente pode trazê-la de volta (ponte ligada, número
  verificado), a frase diz como.
- **"Traz a sacola para cá"** ("prefiro pedir por aqui"): a oferta inversa, oferta
  e aceite no mesmo turno (``tools.bring_site_cart``), só com sacola aberta no site.
  Com sacola aqui também, os itens entram nela (mescla, decisão do dono de 24/11).

A cliente que não pede o site nunca recebe o link (§5.3): nada aqui oferece o
site sem ser pedido, e frase com negação ("não quero o site", "o site não abre")
não é pedido. Com a ponte desligada (``CONCIERGE_TRANSFER_ENABLED``), nada daqui
responde: o turno segue pelo caminho de sempre.
"""

from __future__ import annotations

import logging
import re

from . import metrics
from .turn_outcome import TurnOutcome

logger = logging.getLogger(__name__)

#: Onde a sacola está, dito uma vez na mensagem seguinte ao aceite no site.
CART_IS_THERE = "Sua sacola está {where}, com {items} ({subtotal})."
#: A oferta inversa, só quando a cliente pode trazer a sacola (X1).
BRING_IT_HERE = "Posso trazer os itens para cá, se quiser."
#: O link pedido depois da passagem: a sacola já está lá.
ALREADY_THERE = "Sua sacola já está no site."
#: O link pedido com sacola que não pôde ir junto (sem acesso para levar a sacola).
CART_STAYS_HERE = "Sua sacola continua aqui na conversa."
BRING_REFUSED = {
    "source_changed": "A sacola do site acabou de mudar. Tente de novo.",
    "not_authorized": (
        "Para trazer a sacola do site, este número precisa estar confirmado na sua conta."
    ),
    "nothing_available": "Nenhum item da sacola do site está disponível aqui agora.",
}
BRING_UNAVAILABLE = "Não consegui trazer a sacola do site agora."
#: Pediu a sacola aqui e ela já está aqui.
ALREADY_HERE = "Sua sacola já está aqui na conversa."
#: Pediu a sacola do site e não há sacola aberta no site.
NO_SITE_CART = "Não encontrei sacola aberta no site. O que você quer pedir?"
#: A cliente disse só que prefere a conversa (C09): a Nice segue, sem insistir no site.
STAY_HERE = "Claro, seguimos por aqui."
STAY_HERE_ASK = "Claro, seguimos por aqui. O que você quer pedir?"

_NEGATION = re.compile(r"\b(nao|nem|sem|nunca)\b")
#: O site com problema é reclamação ou dúvida, não pedido de link.
_TROUBLE = re.compile(r"\b(erro|travou|travando|trava|caiu|bug|problema|fora do ar)\b")
#: Acompanhar pedido já feito: a consulta de pedido responde, com a página dele.
_TRACKING = re.compile(r"\b(acompanhar|acompanhamento|rastrear|cade|status)\b")
_SITE = re.compile(r"\bsite\b|\blink\b.*\b(cardapio|loja)\b|\b(cardapio|loja)\b.*\blink\b")
_SITE_ASK = re.compile(
    r"\b(ver|olhar|manda|mande|mandar|me manda|envia|envie|enviar|passa|passe|link|endereco|terminar|"
    r"finalizar|fechar|continuar|prefiro|quero|queria|abrir|acessar|comprar|pedir|qual|tem)\b"
)
_BRING_VERB = re.compile(r"\b(traz|traga|trazer|tras|traze|trazes|puxa|puxar)\b")
_BRING_OBJECT = re.compile(r"\b(sacola|carrinho|pra ca|para ca|aqui)\b")
_CART_WORD = re.compile(r"\b(sacola|carrinho)\b")
_HERE_ASK = re.compile(
    r"\b(pedir|comprar|terminar|finalizar|fechar|continuar|fazer|seguir)\b.*"
    r"\b(por aqui|aqui mesmo|aqui na conversa|pelo whatsapp|pelo zap|por whatsapp|na conversa)\b"
)
#: As palavras de uma fala que só diz o canal ("não quero o site, prefiro pedir por aqui"):
#: fora delas, a fala pede mais alguma coisa, e o turno de sempre responde.
_CHANNEL_ONLY_WORDS = frozenset({
    "nao", "quero", "queria", "o", "a", "os", "as", "site", "prefiro", "pelo", "pela", "por", "aqui", "mesmo",
    "eu", "vou", "melhor", "so", "pode", "ser", "no", "na", "de", "do", "da", "whatsapp", "zap", "conversa", "pedir",
    "comprar", "terminar", "finalizar", "fechar", "continuar", "fazer", "seguir", "e", "ok", "obrigado",
    "obrigada", "link", "nem", "precisa", "prefere", "gostaria", "acho", "fica", "ficar", "assim", "mais", "facil",
})
#: As palavras do fluxo de login no ManyChat (e a mensagem pronta da loja): não são desta porta.
_OTHER_DOORS = ("quero entrar no site", "#menu", "sacola que montei no site")


def _fold(text: str) -> str:
    from .house_rules import fold

    return fold(text)


def _other_door(folded: str) -> bool:
    return any(marker in folded for marker in _OTHER_DOORS)


def _negated(folded: str, match) -> bool:
    """A negação nas três palavras antes do verbo: "não traz a sacola", "não quero pedir por aqui"."""
    before = re.findall(r"[a-z]+", folded[: match.start()])[-3:]
    return any(_NEGATION.fullmatch(word) for word in before)


def asks_for_site(text: str) -> bool:
    """A cliente pede o site: ver no site, o link, terminar pelo site. Negação nunca é pedido."""
    folded = _fold(text)
    if not _SITE.search(folded) or _other_door(folded):
        return False
    if _NEGATION.search(folded) or _TROUBLE.search(folded) or _TRACKING.search(folded):
        return False
    return bool(_SITE_ASK.search(folded))


def asks_to_bring_here(text: str) -> bool:
    """A cliente quer pedir por aqui: "traz a sacola", "prefiro pedir por aqui". Negação nunca é pedido."""
    folded = _fold(text)
    if _other_door(folded):
        return False
    verb = _BRING_VERB.search(folded)
    if verb and _BRING_OBJECT.search(folded) and not _negated(folded, verb):
        return True
    here = _HERE_ASK.search(folded)
    return bool(here and not _negated(folded, here))


def only_about_the_channel(text: str) -> bool:
    """A fala só diz onde a cliente quer seguir ("prefiro pedir por aqui", "não quero o site")."""
    folded = _fold(text)
    words = re.findall(r"[a-z]+", folded)
    if not words or _other_door(folded) or any(word not in _CHANNEL_ONLY_WORDS for word in words):
        return False
    return bool(_HERE_ASK.search(folded) or (_NEGATION.search(folded) and "site" in words))


def _context(conversation, binding, text: str):
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


def _can_bring(conversation) -> bool:
    return bool(
        conversation.customer_ref
        and (getattr(conversation, "_cart_authority", False) or getattr(conversation, "_commercial_authority", False))
    )


def _where(moved: dict, *, offer_back: bool) -> str:
    line = CART_IS_THERE.format(where=moved["where"], items=moved["items"], subtotal=moved["subtotal"])
    return f"{line} {BRING_IT_HERE}" if offer_back else line


def handle(conversation, binding, text: str, *, decision=None) -> TurnOutcome | None:
    """A resposta do turno quando a cliente pede o site ou pedir por aqui; ``None`` quando não pede.

    ``None`` deixa o turno seguir pelo caminho de sempre. Com a equipe chamada pela
    triagem, a equipe conduz: nada daqui responde.
    """
    from .service import transfer_bridge_channel

    if not transfer_bridge_channel() or getattr(decision, "escalates", False):
        return None
    if asks_to_bring_here(text) or only_about_the_channel(text):
        outcome = _here(conversation, binding, text)
        if outcome is not None:
            return outcome
    if asks_for_site(text):
        return _send_site(conversation, binding, text)
    return None


def _here(conversation, binding, text: str) -> TurnOutcome | None:
    """Pedir por aqui: a sacola do site vem (oferta inversa), ou a Nice segue na conversa."""
    from . import cart_arrival, tools

    ctx = _context(conversation, binding, text)
    tools.cart_moved_away(ctx)
    site = tools.site_cart(ctx)
    if site is not None and asks_to_bring_here(text):
        result = tools.bring_site_cart(ctx)
        if not result.get("ok"):
            logger.info("concierge.site_passage.bring_refused code=%s", result.get("error"))
            return TurnOutcome(
                reply_text=BRING_REFUSED.get(str(result.get("error") or ""), BRING_UNAVAILABLE),
                layer=metrics.LAYER_CONTEXT,
            )
        return TurnOutcome(
            reply_text=cart_arrival.arrival_text(
                result, cart_text=tools.render_result("view_cart", tools.view_cart(ctx))
            ),
            layer=metrics.LAYER_CONTEXT,
            tool_events=[{"name": "bring_site_cart", "ok": True, "replayed": bool(result.get("replayed"))}],
        )
    alone = only_about_the_channel(text)
    if not (alone or _CART_WORD.search(_fold(text))):
        # "Traz 2 pães pra cá" é pedido de produto: o turno de sempre responde.
        return None
    cart = tools.view_cart(ctx)
    if cart.get("ok") and not cart.get("empty") and cart.get("lines"):
        rows = [STAY_HERE if alone else ALREADY_HERE, tools.render_result("view_cart", cart)]
    elif site is not None:
        # "Não quero o site" com a sacola lá: a Nice segue aqui e diz onde ela está, e como trazer.
        where = {"where": "no site", **tools.cart_elsewhere_summary(site)}
        rows = [STAY_HERE, _where(where, offer_back=_can_bring(conversation))]
    else:
        rows = [STAY_HERE_ASK if alone else NO_SITE_CART]
    return TurnOutcome(reply_text="\n\n".join(row for row in rows if row), layer=metrics.LAYER_CONTEXT)


def _send_site(conversation, binding, text: str) -> TurnOutcome:
    from . import tools

    ctx = _context(conversation, binding, text)
    tools.cart_moved_away(ctx)
    cart = tools.view_cart(ctx)
    has_cart = bool(cart.get("ok") and not cart.get("empty") and cart.get("lines"))
    if not has_cart and not getattr(conversation, "_commercial_authority", False):
        # Sem sacola, o link seria um acesso à conta, que pede a autoridade comercial completa
        # (a entrada sem identificador de mensagem não tem, ADR-050): vai o endereço público.
        # Com sacola, o convite vale com a autoridade de sacola e leva só a sacola (#3529).
        rows = [tools.render_result("send_web_link", {"ok": True, "url": tools.public_site_url()})]
        if tools.site_cart(ctx) is not None:
            rows.append(ALREADY_THERE)
        return TurnOutcome(
            reply_text="\n".join(rows),
            layer=metrics.LAYER_CONTEXT,
            tool_events=[{"name": "public_site_url", "ok": True, "cart_carried": False}],
        )
    result = tools.execute("send_web_link", {"destination": "checkout" if has_cart else "menu"}, ctx)
    reply = tools.render_result("send_web_link", result)
    rows = [reply]
    if result.get("ok"):
        if has_cart and not result.get("cart_carried"):
            rows.append(CART_STAYS_HERE)
        if not has_cart and tools.site_cart(ctx) is not None:
            rows.append(ALREADY_THERE)
    return TurnOutcome(
        reply_text="\n".join(rows),
        layer=metrics.LAYER_CONTEXT,
        tool_events=[{"name": "send_web_link", "ok": bool(result.get("ok")),
                      "cart_carried": bool(result.get("cart_carried"))}],
    )


def lead(conversation, binding) -> str:
    """O aviso de onde a sacola está, na mensagem seguinte ao aceite no site; vazio quando não há.

    Dito uma vez (``cart_moved_away`` esquece a chave) e só enquanto a sacola do outro
    lado está aberta. A oferta inversa vai junto só quando é possível agora (X1).
    """
    from . import tools
    from .service import transfer_bridge_channel

    moved = tools.cart_moved_away(_context(conversation, binding, ""))
    if not moved or not moved.get("open"):
        return ""
    return _where(moved, offer_back=bool(transfer_bridge_channel()) and _can_bring(conversation) and moved["site"])


def with_lead(outcome: TurnOutcome, text: str) -> TurnOutcome:
    """O aviso antes da resposta do turno; depois dela quando o turno foi só cortesia ("oi")."""
    if not text or outcome.handoff:
        return outcome
    if not outcome.reply_text:
        outcome.reply_text = text
    elif outcome.layer == metrics.LAYER_COURTESY:
        outcome.reply_text = f"{outcome.reply_text}\n\n{text}"
    else:
        outcome.reply_text = f"{text}\n\n{outcome.reply_text}"
    return outcome
