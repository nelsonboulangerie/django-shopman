"""Placar de conversa: o cliente foi atendido, turno a turno, e o que a alternativa faria.

A régua de mensagem (o destino certo, a intenção certa) mede se a casa entendeu. Não mede se o
cliente saiu atendido: "Croissant: Indisponível." acerta o destino e a intenção e deixa o
cliente sem caminho. Este placar mede o que o cliente vive, com quatro desfechos por turno,
nesta ordem de gravidade:

- ``silent``: o cliente falou e a casa não respondeu, sem que alguém tenha assumido a conversa;
- ``unbacked``: a resposta afirmou algo sem lastro (um fato fora do sistema de registro);
- ``dead_end``: respondeu, com lastro, mas o cliente ficou sem próximo passo;
- ``useful``: respondeu, com lastro, e deixou o próximo passo (o que tem, quando tem, a pergunta
  que falta, o "vou verificar" com dono, a ação feita).

``repeated`` (a mesma frase duas vezes na resposta) é marca à parte: estraga a resposta sem
mudar o desfecho.

O lastro pode ser **desconhecido** (texto redigido por modelo, sem conferência): conta à
parte, nunca como "com lastro" (v2 4.6). Desconhecido não é zero, e não é sim.

**A alternativa de mercado** entra como um perfil declarado de capacidades
(``IncumbentProfile``): lê dado vivo?, age no comércio?, responde texto livre neste canal? Para
cada turno o placar diz se ela **alcançaria** um atendimento útil ou por que não. É uma
comparação por capacidade declarada, não por execução: prova onde a alternativa nem chega,
nunca que ela erraria onde chega.

Nada aqui conhece língua, canal, loja ou modelo: o adaptador traduz a sua conversa em
``TurnEvidence`` (o leitor de cada língua mora lá) e este módulo só conta.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

Outcome = Literal["silent", "unbacked", "dead_end", "useful"]
OUTCOMES: tuple[Outcome, ...] = ("silent", "unbacked", "dead_end", "useful")
Reach = Literal["reaches", "no_free_text", "no_live_data", "cannot_act"]


@dataclass(frozen=True, slots=True)
class TurnEvidence:
    """Um turno do cliente e o que a casa fez com ele, já lido pelo adaptador."""

    turn_id: str
    #: A casa respondeu este turno.
    replied: bool
    #: Silêncio legítimo: uma pessoa da equipe assumiu a conversa, ou o cliente pediu silêncio.
    silence_expected: bool = False
    #: Toda afirmação da resposta tem lastro. ``None``: desconhecido (texto de modelo sem conferência).
    backed: bool | None = True
    #: A resposta deixa o cliente com um próximo passo.
    next_step: bool = False
    #: A mesma frase saiu duas vezes na resposta.
    repeated: bool = False
    #: Atender bem exigia dado vivo (estoque, preço do dia, sacola, pedido).
    needs_live_data: bool = False
    #: Atender bem exigia agir no comércio (sacola, pedido, cancelamento, desconto).
    needs_action: bool = False
    latency_ms: int | None = None
    #: Rótulo livre do adaptador (o assunto do turno), só para leitura humana.
    topic: str = ""


@dataclass(frozen=True, slots=True)
class IncumbentProfile:
    """O que uma alternativa de mercado declara saber fazer, num canal."""

    name: str
    reads_live_data: bool
    acts_on_commerce: bool
    free_text_in_channel: bool


def outcome_of(turn: TurnEvidence) -> Outcome | None:
    """O desfecho do turno. ``None``: silêncio legítimo, fora do placar."""
    if not turn.replied:
        return None if turn.silence_expected else "silent"
    if turn.backed is False:
        return "unbacked"
    if not turn.next_step:
        return "dead_end"
    return "useful"


def incumbent_reach(turn: TurnEvidence, incumbent: IncumbentProfile) -> Reach:
    """Se a alternativa alcançaria um atendimento útil neste turno, ou o primeiro motivo por que não."""
    if not incumbent.free_text_in_channel:
        return "no_free_text"
    if turn.needs_live_data and not incumbent.reads_live_data:
        return "no_live_data"
    if turn.needs_action and not incumbent.acts_on_commerce:
        return "cannot_act"
    return "reaches"


@dataclass(frozen=True, slots=True)
class Scorecard:
    turns: int
    #: Desfecho → turnos (silêncio legítimo fora).
    outcomes: Mapping[str, int]
    excused_silence: int
    unknown_backing: int
    repeated: int
    #: Alternativa → (alcance → turnos), sobre os turnos que contam.
    incumbents: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    latencies_ms: tuple[int, ...] = ()

    @property
    def scored(self) -> int:
        return sum(self.outcomes.values())

    def rate(self, outcome: str) -> float | None:
        """Fração dos turnos que contam. ``None`` sem turno: desconhecido, não zero."""
        return None if not self.scored else self.outcomes.get(outcome, 0) / self.scored

    def meets(self, *, useful_at_least: float = 0.9) -> bool:
        """O alvo de "pronto": nenhum sem lastro, nenhum silêncio, e útil na fração pedida."""
        useful = self.rate("useful")
        return (
            useful is not None
            and self.outcomes.get("unbacked", 0) == 0
            and self.outcomes.get("silent", 0) == 0
            and self.unknown_backing == 0
            and useful >= useful_at_least
        )


def score(turns: Iterable[TurnEvidence], incumbents: Iterable[IncumbentProfile] = ()) -> Scorecard:
    turns = list(turns)
    incumbents = list(incumbents)
    outcomes: Counter = Counter(dict.fromkeys(OUTCOMES, 0))
    reach: dict[str, Counter] = {inc.name: Counter() for inc in incumbents}
    excused = unknown = repeated = 0
    latencies = []
    for turn in turns:
        outcome = outcome_of(turn)
        if outcome is None:
            excused += 1
            continue
        outcomes[outcome] += 1
        if turn.replied and turn.backed is None:
            unknown += 1
        if turn.repeated:
            repeated += 1
        if turn.latency_ms is not None:
            latencies.append(turn.latency_ms)
        for inc in incumbents:
            reach[inc.name][incumbent_reach(turn, inc)] += 1
    return Scorecard(
        turns=len(turns),
        outcomes=dict(outcomes),
        excused_silence=excused,
        unknown_backing=unknown,
        repeated=repeated,
        incumbents={name: dict(counts) for name, counts in reach.items()},
        latencies_ms=tuple(sorted(latencies)),
    )


__all__ = [
    "OUTCOMES",
    "IncumbentProfile",
    "Scorecard",
    "TurnEvidence",
    "incumbent_reach",
    "outcome_of",
    "score",
]
