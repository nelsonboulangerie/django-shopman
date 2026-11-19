"""Tetos do turno: passos, tempo, chamadas de modelo e gasto (v2 5.3; perfil ``limits``).

Estouro de teto nunca derruba o turno: o que pedia modelo cai para o caminho sem
modelo (regra local), o que pedia leitura vira fato desconhecido, e a queda fica
registrada. O sistema atende sem nenhum modelo, pior porém certo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conversational_commerce.contracts import DeploymentProfile


@dataclass
class TurnBudget:
    max_steps: int
    max_model_calls: int
    max_spend_minor: int
    steps: int = 0
    model_calls: int = 0
    spend_minor: int = 0
    events: list[str] = field(default_factory=list)

    @classmethod
    def from_profile(cls, profile: DeploymentProfile) -> TurnBudget:
        limits = profile.limits
        return cls(max_steps=limits.max_steps, max_model_calls=limits.max_model_calls,
                   max_spend_minor=limits.max_spend.amount_minor)

    def take_step(self, what: str) -> bool:
        """Um passo (leitura de porta ou chamada de modelo). Falso quando o teto acabou."""
        if self.steps >= self.max_steps:
            self.events.append(f"steps_exhausted:{what}")
            return False
        self.steps += 1
        return True

    def may_call_model(self) -> bool:
        if self.model_calls >= self.max_model_calls:
            self.events.append("model_calls_exhausted")
            return False
        if self.spend_minor > self.max_spend_minor:
            self.events.append("spend_exhausted")
            return False
        return self.take_step("model")

    def record_model_call(self, cost_minor: int | None) -> None:
        self.model_calls += 1
        if cost_minor is None:
            # Custo desconhecido não é zero (N21): fica registrado, e a comparação econômica é vetada.
            self.events.append("model_cost_unknown")
        else:
            self.spend_minor += cost_minor
            if self.spend_minor > self.max_spend_minor:
                self.events.append("spend_exceeded")
