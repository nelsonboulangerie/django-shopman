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


# ── A escada, em sombra ────────────────────────────────────────────────

#: Os degraus da Nice, do barato ao capaz: propósitos da porta de IA, com rota no Admin.
LADDER_PURPOSES = ("concierge_rewrite", "concierge_escalation")
REWRITE_MAX_TOKENS = 300
REWRITE_TIMEOUT_S = 8.0
DEFAULT_POLICY = {"max_attempts": 3, "turn_usd": 0.01}
REWRITE_SYSTEM = (
    "Você é a concierge de uma padaria no WhatsApp e reescreve uma resposta que a conferência "
    "reprovou. Regras, todas obrigatórias:\n"
    "1. Use SOMENTE os fatos da resposta original (nomes, preços, quantidades, horários). Não "
    "acrescente produto, preço, número, prazo nem promessa que não esteja nela.\n"
    "2. Corrija o motivo da reprovação. Se faltou o próximo passo, termine oferecendo UM dos "
    "passos permitidos, e nenhum outro.\n"
    "3. Voz feminina, cordial e curta, em português do Brasil. Sem travessão. Sem emoji além de 💛.\n"
    "4. Responda só com o texto da mensagem, sem aspas e sem explicação."
)
REJECTION_LABELS = {
    "useful:no_next_step": "a resposta não diz ao cliente o que ele pode fazer em seguida",
    "useful:judge_off_target": "a resposta não atende ao que o cliente pediu",
    "correct:judge_contradicts": "a resposta se contradiz ou repete informação de forma confusa",
    "correct:judge_rejected": "a resposta não se sustenta",
    "correct:unconferred": "ninguém conferiu a resposta",
    "acceptable:held": "a resposta fere uma regra da casa (número sem fato, voz ou forma)",
}


def ladder_policy():
    """A política da escada, de ``Shop.ai_limits["conference"]`` (Admin), com o padrão do dono (3)."""
    from conversational_commerce.reply import LadderPolicy

    from shopman.shop.models import Shop

    shop = Shop.load()
    raw = ((getattr(shop, "ai_limits", None) or {}) if shop else {}).get("conference") or {}
    try:
        attempts = int(raw.get("max_attempts", DEFAULT_POLICY["max_attempts"]))
        turn_usd = float(raw.get("turn_usd", DEFAULT_POLICY["turn_usd"]))
    except (TypeError, ValueError):
        attempts, turn_usd = DEFAULT_POLICY["max_attempts"], DEFAULT_POLICY["turn_usd"]
    # Valendo é a #3040: até lá a escada só mede, qualquer que seja a configuração.
    return LadderPolicy(max_attempts=max(1, min(attempts, 5)), turn_budget_usd=max(0.0, min(turn_usd, 0.05)))


class ModelDrafter:
    """Um degrau: a porta de IA no propósito dado, só com rota EXPLÍCITA no Admin (sem cair na ``default``)."""

    def __init__(self, purpose: str):
        from shopman.shop import ai

        if not isinstance(ai._routes().get(purpose), dict) or not ai._routes()[purpose].get("connection"):
            raise ai.AINotConfigured(f"sem rota explícita para {purpose}", code="no_connection")
        self.name = purpose
        self.client, self.model = ai.anthropic_client(purpose, timeout=REWRITE_TIMEOUT_S, max_retries=0)

    def estimate_usd(self) -> float | None:
        from shopman.shop import ai_governor

        try:
            return ai_governor.estimate_usd(self.model, tokens_in=900, tokens_out=REWRITE_MAX_TOKENS)
        except Exception:  # noqa: BLE001
            return None

    def build_request(self, *, customer, facts, allowed_steps, rejection, previous="") -> dict:
        from .triage import _ORDER_CODE_RE

        reasons = [REJECTION_LABELS.get(r, r) for r in rejection]
        # Minimização (o que /privacidade declara): a fala do cliente e a resposta reprovada,
        # redigidas, sem o código do pedido; a conversa anterior não vai. Os valores ficam:
        # são o lastro da reescrita, e a frase de /privacidade diz.
        facts_out = _ORDER_CODE_RE.sub(r"\1 [pedido omitido]", _redacted(facts))
        lines = [
            f"Mensagem do cliente: {_redacted(customer)}",
            f"Resposta original (os únicos fatos que você pode usar):\n{facts_out}",
            "Por que foi reprovada: " + "; ".join(reasons),
            "Passos permitidos: " + ("; ".join(allowed_steps) if allowed_steps else "nenhum (só corrija o resto)"),
        ]
        return {
            "model": self.model,
            "max_tokens": REWRITE_MAX_TOKENS,
            "system": REWRITE_SYSTEM,
            "messages": [{"role": "user", "content": "\n\n".join(lines)}],
        }

    def draft(self, *, customer, facts, allowed_steps, rejection, previous=""):
        from conversational_commerce.reply import Draft

        from shopman.shop.services.ai_pricing import usage_cost

        response = self.client.messages.create(**self.build_request(
            customer=customer, facts=facts, allowed_steps=allowed_steps, rejection=rejection, previous=previous,
        ))
        if getattr(response, "stop_reason", "") in {"max_tokens", "refusal"}:
            raise RuntimeError(f"stop_{response.stop_reason}")
        text = "".join(getattr(b, "text", "") for b in getattr(response, "content", []) if getattr(b, "type", "") == "text")
        usage = getattr(response, "usage", None)
        usage = usage.model_dump() if hasattr(usage, "model_dump") else (usage or {})
        return Draft(text.strip(), usage_cost(self.model, usage))


