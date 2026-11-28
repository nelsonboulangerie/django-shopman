"""Modelo falso: leitor por regra, saída fora do esquema, ato fora da lista, orçamento, provedor fora."""

from __future__ import annotations

from conversational_commerce.contracts import Producer, ReplyPlan, Unavailable, Understanding
from conversational_commerce.ports import (
    AdjudicateRequest,
    Adjudication,
    Capabilities,
    Consumption,
    Draft,
    InterpretRequest,
    ModelRequest,
    PortError,
    ScoreRequest,
    Scores,
    TrustedContext,
)
from conversational_commerce.ports.model import OPERATIONS

from .base import FakeBase
from .faults import Fault

MODEL = Producer(name="fake-rule-reader", version="1")


class FakeModel(FakeBase):
    """Lê ``content_ref`` como ``texto:...`` e aplica regras de palavra-chave. Nunca tem preço."""

    PORT = "model"

    RULES: tuple[tuple[str, str], ...] = (
        ("hours", "ask_hours"),
        ("price", "ask_price"),
        ("cancel", "cancel_order"),
        ("complaint", "complain"),
        ("thanks", "thank"),
    )

    def __init__(self, clock, faults=None) -> None:
        super().__init__(clock, faults)
        self.calls_made = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(port="model", operations=OPERATIONS,
                            guarantees={"schema_validated_output": True, "priced": False, "data_classes": ["public",
                                                                                                          "redacted"]})

    def _consume(self, request: ModelRequest) -> Consumption:
        if self.calls_made >= request.budget.max_calls:
            raise PortError("budget_exhausted", "teto de chamadas do turno")
        self.calls_made += 1
        # Sem preço cadastrado: custo desconhecido, nunca zero (N21, K34).
        return Consumption(model=MODEL, calls=1, cost=Unavailable(reason="no_price"))

    def _common_faults(self, operation: str, request: ModelRequest) -> Fault | None:
        fault = self._fault(operation)
        if fault is Fault.PROVIDER_DOWN:
            raise PortError("provider_unavailable", "provedor do modelo fora")
        if fault is Fault.BUDGET_EXHAUSTED:
            raise PortError("budget_exhausted", "orçamento esgotado")
        if fault is Fault.OUT_OF_SCHEMA:
            raise PortError("invalid_content", "saída do modelo fora do esquema")
        if request.data_class == "personal":
            raise PortError("object_forbidden", "dado pessoal não vai a este modelo")
        return fault

    def interpret(self, ctx: TrustedContext, request: InterpretRequest) -> tuple[Understanding, Consumption]:
        fault = self._common_faults("interpret", request.request)
        consumption = self._consume(request.request)
        text = request.content_ref.split(":", 1)[-1].lower()
        acts = [act for keyword, act in self.RULES if keyword in text]
        if fault is Fault.ACT_OUTSIDE_LIST:
            acts.append("transfer_all_funds")
        if not acts:
            acts = ["unknown"]
        understanding = Understanding(
            **self.envelope(ctx, "und"),
            event_id=request.event_id,
            acts=[{"act": act, "fields": {}, "confidence": {"status": "unavailable", "reason": "rule_reader"}}
                  for act in acts],
            signals={"friction": "high" if "complain" in acts else "low", "risk": "unknown"},
            reader=MODEL,
        )
        return understanding, consumption

    def draft(self, ctx: TrustedContext, request: ModelRequest, plan: ReplyPlan) -> Draft:
        self._common_faults("draft", request)
        consumption = self._consume(request)
        moves = ", ".join(part.move for part in plan.parts)
        return Draft(text=f"[draft: {moves}]", consumption=consumption)

    def adjudicate(self, ctx: TrustedContext, request: AdjudicateRequest) -> Adjudication:
        """O verificador sintético: a primeira candidata com um ato que responde à pergunta no ar; sem ela,
        dúvida."""
        self._common_faults("adjudicate", request.request)
        consumption = self._consume(request.request)
        expected = set(request.context.expected_acts)
        choice = next((index for index, candidate in enumerate(request.candidates)
                       if {act.act for act in candidate.acts} & expected), None)
        return Adjudication(choice=choice, consumption=consumption)

    def score(self, ctx: TrustedContext, request: ScoreRequest) -> Scores:
        self._common_faults("score", request.request)
        consumption = self._consume(request.request)
        count = len(request.options)
        # Distribuição uniforme, em decimal exato.
        from decimal import Decimal

        share = Decimal(1) / Decimal(count) if count else Decimal(0)
        values = tuple(format(share.quantize(Decimal("0.0001")).normalize(), "f") for _ in request.options)
        return Scores(values=values, consumption=consumption)
