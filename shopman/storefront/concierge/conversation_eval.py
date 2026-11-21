"""Placar de conversa da Nice: as conversas reais, turno a turno, e o que a IA do ManyChat faria.

A régua de mensagem (``reply_eval``) mede o destino e a intenção. Esta mede o que o cliente
viveu: se a casa respondeu, se a resposta tinha lastro e se deixou o próximo passo. A conta é
do framework (``conversational_commerce.evaluation.conversation``); aqui mora só o que é da
Nice: ler ``ConversationMessage``, e o leitor em português de "próximo passo" e "frase
repetida".

Um turno é o bloco de falas seguidas do cliente e as respostas da casa até a próxima fala
dele. O que cada sinal lê:

- **respondeu**: ao menos um bloco ``reply`` da casa antes da próxima fala do cliente;
- **silêncio legítimo**: a fala chegou com a conversa com a equipe (entre a nota "Atendimento
  humano solicitado" e a nota "Voltou para o concierge", ou depois do ``handoff_at`` de uma
  conversa que segue com a equipe), ou não era elegível à automação;
- **lastro**: a frase da casa sai por molde, com o fato do sistema (o modelo não redige,
  D-040 item 3), e a resposta da FAQ pela IA só sai depois da conferência mecânica
  (``faq_answer.inventions``). Sem lastro é o que a última trava das regras da casa
  segurou (``envelope.house_rules.held``);
- **próximo passo**: pergunta ao cliente, oferta, ação feita, "vou verificar" ou equipe
  avisada, link; um "obrigado" do cliente não pede passo nenhum;
- **dado vivo / ação**: pelos atos que a leitura gravou em ``usage.intents``.

A IA do ManyChat entra como perfil de capacidade, do levantamento de 21/11/2026 na conta da
casa: no WhatsApp ela só reconhece intenção e roteia para fluxo pronto (AI Step, Intention
Recognition); responder texto livre (AI Replies) é só no Instagram, em beta; e ela não enxerga
dado ao vivo nem age no comércio. Comparação por capacidade declarada, não por execução.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from conversational_commerce.evaluation import IncumbentProfile, Scorecard, TurnEvidence, incumbent_reach, outcome_of
from conversational_commerce.evaluation import score as score_turns

MANYCHAT_WHATSAPP = IncumbentProfile(
    "ManyChat AI no WhatsApp", reads_live_data=False, acts_on_commerce=False, free_text_in_channel=False
)
MANYCHAT_INSTAGRAM = IncumbentProfile(
    "ManyChat AI no Instagram", reads_live_data=False, acts_on_commerce=False, free_text_in_channel=True
)
INCUMBENTS = (MANYCHAT_WHATSAPP, MANYCHAT_INSTAGRAM)

REACH_LABELS = {
    "reaches": "alcançaria",
    "no_free_text": "só roteia para fluxo pronto",
    "no_live_data": "não enxerga estoque, preço do dia nem pedido",
    "cannot_act": "não mexe na sacola nem no pedido",
}
OUTCOME_LABELS = {
    "useful": "útil (com lastro e próximo passo)",
    "dead_end": "sem saída (respondeu e parou)",
    "unbacked": "sem lastro",
    "silent": "silêncio (ninguém respondeu)",
}

#: Atos (``intents.ACT_NAMES``) que pedem dado vivo para serem bem atendidos, e os que pedem ação.
LIVE_DATA_ACTS = frozenset({"product_question", "order", "order_status"})
ACTION_ACTS = frozenset({"order", "cancel_order", "negotiation"})
#: Atos que não pedem próximo passo: o cliente agradeceu ou se despediu.
CLOSING_ACTS = frozenset({"thanks"})

_NEXT_STEP = re.compile(
    r"\?|https?://"
    r"|\b(quer|queira|querem|posso|podemos|pode me|gostaria|deseja|prefere|separo|reservo|anoto|confirma"
    r"|vou verificar|verifico|ja volto|volto (aqui|ja|com)|te (aviso|respondo|conto)"
    r"|(ja )?(chamei|avisei) a equipe|a equipe (vai|ja|te)|alguem da equipe"
    r"|na (sua )?sacola|seu pedido|pedido [a-z0-9-]*\s*(registrado|confirmado|feito)"
    r"|toque|acesse|pelo site|pela loja|amanha|a partir d[ae]s?|volta (a ter|amanha|hoje))\b"
)
#: As notas que a casa grava quando a equipe assume e quando devolve (``service``).
TEAM_TAKES_NOTE = "Atendimento humano solicitado"
BACK_NOTE = "Voltou para o concierge"
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def fold(text: str) -> str:
    """Minúsculas e sem acento, para o leitor de padrões."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def has_next_step(reply: str) -> bool:
    return bool(_NEXT_STEP.search(fold(reply)))


