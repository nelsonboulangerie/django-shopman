"""A régua da Concierge: quanto custou e quanto demorou cada resposta.

Fatia 1 do estudo ``docs/plans/CONCIERGE-ARQUITETURA-ALVO.md`` (OBS0310-K). O
cliente não vê nada mudar: o turno roda igual, e o que ele gastou fica gravado
em ``ConversationMessage.usage`` do primeiro bloco da resposta (formato em
``docs/reference/data-schemas.md``, "Régua da Concierge").

Um ``TurnMeter`` acompanha um turno:

- ``stage(nome)`` cronometra uma etapa (``triage``, ``agent``, ``tools``);
- ``wrap(cliente, etapa)`` devolve o cliente do modelo medido: cada
  ``messages.create`` soma tempo na etapa e tokens por (etapa, modelo),
  inclusive a ESCRITA de cache, que a conversa nunca gravou;
- ``wrap_jev(concorrente)`` faz o mesmo com o Jev (``scores``).

O medidor nunca derruba o turno: medir é efeito colateral, e qualquer coisa
estranha no ``usage`` vira zero.
"""

from __future__ import annotations

import time
from contextlib import contextmanager, nullcontext
from datetime import datetime

from django.utils import timezone

from shopman.shop.services.ai_pricing import usage_cost

USAGE_VERSION = 1
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
#: US$ por milhão de tokens de entrada do Jev (preço anunciado; saída grátis).
JEV_PRICE_IN_PER_M = 0.042

#: Quem respondeu o turno, no vocabulário das camadas do estudo (seção 6).
LAYER_COURTESY = "courtesy"  # C1: cortesia, frase da casa, sem modelo
LAYER_CONTEXT = "context"  # memória: a casa resolveu ou perguntou pela conversa, sem modelo
LAYER_MEDIA = "media"  # C1: mídia sem texto, mensagem fixa
LAYER_TURN_LIMIT = "turn_limit"  # teto diário de turnos
LAYER_AGENT = "agent"  # C6: o laço com o modelo e as ferramentas (o de hoje)
LAYER_ERROR = "error"  # o agente falhou; mensagem de indisponível
LAYER_TEAM = "team"  # C7: a triagem mandou para a equipe ou outra mesa
LAYER_AGENT_HANDOFF = "agent_handoff"  # o agente chamou a equipe
LAYER_HOUSE_RULE = "house_rule"  # regra da casa: frase fixa (R7, R8) ou resposta segurada (equipe)
LAYER_INTENTS = "intents"  # intenções no plural: cada parte pelo executor da casa, uma resposta


def _int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class TurnMeter:
    """Tempo por etapa e tokens por (etapa, modelo) de um turno."""

    def __init__(self):
        self._started = time.perf_counter()
        self.stages_ms: dict[str, float] = {}
        self.calls: dict[tuple[str, str], dict] = {}
        self.layer = ""
        self.received_at: datetime | None = None
        self.triage_source = ""
        self.triage_classifier = ""
        #: Intenções no plural: as partes do turno e quem as leu (``intents.Plan.as_dict``).
        self.intents: dict = {}

    # ── Etapas ───────────────────────────────────────────────────────

    @contextmanager
    def stage(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.add_time(name, (time.perf_counter() - started) * 1000)

    def add_time(self, name: str, ms: float) -> None:
        self.stages_ms[name] = self.stages_ms.get(name, 0.0) + ms

    # ── Tokens ───────────────────────────────────────────────────────

    def add_call(self, stage: str, model: str, usage=None, *, provider: str = "anthropic") -> None:
        row = self.calls.setdefault(
            (stage, model or "?"),
            {"stage": stage, "model": model or "?", "provider": provider, "calls": 0, **dict.fromkeys(TOKEN_KEYS, 0)},
        )
        row["calls"] += 1
        for key in TOKEN_KEYS:
            value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, 0)
            row[key] += _int(value)

    def wrap(self, client, stage: str, *, factory=None):
        """O cliente do modelo, medido. ``factory`` cria o cliente só se for usado."""
        if client is None and factory is None:
            return None
        return _MeteredClient(self, stage, client, factory)

    def wrap_jev(self, contender):
        return None if contender is None else _MeteredJev(self, contender)

    # ── Registro ─────────────────────────────────────────────────────

    def as_usage(self, *, received_at: datetime | None = None, now: datetime | None = None) -> dict:
        """O que vai para ``ConversationMessage.usage`` (data-schemas, "Régua da Concierge")."""
        totals = dict.fromkeys(TOKEN_KEYS, 0)
        cost, unpriced, calls = 0.0, [], []
        for row in self.calls.values():
            row = dict(row)
            for key in TOKEN_KEYS:
                totals[key] += row[key]
            if row["provider"] == "typesafe":
                row_cost = row["input_tokens"] * JEV_PRICE_IN_PER_M / 1_000_000
            else:
                row_cost = usage_cost(row["model"], row)
            if row_cost is None:
                unpriced.append(row["model"])
                row["cost_usd"] = None
            else:
                row["cost_usd"] = round(row_cost, 6)
                cost += row_cost
            calls.append(row)
        turn_ms = (time.perf_counter() - self._started) * 1000
        latency = {"turn": round(turn_ms)}
        if received_at is not None:
            now = now or timezone.now()
            latency["total"] = max(0, round((now - received_at).total_seconds() * 1000))
        for name, ms in sorted(self.stages_ms.items()):
            latency[name] = round(ms)
        payload = {
            "version": USAGE_VERSION,
            "layer": self.layer,
            "triage": {"classifier": self.triage_classifier, "source": self.triage_source},
            "calls": calls,
            **totals,
            "cost_usd": None if unpriced else round(cost, 6),
            "latency_ms": latency,
        }
        if unpriced:
            payload["unpriced_models"] = sorted(set(unpriced))
        if self.intents:
            payload["intents"] = self.intents
        return payload


