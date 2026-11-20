""""Não sei, vou verificar": a Concierge pergunta à equipe e devolve a resposta (WP-05).

Bloco 4 de ``docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md`` (seção 8), o que o dono
chamou de ouro: quando não sabe, a atendente não inventa e não larga o cliente.

O caminho, de ponta a ponta:

1. **A parte sem fato.** Uma consulta (produto, horário ou entrega, como funciona a
   casa) que a busca pública não responde vira uma pergunta à equipe, em vez de
   "não tenho, quer a equipe?" (``intents.execute``). As outras partes da mesma
   mensagem são respondidas como sempre, e a conversa SEGUE com a Concierge: não é
   handoff.
2. **O prazo honesto** (``promise_for``). Os dois prazos são do Admin
   (``ChannelConfig.confirmation.concierge_verify_nudge_minutes`` e
   ``..._handoff_minutes``; dono, 16/11/2026: 10 e 30 minutos) e contam só tempo de
   loja aberta (``business_calendar.next_operational_deadline``). Casa aberta: "te
   respondo em até 10 minutos". Casa fechada: "te respondo até amanhã às 7h10". Se a
   resposta não cabe na janela de 24 horas do WhatsApp, nada é prometido: a
   Concierge diz quando a equipe volta (a mensagem aprovada pela Meta é o WP-16).
3. **Uma verificação aberta por conversa** (``Conversation.flags["verification"]``).
   Dúvida nova enquanto espera entra no mesmo cartão. Gravada no turno, na mesma
   transação da resposta e com o mesmo ``turn_fence``: turno revogado não grava
   (``record_turn``). A memória da conversa lê o estado como ``verifying``
   (``dialogue.for_turn``): "e aí?" durante a espera é respondido por ele, sem
   cartão novo (``waiting_reply``).
4. **O cartão** ``concierge_verify``, no sino do Gestor de pedidos, com a pergunta do
   cliente (redigida: dado pessoal não vai para o cartão) e o prazo prometido
   (``notify_team``).
5. **A resposta da equipe volta pela Concierge** (``answer``): "A equipe confirmou:
   ...". É fato de origem humana; passa pelas regras de forma da casa (voz, travessão,
   dado pessoal) e pela autorização da janela de 24 horas, pelo envio fora do turno
   (``service.send_out_of_turn``, o mesmo que o WP-06 usa para o aviso do prazo). Se o
   envio não sai, a verificação continua aberta e o cartão diz por quê.
6. **Ou alguém assume a conversa** (``take_over``): vira handoff, e o cliente sabe.

Fora daqui: o relógio dos prazos (WP-06), a tela do cartão (WP-07), promover a
resposta a pergunta frequente (WP-15), a mensagem aprovada pela Meta (WP-16).
Nenhuma chamada de modelo.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

FLAG_KEY = "verification"
VERSION = 1
ALERT_TYPE = "concierge_verify"

OPEN = "open"
ANSWERED = "answered"
TAKEN_OVER = "taken_over"

#: O prazo que a Concierge pôde prometer (``promise_for``).
NOW = "now"  # casa aberta: "em até 10 minutos"
LATER = "later"  # casa fechada (ou fechando): "até amanhã às 7h10"
NO_PROMISE = "no_promise"  # a resposta não caberia na janela de 24 horas

#: Perguntas num cartão só; a partir daí a equipe já tem o bastante para assumir.
MAX_QUESTIONS = 5
QUESTION_CHARS = 160
MAX_ANSWER_CHARS = 300

ASKED_COPY_KEY = "CONCIERGE_VERIFY_ASKED"
ASKED_LATER_COPY_KEY = "CONCIERGE_VERIFY_ASKED_LATER"
JOINED_COPY_KEY = "CONCIERGE_VERIFY_JOINED"
NO_PROMISE_COPY_KEY = "CONCIERGE_VERIFY_NO_PROMISE"
NO_PROMISE_UNKNOWN_COPY_KEY = "CONCIERGE_VERIFY_NO_PROMISE_UNKNOWN"
WAITING_COPY_KEY = "CONCIERGE_VERIFY_WAITING"
ANSWER_COPY_KEY = "CONCIERGE_VERIFY_ANSWER"
#: Os dois prazos sem resposta (WP-06 dispara; a copy nasce aqui).
NUDGE_COPY_KEY = "CONCIERGE_VERIFY_NUDGE"
HANDOFF_COPY_KEY = "CONCIERGE_VERIFY_HANDOFF"
COPY_KEYS = (
    ASKED_COPY_KEY,
    ASKED_LATER_COPY_KEY,
    JOINED_COPY_KEY,
    NO_PROMISE_COPY_KEY,
    NO_PROMISE_UNKNOWN_COPY_KEY,
    WAITING_COPY_KEY,
    ANSWER_COPY_KEY,
    NUDGE_COPY_KEY,
    HANDOFF_COPY_KEY,
)

#: Quem a resposta e o handoff gravam como ator.
ACTOR = "concierge"


def _now() -> datetime:
    return timezone.now()


def _copy(key: str) -> str:
    from .service import copy_message

    return (copy_message(key) or "").strip()


def _fill(template: str, **values) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template.strip()


def _channel_ref(conversation) -> str:
    from .service import config

    return str(getattr(conversation, "channel_ref", "") or config().get("channel_ref") or "")


def deadlines(channel_ref: str) -> tuple[int, int]:
    """(primeiro, segundo) prazo do canal, em minutos de loja aberta."""
    from shopman.shop.config import ChannelConfig

    confirmation = ChannelConfig.for_channel(channel_ref).confirmation
    return int(confirmation.concierge_verify_nudge_minutes), int(confirmation.concierge_verify_handoff_minutes)


# ── O estado ──────────────────────────────────────────────────────────


def current(conversation) -> dict | None:
    """A verificação aberta da conversa, ou ``None``."""
    record = (getattr(conversation, "flags", None) or {}).get(FLAG_KEY)
    if isinstance(record, dict) and record.get("v") == VERSION and record.get("status") == OPEN:
        return record
    return None


def memory_view(conversation) -> dict | None:
    """O que a memória da conversa guarda como ``verifying``: as perguntas em espera."""
    record = current(conversation)
    if record is None:
        return None
    return {
        "id": record.get("id", ""),
        "questions": [q.get("text", "") for q in record.get("questions") or [] if isinstance(q, dict)],
        "promise": (record.get("promise") or {}).get("kind", ""),
    }


# ── O prazo honesto ───────────────────────────────────────────────────


def _window_until(conversation) -> datetime | None:
    """Até quando a casa pode responder em texto livre: a janela da última entrada."""
    from shopman.shop.models import ConversationMessage

    from .contracts import WindowEvidence

    latest = (
        conversation.messages.filter(kind=ConversationMessage.Kind.INBOUND).order_by("-pk").first()
        if getattr(conversation, "pk", None)
        else None
    )
    if latest is None:
        return None
    try:
        evidence = WindowEvidence.from_value((latest.envelope or {}).get("window_evidence"))
    except Exception:
        # Prova de janela ilegível: vale a conta pela hora da entrada, nunca o turno caído.
        logger.warning("concierge.verification.window_evidence_unreadable conversation=%s", conversation.pk)
        evidence = None
    if evidence is not None and evidence.valid_until:
        return evidence.valid_until
    return latest.created_at + timedelta(hours=24)


def promise_for(conversation, *, now: datetime | None = None) -> dict:
    """O que a Concierge pode prometer agora, pelo calendário da casa e pela janela.

    ``{kind, minutes, when, nudge_due_at, handoff_due_at}``; os instantes em ISO 8601
    (vazios quando nada é prometido). O segundo prazo é o último instante em que a
    equipe ainda responde pela Concierge: se ele passa da janela de 24 horas, a
    resposta não chegaria, e a promessa não é feita.
    """
    from shopman.shop.services import business_calendar

    now = now or _now()
    nudge, handoff = deadlines(_channel_ref(conversation))
    nudge_due, state = business_calendar.next_operational_deadline(timeout=timedelta(minutes=nudge), now=now)
    handoff_due, _state = business_calendar.next_operational_deadline(timeout=timedelta(minutes=handoff), now=now)
    window_until = _window_until(conversation)
    if nudge_due is None or handoff_due is None or (window_until is not None and handoff_due > window_until):
        when = business_calendar.format_next_opening(state.next_open_at, now=now) if state.is_closed else ""
        return {"kind": NO_PROMISE, "minutes": nudge, "when": when, "nudge_due_at": "", "handoff_due_at": ""}
    kind = NOW if state.is_open and nudge_due <= now + timedelta(minutes=nudge, seconds=59) else LATER
    return {
        "kind": kind,
        "minutes": nudge,
        "when": "" if kind == NOW else business_calendar.format_deadline(nudge_due, now=now),
        "nudge_due_at": nudge_due.isoformat(),
        "handoff_due_at": handoff_due.isoformat(),
    }


def promise_text(promise: dict, *, joined: bool = False) -> str:
    """A frase do prazo, que fecha a resposta do turno."""
    kind = promise.get("kind")
    if kind == NO_PROMISE:
        if promise.get("when"):
            return _fill(_copy(NO_PROMISE_COPY_KEY), when=promise["when"])
        return _copy(NO_PROMISE_UNKNOWN_COPY_KEY)
    if joined:
        return _copy(JOINED_COPY_KEY)
    if kind == LATER and promise.get("when"):
        return _fill(_copy(ASKED_LATER_COPY_KEY), when=promise["when"])
    return _fill(_copy(ASKED_COPY_KEY), minutes=promise.get("minutes") or deadlines("")[0])


def can_verify(conversation) -> bool:
    """A conversa é real (tem banco e vínculo); fora disso, vale o "não tenho" de sempre."""
    return bool(conversation is not None and getattr(conversation, "pk", None))


def question_text(act) -> str:
    """A pergunta do cliente como vai para o cartão: redigida, sem a pontuação final."""
    from .triage import _redacted

    text = " ".join(_redacted(getattr(act, "span", "") or getattr(act, "product", "")).split())
    text = text.rstrip(" .,;:")
    if len(text) > QUESTION_CHARS:
        text = text[: QUESTION_CHARS - 1].rstrip() + "…"
    return text


# ── "E aí?" durante a espera ──────────────────────────────────────────

#: "e aí?", "alguma novidade?", "conseguiu ver?", "já confirmaram?": a cobrança da
#: resposta que a casa prometeu. Só vale com uma verificação aberta e sem outra pergunta.
_NEWS_RE = re.compile(
    r"^(?:e\s+ai|e\s+entao|e\s+agora|entao|e\s+ai\s+moca|oi\s+e\s+ai)\W*$"
    r"|\b(?:alguma|tem|teve|ha)\s+novidade\w*\b"
    r"|\bnovidades?\b"
    r"|\bconsegui\w*\s+(?:ver|saber|confirmar|descobrir|checar|verificar|resposta)\b"
    r"|\b(?:ja|e)\s+(?:sabe|soube|confirmou|confirmaram|responderam|respondeu|tem\s+(?:a\s+)?resposta)\b"
    r"|\b(?:a\s+)?equipe\s+(?:ja\s+)?(?:respondeu|confirmou|falou|disse)\b"
)


def asks_for_news(text: str) -> bool:
    from . import dialogue

    folded = dialogue._fold(text)
    if not folded.strip():
        return False
    return bool(_NEWS_RE.search(folded.strip())) or (
        dialogue.asks_again(text) and dialogue.without_nudge(text) == ""
    )


def waiting_reply(view: dict) -> str:
    questions = [q for q in (view or {}).get("questions") or [] if q]
    part = questions[-1] if questions else ""
    if len(part) > 60:
        part = part[:59].rstrip() + "…"
    return _fill(_copy(WAITING_COPY_KEY), part=part or "a sua pergunta")


# ── No turno: gravar e avisar a equipe ────────────────────────────────


def record_turn(conversation, outcome, *, now: datetime | None = None) -> dict | None:
    """Abre (ou estende) a verificação do turno. Dentro da transação da resposta.

    Confere o ``turn_fence`` do turno: revogado (entrada nova, handoff, contenção),
    nada é gravado e nenhum cartão sai. Devolve o registro gravado, com ``_new`` quando
    a verificação acabou de abrir.
    """
    from shopman.shop.models import Conversation

    data = getattr(outcome, "verification", None) or {}
    questions = [q for q in data.get("requests") or [] if q.get("text")]
    if not questions:
        return None
    fence = getattr(conversation, "_turn_fence", None)
    if fence is None:
        return None
    now = now or _now()
    locked = Conversation.objects.select_for_update().filter(pk=conversation.pk, turn_fence=fence).first()
    if locked is None:
        return None
    flags = dict(locked.flags or {})
    record = current(locked)
    is_new = record is None
    if is_new:
        promise = data.get("promise") or {}
        record = {
            "v": VERSION,
            "id": uuid.uuid4().hex[:12],
            "status": OPEN,
            "opened_at": now.isoformat(),
            "fence": fence,
            "questions": [],
            "promise": {key: promise.get(key, "") for key in ("kind", "minutes", "when")},
            "nudge_due_at": promise.get("nudge_due_at", ""),
            "handoff_due_at": promise.get("handoff_due_at", ""),
            "nudged_at": "",
            "alert_pk": None,
        }
    else:
        record = dict(record)
        record["questions"] = list(record.get("questions") or [])
    known = {q.get("text") for q in record["questions"]}
    for question in questions:
        if question["text"] in known or len(record["questions"]) >= MAX_QUESTIONS:
            continue
        known.add(question["text"])
        record["questions"].append({"text": question["text"], "product": question.get("product", "")[:80],
                                    "at": now.isoformat()})
    flags[FLAG_KEY] = record
    if not Conversation.objects.filter(pk=conversation.pk, turn_fence=fence).update(flags=flags):
        return None
    conversation.flags = flags
    return {**record, "_new": is_new}


def open_for(conversation, question: str, *, product: str = "", actor: str = "", now: datetime | None = None) -> dict | None:
    """Abre (ou estende) a verificação FORA do turno: a porta de equipe do framework (N7).

    O ``record_turn`` roda dentro da transação da resposta, com o fence do claim do turno.
    Aqui não há turno: a conversa é travada (``select_for_update``), a promessa é a de
    agora (``promise_for``) e o fence é o da conversa travada, então um turno em andamento
    não sobrescreve o registro (ele espera a trava e relê). Depois da transação, o cartão
    (``notify_team``). ``actor`` fica em ``opened_by`` quando a verificação nasce aqui.

    ``None`` sem pergunta, com a conversa fora da Concierge (HANDOFF, encerrada) ou quando
    a casa não pode prometer resposta dentro da janela (``no_promise``): quem chama decide
    o que dizer ao cliente nesse caso.
    """
    from types import SimpleNamespace

    from shopman.shop.models import Conversation

    text = question_text(SimpleNamespace(span=str(question or ""), product=str(product or "")))
    if not text:
        return None
    now = now or _now()
    with transaction.atomic():
        locked = Conversation.objects.select_for_update().filter(pk=conversation.pk).first()
        if locked is None or locked.state != Conversation.State.ACTIVE:
            return None
        promise = promise_for(locked, now=now)
        if promise.get("kind") == NO_PROMISE:
            return None
        locked._turn_fence = locked.turn_fence
        outcome = SimpleNamespace(verification={
            "requests": [{"text": text, "product": str(product or "")[:80]}],
            "promise": promise,
        })
        record = record_turn(locked, outcome, now=now)
        if record and record.get("_new") and actor:
            flags = dict(locked.flags or {})
            flags[FLAG_KEY] = {**flags[FLAG_KEY], "opened_by": str(actor)[:100]}
            Conversation.objects.filter(pk=locked.pk).update(flags=flags)
            locked.flags = flags
            record = {**record, "opened_by": str(actor)[:100]}
    if record:
        conversation.flags = locked.flags
        notify_team(conversation, record)
    return record


def promised_label(record: dict) -> str:
    """O prazo que a Concierge prometeu, como hora da casa: "16h12", "amanhã às 7h10"."""
    from shopman.utils.formatting import format_clock

    promise = record.get("promise") or {}
    if promise.get("kind") == NOW:
        due = _parse(record.get("nudge_due_at"))
        return format_clock(timezone.localtime(due)) if due else ""
    if promise.get("kind") == LATER:
        return promise.get("when", "")
    return ""


def alert_message(conversation, record: dict) -> str:
    """O cartão da equipe: a pergunta do cliente e o prazo prometido, nessa ordem.

    Quem espera vai no título (``shop.concierge_verification.card_subject``, pela
    projeção do sino); os gestos
    (responder, assumir) são do cartão. O prazo é UM só, o que a Concierge prometeu:
    o segundo, de passar à equipe, não aparece para quem opera.
    """
    questions = [q.get("text", "") for q in record.get("questions") or [] if q.get("text")]
    if len(questions) == 1:
        asked = f"“{questions[0]}”"
    else:
        asked = "; ".join(f"{i}) “{q}”" for i, q in enumerate(questions, 1))
    when = promised_label(record)
    promised = f"Prometemos responder até {when}." if when else "A Concierge não prometeu prazo."
    return f"{asked}\n{promised}"


def notify_team(conversation, record: dict | None) -> None:
    """Cria o cartão (verificação nova) ou põe a pergunta nova nele. Depois da transação."""
    if not record:
        return
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.models import Conversation

    message = alert_message(conversation, record)
    try:
        if record.get("_new") or not record.get("alert_pk"):
            from shopman.shop.services.observability import create_operator_alert

            alert = create_operator_alert(
                type=ALERT_TYPE,
                severity="warning",
                message=message,
                # Um cartão por verificação, guardado em ``alert_pk``: a mensagem é só o que
                # a equipe lê, sem o marcador de engenheiro (dono, 20/11/2026).
                stamp_dedupe=False,
                order_ref=getattr(conversation, "last_order_ref", "") or "",
                conversation_id=conversation.pk,
                owner_role="atendimento",
                action="answer_concierge_verification",
                # O prazo prometido ao cliente: o sino conta até ele e, vencido, segue
                # mostrando há quanto passou (``alert_specs``: o prazo próprio fica).
                respond_by=_parse(record.get("nudge_due_at")),
            )
            if alert is None:
                return
            with transaction.atomic():
                locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
                flags = dict(locked.flags or {})
                stored = flags.get(FLAG_KEY)
                if isinstance(stored, dict) and stored.get("id") == record.get("id"):
                    flags[FLAG_KEY] = {**stored, "alert_pk": alert.pk}
                    Conversation.objects.filter(pk=conversation.pk).update(flags=flags)
                    conversation.flags = flags
        else:
            alert_adapter.revise(int(record["alert_pk"]), message=message)
    except Exception:
        logger.warning("concierge.verification.alert_failed conversation=%s", conversation.pk, exc_info=True)


# ── A equipe responde, ou assume ──────────────────────────────────────


def _by_alert(alert_pk: int):
    from shopman.shop.models import Conversation

    return Conversation.objects.filter(**{f"flags__{FLAG_KEY}__alert_pk": int(alert_pk)}).order_by("-pk").first()


def _close(conversation_pk: int, record_id: str, *, status: str, actor: str, answer: str = "") -> dict | None:
    from shopman.shop.models import Conversation

    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=conversation_pk)
        flags = dict(locked.flags or {})
        stored = flags.get(FLAG_KEY)
        if not isinstance(stored, dict) or stored.get("id") != record_id or stored.get("status") != OPEN:
            return None
        closed = {**stored, "status": status, "closed_at": _now().isoformat(), "closed_by": actor[:100]}
        if answer:
            closed["answer"] = answer
        flags[FLAG_KEY] = closed
        Conversation.objects.filter(pk=conversation_pk).update(flags=flags)
        return closed


def _resolve_card(conversation, record: dict, *, actor: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter

    try:
        if record.get("alert_pk"):
            alert_adapter.resolve_pk(int(record["alert_pk"]), actor=actor)
    except Exception:
        logger.warning("concierge.verification.resolve_failed conversation=%s", conversation.pk, exc_info=True)


def compose_answer(text: str) -> str:
    return _fill(_copy(ANSWER_COPY_KEY), answer=" ".join(str(text or "").split()))


def answer(alert_pk: int, text: str, *, actor: str):
    """A resposta da equipe sai ao cliente pela Concierge; a verificação fecha se sair."""
    from shopman.shop.concierge_verification import DeskResult
    from shopman.shop.models import Conversation

    from . import house_rules
    from .service import send_out_of_turn

    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return DeskResult(False, "empty_answer")
    if len(cleaned) > MAX_ANSWER_CHARS:
        return DeskResult(False, "answer_too_long", str(MAX_ANSWER_CHARS))
    conversation = _by_alert(alert_pk)
    record = current(conversation) if conversation is not None else None
    if conversation is None:
        return DeskResult(False, "not_found")
    if record is None:
        return DeskResult(False, "not_open")
    if conversation.state != Conversation.State.ACTIVE:
        return DeskResult(False, "with_team")
    reply = compose_answer(cleaned)
    reviewed = house_rules.review(
        [reply],
        house_rules.ReplyContext(
            origin=house_rules.HOUSE,
            receipts=frozenset({house_rules.VERIFY}),
            house_contacts=house_rules.house_contacts(),
        ),
    )
    if reviewed.held:
        return DeskResult(False, "house_rule_held", ",".join(sorted({v.rule for v in reviewed.held})), reply)
    reply = reviewed.texts[0]
    message = send_out_of_turn(conversation, reply, receipts=frozenset({house_rules.VERIFY}))
    if message is None or message.transport_state != "accepted":
        code = (getattr(message, "envelope", None) or {}).get("code") or getattr(message, "transport_state", "")
        return DeskResult(False, "not_sent", str(code or "no_binding"), reply)
    closed = _close(conversation.pk, record["id"], status=ANSWERED, actor=actor, answer=cleaned)
    if closed is not None:
        _resolve_card(conversation, closed, actor=actor or ACTOR)
    return DeskResult(True, sent_text=reply)


def take_over(alert_pk: int, *, actor: str):
    """Alguém da equipe assume: a conversa vai para a equipe, e o cliente é avisado."""
    from shopman.shop.concierge_verification import DeskResult
    from shopman.shop.models import Conversation, ConversationMessage

    from .service import mark_handoff, send_out_of_turn

    conversation = _by_alert(alert_pk)
    if conversation is None:
        return DeskResult(False, "not_found")
    record = current(conversation)
    if record is None:
        return DeskResult(False, "not_open")
    closed = _close(conversation.pk, record["id"], status=TAKEN_OVER, actor=actor)
    if closed is None:
        return DeskResult(False, "not_open")
    _resolve_card(conversation, closed, actor=actor or ACTOR)
    if conversation.state != Conversation.State.ACTIVE:
        return DeskResult(True)
    latest = (
        conversation.messages.filter(kind=ConversationMessage.Kind.INBOUND, binding__isnull=False)
        .order_by("-pk")
        .first()
    )
    if latest is None:
        return DeskResult(False, "not_sent", "no_binding")
    questions = "; ".join(q.get("text", "") for q in closed.get("questions") or [])
    mark_handoff(
        conversation,
        latest.binding,
        f"Equipe assumiu a verificação: {questions}"[:200],
        notify_team=False,
    )
    conversation.refresh_from_db()
    ack = _copy(HANDOFF_COPY_KEY)
    message = send_out_of_turn(conversation, ack, purpose="handoff_ack") if ack else None
    if message is not None and message.transport_state != "accepted":
        return DeskResult(True, "not_sent", (message.envelope or {}).get("code", ""), ack)
    return DeskResult(True, sent_text=ack)


# ── Os prazos (WP-06) ─────────────────────────────────────────────────

#: A verificação que passou do segundo prazo e foi entregue à equipe.
HANDED_OFF = "handed_off"

#: A conversa que foi à equipe pelo prazo voltou à Concierge com a mensagem nova do cliente.
RETURNED = "returned"


def returns_on_new_message(conversation) -> bool:
    """Volta sozinha à Concierge quando o cliente escreve de novo? (dono, 20/11/2026, #2836)

    Só a que foi à equipe pelo prazo do "vou verificar" (``verification_timeout``) e que
    ninguém assumiu: a assumida pelo sino (``taken_over``) fica com a equipe, sempre.
    """
    flags = getattr(conversation, "flags", None) or {}
    record = flags.get(FLAG_KEY)
    triage_stamp = flags.get("triage") or {}
    return (
        isinstance(record, dict)
        and record.get("status") == HANDED_OFF
        and triage_stamp.get("escalated_by") == ESCALATED_BY
    )


def mark_returned(conversation_pk: int) -> None:
    """A volta aconteceu: o registro deixa de pedir volta (um handoff depois disso é outro)."""
    from django.db import transaction

    from shopman.shop.models import Conversation

    with transaction.atomic():
        locked = Conversation.objects.select_for_update().filter(pk=conversation_pk).first()
        if locked is None:
            return
        flags = dict(locked.flags or {})
        stored = flags.get(FLAG_KEY)
        if not isinstance(stored, dict) or stored.get("status") != HANDED_OFF:
            return
        flags[FLAG_KEY] = {**stored, "status": RETURNED, "returned_at": _now().isoformat()}
        Conversation.objects.filter(pk=conversation_pk).update(flags=flags)
#: O ``escalated_by`` da triagem do handoff no segundo prazo (``triage.Triage``).
ESCALATED_BY = "verification_timeout"


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _claim_step(conversation_pk: int, record_id: str, *, step: str, now: datetime) -> dict | None:
    """Reivindica um passo do relógio sob trava, ANTES de qualquer envio: sai uma vez só.

    ``step`` é ``nudge`` (grava ``nudged_at``) ou ``handoff`` (fecha como ``handed_off``).
    Devolve o registro como ficou, ou ``None`` se outro ciclo (ou a equipe) chegou antes.
    """
    from shopman.shop.models import Conversation

    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=conversation_pk)
        flags = dict(locked.flags or {})
        stored = flags.get(FLAG_KEY)
        if not isinstance(stored, dict) or stored.get("id") != record_id or stored.get("status") != OPEN:
            return None
        if step == "nudge":
            if stored.get("nudged_at"):
                return None
            updated = {**stored, "nudged_at": now.isoformat()}
        else:
            updated = {**stored, "status": HANDED_OFF, "closed_at": now.isoformat(), "closed_by": ACTOR}
        flags[FLAG_KEY] = updated
        Conversation.objects.filter(pk=conversation_pk).update(flags=flags)
        return updated


def _handoff_triage(record: dict):
    from . import triage

    questions = "; ".join(f"“{q.get('text', '')}”" for q in record.get("questions") or [] if q.get("text"))
    summary = f"A Concierge perguntou à equipe e ninguém respondeu no prazo: {questions}."
    return triage.Triage("human", triage.NOW, triage.TEAM, summary[:480], "verification", ESCALATED_BY)


def _nudge(conversation, record: dict, *, now: datetime) -> str:
    """Primeiro prazo (o prometido): o cliente recebe UM aviso.

    O cartão já conta até este prazo desde que nasceu (``respond_by``) e, vencido, a
    janela do aviso segue na tela dizendo há quanto passou: nada muda nele aqui. A
    severidade fica a de aviso: uma pergunta de cliente não é erro.
    """
    from . import house_rules
    from .service import send_out_of_turn

    claimed = _claim_step(conversation.pk, record["id"], step="nudge", now=now)
    if claimed is None:
        return ""
    text = _copy(NUDGE_COPY_KEY)
    message = send_out_of_turn(conversation, text, receipts=frozenset({house_rules.VERIFY})) if text else None
    if message is None or message.transport_state != "accepted":
        # O aviso é uma vez só: falhou, não volta. O cartão urgente é o que segue valendo.
        logger.warning(
            "concierge.verification.nudge_not_sent conversation=%s code=%s",
            conversation.pk,
            (getattr(message, "envelope", None) or {}).get("code", "") if message is not None else "no_binding",
        )
        return "nudge_not_sent"
    return "nudged"


def _hand_off(conversation, record: dict, *, now: datetime) -> str:
    """Segundo prazo: a conversa vai para a equipe, com a pergunta no cartão de handoff."""
    from shopman.shop.models import Conversation, ConversationMessage

    from .service import mark_handoff, send_out_of_turn

    claimed = _claim_step(conversation.pk, record["id"], step="handoff", now=now)
    if claimed is None:
        return ""
    _resolve_card(conversation, claimed, actor=ACTOR)
    conversation.refresh_from_db()
    if conversation.state != Conversation.State.ACTIVE:
        return "already_with_team"
    latest = (
        conversation.messages.filter(kind=ConversationMessage.Kind.INBOUND, binding__isnull=False)
        .order_by("-pk")
        .first()
    )
    if latest is None:
        return "no_binding"
    team = _handoff_triage(claimed)
    mark_handoff(conversation, latest.binding, team.reason_line(), triage=team)
    conversation.refresh_from_db()
    ack = _copy(HANDOFF_COPY_KEY)
    message = send_out_of_turn(conversation, ack, purpose="handoff_ack") if ack else None
    if message is None or message.transport_state != "accepted":
        return "handed_off_ack_not_sent"
    return "handed_off"


def sweep(*, now: datetime | None = None, limit: int = 200) -> dict[str, int]:
    """Os dois prazos de cada verificação aberta. Custo zero: nenhuma chamada de modelo.

    Os instantes (``nudge_due_at``, ``handoff_due_at``) já foram contados pelo
    calendário da casa quando a verificação abriu; mesmo assim, com a casa fechada
    agora, nada corre (o calendário pode ter mudado depois). Verificação de conversa
    que já está com a equipe fecha calada, com o cartão.
    """
    from shopman.shop.models import Conversation
    from shopman.shop.services import business_calendar

    now = now or _now()
    counts = {"open": 0, "nudged": 0, "nudge_not_sent": 0, "handed_off": 0, "closed_with_team": 0, "closed": 0}
    rows = list(
        Conversation.objects.filter(**{f"flags__{FLAG_KEY}__status": OPEN}).order_by("pk")[: max(1, int(limit))]
    )
    counts["open"] = len(rows)
    if not rows:
        return counts
    house_open = business_calendar.current_business_state(now=now).is_open
    for conversation in rows:
        record = current(conversation)
        if record is None:
            continue
        try:
            if conversation.state != Conversation.State.ACTIVE:
                closed = _close(conversation.pk, record["id"], status=HANDED_OFF, actor=ACTOR)
                if closed is not None:
                    _resolve_card(conversation, closed, actor=ACTOR)
                    counts["closed_with_team"] += 1
                continue
            if not house_open:
                continue
            handoff_due = _parse(record.get("handoff_due_at"))
            nudge_due = _parse(record.get("nudge_due_at"))
            if handoff_due is not None and now >= handoff_due:
                outcome = _hand_off(conversation, record, now=now)
                if outcome.startswith("handed_off"):
                    counts["handed_off"] += 1
                elif outcome:
                    counts["closed"] += 1
            elif nudge_due is not None and now >= nudge_due and not record.get("nudged_at"):
                outcome = _nudge(conversation, record, now=now)
                if outcome:
                    counts[outcome] += 1
        except Exception:
            logger.warning("concierge.verification.sweep_failed conversation=%s", conversation.pk, exc_info=True)
    return counts
