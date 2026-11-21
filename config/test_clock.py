"""Relógio de teste da pilha local (#2585).

A suíte de operador roda contra o Django de verdade, e "agora" é o que mais decide
nela: a hora em que a encomenda do dia vai para a Cozinha, a virada do dia, o prazo
de aceite. Sem relógio de teste, essas jornadas só passavam no horário real da casa,
ou não passavam.

Como funciona: o processo lê um ARQUIVO com um instante ISO 8601 com fuso
(``2026-11-23T15:50:00-03:00``). O relógio do processo passa a valer esse instante
no momento em que o arquivo foi gravado, e anda a partir dali no ritmo do relógio
real: duas gravações do arquivo são duas viagens no tempo, sem reiniciar nada.
Arquivo ausente ou vazio é a hora real. O runserver e o worker leem o mesmo
arquivo, e o navegador da suíte acerta o próprio relógio pelo Playwright.

O que muda: ``django.utils.timezone.now`` e tudo que passa por ele
(``localdate``, ``localtime``, ``auto_now``, ``default=timezone.now``). Por isso
a troca acontece no settings, antes de qualquer modelo ser importado. O que lê
``datetime.now()`` direto (Concierge, Watchman, prontidão de certificado) segue a
hora real.

Só existe na pilha de teste: o settings recusa subir com ele fora de DEBUG ou em
produção, e o check de portas de teste (``SHOPMAN_E027``) o lista como porta aberta.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.utils import timezone

_lock = threading.Lock()
_state: dict = {"path": None, "mtime_ns": None, "offset": timedelta(0)}
_real_now = timezone.now


class TestClockError(ValueError):
    """O arquivo do relógio existe e não diz um instante com fuso."""


def offset_for(path: Path) -> timedelta:
    """Quanto o relógio do processo está à frente (ou atrás) da hora real."""
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return timedelta(0)
    with _lock:
        if _state["mtime_ns"] == stat.st_mtime_ns:
            return _state["offset"]
        text = Path(path).read_text(encoding="utf-8").strip()
        if not text:
            offset = timedelta(0)
        else:
            try:
                target = datetime.fromisoformat(text)
            except ValueError as exc:
                raise TestClockError(f"Relógio de teste em {path}: '{text}' não é um instante ISO 8601.") from exc
            if target.tzinfo is None:
                raise TestClockError(f"Relógio de teste em {path}: '{text}' não diz o fuso (ex.: -03:00).")
            written = datetime.fromtimestamp(stat.st_mtime_ns / 1_000_000_000, UTC)
            offset = target - written
        _state["mtime_ns"] = stat.st_mtime_ns
        _state["offset"] = offset
        return offset


def clock_now() -> datetime:
    path = _state["path"]
    real = _real_now()
    if path is None:
        return real
    return real + offset_for(path)


def install(path: str | os.PathLike) -> None:
    """Troca ``timezone.now`` pelo relógio do arquivo. Chamado pelo settings."""
    _state["path"] = Path(path)
    _state["mtime_ns"] = None
    timezone.now = clock_now