class _Messages:
    def __init__(self, metered):
        self._metered = metered

    def create(self, **kwargs):
        metered = self._metered
        started = time.perf_counter()
        try:
            response = metered.target.messages.create(**kwargs)
        finally:
            metered.meter.add_time(metered.stage, (time.perf_counter() - started) * 1000)
        model = str(kwargs.get("model") or getattr(response, "model", "") or "")
        metered.meter.add_call(metered.stage, model, getattr(response, "usage", None))
        return response


class _MeteredClient:
    """Repassa tudo ao cliente real; só ``messages.create`` é medido."""

    def __init__(self, meter: TurnMeter, stage: str, client, factory):
        self.meter, self.stage = meter, stage
        self._client, self._factory = client, factory
        self.messages = _Messages(self)

    @property
    def target(self):
        if self._client is None:
            self._client = self._factory()
        return self._client

    def __getattr__(self, name):
        return getattr(self.target, name)


class _MeteredJev:
    """O concorrente Jev medido: tempo da chamada e tokens de entrada."""

    def __init__(self, meter: TurnMeter, contender):
        self.meter, self.contender = meter, contender

    def scores(self, sample, categories):
        started = time.perf_counter()
        try:
            prediction = self.contender.scores(sample, categories)
        finally:
            # Parte da etapa de triagem (cronometrada inteira por quem chama).
            self.meter.add_time("jev", (time.perf_counter() - started) * 1000)
        self.meter.add_call(
            "jev",
            str(getattr(self.contender, "model", "") or "jev"),
            {"input_tokens": getattr(prediction, "input_tokens", 0), "output_tokens": getattr(prediction, "output_tokens", 0)},
            provider="typesafe",
        )
        return prediction

    def __getattr__(self, name):
        return getattr(self.contender, name)


def stage_of(conversation, name: str):
    """A etapa ``name`` do medidor do turno, ou nada quando o turno não é medido."""
    meter = getattr(conversation, "_meter", None)
    return meter.stage(name) if meter is not None else nullcontext()


def triage_client_for(meter: TurnMeter, triage_client=None):
    """O cliente da triagem, medido, com a MESMA regra de quando há modelo.

    ``triage.decide`` cria o próprio cliente quando recebe ``None`` (e só se o
    modelo estiver ligado). Aqui ele é criado do mesmo jeito para poder ser
    medido; cliente injetado (teste, comando) é só embrulhado. Desligado, segue
    ``None``: a regra local responde sem rede.
    """
    from django.conf import settings

    from . import triage

    if triage.classifier() == "jev":
        meter.triage_classifier = "jev"
        if triage_client is None and triage._model_toggle():
            from .intent_benchmark import ContenderNotConfigured, JevContender

            try:
                triage_client = JevContender(timeout=10.0)
            except ContenderNotConfigured:
                return None
        return meter.wrap_jev(triage_client)
    meter.triage_classifier = "anthropic"
    if triage_client is None:
        if not triage._model_enabled():
            return None
        import anthropic

        triage_client = anthropic.Anthropic(api_key=settings.AI_ASSIST_API_KEY, timeout=15.0, max_retries=1)
    return meter.wrap(triage_client, "triage")
