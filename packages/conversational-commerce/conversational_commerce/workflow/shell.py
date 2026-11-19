"""A casca durável: receber uma vez e avançar o episódio com comparar e gravar.

Passo 1 do turno (plano 3.4): a entrada é gravada uma vez e deduplicada ANTES
de qualquer trabalho. Duplicata não chama trabalho nenhum, logo não cria
comando (K01); texto igual com identidade diferente são duas entradas (K02).

Avançar o episódio: carrega, aplica a transição, confirma com a versão que viu.
Se outro trabalhador venceu (``revision_conflict``), recarrega e tenta de novo
sobre o estado NOVO. Como a máquina só aceita o evento a partir de certos
estados, o perdedor que encontra o evento já consumido não o repete: devolve
``superseded``, sem decisão nem efeito novos (K13, simulado; a prova de
concorrência de verdade é do adaptador, no mecanismo dele).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from conversational_commerce.contracts import Episode, InteractionEvent, Record
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import (
    ChannelPort,
    ClockPort,
    PortError,
    StorePort,
    Transition,
    TrustedContext,
    WorkItem,
)

from .errors import InvalidTransition
from .machine import EpisodeEvent, transition


@dataclass(frozen=True, slots=True)
class Received:
    event: InteractionEvent
    created: bool


def receive(ctx: TrustedContext, raw: Mapping[str, Any], *, channel: ChannelPort, store: StorePort,
            clock: ClockPort) -> Received:
    """Normaliza e grava a entrada uma vez. ``created`` falso é duplicata: nada mais acontece."""
    event = channel.normalize(ctx, raw, clock.now())
    stored, created = store.record_event_once(ctx, event)
    return Received(stored, created)


def handle_inbound[T](ctx: TrustedContext, raw: Mapping[str, Any], work: Callable[[InteractionEvent], T], *,
                   channel: ChannelPort, store: StorePort, clock: ClockPort) -> tuple[Received, T | None]:
    """Recebe e só então trabalha. Duplicata não chega ao ``work``."""
    received = receive(ctx, raw, channel=channel, store=store, clock=clock)
    if not received.created:
        return received, None
    return received, work(received.event)


@dataclass(frozen=True, slots=True)
class Advance:
    outcome: Literal["applied", "superseded"]
    episode: Episode
    attempts: int
    reason: str = ""


# O que a transição produz além do episódio: registros e trabalho, gravados juntos.
Effects = Callable[[Episode], tuple[tuple[Record, ...], tuple[WorkItem, ...]]]


def advance(ctx: TrustedContext, episode_id: str, event: EpisodeEvent, *, store: StorePort, clock: ClockPort,
            effects: Effects | None = None, loaded: Episode | None = None, max_attempts: int = 2) -> Advance:
    """Aplica ``event`` ao episódio e confirma; num conflito, recarrega e não repete o já feito.

    ``loaded``: o episódio como este trabalhador o viu (para simular dois
    trabalhadores na mesma versão); sem ele, carrega da porta.
    """
    episode = loaded if loaded is not None else store.load_episode(ctx, episode_id)
    if episode is None:
        raise PortError(ErrorCode.INVALID_CONTENT, f"episódio inexistente: {episode_id}")
    for attempt in range(1, max_attempts + 1):
        try:
            new = transition(episode, event, expected_version=episode.version, record_id=clock.new_id("eprec"))
        except InvalidTransition as invalid:
            if attempt == 1:
                raise
            return Advance("superseded", episode, attempt, invalid.reason)
        records, outbox = effects(new) if effects is not None else ((), ())
        try:
            committed = store.commit_transition(ctx, Transition(episode=new, expected_version=episode.version),
                                                (new, *records), outbox)
        except PortError as conflict:
            if conflict.code != ErrorCode.REVISION_CONFLICT:
                raise
            reloaded = store.load_episode(ctx, episode_id)
            if reloaded is None:
                raise
            episode = reloaded
            continue
        return Advance("applied", committed, attempt)
    return Advance("superseded", episode, max_attempts, "conflito de versão persistente")
