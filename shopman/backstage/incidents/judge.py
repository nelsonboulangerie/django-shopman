"""O classificador em cascata: a IA lê o que a regra não decide, e só escolhe dentro da lista.

Entra só quando o remédio diz ``judge`` (ex.: o emissor recusou a NFC-e, e a resposta
pode ser cadastro, que pede gente, ou a SEFAZ fora, que reprocessar resolve).

A pergunta é sempre a mesma e fechada: para ESTE remédio, ``act`` (acionar) ou
``people`` (fica com gente). O modelo nunca escreve comando nem escolhe outro
remédio: a lista é do código.

Os dois papéis NÃO são intercambiáveis (dono, 21/11/2026: "Jev e outros modelos LLM
NÃO SÃO DIRETAMENTE INTERCAMBIÁVEIS"). Cada um tem o seu propósito e a sua conexão,
configurável em Admin → Loja → rotas de IA:

- **decisão** (``incident``): o Jev, motor de decisão tipada. Devolve probabilidade e
  confiança num ``choice``. Só aceita conexão Jev (~US$ 0,00003 por leitura).
- **leitura** (``incident_review``): um LLM (deepseek-flash, por exemplo, no formato
  Anthropic). Só aceita conexão desse formato, e só é chamado quando estritamente
  necessário: a decisão do Jev ficou abaixo de ``ACCEPT_AT``, o Jev falhou, ou não há
  Jev configurado.

Arranjos válidos: Jev + LLM (o LLM só na dúvida) ou só LLM. Abaixo de ``ACCEPT_AT`` no
fim, ou sem modelo, o caso fica com gente, com a leitura registrada.

Cada degrau passa pelo freio de gasto (``ai_governor``, teto por propósito) e vira
``AiInvocation``. O custo da decisão vai para o placar.

O que sai para o provedor: o tipo do alerta e a evidência com números longos e
e-mails mascarados. Nunca a mensagem do alerta.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from django.utils import timezone

from shopman.backstage.incidents.remedies import Verdict

logger = logging.getLogger(__name__)

TIERS = ("incident", "incident_review")
#: Confiança mínima para o modelo decidir sozinho.
ACCEPT_AT = 0.8
QUESTION = "remedio"
TIMEOUT_SECONDS = 15

_LONG_NUMBER = re.compile(r"\d[\d.\-/ ]{6,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def mask(text: str) -> str:
    """Tira da evidência o que poderia identificar alguém: números longos e e-mails."""

    return _EMAIL.sub("[e-mail]", _LONG_NUMBER.sub("[número]", str(text or "")))[:600]


@dataclass(frozen=True)
class Reading:
    choice: str
    confidence: float
    #: Custo da leitura em micro-dólares (inteiro, como o ``AiInvocation``).
    cost_usd_micros: int
    label: str


def judge(alert, remedy, verdict: Verdict):
    """``(Verdict, decided_by, confidence, cost)`` para ``act.step``."""

    from shopman.shop import ai

    evidence = mask(verdict.evidence)
    total = 0
    best: Reading | None = None
    for purpose in TIERS:
        try:
            resolved = ai.resolve(purpose)
        except ai.AINotConfigured as reason:
            logger.info("incident.judge_skipped purpose=%s reason=%s", purpose, reason)
            continue
        try:
            reading = ask(resolved, purpose=purpose, alert_type=alert.type, remedy=remedy, evidence=evidence)
        except Exception as exc:  # noqa: BLE001 - modelo fora não decide nada; o caso fica com gente
            logger.warning("incident.judge_failed purpose=%s error=%s", purpose, type(exc).__name__)
            continue
        total += reading.cost_usd_micros
        best = reading
        if reading.confidence >= ACCEPT_AT:
            if reading.choice == "act":
                return Verdict("act", f"{remedy.judge_act_reason} (leitura do modelo)"), reading.label, reading.confidence, total
            return Verdict("no", remedy.judge_people_reason), reading.label, reading.confidence, total
    if best is not None:
        reason = f"{verdict.reason}: o modelo não teve confiança ({best.confidence:.2f})"
        return Verdict("no", reason), best.label, best.confidence, total
    return verdict, "regra", None, total


def ask(resolved, *, purpose: str, alert_type: str, remedy, evidence: str) -> Reading:
    from shopman.shop.models import AIProtocol

    label = f"ia:{purpose}:{resolved.ref}/{resolved.model}"[:80]
    started = timezone.now()
    # O formato é do papel: ``incident`` só resolve para Jev, ``incident_review`` só para LLM.
    if resolved.protocol == AIProtocol.JEV:
        choice, confidence = _ask_jev(resolved, purpose=purpose, alert_type=alert_type, remedy=remedy, evidence=evidence)
    else:
        choice, confidence = _ask_messages(purpose, alert_type=alert_type, remedy=remedy, evidence=evidence)
    return Reading(choice=choice, confidence=confidence, cost_usd_micros=_cost_since(purpose, started), label=label)


def _instructions(remedy) -> str:
    return (
        f"Um alerta de produção de uma padaria pede o remédio '{remedy.label}'. Leia a evidência e "
        "diga se acionar esse remédio resolve (act) ou se o caso precisa de uma pessoa (people). "
        "Na dúvida, people."
    )


def _ask_jev(resolved, *, purpose, alert_type, remedy, evidence) -> tuple[str, float]:
    import requests

    from shopman.shop import ai, ai_governor

    body = {
        "model": resolved.model,
        "state": {"alerta": alert_type, "evidencia": evidence},
        "questions": {
            QUESTION: {"type": "choice", "instructions": _instructions(remedy), "criteria": remedy.judge_criteria}
        },
    }
    tokens_in = ai_governor.estimate_input_tokens({"messages": body})
    estimate = ai_governor.estimate_usd(resolved.model, tokens_in=tokens_in, tokens_out=0, protocol="jev")
    with ai_governor.metered(
        purpose, connection_ref=resolved.ref, model=resolved.model, estimate_usd_value=estimate, protocol="jev"
    ) as box:
        response = requests.post(
            resolved.base_url or ai.JEV_DEFAULT_URL,
            json=body,
            headers={"Authorization": f"Bearer {resolved.api_key}"},
            timeout=TIMEOUT_SECONDS,
        )
        box["usage"] = {"input_tokens": tokens_in}
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict) and usage.get("input_tokens") is not None:
            box["usage"] = {"input_tokens": usage["input_tokens"]}
    return parse_jev_choice(payload, options=remedy.judge_criteria)


def parse_jev_choice(payload: dict, *, options) -> tuple[str, float]:
    """``(escolha, probabilidade dela)``. Formato: docs.typesafe.ai, ``choice`` answer."""

    answer = (payload.get("answers") or {}).get(QUESTION) if isinstance(payload, dict) else None
    if not isinstance(answer, dict):
        raise ValueError("resposta do Jev sem a pergunta")
    choice = answer.get("choice")
    probabilities = answer.get("probabilities") or {}
    if choice not in options or not isinstance(probabilities.get(choice), (int, float)):
        raise ValueError("resposta do Jev fora das opções")
    confidence = float(probabilities[choice])
    stated = answer.get("confidence")
    if isinstance(stated, (int, float)) and not isinstance(stated, bool):
        confidence = min(confidence, float(stated))
    return choice, max(0.0, min(1.0, confidence))


SCHEMA = {
    "type": "object",
    "properties": {
        "choice": {"type": "string", "enum": ["act", "people"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["choice", "confidence"],
    "additionalProperties": False,
}


def _ask_messages(purpose, *, alert_type, remedy, evidence) -> tuple[str, float]:
    from shopman.shop import ai

    client, model = ai.anthropic_client(purpose, timeout=TIMEOUT_SECONDS, max_retries=1)
    criteria = "\n".join(f"- {key}: {text}" for key, text in remedy.judge_criteria.items())
    response = client.messages.create(
        model=model,
        max_tokens=200,
        system=(
            _instructions(remedy)
            + "\nOpções:\n"
            + criteria
            + '\nResponda só JSON: {"choice": "act" ou "people", "confidence": 0 a 1}.'
        ),
        messages=[{"role": "user", "content": f"Alerta: {alert_type}\nEvidência: {evidence}"}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = "".join(getattr(block, "text", "") for block in getattr(response, "content", []) or [])
    return parse_json_choice(text)


def parse_json_choice(text: str) -> tuple[str, float]:
    found = re.search(r"\{.*\}", text or "", re.S)
    if not found:
        raise ValueError("resposta sem JSON")
    data = json.loads(found.group(0))
    choice, confidence = data.get("choice"), data.get("confidence")
    if choice not in {"act", "people"} or not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("resposta fora do formato")
    return choice, max(0.0, min(1.0, float(confidence)))


def _cost_since(purpose: str, started) -> int:
    """Os micro-dólares que o freio gravou para este propósito desde o início da leitura."""

    from django.db.models import Sum

    from shopman.shop.models import AiInvocation

    return int(
        AiInvocation.objects.filter(purpose=purpose, created_at__gte=started)
        .aggregate(total=Sum("cost_usd_micros"))
        .get("total")
        or 0
    )
