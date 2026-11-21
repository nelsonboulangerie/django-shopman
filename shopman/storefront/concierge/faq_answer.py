"""A resposta às perguntas frequentes pela IA, a partir das FAQs publicadas (#2935).

O motor que o placar do WP-18 mediu (``faq_eval``) e que a Concierge usa desde a palavra do
dono (21/11/2026, "1) sim"): a IA compõe a resposta usando SÓ as perguntas frequentes,
cita as referências que usou e devolve em ``uncovered`` o que nenhuma cobre. O verificador
(``inventions``) é sem modelo: número, hora ou valor fora das FAQs citadas, referência
inexistente, resposta sem citar ou travessão reprovam a resposta, e quem chama cai na FAQ
direta.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_TOKENS = 700
_NUMBER = re.compile(r"\d+(?:[.,:h]\d+)?")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


@dataclass
class Answer:
    refs: list[str]
    text: str = ""
    uncovered: str = ""
    error: str = ""
    cost_usd: float | None = 0.0
    ms: float = 0.0


_SYSTEM = """Você é a Concierge da padaria, no WhatsApp. Responda à cliente usando SÓ as \
perguntas frequentes abaixo. Nunca afirme nada que elas não digam: nada de preço, horário, \
prazo, endereço, ingrediente ou política que não esteja escrito nelas.

Regras:
- cite as referências (ref) só das perguntas frequentes cuja resposta você usou de fato; \
não cite uma pergunta frequente só porque é do mesmo assunto (a pergunta sobre encomendar \
no sábado cita a de encomenda; a de horário só entra se a resposta disser o horário);
- se uma parte da pergunta não é coberta por nenhuma, escreva essa parte em "uncovered" e não \
a responda (a casa vai verificar);
- se nenhuma parte é coberta, devolva refs vazio e answer vazio;
- voz feminina, cordial e curta; sem travessão.