def repeated_sentence(reply: str) -> bool:
    seen = set()
    for sentence in _SENTENCE_SPLIT.split(reply or ""):
        key = re.sub(r"[^a-z0-9 ]", "", fold(sentence)).strip()
        if len(key) < 12:
            continue
        if key in seen:
            return True
        seen.add(key)
    return False


@dataclass
class Turn:
    """Um turno lido do banco, com o texto para a leitura humana do placar."""

    evidence: TurnEvidence
    customer: str
    reply: str
    conversation_id: int
    #: O veredito da conferência antes do envio (``envelope["conference"]``), quando houve.
    conference: dict | None = None
    #: A escada em sombra (``envelope["ladder"]``): o que a reescrita teria mandado.
    ladder: dict | None = None
    #: Dia do turno e o gasto dele (régua do turno + escada), em US$; ``None`` = desconhecido.
    day: str = ""
    cost_usd: float | None = 0.0


def _acts(usage: dict) -> set[str]:
    return {a.get("act", "") for a in ((usage or {}).get("intents") or {}).get("acts", []) if isinstance(a, dict)}


def _evidence(turn_id: str, inbound: list, replies: list, *, with_team: bool) -> TurnEvidence:
    excused = with_team or not any(m.automation_eligible for m in inbound)
    if not replies:
        return TurnEvidence(turn_id, replied=False, silence_expected=excused, topic="")
    usage = next((r.usage for r in replies if r.usage), {}) or {}
    acts = _acts(usage)
    text = "\n".join(r.text for r in replies if r.text)
    held = any(((r.envelope or {}).get("house_rules") or {}).get("held") for r in replies)
    latency = (usage.get("latency_ms") or {}).get("total")
    return TurnEvidence(
        turn_id,
        replied=True,
        backed=False if held else True,
        next_step=bool(acts) and acts <= CLOSING_ACTS or has_next_step(text),
        repeated=repeated_sentence(text),
        needs_live_data=bool(acts & LIVE_DATA_ACTS),
        needs_action=bool(acts & ACTION_ACTS),
        latency_ms=int(latency) if isinstance(latency, (int, float)) else None,
        topic=",".join(sorted(acts)) or usage.get("layer", ""),
    )


def _turn_cost(replies) -> float | None:
    """O gasto do turno: a régua (``usage.cost_usd``) mais a escada em sombra. Desconhecido não é zero."""
    total = 0.0
    for reply in replies:
        # Só conta o que foi gravado: chave ausente é "nada gasto aqui"; ``None`` gravado é desconhecido.
        for source in (reply.usage or {}, (reply.envelope or {}).get("ladder") or {}):
            if "cost_usd" not in source:
                continue
            if source["cost_usd"] is None:
                return None
            total += float(source["cost_usd"])
    return round(total, 6)


