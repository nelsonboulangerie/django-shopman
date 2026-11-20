"""Promover a resposta da equipe a pergunta frequente (WP-15, dono, 16/11/2026).

Depois que a equipe responde um "vou verificar", quem respondeu pode promover a
pergunta: nasce uma ``FAQEntry`` **não publicada**, com pergunta, resposta e termos de
busca sugeridos pela IA a partir da pergunta do cliente (redigida) e da resposta da
equipe. Só vale para os próximos clientes depois de publicada no Admin, por quem já
publica pergunta frequente. Sem IA configurada, com o freio fechado ou com resposta que
não serve, o rascunho nasce com os textos originais, sem sugestão.

A sugestão vai pelo propósito ``concierge``: é texto de cliente, e só a conexão liberada
para mensagem de cliente o recebe (``ai.CUSTOMER_TEXT_PURPOSES``). O propósito ``copy``
do catálogo não serve, porque não passa por essa liberação.

Promover duas vezes a mesma verificação devolve o mesmo rascunho: a referência sai da
conversa e da verificação (``concierge-<conversa>-<verificação>``).
"""

from __future__ import annotations

import json
import logging
import re

from shopman.shop.concierge_verification import DATED_WARNING, cites_a_date, faq_ref

logger = logging.getLogger(__name__)

QUESTION_CHARS = 220
ANSWER_CHARS = 2000
TERMS_CHARS = 300
SUGGEST_MAX_TOKENS = 800

def _redacted(text: str, *, names=()) -> str:
    from .observation_privacy import redact_observation_text

    return redact_observation_text(str(text or ""), names=names).text


def _house_text(text: str, *, names=()) -> str:
    """O texto da casa (a resposta da equipe, o que a IA devolve): sem contato, segredo e o
    nome do cliente, mas com o endereço da casa, que é resposta e não dado de ninguém."""
    from shopman.shop.telemetry_redaction import redact_text

    from .observation_privacy import _redact_known_names

    text, _count = _redact_known_names(str(text or ""), list(names))
    return " ".join(redact_text(text).split())


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


_PROMPT = """Uma cliente perguntou e a equipe da padaria respondeu. Transforme em uma pergunta \
frequente que sirva para qualquer cliente, sem nada desta conversa em particular.

Pergunta da cliente: {question}
Resposta da equipe: {answer}

Regras:
- não acrescente fato que a resposta da equipe não diz (preço, horário, prazo, ingrediente);
- nada de nome, telefone, e-mail, endereço ou documento;
- sem travessão;
- pergunta em até {question_chars} caracteres, resposta em até {answer_chars};
- termos de busca: até 8 sinônimos curtos, separados por vírgula.

Responda só com JSON: {{"question": "...", "answer": "...", "search_terms": "..."}}"""


def suggest(question: str, answer: str) -> dict | None:
    """A generalização pela IA, ou ``None`` (sem IA, freio fechado, resposta torta)."""
    from shopman.shop.services import copy_assist

    prompt = _PROMPT.format(
        question=question, answer=answer, question_chars=QUESTION_CHARS, answer_chars=ANSWER_CHARS
    )
    try:
        raw = copy_assist.suggest(prompt, max_tokens=SUGGEST_MAX_TOKENS, purpose="concierge")
    except Exception as exc:  # sem IA, freio, provedor fora: o rascunho nasce sem sugestão
        logger.info("concierge.faq_promotion.no_suggestion reason=%s", type(exc).__name__)
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not str(data.get("question") or "").strip() or not str(data.get("answer") or "").strip():
        return None
    return data


def promote(alert_pk: int, *, actor: str):
    """Cria (ou devolve) o rascunho de pergunta frequente da verificação respondida.

    ``DeskResult``: ``detail`` é a referência do rascunho; ``sent_text`` leva o aviso de
    data, quando a resposta cita um dia. ``code`` ``not_found`` (o cartão não é de uma
    verificação desta conversa), ``not_answered`` (a equipe ainda não respondeu, ou a
    conversa já abriu outra verificação) ou ``already_promoted`` (``ok`` verdadeiro: o
    rascunho já existe).
    """
    from shopman.shop.concierge_verification import DeskResult
    from shopman.shop.models import FAQEntry

    from . import verification

    conversation = verification._by_alert(alert_pk)
    if conversation is None:
        return DeskResult(False, "not_found")
    record = (conversation.flags or {}).get(verification.FLAG_KEY) or {}
    if record.get("status") != verification.ANSWERED or not record.get("answer"):
        return DeskResult(False, "not_answered")
    ref = faq_ref(conversation.pk, str(record.get("id") or ""))
    existing = FAQEntry.objects.filter(ref=ref).first()
    if existing is not None:
        return DeskResult(True, "already_promoted", ref, DATED_WARNING if cites_a_date(existing.answer) else "")

    names = [conversation.customer_name] if conversation.customer_name else []
    question = _redacted(
        " ".join(q.get("text", "") for q in record.get("questions") or [] if q.get("text")), names=names
    )
    answer = _house_text(record["answer"], names=names)
    suggested = suggest(question, answer) or {}
    # O que volta da IA passa de novo pelo redator: ela não acrescenta contato nem nome.
    entry = FAQEntry(
        ref=ref,
        question=_clip(_house_text(suggested.get("question") or question, names=names), QUESTION_CHARS),
        answer=_clip(_house_text(suggested.get("answer") or answer, names=names), ANSWER_CHARS),
        search_terms=_clip(_house_text(suggested.get("search_terms") or "", names=names), TERMS_CHARS),
        is_published=False,
    )
    from django.db import IntegrityError, transaction

    entry._change_reason = (
        f"Promovida da verificação {record.get('id', '')} da conversa {conversation.pk}"
        f" por {actor or 'operador'}" + (" (sugestão da IA)" if suggested else " (textos originais, sem IA)")
    )[:100]
    try:
        with transaction.atomic():
            entry.save()
    except IntegrityError:
        # Dois cliques ao mesmo tempo: o outro criou primeiro, e é o mesmo rascunho.
        return DeskResult(True, "already_promoted", ref, DATED_WARNING if cites_a_date(entry.answer) else "")
    return DeskResult(True, "", ref, DATED_WARNING if cites_a_date(entry.answer) else "")
