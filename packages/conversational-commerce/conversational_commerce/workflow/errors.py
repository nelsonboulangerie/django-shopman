"""Erros do fluxo do episódio."""

from __future__ import annotations


class InvalidTransition(ValueError):
    """O evento não leva a lugar nenhum a partir do estado atual (ou falta o que ele exige)."""

    def __init__(self, state: str, event: str, reason: str):
        self.state = state
        self.event = event
        self.reason = reason
        super().__init__(f"{event} a partir de {state}: {reason}")


class StaleVersion(ValueError):
    """Quem decidiu viu uma versão do episódio que já não é a atual."""

    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"versão esperada {expected}, atual {current}")
