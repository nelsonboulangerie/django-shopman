"""Alterar o pedido já feito na conversa (OC-11, Etapa III omnicanal, DEV-2026-085).

"Troca o horário", "tira um item", "troca o endereço": a Nice resolve quando o pedido
ainda aceita a mudança, pelo MESMO serviço do balcão (``shop.services.order_edit``), sem
regra própria (X16):

- a porta: ``order_edit.state_refusal`` (até "em preparo", sem NFC-e autorizada, fora do
  iFood); a data e o horário pela régua do reagendar (``reschedule``), que o
  ``order_edit.plan`` já chama;
- o horário oferecido: a grade que o cliente escolhe sozinho no site, para os itens do
  pedido (``pickup_slots.annotate_*_for_checkout``), com o motivo quando a janela está
  fechada;
- o endereço: montado como no fechamento do pedido (``concierge/address.py``), e a taxa
  sai do motor da venda (``pos.resolve_delivery_fee``, dentro de ``order_edit.plan``);
- o dinheiro: o que o ``order_edit`` decide. A diferença a mais fica a pagar na retirada
  ou na entrega. Devolução precisa do gerente, e cobrança digital aberta com o valor antigo
  trava a mudança: aí a Nice diz o motivo e chama a equipe com o contexto.

Antes de aplicar, o efeito (o horário, o item que sai, o endereço, a taxa e o total) e o
código de confirmação, como no pedido (ADR-050): "confirmo 1234". O código sai da prévia;
se o pedido mudou entre a pergunta e o código (X5), o código antigo não aplica e a prévia
nova vai com outro código. A mesma confirmação de novo não aplica duas vezes (X4).

O que está no ar mora em ``Conversation.flags["pending_amendment"]``
(``docs/reference/data-schemas.md``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

RESCHEDULE = "reschedule_order"
REMOVE_ITEM = "remove_item"
CHANGE_ADDRESS = "change_address"
KINDS = (RESCHEDULE, REMOVE_ITEM, CHANGE_ADDRESS)

PENDING_FLAG = "pending_amendment"
#: A pergunta (e a confirmação dada) vale por este tempo.
PENDING_TTL = timedelta(minutes=30)
ACTOR = "concierge"
HISTORY_NOTE = "Pedido alterado pela Concierge a pedido do cliente"

STAGE_ASK = "ask"
STAGE_CONFIRM = "confirm"
STAGE_APPLIED = "applied"

#: Recusas em que a Nice não tem como seguir sozinha e a equipe tem: o dinheiro que o
#: serviço não move sem gente (devolução com gerente, cobrança aberta com o valor antigo,
#: forma de receber na porta) e a nota já emitida (cancelar e refazer é do balcão).
TEAM_CODES = frozenset({
    "manager_approval_required",
    "open_digital_charge",
    "delivery_payment_method_required",
    "mixed_payment_refund",
    "on_account_total_locked",
    "split_pending_tenders",
    "payment_unreadable",
    "pix_paid_meanwhile",
    "open_pix_not_cancelled",
    "fiscal_authorized",
    "activation_running",
})


def _fold(text: str) -> str:
    from .dialogue import _fold as fold

    return " ".join(fold(text).split())


# ── A fala ────────────────────────────────────────────────────────────

_CHANGE = r"(?:troc\w*|mud\w*|alter\w*|remarc\w*|passa|passar|adia\w*|antecip\w*|corrig\w*|muda)"
_WHEN_NOUN = r"(?:horario|hora|data|dia|retirada|entrega)"
_RESCHEDULE_RE = re.compile(rf"\b{_CHANGE}\b.{{0,40}}\b{_WHEN_NOUN}\b|\b{_WHEN_NOUN}\b.{{0,20}}\b{_CHANGE}\b|\bremarc\w*\b")
_ADDRESS_RE = re.compile(rf"\bendereco\b.{{0,40}}\b{_CHANGE}\b|\b{_CHANGE}\b.{{0,40}}\bendereco\b|\b(?:outro|novo)\s+endereco\b|\bendereco\s+(?:novo|outro)\b")
_REMOVE_RE = re.compile(r"\b(?:tira|tirar|tire|tirem|remove|remover|remova|exclui|excluir|exclua|retira|retirar|retire)\b")
_ORDER_CUE_RE = re.compile(r"\b(?:pedido|encomenda)\b")
#: "do meu pedido", "da encomenda": o fim da fala que só diz de onde tirar.
_FROM_ORDER_RE = re.compile(r"\b(?:d[oa]s?|n[oa]s?)\s+(?:meu\s+|minha\s+|esse\s+|essa\s+|ultimo\s+|ultima\s+)?(?:pedido|encomenda)\b.*$")
_ADDRESS_TAIL_RE = re.compile(r"\b(?:para|pra|p/)\s+(?:o\s+|a\s+)?(.+)$|:\s*(.+)$|\b(?:e|é)\s+(?:na\s+|no\s+|a\s+|o\s+)?(.+)$", re.I | re.S)
_NUMBER_WORDS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6}
_ITEM_FILLER = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "e", "por", "favor", "pfv", "so",
                "me", "pra", "para", "mim", "ai", "isso", "esse", "essa", "item", "itens"}


@dataclass
class Request:
    """O que o cliente pediu para mudar, lido sem modelo."""

    kind: str
    #: Remarcar: o dia (ISO), a hora (minutos) e a escolha numerada.
    day: str = ""
    minutes: int | None = None
    time_text: str = ""
    pick: int = 0
    #: Tirar: o que o cliente disse do item e quantas unidades (0 = a linha inteira).
    item: str = ""
    qty: int = 0
    #: Trocar o endereço: o texto do endereço novo, e o endereço montado na prévia (a
    #: confirmação aplica o MESMO endereço, sem geocodificar de novo).
    address: str = ""
    structured: dict = field(default_factory=dict)

    def args(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if value not in ("", None, 0) and value != {}}


def read(text: str, *, kind: str = "", options: list | None = None) -> Request | None:
    """A fala como alteração do pedido, ou ``None`` quando ela não pede alteração.

    ``kind`` vem da pergunta no ar ("Qual horário?", "Qual item?"): aí a fala é a resposta
    e não precisa repetir o verbo.
    """
    from . import order_closing

    folded = _fold(text)
    if not folded:
        return None
    answering = bool(kind)
    if not kind:
        if _ADDRESS_RE.search(folded):
            kind = CHANGE_ADDRESS
        elif _REMOVE_RE.search(folded) and _ORDER_CUE_RE.search(folded) and not _pickup_cue(folded):
            kind = REMOVE_ITEM
        elif _RESCHEDULE_RE.search(folded) and _ORDER_CUE_RE.search(folded):
            kind = RESCHEDULE
        else:
            return None
    request = Request(kind)
    if kind == RESCHEDULE:
        said = order_closing.read(text, {"options": options or []})
        request.day, request.minutes, request.time_text, request.pick = said.day, said.minutes, said.time_text, said.pick
    elif kind == REMOVE_ITEM:
        request.item, request.qty = _item_said(folded, options or [])
    else:
        # Respondendo a "Qual é o endereço novo?", a fala inteira é o endereço.
        request.address = _address_said(text) or (" ".join(str(text or "").split()) if answering else "")
    return request


def _pickup_cue(folded: str) -> bool:
    from . import order_closing

    return bool(re.search(r"\bretir\w*\b", folded)) and order_closing.fulfillment_cue(folded)


def _item_said(folded: str, options: list) -> tuple[str, int]:
    from . import dialogue

    tokens = dialogue.words(folded)
    if options:
        pick = dialogue.selection(tokens, len(options))
        if pick:
            return str(options[pick - 1].get("name") or ""), 0
    match = _REMOVE_RE.search(folded)
    rest = folded[match.end():] if match else folded
    rest = _FROM_ORDER_RE.sub("", rest)
    words = dialogue.words(rest)
    qty = 0
    kept = []
    for index, word in enumerate(words):
        if not qty and word.isdigit() and len(word) <= 2:
            qty = int(word)
        elif not qty and index == 0 and word in _NUMBER_WORDS and word not in {"um", "uma"}:
            qty = _NUMBER_WORDS[word]
        elif not qty and index == 0 and word in {"um", "uma"}:
            qty = 1
        elif word not in _ITEM_FILLER:
            kept.append(word)
    return " ".join(kept), qty


def _address_said(text: str) -> str:
    """O endereço novo dito depois de "endereço ... para", "endereço: ..." ou "o novo é ..."."""
    raw = " ".join(str(text or "").split())
    found = re.search(r"endere[cç]o", raw, re.I)
    tail = raw[found.end():] if found else raw
    match = _ADDRESS_TAIL_RE.search(tail)
    if not match:
        return ""
    address = next((group for group in match.groups() if group), "")
    return address.strip(" .,;")


# ── O pedido ──────────────────────────────────────────────────────────


@dataclass
class Result:
    """O que a ferramenta devolve: o código, o texto da Nice e o que a conversa guarda."""

    code: str
    order_ref: str = ""
    lead: str = ""
    lines: list[str] = field(default_factory=list)
    confirm_code: str = ""
    team: bool = False
    team_reason: str = ""
    #: A pergunta que fica no ar (``flags["pending_amendment"]``) quando falta o que mudar.
    pending: dict | None = None
    #: O que segue em mensagem própria: o código Pix novo (OC-05), para copiar.
    copies: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": True,
            "code": self.code,
            "order_ref": self.order_ref,
            "lead": self.lead,
            "lines": list(self.lines),
            "confirm_code": self.confirm_code,
            "team": self.team,
            "team_reason": self.team_reason,
            "order_found": bool(self.order_ref),
            "copies": list(self.copies),
        }


def _target(conversation, text: str, order_ref: str = ""):
    """``(pedido, recusa)``: o pedido do cliente de que se fala, ou por que não há um só.

    O citado (inteiro ou o código do fim), o único em andamento, ou, sem nenhum em
    andamento, o mais recente (para dizer por que ele não muda mais). Só pedido do
    próprio cliente, pela identidade da conversa.
    """
    from shopman.orderman.models import Order

    from shopman.shop.services.customer_orders import customer_identity_filter

    from . import cancellation, tools

    order = cancellation.target_order(conversation, text, order_ref=order_ref)
    if order is not None:
        return order, None
    identity = customer_identity_filter(
        customer_ref=conversation.customer_ref or None, phone=conversation.phone or None
    )
    if identity is None:
        return None, Result("no_order", lead=tools.AMEND_REFUSED["no_order"])
    orders = list(Order.objects.filter(identity).distinct().order_by("-created_at")[:10])
    if order_ref:
        wanted = str(order_ref).strip().upper()
        orders = [o for o in orders if o.ref.upper() == wanted or o.ref.upper().rsplit("-", 1)[-1] == wanted]
    open_orders = [o for o in orders if o.status not in Order.TERMINAL_STATUSES]
    if len(open_orders) > 1:
        refs = " e ".join(o.ref for o in open_orders[:3])
        return None, Result("many_orders", lead=tools.AMEND_REFUSED["many_orders"].format(refs=refs))
    if orders:
        return orders[0], None
    return None, Result("no_order", lead=tools.AMEND_REFUSED["no_order"])


def _refresh(order) -> None:
    try:
        from shopman.storefront.services.orders import resolve_timeouts_if_due

        resolve_timeouts_if_due(order)
    except Exception:
        logger.warning("concierge.amend: timeout resolution failed order=%s", order.ref, exc_info=True)
    order.refresh_from_db()


def _when_words(day_iso: str) -> str:
    from . import order_closing

    try:
        return order_closing.day_word(date.fromisoformat(day_iso))
    except ValueError:
        return order_closing.day_word(timezone.localdate())


def _mode(order) -> str:
    return "delivery" if str((order.data or {}).get("fulfillment_type") or "") == "delivery" else "pickup"


def _slots(order, day_iso: str) -> list[dict]:
    """A grade que o cliente escolhe sozinho para os itens do pedido, nesse dia, com o motivo."""
    from shopman.shop.services import order_composition
    from shopman.storefront.services.pickup_slots import (
        annotate_delivery_windows_for_checkout,
        annotate_slots_for_checkout,
    )

    skus = [str(item.sku) for item in order_composition.effective_items(order) if not str(item.sku).startswith("__")]
    try:
        if _mode(order) == "delivery":
            rows = annotate_delivery_windows_for_checkout(skus, delivery_date=day_iso, channel_ref=order.channel_ref).get("windows") or []
        else:
            rows = annotate_slots_for_checkout(skus, delivery_date=day_iso, channel_ref=order.channel_ref).get("pickup_slots") or []
    except Exception:
        logger.warning("concierge.amend: slots unavailable order=%s day=%s", order.ref, day_iso, exc_info=True)
        return []
    return [
        {"ref": str(row.get("ref") or ""), "label": str(row.get("label") or ""),
         "available": bool(row.get("enabled")), "reason": str(row.get("reason") or "")}
        for row in rows if row.get("ref")
    ]


def _slot_options(slots: list[dict]) -> list[dict]:
    return [{"n": index, "ref": slot["ref"], "name": slot["label"]}
            for index, slot in enumerate((s for s in slots if s["available"]), start=1)]


def _options_text(options: list[dict]) -> str:
    return "; ".join(f"{option['n']}) {option['name']}" for option in options)


def _ask(order, kind: str, lead: str, *, options=None) -> Result:
    return Result("ask", order.ref, lead=lead,
                  pending={"stage": STAGE_ASK, "kind": kind, "order_ref": order.ref, "options": options or []})


def _schedule(order, request: Request, options: list) -> tuple[dict | None, Result | None]:
    """``({date, slot}, None)`` para o ``order_edit.plan``, ou a pergunta/recusa."""
    from . import order_closing, tools

    data = order.data or {}
    current_day = str(data.get("delivery_date") or "") or timezone.localdate().isoformat()
    current_slot = str(data.get("delivery_time_slot") or "")
    day = request.day or current_day
    slots = _slots(order, day)
    choices = _slot_options(slots)
    mode = tools.AMEND_MODE_WORDS[_mode(order)]
    when = _when_words(day)

    def ask(prefix: str = "") -> Result:
        if not choices:
            return _ask(order, RESCHEDULE, " ".join(p for p in (
                prefix, tools.AMEND_ASK["no_slots"].format(mode=mode, day=when)) if p))
        question = tools.AMEND_ASK[RESCHEDULE].format(day=when, options=_options_text(choices))
        return _ask(order, RESCHEDULE, " ".join(p for p in (prefix, question) if p), options=choices)

    chosen = None
    if request.pick and options and 1 <= request.pick <= len(options):
        chosen = next((slot for slot in slots if slot["ref"] == options[request.pick - 1].get("ref")), None)
    elif request.minutes is not None:
        chosen = order_closing._match_slot(slots, request.minutes)
        if chosen is None:
            return None, ask(tools.AMEND_REFUSED["no_slot_at"].format(mode=mode, time=request.time_text, day=when))
    elif request.day and request.day != current_day:
        chosen = next((slot for slot in slots if slot["ref"] == current_slot), None)
        if chosen is None:
            return None, ask()
    else:
        return None, ask()
    if chosen is None:
        return None, ask()
    if not chosen["available"]:
        reason = chosen["reason"].rstrip(".") or "não está disponível"
        return None, ask(tools.AMEND_REFUSED["slot_closed"].format(slot=chosen["label"], day=when, reason=reason))
    return {"date": day, "slot": chosen["ref"]}, None


def _lines_without(order, request: Request, options: list) -> tuple[list | None, Result | None]:
    """``(lista final, None)`` para o ``order_edit.plan``, ou a pergunta/recusa."""
    from shopman.shop.services import order_edit

    from . import dialogue, tools

    lines = order_edit.product_lines(order)
    choices = [{"n": index, "name": line["name"], "line_id": line["line_id"],
                "label": f"{_qty_text(line['qty'])} {line['name']}"}
               for index, line in enumerate(lines, start=1)]
    listing = "; ".join(f"{choice['n']}) {choice['label']}" for choice in choices)
    picked = []
    if request.item:
        picked = [choice for choice in choices if _fold(choice["name"]) == _fold(request.item)]
        if not picked:
            picked = dialogue.named_options(dialogue.words(request.item), choices)
    if not request.item or len(picked) > 1:
        return None, _ask(order, REMOVE_ITEM, tools.AMEND_ASK[REMOVE_ITEM].format(ref=order.ref, options=listing),
                              options=[{"n": c["n"], "name": c["name"]} for c in choices])
    if not picked:
        items = "; ".join(choice["label"] for choice in choices)
        return None, Result("item_not_found", order.ref, lead=tools.AMEND_REFUSED["item_not_found"].format(
            item=request.item, ref=order.ref, items=items))
    target = picked[0]["line_id"]
    final = []
    for line in lines:
        if line["line_id"] != target:
            final.append({"line_id": line["line_id"], "sku": line["sku"], "qty": line["qty"]})
            continue
        qty = Decimal(str(line["qty"]))
        weighed = qty != qty.to_integral_value()
        if request.qty and not weighed and Decimal(request.qty) < qty:
            final.append({"line_id": line["line_id"], "sku": line["sku"], "qty": str(qty - Decimal(request.qty))})
    return final, None


def _qty_text(value) -> str:
    qty = Decimal(str(value))
    return str(int(qty)) if qty == qty.to_integral_value() else str(qty.normalize()).replace(".", ",")


def _fulfillment(conversation, order, request: Request) -> tuple[dict | None, Result | None]:
    """O recebimento novo (a entrega no endereço dito) para o ``order_edit.plan``, ou a pergunta/recusa."""
    from shopman.shop.services import delivery_fiscal_identity as identity

    from . import address as delivery_address
    from . import tools

    if _mode(order) != "delivery":
        return None, Result("pickup_order", order.ref, lead=tools.AMEND_REFUSED["pickup_order"].format(ref=order.ref))
    if request.structured:
        structured = dict(request.structured)
        return {
            "type": "delivery",
            "delivery_address": structured.get("formatted_address", ""),
            "delivery_address_structured": structured,
        }, None
    said = str(request.address or "").strip()
    if not said:
        return None, _ask(order, CHANGE_ADDRESS, tools.AMEND_ASK[CHANGE_ADDRESS])
    structured = None
    if not re.search(r"\d", said):
        # "Para o de casa", "o do trabalho": o endereço do cadastro do próprio cliente.
        saved = delivery_address.pick_saved(delivery_address.saved_addresses(conversation.customer_ref), _saved_label(said))
        if saved is not None:
            try:
                structured = delivery_address.from_saved(saved)
            except delivery_address.AddressNotLocated:
                structured = None
    if structured is None:
        try:
            structured = delivery_address.compose(current=None, pin=None, text=said, parts={})
        except delivery_address.AddressNotLocated:
            return None, _ask(order, CHANGE_ADDRESS, " ".join((
                tools.AMEND_REFUSED["address_not_located"], tools.AMEND_ASK[CHANGE_ADDRESS])))
    missing = delivery_address.missing_words(structured)
    if missing:
        return None, _ask(order, CHANGE_ADDRESS, tools.AMEND_ASK["address_incomplete"].format(
            words=identity.join_words(missing)))
    return {
        "type": "delivery",
        "delivery_address": structured["formatted_address"],
        "delivery_address_structured": structured,
    }, None


def _saved_label(said: str) -> str:
    folded = _fold(said)
    folded = re.sub(r"^(?:o|a)\s+(?:endereco\s+)?(?:de|do|da)\s+", "", folded)
    return folded.strip()


# ── A prévia ──────────────────────────────────────────────────────────


@dataclass
class Draft:
    """A alteração calculada (``order_edit.plan``) e o que foi pedido para chegar nela."""

    order: object
    kind: str
    edit_args: dict
    plan: object

    def token(self) -> str:
        plan = self.plan
        payload = {
            "order": self.order.ref,
            "kind": self.kind,
            "args": self.edit_args,
            "items": [(i.get("line_id"), i.get("sku"), str(i.get("qty")), i.get("line_total_q")) for i in plan.items],
            "previous_total_q": plan.previous_total_q,
            "total_q": plan.total_q,
            "date": plan.date_after,
            "slot": plan.slot_after,
            "address": plan.delivery_address_after,
            "fee": [plan.delivery_fee_before_q, plan.delivery_fee_after_q],
            "settlement": [plan.settlement.kind, plan.settlement.amount_q],
            "balance": plan.balance_after_q,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _refused(order, code: str, message: str, kind: str) -> Result:
    from . import tools

    status_reason = tools.AMEND_STATUS_REFUSED.get(str(order.status)) if code in {
        "order_not_editable", "order_not_reschedulable"} else None
    template = status_reason or tools.AMEND_REFUSED.get(code) or ""
    try:
        reason = template.format(ref=order.ref)
    except (KeyError, IndexError):
        reason = ""  # frase da casa com outro dado: vale a do serviço
    # O que a casa não traduz (data, horário, estoque) sai com a frase do serviço.
    reason = reason or _sentence(message)
    # Sem motivo nenhum, a Nice não inventa: diz que não consegue e chama a equipe.
    team = code in TEAM_CODES or not reason
    reason = reason or tools.AMEND_REFUSED["generic"].format(ref=order.ref)
    result = Result("refused", order.ref, lead=reason)
    if team:
        result.lead = f"{reason} {tools.AMEND_TEAM_SUFFIX}"
        result.team = True
        result.team_reason = f"Cliente pediu para {tools.AMEND_GESTURES[kind]} no pedido {order.ref}: {reason}"[:200]
    return result


def _sentence(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text if not text or text.endswith((".", "!", "?")) else f"{text}."


def draft(conversation, order, request: Request, *, options=None) -> tuple[Draft | None, Result | None]:
    """A alteração calculada pelo ``order_edit.plan`` (nada gravado), ou a pergunta/recusa."""
    from shopman.shop.services import order_edit, reschedule

    code, message = order_edit.state_refusal(order)
    if code:
        return None, _refused(order, code, message, request.kind)
    edit_args: dict = {}
    if request.kind == RESCHEDULE:
        refusal = reschedule.state_refusal(order)
        if refusal:
            return None, _refused(order, "order_not_reschedulable", refusal, request.kind)
        schedule, stop = _schedule(order, request, options or [])
        if stop is not None:
            return None, stop
        edit_args["schedule"] = schedule
    elif request.kind == REMOVE_ITEM:
        lines, stop = _lines_without(order, request, options or [])
        if stop is not None:
            return None, stop
        edit_args["lines"] = lines
    else:
        fulfillment, stop = _fulfillment(conversation, order, request)
        if stop is not None:
            return None, stop
        edit_args["fulfillment"] = fulfillment
    try:
        plan = order_edit.plan(order, source=order_edit.CONCIERGE_AMEND_SOURCE, reissue_open_pix=True, **edit_args)
    except order_edit.EditRefused as exc:
        return None, _refused(order, exc.code, exc.message, request.kind)
    if not plan.changed:
        from . import tools

        return None, Result("unchanged", order.ref, lead=tools.AMEND_REFUSED["unchanged"].format(ref=order.ref))
    if plan.requires_manager_approval:
        from . import tools

        refusal = tools.AMEND_REFUSED["manager_approval_required"].format(
            ref=order.ref, amount=_brl(plan.settlement.amount_q))
        result = Result("refused", order.ref, lead=f"{refusal} {tools.AMEND_TEAM_SUFFIX}", team=True)
        result.team_reason = f"Cliente pediu para {tools.AMEND_GESTURES[request.kind]} no pedido {order.ref}: {refusal}"[:200]
        return None, result
    return Draft(order, request.kind, edit_args, plan), None


def _brl(value_q: int) -> str:
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(int(value_q))}"


def effect_lines(found: Draft) -> list[str]:
    """O efeito da alteração, em fatos do sistema: o horário, o item, o endereço, a taxa e o total."""
    from shopman.shop.services import order_edit

    from . import order_closing, tools

    plan = found.plan
    rows: list[str] = []
    mode = tools.AMEND_MODE_WORDS[plan.fulfillment_after]
    if plan.schedule_changed:
        label = _slot_label(found.order, plan.date_after, plan.slot_after)
        when = _when_words(plan.date_after)
        when = f"{when}, {order_closing.window_phrase(label)}" if label else when
        rows.append(tools.AMEND_EFFECT["when"].format(mode=mode.capitalize(), when=when))
    diff = plan.diff or {}
    gone = [f"{_qty_text(entry['qty'])} {entry['name']}" for entry in diff.get("removed") or []
            if not str(entry.get("sku") or "").startswith("__")]
    if gone:
        rows.append(tools.AMEND_EFFECT["removed"].format(items=", ".join(gone)))
    for entry in diff.get("changed") or []:
        rows.append(tools.AMEND_EFFECT["reduced"].format(
            name=entry["name"], before=_qty_text(entry["previous_qty"]), after=_qty_text(entry["qty"])))
    if found.kind == CHANGE_ADDRESS:
        rows.append(tools.AMEND_EFFECT["address"].format(address=plan.delivery_address_after))
        before, after = plan.delivery_fee_before_q, plan.delivery_fee_after_q
        if after == before:
            rows.append(tools.AMEND_EFFECT["fee_same"].format(fee=_brl(after)) if after else tools.AMEND_EFFECT["fee_none"])
        else:
            rows.append(tools.AMEND_EFFECT["fee"].format(after=_brl(after), before=_brl(before)))
    if plan.total_q != plan.previous_total_q:
        rows.append(tools.AMEND_EFFECT["total"].format(after=_brl(plan.total_q), before=_brl(plan.previous_total_q)))
    else:
        rows.append(tools.AMEND_EFFECT["total_same"].format(total=_brl(plan.total_q)))
    if plan.reissues_pix:
        rows.append(tools.AMEND_EFFECT["new_pix"])
    if plan.settlement.kind == order_edit.SETTLE_COLLECT and plan.balance_after_q != plan.balance_before_q:
        rows.append(tools.AMEND_EFFECT["collect"].format(mode=mode, amount=_brl(plan.settlement.amount_q)))
    return rows


def _slot_label(order, day_iso: str, slot_ref: str) -> str:
    from shopman.shop.services import fulfillment_window

    label = next((slot["label"] for slot in _slots(order, day_iso) if slot["ref"] == slot_ref), "")
    return label or fulfillment_window.window_label(slot_ref, for_customer=True) or ""


# ── A conversa ────────────────────────────────────────────────────────


def pending(conversation) -> dict | None:
    value = (conversation.flags or {}).get(PENDING_FLAG)
    return value if isinstance(value, dict) and value.get("order_ref") else None


def _expired(state: dict) -> bool:
    at = parse_datetime(str(state.get("at") or ""))
    return at is None or timezone.now() - at > PENDING_TTL


def _set_pending(conversation, value: dict | None) -> None:
    from shopman.shop.models import Conversation

    flags = dict(conversation.flags or {})
    if value is None:
        if PENDING_FLAG not in flags:
            return
        flags.pop(PENDING_FLAG, None)
    else:
        flags[PENDING_FLAG] = {**value, "at": timezone.now().isoformat()}
    conversation.flags = flags
    Conversation.objects.filter(pk=conversation.pk).update(flags=flags, updated_at=timezone.now())


def clear(conversation) -> None:
    _set_pending(conversation, None)


def _code_for(token: str, *, avoid: str = "") -> str:
    from .tools import quote_code

    return quote_code(f"amend:{token}", avoid=avoid)


def _confirm_code(text: str) -> str:
    """O código de uma confirmação no formato aceito (ADR-050): "1234", "confirmo 1234",
    "confirmar 1234", "sim 1234", "sim, confirmo 1234"; vazio quando não é isso."""
    folded = " ".join(_fold(text).rstrip(".! ").replace(",", " ").split())
    found = re.fullmatch(r"(?:sim\s+)?(?:confirm(?:o|ar|a)\s+)?(\d{4})", folded)
    return found.group(1) if found else ""


def _tries_to_confirm(text: str) -> bool:
    from . import order_closing

    return order_closing._confirms(text, "")


def propose(conversation, request: Request, *, order_ref: str = "", text: str = "") -> Result:
    """A prévia com o código, ou a pergunta/recusa. Nada muda no pedido aqui."""
    from . import tools

    order, stop = _target(conversation, text, order_ref)
    if order is None:
        clear(conversation)
        return stop
    _refresh(order)
    # A resposta à pergunta no ar ("o 2", "às 15h") lê as opções que a pergunta mostrou.
    asked = pending(conversation) or {}
    options = asked.get("options") or [] if (
        asked.get("stage") == STAGE_ASK and asked.get("kind") == request.kind and asked.get("order_ref") == order.ref
    ) else []
    found, stop = draft(conversation, order, request, options=options)
    if stop is not None:
        _set_pending(conversation, stop.pending)
        return stop
    previous = pending(conversation) or {}
    if request.kind == CHANGE_ADDRESS:
        request.structured = dict(found.edit_args["fulfillment"]["delivery_address_structured"])
    token = found.token()
    code = _code_for(token, avoid=str(previous.get("code") or ""))
    _set_pending(conversation, {
        "stage": STAGE_CONFIRM, "kind": request.kind, "order_ref": order.ref,
        "request": request.args(), "options": options or [], "token": token, "code": code,
        "reissues_pix": bool(found.plan.reissues_pix),
    })
    return Result(
        "proposed", order.ref, lead=tools.AMEND_PREVIEW_LEAD.format(ref=order.ref), lines=effect_lines(found),
        confirm_code=code,
    )


def confirm(conversation, code: str, *, channel_ref: str) -> Result:
    """O "confirmo 1234": aplica pelo ``order_edit.edit`` se o pedido ainda é o da prévia."""
    from shopman.orderman.models import Order

    from shopman.shop.models import ConversationMessage
    from shopman.shop.services import order_edit

    from . import tools
    from .effect_authority import lock_turn_authority

    state = pending(conversation)
    if state is None or _expired(state):
        clear(conversation)
        return Result("nothing_pending", lead=tools.AMEND_REFUSED["nothing_pending"])
    ref = str(state["order_ref"])
    if state.get("stage") == STAGE_APPLIED:
        if code == state.get("code"):
            # X4: a mesma confirmação de novo (reenvio, ou o cliente repetindo) não aplica outra vez.
            return Result("already_applied", ref, lead=tools.AMEND_DONE["already_applied"].format(ref=ref))
        return Result("nothing_pending", ref, lead=tools.AMEND_REFUSED["nothing_pending"])
    if state.get("stage") != STAGE_CONFIRM:
        return Result("nothing_pending", ref, lead=tools.AMEND_REFUSED["nothing_pending"])
    if code != state.get("code"):
        return Result("wrong_code", ref, lead=tools.AMEND_CONFIRM.format(code=state["code"]),
                      confirm_code=str(state["code"]))
    request = Request(**{**(state.get("request") or {}), "kind": state["kind"]})
    order = Order.objects.filter(ref=ref).first()
    if order is None:
        clear(conversation)
        return Result("no_order", lead=tools.AMEND_REFUSED["no_order"])
    _refresh(order)
    if state.get("reissues_pix") and _open_pix(order):
        # Antes de trocar o Pix, a pergunta ao gateway: pago e ainda sem aviso, o pagamento
        # é registrado agora (fora da transação da alteração, para valer mesmo se ela
        # voltar), e a prévia recalculada abaixo segue o caminho do pedido pago.
        from shopman.shop.services import payment as payment_service

        if payment_service.settle_from_gateway(order) == "indeterminate":
            clear(conversation)
            return _refused(order, "payment_unreadable", "", request.kind)
        order.refresh_from_db()
    with transaction.atomic():
        # A posse da conversa reconferida na transação que grava (#2625), e o pedido e os
        # pagamentos travados: a prévia é recalculada sob a trava, e só o que o cliente viu
        # é aplicado (X5). Um Pix confirmado agora espera esta transação.
        from shopman.shop.services import payment as payment_service

        lock_turn_authority(conversation, channel_ref=channel_ref, level=tools.CART_LEVEL)
        locked = Order.objects.select_for_update().get(pk=order.pk)
        payment_service.lock_order_payment(locked)
        found, stop = draft(conversation, locked, request, options=state.get("options") or [])
        if stop is not None:
            clear(conversation)
            return stop
        token = found.token()
        if token != state.get("token"):
            fresh = _code_for(token, avoid=str(state.get("code") or ""))
            _set_pending(conversation, {**state, "token": token, "code": fresh,
                                        "reissues_pix": bool(found.plan.reissues_pix)})
            return Result("stale", ref, lead=tools.AMEND_STALE.format(ref=ref), lines=effect_lines(found),
                          confirm_code=fresh)
        try:
            # Uma mensagem só: a resposta da Nice leva o efeito, e o aviso ``order_updated`` não sai.
            done = order_edit.edit(
                locked, actor=ACTOR, source=order_edit.CONCIERGE_AMEND_SOURCE, notify_customer=False,
                reissue_open_pix=True, **found.edit_args,
            )
        except order_edit.EditRefused as exc:
            # O ``edit`` voltou inteiro (a transação dele): nada foi gravado no pedido nem
            # no pagamento. A recusa sai depois deste bloco.
            refusal = _refused(locked, exc.code, exc.message, request.kind)
        else:
            refusal = None
            ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.Role.ASSISTANT,
                kind=ConversationMessage.Kind.NOTE,
                text=f"{HISTORY_NOTE}: {tools.AMEND_GESTURES[request.kind]} (pedido {ref}).",
                envelope={"version": 3, "order_ref": ref, "turn_fence": conversation.turn_fence},
            )
            _set_pending(conversation, {**state, "stage": STAGE_APPLIED})
    if refusal is not None:
        clear(conversation)
        return refusal
    logger.info("concierge.amend: order=%s kind=%s revision=%s", ref, request.kind, done.revision)
    result = Result("applied", ref, lead=tools.AMEND_DONE["applied"].format(ref=ref),
                    lines=effect_lines(Draft(found.order, found.kind, found.edit_args, done.plan)))
    if done.plan.reissues_pix:
        # O código Pix novo, sozinho na mensagem seguinte (OC-05); sem ele, o que a página
        # oferece ("Tentar novamente"), pela mesma frase do OC-12.
        locked.refresh_from_db()
        code = str(((locked.data or {}).get("payment") or {}).get("copy_paste") or "").strip()
        if code:
            result.lines.append(tools.PIX_CODE_FOLLOWS)
            result.copies = [code]
        else:
            result.lines.append(tools.REPAY_DONE["still_failing"].format(ref=ref))
    return result


def _open_pix(order) -> bool:
    """O pedido é de Pix, com a cobrança esperando pagamento (o caso da troca do Pix)."""
    from shopman.shop.services import payment as payment_service

    method = str(((order.data or {}).get("payment") or {}).get("method") or "").lower()
    return method == "pix" and (payment_service.get_payment_status(order) or "").lower() == "pending"


# ── O turno ───────────────────────────────────────────────────────────


def _context(conversation, *, binding, channel_ref: str, text: str):
    from .tools import ToolContext

    return ToolContext(
        conversation=conversation, channel_ref=channel_ref,
        provider=str(getattr(binding, "provider", "") or ""), account=str(getattr(binding, "account", "") or ""),
        transport_channel=str(getattr(binding, "transport_channel", "") or ""),
        connection_key=str(getattr(binding, "connection_key", "") or ""), customer_text=text,
    )


def handle(conversation, text: str, *, binding, channel_ref: str, memory, decision=None):
    """O turno da alteração do pedido, ou ``None`` quando a fala não é dela.

    Primeiro a resposta ao que está no ar (o código, ou o horário/item/endereço que faltava);
    depois o pedido de alteração. Qualquer outra fala desfaz o que estava no ar: um
    "confirmo" de outro assunto nunca altera pedido.
    """
    from .intents import _cart_authorized

    if conversation is None or not _cart_authorized(conversation):
        return None
    state = pending(conversation)
    arguments = None
    if state is not None:
        if _expired(state):
            clear(conversation)
        elif state.get("stage") in {STAGE_CONFIRM, STAGE_APPLIED} and _confirm_code(text):
            arguments = {"code": _confirm_code(text)}
        elif state.get("stage") == STAGE_CONFIRM and _tries_to_confirm(text):
            arguments = {"code": "-"}
        elif state.get("stage") == STAGE_ASK:
            answer = read(text, kind=str(state.get("kind") or ""), options=state.get("options") or [])
            if answer is not None and (answer.day or answer.minutes is not None or answer.pick
                                       or answer.item or answer.address):
                arguments = {**answer.args(), "order_ref": state["order_ref"]}
        if arguments is None:
            clear(conversation)
    if arguments is None:
        if decision is not None and getattr(decision, "escalates", False) and getattr(
                decision, "escalated_by", "") != "order_not_closed":
            return None
        request = read(text)
        if request is None:
            return None
        arguments = request.args()
    from . import tools

    ctx = _context(conversation, binding=binding, channel_ref=channel_ref, text=text)
    result = tools.execute("amend_order", arguments, ctx)
    return outcome(result, memory=memory)


def outcome(result: dict, *, memory):
    from . import tools
    from .metrics import LAYER_CONTEXT
    from .turn_outcome import TurnOutcome

    text = tools.render_result("amend_order", result)
    event = {"name": "amend_order", "input": {}, "ok": bool(result.get("ok")),
             "order_found": bool(result.get("order_ref"))}
    if result.get("team"):
        return TurnOutcome(reply_text="", handoff=True, handoff_reason=str(result.get("team_reason") or ""),
                           handoff_ack=text, layer=LAYER_CONTEXT, memory=memory, tool_events=[event])
    return TurnOutcome(
        reply_text=text, layer=LAYER_CONTEXT, memory=memory, tool_events=[event],
        order_ref=str(result.get("order_ref") or "") if result.get("code") == "applied" else "",
        extra_replies=list(result.get("copies") or []),
    )


def run_tool(ctx, *, kind: str = "", order_ref: str = "", code: str = "", **said) -> dict:
    """A ferramenta ``amend_order``: a prévia (sem ``code``) ou a confirmação (com ``code``)."""
    conversation = ctx.conversation
    if code:
        return confirm(conversation, str(code), channel_ref=ctx.channel_ref).as_dict()
    if kind not in KINDS:
        from .tools import _error

        return _error("invalid_input", "Diga o que mudar no pedido: o horário, um item ou o endereço.")
    allowed = {"day", "minutes", "time_text", "pick", "item", "qty", "address"}
    request = Request(kind, **{key: value for key, value in said.items() if key in allowed})
    return propose(conversation, request, order_ref=order_ref, text=ctx.customer_text).as_dict()


# ── O que a consulta oferece ──────────────────────────────────────────


def offered(order) -> list[str]:
    """As alterações que este pedido aceita agora, pelo serviço do balcão (X1).

    Remarcar e trocar o endereço pela porta do pedido (``state_refusal``); tirar um item só
    quando a prévia de tirar uma unidade passa sem gerente (cobrança aberta, devolução, item
    único: aí a Nice não oferece).
    """
    from shopman.shop.services import order_edit, reschedule

    code, _message = order_edit.state_refusal(order)
    if code:
        return []
    out = []
    if not reschedule.state_refusal(order):
        out.append(RESCHEDULE)
    lines = order_edit.product_lines(order)
    if lines:
        first = lines[0]
        qty = Decimal(str(first["qty"]))
        trial = [{"line_id": line["line_id"], "sku": line["sku"], "qty": line["qty"]} for line in lines[1:]]
        if qty > 1 and qty == qty.to_integral_value():
            trial.insert(0, {"line_id": first["line_id"], "sku": first["sku"], "qty": str(qty - 1)})
        try:
            plan = order_edit.plan(
                order, lines=trial, source=order_edit.CONCIERGE_AMEND_SOURCE, reissue_open_pix=True,
            ) if trial else None
        except order_edit.EditRefused:
            plan = None
        if plan is not None and not plan.requires_manager_approval:
            out.append(REMOVE_ITEM)
    if _mode(order) == "delivery":
        out.append(CHANGE_ADDRESS)
    return out
