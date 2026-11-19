"""O livro das exposições: o que de fato chegou ao cliente, separado da decisão e da execução (v2 8.5).

Atribuição ao tratamento (a decisão, com a seleção), exposição efetiva (este livro)
e execução (os recibos, F8) são três registros separados. O provedor aceitar a
mensagem não é o cliente tê-la recebido: só ``delivered`` e ``read`` são
exposição efetiva, e "lida" só existe quando o canal a observa (K18). Cada
atualização de estado é um registro novo; o anterior fica no histórico.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conversational_commerce.contracts import ExposureEvent

EFFECTIVE = frozenset({"delivered", "read"})


@dataclass
class ExposureLedger:
    history: list[ExposureEvent] = field(default_factory=list)

    def record(self, exposure: ExposureEvent) -> ExposureEvent:
        if any(existing.id == exposure.id for existing in self.history):
            return exposure  # o mesmo registro duas vezes não é exposição nova
        self.history.append(exposure)
        return exposure

    def latest(self, decision_id: str) -> ExposureEvent | None:
        found = [item for item in self.history if item.decision_id == decision_id]
        return found[-1] if found else None

    def exposed(self, decision_id: str) -> bool:
        """A decisão chegou ao cliente? Aceito pelo provedor não basta."""
        return any(item.decision_id == decision_id and item.state in EFFECTIVE for item in self.history)