Responda só com JSON: {"refs": ["..."], "answer": "...", "uncovered": "..."}"""


def build_request(text: str, faqs: list, *, model: str) -> dict:
    catalog = "\n\n".join(f"ref: {f.ref}\npergunta: {f.question}\nresposta: {f.answer}" for f in faqs)
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        # Resposta curta, sem raciocínio (o mesmo aprendizado do #2909).
        "thinking": {"type": "disabled"},
        "system": [{"type": "text", "text": _SYSTEM + "\n\nPerguntas frequentes:\n\n" + catalog}],
        "messages": [{"role": "user", "content": f"Mensagem da cliente:\n<<<\n{text}\n>>>"}],
    }


def answer_with_model(text: str, *, faqs: list, client, model: str) -> Answer:
    """Braço B: a IA compõe a resposta a partir das FAQs, citando quais usou."""
    from .observation_privacy import redact_observation_text

    redacted = redact_observation_text(text).text
    started = time.perf_counter()
    try:
        response = client.messages.create(**build_request(redacted, faqs, model=model))
    except Exception as exc:  # fora do ar, tempo, freio: vale a FAQ direta
        logger.warning("concierge.faq_answer.model_failed exception_type=%s", type(exc).__name__)
        return Answer(refs=[], error=type(exc).__name__, ms=(time.perf_counter() - started) * 1000)
    elapsed = (time.perf_counter() - started) * 1000
    if getattr(response, "stop_reason", "") in {"max_tokens", "refusal"}:
        return Answer(refs=[], error=str(response.stop_reason), ms=elapsed)
    raw = "".join(getattr(b, "text", "") for b in getattr(response, "content", []) if getattr(b, "type", "") == "text")
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return Answer(refs=[], error="fora_do_esquema", ms=elapsed)
    refs = [str(r) for r in (data.get("refs") or []) if isinstance(r, str)]
    return Answer(refs=refs, text=str(data.get("answer") or ""), uncovered=str(data.get("uncovered") or ""), ms=elapsed)


def inventions(answer: Answer, faqs: list) -> list[str]:
    """O que a resposta afirma sem estar nas FAQs citadas. Vazio = nada inventado."""
    by_ref = {f.ref: f for f in faqs}
    out = [f"referência inexistente: {ref}" for ref in answer.refs if ref not in by_ref]
    if answer.text.strip() and not answer.refs:
        out.append("respondeu sem citar pergunta frequente")
    cited = _fold(" ".join(by_ref[r].answer + " " + by_ref[r].question for r in answer.refs if r in by_ref))
    cited_numbers = {n.replace(",", ".") for n in _NUMBER.findall(cited)}
    for number in _NUMBER.findall(_fold(answer.text)):
        if number.replace(",", ".") not in cited_numbers:
            out.append(f"número fora das FAQs: {number}")
    if "—" in answer.text:
        out.append("travessão")
    return out


# ── Conferência pelo Jev (auditoria do Jev, item 2, 21/11/2026) ─────────────

#: A partir de quanto o Jev diz que a resposta se sustenta nas FAQs citadas.
SUPPORTED_AT = 0.5
SUPPORT_QUESTION = "supported"
SUPPORT_INSTRUCTIONS = (
    "A resposta da loja diz só o que as perguntas frequentes citadas dizem, sem acrescentar fato, "
    "número, prazo, preço ou política que elas não tragam?"
)


def support_request(answer: Answer, faqs: list, *, model: str) -> dict:
    """O pedido ao Jev: as FAQs citadas e a resposta (redigida) no estado, uma pergunta sim/não."""
    from .observation_privacy import redact_observation_text

    by_ref = {f.ref: f for f in faqs}
    cited = [by_ref[r] for r in answer.refs if r in by_ref]
    return {
        "model": model,
        "state": {
            "faqs": "\n\n".join(f"pergunta: {f.question}\nresposta: {f.answer}" for f in cited),
            "store_answer": redact_observation_text(answer.text).text,
        },
        "questions": {SUPPORT_QUESTION: {"type": "noul", "instructions": SUPPORT_INSTRUCTIONS}},
    }


def jev_support(answer: Answer, faqs: list, *, session=None, timeout: float = 5.0) -> float | None:
    """A probabilidade de a resposta se sustentar nas FAQs citadas, pelo Jev; ``None`` sem Jev.

    Sem Jev configurado, com o freio fechado ou com falha do provedor, ``None``: quem chama
    segue com o verificador sem modelo (``inventions``), que já passou.
    """
    from shopman.shop import ai

    from .intent_benchmark import parse_jev_boolean

    try:
        url, api_key, model = ai.jev_endpoint(customer_text=True)
    except ai.AINotConfigured:
        return None
    if session is None:
        import requests

        session = requests.Session()
    body = support_request(answer, faqs, model=model)
    try:
        response = ai.jev_post(session, url, api_key, body, timeout=timeout, model=model)
        if response.status_code >= 400:
            logger.warning("concierge.faq_answer.jev_http status=%s", response.status_code)
            return None
        return parse_jev_boolean(response.json(), question=SUPPORT_QUESTION)
    except Exception as exc:
        logger.warning("concierge.faq_answer.jev_failed exception_type=%s", type(exc).__name__)
        return None


def held_by_jev(answer: Answer, faqs: list, *, session=None) -> bool:
    """O Jev diz que a resposta NÃO se sustenta nas FAQs citadas (com Jev; sem ele, nunca)."""
    if not answer.refs or not answer.text.strip():
        return False
    support = jev_support(answer, faqs, session=session)
    return support is not None and support < SUPPORTED_AT


def cited_verbatim(answer: Answer, faqs: list, *, limit: int = 2) -> Answer:
    """A resposta com o texto das FAQs que a IA citou, palavra por palavra (sem o texto da IA).

    É o caminho quando o Jev reprova (placar de produção, 21/11/2026): a FAQ direta caía
    na primeira que casava e perdia o assunto (o feriado virava só o horário), e as FAQs
    citadas pela IA eram as certas. Aqui não há o que inventar: é o texto da casa.
    """
    by_ref = {f.ref: f for f in faqs}
    cited = [by_ref[ref] for ref in dict.fromkeys(answer.refs) if ref in by_ref][:limit]
    if not cited:
        return Answer(refs=[], text="", uncovered=answer.uncovered, ms=answer.ms, cost_usd=answer.cost_usd)
    return Answer(
        refs=[f.ref for f in cited],
        text="\n\n".join(f.answer.strip() for f in cited),
        uncovered=answer.uncovered,
        ms=answer.ms,
        cost_usd=answer.cost_usd,
    )