def drafters_for() -> list:
    """Os degraus com rota no Admin, na ordem da escada. Sem rota, o degrau não existe."""
    from shopman.shop import ai

    out = []
    for purpose in LADDER_PURPOSES:
        try:
            out.append(ModelDrafter(purpose))
        except ai.AINotConfigured:
            continue
        except Exception:  # noqa: BLE001
            logger.warning("concierge.ladder.drafter_unavailable purpose=%s", purpose, exc_info=True)
    return out


def allowed_steps(conversation) -> tuple[str, ...]:
    """Os próximos passos que a casa CUMPRE no turno seguinte (nenhuma promessa sem dono)."""
    from .intents import _cart_authorized

    if conversation is not None and _cart_authorized(conversation):
        return (
            "perguntar quantas unidades o cliente quer, para a casa separar na sacola",
            "dizer que, quando terminar de escolher, é só escrever 'pode fechar'",
        )
    return ()


def _acceptable(text: str) -> bool:
    from . import house_rules

    if "—" in text:
        return False
    reviewed = house_rules.review([text], house_rules.ReplyContext(receipts=frozenset(), customer_text="",
                                                                    house_contacts=house_rules.house_contacts()))
    return not reviewed.held


def _safe_kind(attempts) -> str:
    """A alternativa segura que a casa mandaria (registro; valer é a #3040)."""
    first = attempts[0].conference
    only_useless = first is not None and all(reason.startswith("useful:") for reason in first.failed)
    return "house_literal" if only_useless else "verify"


def shadow_climb(*, conversation, message_pk: int, outcome, customer_text: str, house_text: str,
                 house_conference) -> dict | None:
    """Sobe a escada DEPOIS do envio (o cliente não espera) e grava ``envelope["ladder"]``. Nunca levanta."""
    from conversational_commerce.reply import climb

    from shopman.shop.models import ConversationMessage

    if house_conference is None or house_conference.decision == "send":
        return None
    try:
        drafters = drafters_for()
        acts = _acts(outcome)
        result = climb(
            customer=customer_text,
            house_text=house_text,
            house_conference=house_conference,
            drafters=drafters,
            judge=judge_for(),
            policy=ladder_policy(),
            allowed_steps=allowed_steps(conversation),
            safe=_safe_kind,
            has_next_step=has_next_step,
            acceptable=_acceptable,
            previous=previous_house_reply(conversation),
            next_step_needed=not (acts and acts <= CLOSING_ACTS),
            estimate_usd=lambda drafter: drafter.estimate_usd(),
        )
        record = result.as_record()
        message = ConversationMessage.objects.get(pk=message_pk)
        message.envelope = {**(message.envelope or {}), "ladder": record}
        message.save(update_fields=["envelope"])
        return record
    except Exception:  # noqa: BLE001
        logger.warning("concierge.ladder.failed conversation=%s", getattr(conversation, "pk", None), exc_info=True)
        return None