def _conversation_turns(conversation, messages) -> list[Turn]:
    """Os turnos de uma conversa, com a posse (casa ou equipe) acompanhada pelas notas."""
    from shopman.shop.models import Conversation, ConversationMessage

    turns: list[Turn] = []
    inbound: list = []
    replies: list = []
    with_team = turn_with_team = False

    def still_with_team(message) -> bool:
        return bool(
            conversation.state == Conversation.State.HANDOFF
            and conversation.handoff_at
            and conversation.handoff_at <= message.created_at
        )

    def flush() -> None:
        turn_id = f"c{conversation.pk}-m{inbound[0].pk}"
        turns.append(Turn(
            _evidence(turn_id, inbound, replies, with_team=turn_with_team),
            customer=" / ".join(m.text for m in inbound if m.text),
            reply="\n".join(r.text for r in replies if r.text),
            conversation_id=conversation.pk,
            conference=next(((r.envelope or {}).get("conference") for r in replies
                             if (r.envelope or {}).get("conference")), None),
            ladder=next(((r.envelope or {}).get("ladder") for r in replies if (r.envelope or {}).get("ladder")), None),
            day=inbound[0].created_at.date().isoformat(),
            cost_usd=_turn_cost(replies),
        ))
        inbound.clear()
        replies.clear()

    for message in messages:
        if message.kind == ConversationMessage.Kind.NOTE:
            takes, back = message.text.startswith(TEAM_TAKES_NOTE), message.text.startswith(BACK_NOTE)
            if (takes or back) and inbound:
                flush()  # a posse mudou: o que veio antes é outro turno
            with_team = True if takes else False if back else with_team
            continue
        if message.kind == ConversationMessage.Kind.INBOUND:
            if replies:
                flush()
            if not inbound:
                turn_with_team = with_team or still_with_team(message)
            inbound.append(message)
        elif inbound:
            replies.append(message)
    if inbound:
        flush()
    return turns


def read_turns(*, days: int = 7, channel_ref: str = "whatsapp", conversation_id: int | None = None) -> list[Turn]:
    """Os turnos reais dos últimos ``days`` dias, em ordem, por conversa."""
    from django.utils import timezone

    from shopman.shop.models import Conversation, ConversationMessage

    since = timezone.now() - timedelta(days=days)
    conversations = Conversation.objects.filter(channel_ref=channel_ref, last_inbound_at__gte=since)
    if conversation_id:
        conversations = conversations.filter(pk=conversation_id)
    turns: list[Turn] = []
    for conversation in conversations.order_by("pk"):
        messages = conversation.messages.filter(
            created_at__gte=since,
            kind__in=(
                ConversationMessage.Kind.INBOUND,
                ConversationMessage.Kind.REPLY,
                ConversationMessage.Kind.NOTE,
            ),
        ).order_by("created_at", "pk")
        turns.extend(_conversation_turns(conversation, messages))
    return turns


def _redacted(text: str) -> str:
    from .observation_privacy import redact_observation_text

    return redact_observation_text(text).text


def _pct(part: int, whole: int) -> str:
    return "n/d" if not whole else f"{100 * part / whole:.0f}%"


