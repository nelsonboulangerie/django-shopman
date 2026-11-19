"""``@conformance``: o teste declara que K prova, que invariantes e em que escopo.

    @conformance("K13", invariants=("N13",), scope="real_mechanism")
    def test_two_workers_same_version(...): ...

O decorador não depende de pytest: só anexa ``__conformance__`` à função e
confere os argumentos na importação. A matriz (``matrix.py``) lê os
decoradores pelo AST, sem importar os testes, e por isso os argumentos são
sempre literais.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from .catalog import INVARIANTS, K_BY_ID, SCOPES

F = TypeVar("F", bound=Callable[..., object])


@dataclass(frozen=True, slots=True)
class ConformanceMark:
    test_id: str
    invariants: tuple[str, ...]
    scope: str


def conformance(test_id: str, *, scope: str, invariants: tuple[str, ...] = ()) -> Callable[[F], F]:
    if test_id not in K_BY_ID:
        raise ValueError(f"teste de conformidade desconhecido: {test_id!r}")
    if scope not in SCOPES:
        raise ValueError(f"escopo {scope!r} fora de {SCOPES}")
    unknown = [inv for inv in invariants if inv not in INVARIANTS]
    if unknown:
        raise ValueError(f"invariante desconhecido: {unknown}")
    mark = ConformanceMark(test_id, tuple(invariants), scope)

    def apply(function: F) -> F:
        marks = (*getattr(function, "__conformance__", ()), mark)
        function.__conformance__ = marks  # type: ignore[attr-defined]
        return function

    return apply
