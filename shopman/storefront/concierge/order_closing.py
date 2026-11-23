"""Fechar o pedido na conversa (WP-13): do recebimento ao Pix.

Com a sacola montada (WP-12), o cliente diz "pode fechar" e a casa pergunta uma coisa por
vez, na ordem da casa (``docs/reference/cenarios-de-pedido.md``: cliente, quando,
recebimento, produtos; aqui o cliente e os produtos já estão na conversa):

1. **quando**: o dia ("hoje", "amanhã", "25/11");
2. **recebimento**: retirada ou entrega (pergunta só quando o canal oferece as duas);
3. **horário** na retirada, **endereço** na entrega (o do cadastro primeiro, e então só o
   que falta, pela régua da nota);
4. **pagamento**: as formas do canal, nunca dinheiro (D-003: dinheiro não entra no fluxo
   remoto);
5. **resumo** com o total do sistema e o código do orçamento (ADR-050): "confirmo 4821"
   fecha o pedido, e o Pix vai numa mensagem à parte.

Tudo passa pelos executores que já existem (``tools.set_fulfillment``,
``list_fulfillment_slots``, ``review_order``, ``place_order``): preço, horário, taxa, total
e código Pix vêm deles, nunca do texto. Cada fala que responde a pergunta no ar avança um
passo; a que não responde (troca de assunto) segue para as partes, e a resposta termina
com a pergunta que estava no ar (``resume``). A sacola fica como estava.

O estado mora na memória da conversa (``flags["dialogue"]["closing"]``): o dia escolhido e
a pergunta no ar. A verdade (a sacola, o recebimento, o orçamento) mora na sessão.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Perguntas no ar (``pending.kind``) que são deste fluxo. ``ask_slot``, ``ask_address`` e
# ``confirm_order`` já existiam na memória; as outras duas nascem aqui.
ASK_DATE = "ask_date"
ASK_FULFILLMENT = "ask_fulfillment"
ASK_PAYMENT = "ask_payment"

ASK_DATE_KEY = "CONCIERGE_CLOSE_ASK_DATE"
ASK_FULFILLMENT_KEY = "CONCIERGE_CLOSE_ASK_FULFILLMENT"
ASK_SLOT_KEY = "CONCIERGE_CLOSE_ASK_SLOT"
NO_SLOTS_KEY = "CONCIERGE_CLOSE_NO_SLOTS"
SLOT_REFUSED_KEY = "CONCIERGE_CLOSE_SLOT_REFUSED"
NO_PICKUP_AT_KEY = "CONCIERGE_CLOSE_NO_PICKUP_AT"
NO_DELIVERY_AT_KEY = "CONCIERGE_CLOSE_NO_DELIVERY_AT"
ASK_ADDRESS_KEY = "CONCIERGE_CLOSE_ASK_ADDRESS"
ASK_PAYMENT_KEY = "CONCIERGE_CLOSE_ASK_PAYMENT"
NO_CASH_KEY = "CONCIERGE_CLOSE_NO_CASH"
CONFIRM_CODE_KEY = "CONCIERGE_CLOSE_CONFIRM_CODE"
GAVE_UP_KEY = "CONCIERGE_CLOSE_GAVE_UP"
COPY_KEYS = (
    ASK_DATE_KEY, ASK_FULFILLMENT_KEY, ASK_SLOT_KEY, NO_SLOTS_KEY, SLOT_REFUSED_KEY, NO_PICKUP_AT_KEY,
    NO_DELIVERY_AT_KEY, ASK_ADDRESS_KEY, ASK_PAYMENT_KEY, NO_CASH_KEY, CONFIRM_CODE_KEY, GAVE_UP_KEY,
    "CONCIERGE_CART_FULFILLMENT_NOTED",
)

#: O que dá início ao fechamento quando há sacola: "pode fechar", "é só isso", "finalizar".
_START_RE = re.compile(
    r"\b(?:fecha\w*|finaliz\w*|conclu\w*|e so isso|so isso|era isso|quero pagar|vou pagar|como (?:eu )?pago)\b"
)
#: Desistir do pedido no meio do fechamento: "deixa", "desisto", "não quero mais".
_GIVE_UP_RE = re.compile(
    r"^\s*(?:nao|n)\s*[.!]*\s*$|\b(?:desist\w*|deixa (?:pra la|quieto)?|nao quero mais|esquece|cancela (?:tudo|o pedido)|melhor nao)\b"
)
_PICKUP_RE = re.compile(r"\b(?:retir\w*|busc\w*|pegar|pego|passo (?:ai|la)|balcao)\b")
_DELIVERY_RE = re.compile(r"\b(?:entreg\w*|delivery|mand\w* (?:pra|para) (?:casa|mim)|em casa)\b")
_CASH_RE = re.compile(r"\b(?:dinheiro|especie|troco)\b")
_PIX_RE = re.compile(r"\bpix\b")
_CARD_RE = re.compile(r"\b(?:cartao|credito|debito|link)\b")
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
_TIME_RE = re.compile(
    r"\b(?:as|a partir das|pelas|por volta das)\s+(\d{1,2})(?:\s*(?:h|:)\s*(\d{2})?)?\b"
    r"|\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b"
)
_LABEL_TIME_RE = re.compile(r"(\d{1,2})\s*(?:h|:)\s*(\d{2})?")
_ADDRESS_HINT_RE = re.compile(
    r"\b(?:rua|r|av|avenida|alameda|al|travessa|tv|praca|estrada|rodovia|cep|numero|n|apto|apartamento|bloco|"
    r"casa|bairro|condominio)\b|\d"
)


@dataclass
class Said:
    """O que a fala traz para o fechamento, lido sem modelo."""

    day: str = ""
    kind: str = ""
    minutes: int | None = None
    time_text: str = ""
    pick: int = 0
    payment: str = ""
    cash: bool = False
    address: str = ""
    accept_saved: bool = False
    answer: str = ""
    start: bool = False
    question: bool = False

    @property
    def anything(self) -> bool:
        return bool(
            self.day or self.kind or self.minutes is not None or self.pick or self.payment or self.cash
            or self.address or self.accept_saved or self.start
        )


@dataclass
class Step:
    """Um passo do fechamento: a frase da casa e o que a memória guarda."""

    text: str
    pending: dict | None = None
    closing: dict | None = None
    quote_token: str = ""
    extra_replies: list[str] = field(default_factory=list)
    order_ref: str = ""
    tool_events: list[dict] = field(default_factory=list)


def _fold(text: str) -> str:
    from .dialogue import _fold as fold

    return fold(text)


def _fill(template: str, **values) -> str:
    out = template or ""
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out.strip()


def _clock(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest:02d}" if rest else f"{hours}h"


def _label_minutes(label: str) -> tuple[int | None, int | None]:
    """(início, fim) em minutos do rótulo da janela ("A partir das 12h", "9h às 12h")."""
    found = _LABEL_TIME_RE.findall(_fold(label))
    times = [int(h) * 60 + int(m or 0) for h, m in found if 0 <= int(h) <= 23]
    if not times:
        return None, None
    return times[0], (times[1] if len(times) > 1 else None)


def _match_slot(slots: list[dict], minutes: int) -> dict | None:
    """A janela que cobre a hora: dentro de "9h às 12h", ou a última "a partir das" antes dela."""
    best = None
    for slot in slots:
        start, end = _label_minutes(str(slot.get("label") or ""))
        if start is None or minutes < start:
            continue
        if end is not None:
            if minutes < end:
                return slot
            continue
        if best is None or start >= (_label_minutes(str(best.get("label") or ""))[0] or 0):
            best = slot
    return best


def _parse_day(folded: str, today: date) -> str:
    if re.search(r"\bdepois de amanha\b", folded):
        return (today + timedelta(days=2)).isoformat()
    if re.search(r"\bamanha\b", folded):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\bhoje\b", folded):
        return today.isoformat()
    found = _DATE_RE.search(folded)
    if found:
        day, month = int(found.group(1)), int(found.group(2))
        try:
            when = date(today.year, month, day)
        except ValueError:
            return ""
        if when < today:
            try:
                when = date(today.year + 1, month, day)
            except ValueError:
                return ""
        return when.isoformat()
    return ""


def read(text: str, pending: dict) -> Said:
    """A fala lida contra a pergunta no ar: escolha numerada, sim/não, dia, hora, endereço."""
    from . import dialogue

    folded = _fold(text)
    tokens = dialogue.words(text)
    said = Said(answer=dialogue.answer_kind(tokens), start=bool(_START_RE.search(folded)), question="?" in str(text or ""))
    said.day = _parse_day(folded, timezone.localdate())
    if _PICKUP_RE.search(folded):
        said.kind = "pickup"
    elif _DELIVERY_RE.search(folded):
        said.kind = "delivery"
    time_match = _TIME_RE.search(folded)
    if time_match and not _DATE_RE.search(time_match.group(0)):
        hours = int(time_match.group(1) or time_match.group(3))
        minutes = int(time_match.group(2) or time_match.group(4) or 0)
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            said.minutes = hours * 60 + minutes
            said.time_text = _clock(said.minutes)
    if _CASH_RE.search(folded):
        said.cash = True
    elif _PIX_RE.search(folded):
        said.payment = "pix"
    elif _CARD_RE.search(folded):
        said.payment = "card"
    kind = pending.get("kind", "")
    options = pending.get("options") or []
    if options:
        said.pick = dialogue.selection(tokens, len(options))
        if not said.pick and said.answer in {"yes", "weak_yes"} and len(options) == 1:
            said.pick = 1
    if kind == "ask_address":
        if pending.get("offer") and said.answer in {"yes", "weak_yes"}:
            said.accept_saved = True
        elif not said.answer and _ADDRESS_HINT_RE.search(folded) and not said.day:
            said.address = " ".join(str(text or "").split())
    return said


#: "retirar" que é RECEBIMENTO, não tirar da sacola: "para/pra/vou/de retirar", "retirada".
_PICKUP_INTENT_RE = re.compile(r"\b(?:(?:para|pra|vou|de|pode|posso|quero) retir\w*|retirada)\b")


def fulfillment_cue(text: str) -> bool:
    """A fala diz QUANDO ou COMO recebe (dia, hora, retirada): "retirar" aí é recebimento.

    WP-14, cartão 1 (dono, 22/11/2026): "quero 2 croissants para retirar amanhã às 16h"
    virou "tira o croissant da sacola". Sem dia, hora nem "para retirar", "retira o
    croissant" continua sendo tirar da sacola.
    """
    folded = _fold(text)
    said = read(text, {})
    return bool(_PICKUP_INTENT_RE.search(folded) or said.day or said.minutes is not None
                or (said.kind == "pickup" and not re.search(r"\b(?:tira|tirar|tire|retira) (?:o|a|os|as)\b", folded)))


def prefill(conversation, text: str, *, binding, channel_ref: str) -> dict:
    """O dia, o recebimento e o horário ditos JUNTO com o pedido, aplicados antes da sacola.

    A casa dita a ordem da encomenda (quando, recebimento, produtos), mas o cliente pode
    dizer tudo de uma vez. Aqui se aplica o que ele disse, pelos executores de sempre
    (``set_fulfillment``, os horários da loja): a sacola passa a medir a fornada DA DATA
    (nunca a sobra de hoje), e o fechamento não pergunta de novo o que já foi dito. Nada
    que falte é inventado: sem dia, não se aplica nada; horário que a loja não tem fica
    para o fechamento perguntar. Devolve o que ficou aplicado (``day``, ``kind``, ``slot``).
    """
    from . import tools

    said = read(text, {})
    if not said.day:
        return {}
    types = _fulfillment_types(channel_ref)
    kind = said.kind if said.kind in types else ("pickup" if said.minutes is not None and "pickup" in types else "")
    if not kind and len(types) == 1:
        kind = types[0]
    if not kind:
        return {}
    ctx = _context(conversation, binding=binding, channel_ref=channel_ref, text=text)
    # Na primeira fala ainda não há sacola: ela nasce aqui, como nasceria no item, para a
    # data valer já na medida do item (a mesma sacola, presa ao telefone).
    tools._ensure_session(ctx)
    result = tools.execute("set_fulfillment", {"fulfillment_type": kind, "delivery_date": said.day}, ctx)
    if not result.get("ok"):
        return {}
    applied = {"day": said.day, "kind": kind, "slot": ""}
    if kind == "pickup" and said.minutes is not None:
        listing = tools.execute("list_fulfillment_slots", {"delivery_date": said.day, "fulfillment_type": "pickup"}, ctx)
        chosen = _match_slot(list(listing.get("pickup_slots") or []), said.minutes)
        if chosen is not None and chosen.get("available", True):
            done = tools.execute("set_fulfillment", {"fulfillment_type": "pickup", "delivery_date": said.day,
                                                     "slot_ref": chosen["ref"]}, ctx)
            if done.get("ok"):
                applied["slot"] = str(chosen.get("label") or "")
    return applied


NOTED_KEY = "CONCIERGE_CART_FULFILLMENT_NOTED"


def noted(applied: dict, *, copy) -> str:
    """ "Combinado: retirada amanhã, a partir das 15h." O que ``prefill`` aplicou, dito de volta."""
    if not applied:
        return ""
    today = timezone.localdate()
    day = date.fromisoformat(applied["day"])
    when = {today: "hoje", today + timedelta(days=1): "amanhã"}.get(day) or day.strftime("%d/%m")
    slot = str(applied.get("slot") or "").strip()
    if slot:
        when = f"{when}, {slot[:1].lower()}{slot[1:]}"
    how = "retirada" if applied.get("kind") == "pickup" else "entrega"
    return _fill(copy(NOTED_KEY) or "", how=how, when=when)


def answers(said: Said, pending: dict) -> bool:
    """A fala responde à pergunta do fechamento que está no ar?"""
    kind = pending.get("kind", "")
    if said.start:
        return True
    if not said.question and (said.day or said.kind or said.minutes is not None):
        # Mudar o dia, o recebimento ou a hora vale em qualquer passo ("na verdade, às 10h").
        # Pergunta não é resposta: "vocês abrem amanhã?" segue para as partes.
        return True
    if kind == ASK_DATE:
        return bool(said.day)
    if kind == ASK_FULFILLMENT:
        return bool(said.kind or said.pick)
    if kind == "ask_slot":
        return bool(said.pick or said.minutes is not None or said.day or said.kind)
    if kind == "ask_address":
        return bool(said.address or said.accept_saved or said.kind)
    if kind == ASK_PAYMENT:
        return bool(said.payment or said.cash or said.pick)
    if kind == "confirm_order":
        return False  # a confirmação tem o caminho dela (``confirm``)
    return False


# ── O passo ──────────────────────────────────────────────────────────


def _methods(channel_ref: str) -> list[str]:
    from shopman.shop.config import ChannelConfig

    return [m for m in ChannelConfig.for_channel(channel_ref).payment.available_methods if m != "cash"]


def _fulfillment_types(channel_ref: str) -> list[str]:
    from shopman.shop.services.channel_policy import resolve_channel_policy

    from .tools import FULFILLMENT_TYPES

    return [t for t in resolve_channel_policy(channel_ref).fulfillment_types if t in FULFILLMENT_TYPES]


def _options(rows: list[dict]) -> list[dict]:
    return [{"n": n, "ref": row["ref"], "name": row["name"]} for n, row in enumerate(rows, 1)]


def _options_text(options: list[dict]) -> str:
    from .dialogue import _options_text as text

    return text(options)


def _event(name: str, result: dict) -> dict:
    return {"name": name, "input": {}, "ok": bool(result.get("ok", True))}


def advance(ctx, said: Said, closing: dict, *, copy) -> Step | None:
    """O próximo passo do fechamento com o que a fala trouxe. ``None``: não há sacola."""
    from . import tools

    session = tools._open_session(ctx)
    if session is None or not (session.items or []):
        return None
    # ``open`` marca o fechamento em curso: a memória descarta dicionário vazio.
    closing = {**(closing or {}), "open": True}
    data = session.data or {}
    # O que o cliente já disse junto com o pedido (``prefill``) está na sessão: o
    # fechamento parte dali e não pergunta de novo o dia nem o recebimento.
    if not closing.get("day") and data.get("delivery_date") and data.get("fulfillment_type"):
        closing["day"] = str(data["delivery_date"])
        closing["kind"] = str(data["fulfillment_type"])
        closing["applied"] = f"{closing['kind']}:{closing['day']}"
    events: list[dict] = []
    channel_ref = ctx.channel_ref

    # 1. Quando.
    day = said.day or closing.get("day") or ""
    if not day:
        return Step(copy(ASK_DATE_KEY), pending={"kind": ASK_DATE}, closing=closing)
    if day != closing.get("day"):
        closing.pop("applied", None)
    closing["day"] = day

    # 2. Recebimento.
    types = _fulfillment_types(channel_ref)
    kind = said.kind or closing.get("kind") or ""
    if not kind and said.pick and closing.get("asked") == ASK_FULFILLMENT and 1 <= said.pick <= len(types):
        kind = types[said.pick - 1]
    if not kind and len(types) == 1:
        kind = types[0]
    if not kind:
        options = _options([{"ref": t, "name": "retirada na loja" if t == "pickup" else "entrega"} for t in types])
        closing["asked"] = ASK_FULFILLMENT
        return Step(copy(ASK_FULFILLMENT_KEY), pending={"kind": ASK_FULFILLMENT, "options": options}, closing=closing)
    if kind != closing.get("kind"):
        closing.pop("applied", None)
    closing["kind"] = kind
    applied = closing.get("applied") == f"{kind}:{day}" and data.get("fulfillment_type") == kind

    # 3. Horário (retirada) ou endereço (entrega).
    if kind == "pickup":
        step = _pickup(ctx, said, closing, day=day, applied=applied, data=data, copy=copy, events=events)
    else:
        step = _delivery(ctx, said, closing, day=day, applied=applied, copy=copy, events=events)
    if step is not None:
        step.tool_events = events + step.tool_events
        return step

    # 4. Pagamento (nunca dinheiro, D-003).
    methods = _methods(channel_ref)
    options = _options([{"ref": m, "name": tools.PAYMENT_LABELS.get(m, m)} for m in methods])
    method = said.payment if said.payment in methods else ""
    if not method and said.pick and closing.get("asked") == ASK_PAYMENT and 1 <= said.pick <= len(methods):
        method = methods[said.pick - 1]
    current = str(((data.get("payment") or {}).get("method")) or "")
    method = method or (current if current in methods else "") or (methods[0] if len(methods) == 1 else "")
    if said.cash and not said.payment:
        closing["asked"] = ASK_PAYMENT
        return Step(_fill(copy(NO_CASH_KEY), options=_options_text(options)),
                    pending={"kind": ASK_PAYMENT, "options": options}, closing=closing, tool_events=events)
    if not method:
        closing["asked"] = ASK_PAYMENT
        return Step(_fill(copy(ASK_PAYMENT_KEY), options=_options_text(options)),
                    pending={"kind": ASK_PAYMENT, "options": options}, closing=closing, tool_events=events)

    # 5. O resumo: o total e o código são do sistema.
    review = tools.execute("review_order", {"payment_method": method}, ctx)
    events.append(_event("review_order", review))
    text = tools.render_result("review_order", review)
    closing["asked"] = "confirm_order"
    if review.get("ok") and review.get("ready") and review.get("quote_token"):
        token = str(review["quote_token"])
        return Step(text, pending={"kind": "confirm_order", "token": token}, closing=closing,
                    quote_token=token, tool_events=events)
    missing = list(review.get("missing") or [])
    if {"delivery_address", "delivery_address_details"} & set(missing):
        closing.pop("applied", None)
        return Step(text, pending={"kind": "ask_address", "day": day}, closing=closing, tool_events=events)
    if {"delivery_date", "delivery_time_slot"} & set(missing):
        closing.pop("applied", None)
        closing.pop("day", None)
        return Step(text, pending={"kind": ASK_DATE}, closing=closing, tool_events=events)
    return Step(text, pending=None, closing=closing, tool_events=events)


def _slot_question(slots: list[dict], *, copy) -> tuple[str, list[dict]]:
    options = _options([{"ref": s["ref"], "name": s["label"]} for s in slots if s.get("available", True)])
    return _fill(copy(ASK_SLOT_KEY), options=_options_text(options)), options


def _pickup(ctx, said: Said, closing: dict, *, day: str, applied: bool, data: dict, copy, events) -> Step | None:
    from . import tools

    if not applied:
        result = tools.execute("set_fulfillment", {"fulfillment_type": "pickup", "delivery_date": day}, ctx)
        events.append(_event("set_fulfillment", result))
        if not result.get("ok"):
            # A data não serve (sem fornada, fechado): o motivo é o do sistema.
            closing.pop("day", None)
            return Step(" ".join(p for p in (tools.render_result("set_fulfillment", result), copy(ASK_DATE_KEY)) if p),
                        pending={"kind": ASK_DATE}, closing=closing)
        closing["applied"] = f"pickup:{day}"
        data = {}
    slot_ref = str(data.get("delivery_time_slot") or "") if applied else ""
    listing = tools.execute("list_fulfillment_slots", {"delivery_date": day, "fulfillment_type": "pickup"}, ctx)
    events.append(_event("list_fulfillment_slots", listing))
    slots = list(listing.get("pickup_slots") or [])
    question, options = _slot_question(slots, copy=copy)
    chosen = None
    if said.minutes is not None:
        chosen = _match_slot(slots, said.minutes)
        if chosen is None:
            closing["asked"] = "ask_slot"
            return Step(" ".join(p for p in (_fill(copy(NO_PICKUP_AT_KEY), time=said.time_text), question) if p),
                        pending={"kind": "ask_slot", "options": options, "day": day}, closing=closing)
    elif said.pick and closing.get("asked") == "ask_slot" and 1 <= said.pick <= len(options):
        ref = options[said.pick - 1]["ref"]
        chosen = next((s for s in slots if s.get("ref") == ref), None)
    if chosen is not None:
        if not chosen.get("available", True):
            closing["asked"] = "ask_slot"
            refused = _fill(copy(SLOT_REFUSED_KEY), slot=chosen.get("label", ""), reason=str(chosen.get("reason") or "").rstrip("."))
            return Step(" ".join(p for p in (refused, question) if p),
                        pending={"kind": "ask_slot", "options": options, "day": day}, closing=closing)
        result = tools.execute(
            "set_fulfillment", {"fulfillment_type": "pickup", "delivery_date": day, "slot_ref": chosen["ref"]}, ctx,
        )
        events.append(_event("set_fulfillment", result))
        if not result.get("ok"):
            closing["asked"] = "ask_slot"
            return Step(" ".join(p for p in (tools.render_result("set_fulfillment", result), question) if p),
                        pending={"kind": "ask_slot", "options": options, "day": day}, closing=closing)
        return None
    if slot_ref:
        return None
    if not options:
        closing.pop("day", None)
        closing.pop("applied", None)
        return Step(copy(NO_SLOTS_KEY), pending={"kind": ASK_DATE}, closing=closing)
    closing["asked"] = "ask_slot"
    return Step(question, pending={"kind": "ask_slot", "options": options, "day": day}, closing=closing)


def _delivery(ctx, said: Said, closing: dict, *, day: str, applied: bool, copy, events) -> Step | None:
    from . import tools

    arguments: dict = {"fulfillment_type": "delivery", "delivery_date": day}
    picked = said.pick if closing.get("asked") == "ask_slot" else 0
    if said.minutes is not None or picked:
        listing = tools.execute("list_fulfillment_slots", {"delivery_date": day, "fulfillment_type": "delivery"}, ctx)
        events.append(_event("list_fulfillment_slots", listing))
        # Só a janela que a casa oferece: a riscada (preparo, prazo de aceite) não se escolhe.
        windows = [w for w in listing.get("delivery_slots") or [] if w.get("available", True)]
        if said.minutes is not None:
            chosen = _match_slot(windows, said.minutes)
        else:
            chosen = windows[picked - 1] if 1 <= picked <= len(windows) else None
        if chosen is None:
            # Fora das janelas de entrega: o motivo é a grade da casa, com as janelas do dia.
            options = _options([{"ref": w["ref"], "name": w["label"]} for w in windows])
            closing["asked"] = "ask_slot"
            return Step(_fill(copy(NO_DELIVERY_AT_KEY), time=said.time_text or "nesse horário", windows=_options_text(options)),
                        pending={"kind": "ask_slot", "options": options, "day": day}, closing=closing)
        arguments["slot_ref"] = chosen["ref"]
        closing["asked"] = ""
    if said.address:
        arguments["address"] = said.address
    if said.accept_saved:
        arguments["use_saved_address"] = True
    if applied and len(arguments) == 2:
        return None
    result = tools.execute("set_fulfillment", arguments, ctx)
    events.append(_event("set_fulfillment", result))
    if not result.get("ok"):
        message = tools.render_result("set_fulfillment", result)
        if result.get("error") in {"validation"} and "delivery_address" not in (result.get("errors") or {}):
            closing.pop("day", None)
            closing.pop("applied", None)
            return Step(" ".join(p for p in (message, copy(ASK_DATE_KEY)) if p), pending={"kind": ASK_DATE}, closing=closing)
        return Step(message or copy(ASK_ADDRESS_KEY), pending={"kind": "ask_address", "day": day}, closing=closing)
    if result.get("code") in {"saved_address_offer", "saved_addresses"}:
        return Step(str(result.get("message") or ""), pending={"kind": "ask_address", "day": day, "offer": True},
                    closing=closing)
    closing["applied"] = f"delivery:{day}"
    if result.get("message"):  # fora da área de entrega
        closing.pop("applied", None)
        return Step(" ".join(p for p in (str(result["message"]), copy(ASK_ADDRESS_KEY)) if p),
                    pending={"kind": "ask_address", "day": day}, closing=closing)
    if result.get("address_question"):
        return Step(str(result["address_question"]), pending={"kind": "ask_address", "day": day}, closing=closing)
    return None


# ── A confirmação ────────────────────────────────────────────────────


def confirm(ctx, quote: dict, *, copy) -> Step:
    """"confirmo 4821": o pedido pelo ``place_order``, que confere o código (ADR-050)."""
    from . import tools

    token = str(quote.get("token") or "")
    result = tools.execute(
        "place_order", {"quote_token": token, "payment_method": str(quote.get("payment_method") or "")}, ctx,
    )
    events = [_event("place_order", result)]
    if result.get("ok"):
        return Step(tools.render_result("place_order", result), pending=None, closing=None,
                    extra_replies=list(ctx.extra_replies), order_ref=str(result.get("order_ref") or ""),
                    tool_events=events)
    if result.get("error") == "confirmation_required":
        # A pergunta leva o token: ela passa a ser o resumo oferecido, e o "confirmo" que
        # vier depois dela vale (o ``_code_confirmation`` lê só o que veio depois da oferta).
        return Step(_fill(copy(CONFIRM_CODE_KEY), code=tools.offered_quote_code(ctx.conversation, token)),
                    pending={"kind": "confirm_order", "token": token}, closing={"asked": "confirm_order"},
                    quote_token=token, tool_events=events)
    return Step(tools.render_result("place_order", result), pending=None, closing={}, tool_events=events)


def _confirms(text: str, token: str) -> bool:
    """A fala é uma tentativa de confirmar: tem "confirm", "sim", ou só o número."""
    folded = _fold(text)
    return bool(re.search(r"\b(?:confirm\w*|sim|fechado|pode registrar)\b", folded) or re.fullmatch(r"\s*\d{4}\s*", folded))


# ── O turno ──────────────────────────────────────────────────────────


def _context(conversation, *, binding, channel_ref: str, text: str):
    from .tools import ToolContext

    return ToolContext(
        conversation=conversation, channel_ref=channel_ref,
        provider=str(getattr(binding, "provider", "") or ""), account=str(getattr(binding, "account", "") or ""),
        transport_channel=str(getattr(binding, "transport_channel", "") or ""),
        connection_key=str(getattr(binding, "connection_key", "") or ""), customer_text=text,
    )


def _memo(step: Step) -> dict:
    return {"tool": "order_closing", "pending": step.pending, "closing": step.closing}


def _outcome(step: Step, *, memory, memos):
    from .metrics import LAYER_CONTEXT
    from .turn_outcome import TurnOutcome

    return TurnOutcome(
        reply_text=step.text, layer=LAYER_CONTEXT, memory=memory, memory_memos=[*memos, _memo(step)],
        quote_token=step.quote_token, extra_replies=step.extra_replies, order_ref=step.order_ref,
        tool_events=step.tool_events,
    )


#: O "pode fechar" dentro de uma fala com mais coisa ("quero 2 croissant e pode fechar"), no texto original.
_START_PHRASE_RE = re.compile(
    r"[,;.]?\s*(?:\be\s+)?(?:\bj[aá]\s+)?(?:\bpode\s+(?:j[aá]\s+)?)?"
    r"(?:\bfecha\w*|\bfinaliz\w*|\bconclu\w*)(?:\s+(?:o|meu)\s+pedido)?"
    r"|[,;.]?\s*(?:\be\s+)?[eé]\s+s[oó]\s+isso\b|[,;.]?\s*(?:\be\s+)?\bera\s+isso\b",
    re.IGNORECASE,
)
_REST_FILLER = {"e", "ok", "entao", "por", "favor", "pfv", "obrigado", "obrigada", "isso", "so", "ja", "pode", "a", "o"}


def split_start(text: str) -> str | None:
    """O resto da fala quando o "pode fechar" vem junto de outro pedido (#2990); ``None`` quando é só fechar.

    "quero 2 croissant e pode fechar" → "quero 2 croissant": as partes põem o item na sacola e o
    fechamento começa no fim do mesmo turno (``resume``). Sem o pedido junto, o fechamento é o turno.
    """
    if not _START_RE.search(_fold(text)):
        return None
    rest = _START_PHRASE_RE.sub(" ", str(text or ""))
    words = [w for w in re.findall(r"[a-z0-9]+", _fold(rest)) if w not in _REST_FILLER]
    return " ".join(rest.split()).strip(" ,;.") if words else None


def handle(conversation, text: str, *, binding, channel_ref: str, memory, memos=(), copy=None):
    """O turno do fechamento, ou ``None`` quando a fala não é dele (segue para as partes)."""
    from .intents import _cart_authorized

    if conversation is None or not _cart_authorized(conversation):
        return None
    if memory.state.get("closing") is None:
        rest = split_start(text)
        if rest is not None:
            # Item e "pode fechar" na mesma fala: primeiro a sacola, o fechamento no fim (#2990).
            conversation._closing_after_parts = rest
            return None
    if not memory.facts.cart:
        return None
    if copy is None:
        from .service import copy_message as copy
    pending = memory.state.get("pending") or {}
    closing = memory.state.get("closing")
    if closing is not None and _GIVE_UP_RE.search(_fold(text)):
        # Desistiu: nada é registrado, a sacola fica como está (para quem mudar de ideia).
        return _outcome(Step(copy(GAVE_UP_KEY), pending=None, closing=None), memory=memory, memos=list(memos))
    if pending.get("kind") == "confirm_order" and closing is not None:
        quote = conversation.quote or {}
        if quote.get("token") == pending.get("token") and _confirms(text, str(pending.get("token") or "")):
            ctx = _context(conversation, binding=binding, channel_ref=channel_ref, text=text)
            return _outcome(confirm(ctx, quote, copy=copy), memory=memory, memos=list(memos))
    said = read(text, pending if closing is not None else {})
    if closing is None:
        if not said.start:
            return None
        closing = {}
    elif not answers(said, pending):
        return None
    ctx = _context(conversation, binding=binding, channel_ref=channel_ref, text=text)
    step = advance(ctx, said, closing, copy=copy)
    if step is None:
        return None
    return _outcome(step, memory=memory, memos=list(memos))


def resume(conversation, outcome, *, binding, channel_ref: str, memory, copy=None):
    """Troca de assunto no meio do fechamento: a resposta das partes termina com a pergunta no ar."""
    from .intents import _cart_authorized

    closing = memory.state.get("closing")
    if closing is None and conversation is not None and getattr(conversation, "_closing_after_parts", None):
        closing = {}  # o "pode fechar" da mesma fala: começa agora, com a sacola já com o item
    if closing is None or outcome.handoff or not outcome.reply_text or conversation is None:
        return outcome
    if not _cart_authorized(conversation):
        return outcome
    if copy is None:
        from .service import copy_message as copy
    ctx = _context(conversation, binding=binding, channel_ref=channel_ref, text="")
    if not memory.state.get("closing"):
        from . import tools

        if not (tools.execute("view_cart", {}, ctx).get("lines")):
            return outcome  # o item não entrou: sem sacola, nada a fechar
    try:
        step = advance(ctx, Said(), closing, copy=copy)
    except Exception:
        logger.warning("concierge.order_closing.resume_failed conversation=%s", conversation.pk, exc_info=True)
        return outcome
    if step is None:
        outcome.memory_memos = [*outcome.memory_memos, {"tool": "order_closing", "closing": None}]
        return outcome
    outcome.reply_text = f"{outcome.reply_text}\n\n{step.text}" if step.text else outcome.reply_text
    outcome.quote_token = step.quote_token or outcome.quote_token
    outcome.tool_events = [*outcome.tool_events, *step.tool_events]
    outcome.memory_memos = [*outcome.memory_memos, _memo(step)]
    return outcome
