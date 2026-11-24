"""Leitor roteirizado e o executor das jornadas."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from conversational_commerce.contracts import Producer, Understanding
from conversational_commerce.ports import Adjudication, Capabilities, Consumption, PortError, TrustedContext
from conversational_commerce.ports.model import OPERATIONS

READER = Producer(name="scripted-reader", version="1")
UNAVAILABLE = {"status": "unavailable", "reason": "scripted"}


class ScriptedModel:
    """Porta de modelo que devolve o entendimento escrito na jornada para cada conteúdo.

    ``script``: ``content_ref`` → ``{"acts": [{"act", "fields"}], "alternatives": [[{"act", "fields"}]]}``.
    Conteúdo fora do roteiro é ``provider_unavailable``: o turno cai para a regra local.
    """

    PORT = "model"

    def __init__(self, clock, script: Mapping[str, Mapping[str, Any]]) -> None:
        self.clock = clock
        self.script = script
        self.requests: list[Any] = []
        self.adjudications: list[Any] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(port="model", operations=OPERATIONS, guarantees={"priced": False})

    def interpret(self, ctx: TrustedContext, request):
        self.requests.append(request)
        entry = self.script.get(request.content_ref)
        if entry is None:
            raise PortError("provider_unavailable", "fora do roteiro")

        def acts(items):
            return [{"act": item["act"], "fields": item.get("fields", {}), "confidence": UNAVAILABLE}
                    for item in items]

        understanding = Understanding(
            id=self.clock.new_id("und"), tenant=ctx.tenant, environment=ctx.environment,
            trace_id=self.clock.new_id("trace"), occurred_at=self.clock.now(), producer=READER,
            event_id=request.event_id, acts=acts(entry["acts"]),
            alternatives=[{"acts": acts(alternative), "confidence": UNAVAILABLE}
                          for alternative in entry.get("alternatives", ())],
            signals={"friction": "low", "risk": "none"}, reader=READER)
        return understanding, Consumption(model=READER, calls=1, cost={"status": "unavailable",
                                                                        "reason": "no_price"})

    def draft(self, ctx, request, plan):
        raise PortError("capability_missing", "o leitor roteirizado não redige")

    def score(self, ctx, request):
        raise PortError("capability_missing", "o leitor roteirizado não pontua")

    def adjudicate(self, ctx: TrustedContext, request):
        """O verificador do roteiro: ``"adjudication"`` na entrada da fala (o índice da candidata); sem ela,
        dúvida. Guarda o pedido, para o teste ver o que o verificador recebeu."""
        self.adjudications.append(request)
        choice = (self.script.get(request.content_ref) or {}).get("adjudication")
        return Adjudication(choice=choice, consumption=Consumption(model=READER, calls=1, cost={
            "status": "unavailable", "reason": "no_price"}))


@dataclass(frozen=True, slots=True)
class JourneyStep:
    message: Mapping[str, Any] | None
    expect_moves: tuple[str, ...]
    expect_text: tuple[str, ...] = ()
    expect_state: str | None = None
    understanding: Mapping[str, Any] | None = None
    # O relógio anda antes do passo (a confirmação é POSTERIOR aos termos, J4).
    advance_seconds: int = 0
    # Passo que não é mensagem do cliente (a equipe responde, J3): ``act(engine, ctx)`` devolve o resultado.
    act: Callable[[Any, TrustedContext], Any] | None = None


@dataclass(frozen=True, slots=True)
class StepResult:
    step: JourneyStep
    result: Any
    problems: tuple[str, ...] = field(default_factory=tuple)


def run_journey(engine, ctx: TrustedContext, steps: Sequence[JourneyStep]) -> list[StepResult]:
    """Roda os passos e devolve, por passo, o que divergiu do esperado (vazio é verde)."""
    out = []
    for step in steps:
        if step.advance_seconds:
            engine.ports.clock.advance(step.advance_seconds)
        result = step.act(engine, ctx) if step.act is not None else engine.turn(ctx, step.message)
        problems = []
        if tuple(result.chosen_moves) != step.expect_moves:
            problems.append(f"movimentos {result.chosen_moves}, esperado {list(step.expect_moves)}")
        for fragment in step.expect_text:
            if not result.text or fragment not in result.text:
                problems.append(f"texto sem {fragment!r}: {result.text!r}")
        if step.expect_state and result.episode is not None and result.episode.state != step.expect_state:
            problems.append(f"estado {result.episode.state}, esperado {step.expect_state}")
        out.append(StepResult(step, result, tuple(problems)))
    return out


def script_of(steps: Sequence[JourneyStep]) -> dict[str, Mapping[str, Any]]:
    return {step.message["content_ref"]: step.understanding for step in steps
            if step.understanding is not None and step.message is not None}