def render(turns: list[Turn], *, show: int = 40) -> str:
    card: Scorecard = score_turns([t.evidence for t in turns], INCUMBENTS)
    scored = card.scored
    lines = [
        f"Placar de conversa: {card.turns} turnos de cliente, {scored} contam "
        f"({card.excused_silence} com a equipe, fora do placar).",
    ]
    for outcome in ("useful", "dead_end", "unbacked", "silent"):
        n = card.outcomes.get(outcome, 0)
        lines.append(f"  {OUTCOME_LABELS[outcome]}: {n}/{scored} ({_pct(n, scored)})")
    lines.append(f"  frase repetida na resposta: {card.repeated}")
    if card.latencies_ms:
        lat = card.latencies_ms
        lines.append(f"  ponta a ponta: p50 {lat[len(lat) // 2] / 1000:.1f} s, máximo {lat[-1] / 1000:.1f} s")
    lines.append(f"  pronto (0 sem lastro, 0 silêncio, útil >= 90%): {'sim' if card.meets() else 'não'}")
    for name, reach in card.incumbents.items():
        ok = reach.get("reaches", 0)
        lines.append(f"  {name} alcançaria {ok}/{scored} ({_pct(ok, scored)}): " + "; ".join(
            f"{REACH_LABELS[k]} {v}" for k, v in sorted(reach.items(), key=lambda kv: -kv[1]) if k != "reaches"
        ))
    conferred = [t for t in turns if t.conference and outcome_of(t.evidence) is not None]
    if conferred:
        would_fall = [t for t in conferred if t.conference.get("decision") == "fallback"]
        agree = sum(
            (t.conference.get("decision") == "fallback") == (outcome_of(t.evidence) != "useful") for t in conferred
        )
        reasons = Counter(
            f"{check}:{(row or {}).get('reason') or (row or {}).get('status')}"
            for t in would_fall for check, row in (t.conference.get("checks") or {}).items()
            if (row or {}).get("status") != "pass"
        )
        lines.append(
            f"  conferência antes do envio (sombra): {len(conferred)} conferidos, reprovaria {len(would_fall)}, "
            f"concorda com o placar em {agree}/{len(conferred)}"
            + (": " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()) if reasons else "")
        )
    climbed = [t for t in turns if t.ladder]
    if climbed:
        chosen = Counter(t.ladder.get("chosen", "?") for t in climbed)
        pauta = Counter(
            reason for t in climbed for a in t.ladder.get("attempts", [])
            for check, row in ((a.get("conference") or {}).get("checks") or {}).items()
            if (row or {}).get("status") != "pass"
            for reason in [f"{check}:{(row or {}).get('reason') or (row or {}).get('status')}"]
        )
        lines.append(
            f"  escada (sombra): {len(climbed)} subidas; escolheria "
            + ", ".join(f"{k} {v}" for k, v in chosen.most_common())
            + ("; pauta (motivos): " + ", ".join(f"{k} {v}" for k, v in pauta.most_common(6)) if pauta else "")
        )
    by_day: dict[str, float | None] = {}
    for t in turns:
        if t.day:
            current = by_day.get(t.day, 0.0)
            by_day[t.day] = None if current is None or t.cost_usd is None else round(current + t.cost_usd, 6)
    if by_day:
        lines.append("  gasto por dia (régua do turno + escada): " + ", ".join(
            f"{day} {'desconhecido' if v is None else f'US$ {v:.4f}'}" for day, v in sorted(by_day.items())
        ))
    bad = [t for t in turns if outcome_of(t.evidence) not in (None, "useful") or t.evidence.repeated]
    if bad and show:
        lines.append("")
        lines.append(f"Turnos a consertar ({min(show, len(bad))} de {len(bad)}):")
        for t in bad[:show]:
            outcome = outcome_of(t.evidence) or "useful"
            mark = OUTCOME_LABELS[outcome].split(" (")[0] + (" + repetida" if t.evidence.repeated else "")
            reach = incumbent_reach(t.evidence, MANYCHAT_WHATSAPP)
            lines.append(f"  [{t.evidence.turn_id}] {mark} · {t.evidence.topic or '?'}")
            lines.append(f"      cliente: {_redacted(t.customer)[:160]}")
            lines.append(f"      casa:    {_redacted(t.reply).replace(chr(10), ' / ')[:240] or '(nada)'}")
            lines.append(f"      ManyChat AI faria: {REACH_LABELS[reach]}")
            if t.conference:
                lines.append(f"      conferência (sombra): {t.conference.get('decision')}")
            if t.ladder:
                chosen = t.ladder.get("chosen")
                text = next((a.get("text") for a in t.ladder.get("attempts", []) if a.get("source") == chosen), "")
                lines.append(f"      escada escolheria: {chosen}" + (f" · {_redacted(text)[:200]}" if text else ""))
    return "\n".join(lines)
