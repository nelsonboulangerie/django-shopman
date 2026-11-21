"""A conferência da Nice antes do envio: o juiz pelo Jev e a leitura do turno (em sombra).

A regra é do framework (``conversational_commerce.reply.conference``); aqui mora o que é da
Nice:

- **o juiz** (``JevJudge``): uma pergunta ``choice`` ao Jev, com a fala do cliente (pelo
  redator da observação) e a resposta que a casa vai enviar pelo MESMO redator da fala da
  casa do 1b (``triage.house_line``: sem nome, contato, documento, endereço, código de pedido
  nem valores; D-040 e o adendo de 21/11). Só essas duas falas, nada da conversa anterior.
  Passa pelo freio e pelo medidor da porta de IA (``ai.jev_post``). Sem Jev configurado, não há
  juiz: a conferência fica com o lado determinístico;
- **por construção**: a resposta é por molde sobre o fato, salvo quando a IA compôs a partir
  das FAQs (``faq_answer``), que é texto redigido;
- **útil**: o leitor de próximo passo do placar de conversa (``conversation_eval``); um
  "obrigado" do cliente não pede passo.

**Modo sombra** (dono, 21/11/2026: "é fundamental uma 'conferência' antes de enviar para o
cliente"): a conferência roda em todo turno e grava o veredito em
``envelope["conference"]`` do primeiro bloco, sem mudar o que sai. O placar de conversa mede
quantas vezes ela reprovaria e se acertou; só então ela passa a valer, com a alternativa
segura. Nada aqui derruba o turno.
"""

from __future__ import annotations

import logging
import time

from conversational_commerce.reply import Conference, JudgeVerdict, confer

from .conversation_eval import CLOSING_ACTS, has_next_step

logger = logging.getLogger(__name__)

VERDICT_QUESTION = "verdict"
VERDICT_INSTRUCTIONS = (
    "Você confere a resposta que uma padaria vai mandar ao cliente pelo WhatsApp, antes do envio. "
    "Leia a mensagem do cliente e a resposta da casa e escolha a opção que descreve a resposta."
)
VERDICT_CRITERIA = {
    "answers": "A resposta atende ao que o cliente pediu: responde, pergunta o que falta, oferece "
    "um próximo passo, ou diz que vai verificar com a equipe.",
    "off_target": "A resposta fala de outra coisa, ignora parte do que o cliente pediu, ou responde "
    "algo que ele não perguntou.",
    "contradicts": "A resposta se contradiz, ou repete a mesma informação de um jeito que confunde.",
}
#: Abaixo desta confiança, a palavra do juiz não reprova (o Jev em dúvida não derruba resposta boa).
MIN_CONFIDENCE_TO_FAIL = 0.6
JUDGE_TIMEOUT_S = 3.0


def _redacted(text: str) -> str:
    from .observation_privacy import redact_observation_text

    return redact_observation_text(text or "").text


class JevJudge:
    """O juiz pelo Jev: uma pergunta ``choice``, texto redigido, freio e medidor da porta."""

    def __init__(self, *, meter=None, session=None, timeout: float = JUDGE_TIMEOUT_S):
        from shopman.shop import ai

        self.url, self.api_key, self.model = ai.jev_endpoint(customer_text=True)
        self.meter, self.timeout = meter, timeout
        if session is None:
            import requests

            session = requests.Session()
        self.session = session

    def build_request(self, *, customer: str, reply: str, previous: str = "") -> dict:
        from .triage import house_line

        # ``previous`` não vai: minimização (só a fala do cliente e a resposta a conferir).
        state = {"customer_message": _redacted(customer), "house_reply": house_line([("Casa", reply)])}
        return {
            "model": self.model,
            "state": state,
            "questions": {VERDICT_QUESTION: {"type": "choice", "instructions": VERDICT_INSTRUCTIONS,
                                             "criteria": VERDICT_CRITERIA}},
        }

    def judge(self, *, customer: str, reply: str, previous: str = "") -> JudgeVerdict:
        from shopman.shop import ai

        from .intent_benchmark import parse_jev_choice

        body = self.build_request(customer=customer, reply=reply, previous=previous)
        started = time.perf_counter()
        try:
            response = ai.jev_post(self.session, self.url, self.api_key, body, timeout=self.timeout, model=self.model)
        finally:
            if self.meter is not None:
                self.meter.add_time("conference", (time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise RuntimeError(f"jev_http_{response.status_code}")
        payload = response.json()
        if self.meter is not None:
            usage = payload.get("usage") or {}
            self.meter.add_call("conference", self.model, {
                "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens", 0)),
            }, provider="typesafe")
        probabilities, confidence = parse_jev_choice(payload, question=VERDICT_QUESTION)
        answer = max(probabilities, key=probabilities.get)
        if answer != "answers" and (confidence or 0.0) < MIN_CONFIDENCE_TO_FAIL:
            answer = "answers"  # dúvida do juiz não reprova
        return JudgeVerdict(answer, confidence)


def judge_for(meter=None):
    """O juiz da casa, ou ``None`` sem Jev configurado (a conferência segue sem ele)."""
    from shopman.shop import ai

    try:
        return JevJudge(meter=meter)
    except ai.AINotConfigured:
        return None
    except Exception:  # noqa: BLE001 — montar o juiz nunca derruba o turno
        logger.warning("concierge.conference.judge_unavailable", exc_info=True)
        return None


def _acts(outcome) -> set[str]:
    return {a.get("act", "") for a in (getattr(outcome, "intents", None) or {}).get("acts", []) if isinstance(a, dict)}


def by_construction(outcome) -> bool:
    """Todo fato saiu de molde sobre lastro: não há parte composta pela IA a partir das FAQs."""
    return not any(event.get("name") == "faq_answer" for event in getattr(outcome, "tool_events", None) or [])


def previous_house_reply(conversation) -> str:
    from shopman.shop.models import ConversationMessage

    last = (
        ConversationMessage.objects.filter(conversation=conversation, kind=ConversationMessage.Kind.REPLY)
        .order_by("-pk").values_list("text", flat=True).first()
    )
    return last or ""


def confer_turn(*, conversation, outcome, customer_text: str, texts: list[str], held: bool,
                meter=None, judge=None) -> Conference | None:
    """O veredito do turno, em sombra. ``None`` quando nem a conferência fechou (nunca derruba o turno)."""
    reply = "\n".join(text for text in texts if text)
    if not reply:
        return None
    acts = _acts(outcome)
    try:
        return confer(
            customer=customer_text,
            reply=reply,
            held=held,
            by_construction=by_construction(outcome),
            has_next_step=has_next_step(reply),
            judge=judge if judge is not None else judge_for(meter),
            previous=previous_house_reply(conversation),
            next_step_needed=not (acts and acts <= CLOSING_ACTS),
        )
    except Exception:  # noqa: BLE001
        logger.warning("concierge.conference.failed conversation=%s", getattr(conversation, "pk", None), exc_info=True)
        return None
