"""Correlação: a que episódio uma entrada se liga (v2 5.7).

Uma entrada se liga ao episódio aberto do mesmo cliente verificado ou, sem
identidade, do mesmo vínculo de canal; continua o episódio enquanto houver
necessidade, espera ou compromisso aberto; abre outro quando chega depois de
tudo resolvido, ou vencida a janela de inatividade do perfil. **Nunca** se unem
pessoas por semelhança de texto: esta função não recebe texto.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from conversational_commerce.contracts import Episode

FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def subject_key(*, verified_subject: str | None, channel: str, conversation_ref: str) -> str:
    """A chave do sujeito do episódio: o cliente verificado ou, sem identidade, o vínculo de canal."""
    if verified_subject:
        return f"subject:{verified_subject}"
    return f"binding:{channel}:{conversation_ref}"


@dataclass(frozen=True, slots=True)
class Correlation:
    action: Literal["continue", "open_new"]
    episode_id: str | None
    reason: str


def _seconds_between(earlier: str, later: str) -> float:
    start = datetime.strptime(earlier, FORMAT).replace(tzinfo=UTC)
    end = datetime.strptime(later, FORMAT).replace(tzinfo=UTC)
    return (end - start) / timedelta(seconds=1)


def correlate(*, subject: str, now: str, episodes: Iterable[Episode], inactivity_seconds: int,
              open_commitments: Iterable[str] = ()) -> Correlation:
    """Decide continuar um episódio do mesmo sujeito ou abrir outro.

    ``episodes``: os registros mais recentes de cada episódio do inquilino.
    ``open_commitments``: episódios com compromisso aberto (vindo do F9).
    """
    mine = sorted((e for e in episodes if e.subject == subject), key=lambda e: e.occurred_at, reverse=True)
    with_commitment = set(open_commitments)
    for episode in mine:
        if episode.state == "resolved":
            continue
        if episode.waits or episode.needs or episode.episode_id in with_commitment:
            return Correlation("continue", episode.episode_id, "necessidade, espera ou compromisso aberto")
        if _seconds_between(episode.occurred_at, now) <= inactivity_seconds:
            return Correlation("continue", episode.episode_id, "dentro da janela de inatividade")
        return Correlation("open_new", None, "janela de inatividade vencida")
    return Correlation("open_new", None, "nenhum episódio aberto do sujeito")
