"""Os turnos de um dia da grade da casa: leitura pura de ``Shop.opening_hours``.

Um dia da grade é ``{"open", "close", "breaks": [{"start", "end"}, ...]}``. ``open`` e
``close`` são o dia inteiro; ``breaks`` são os intervalos que partem o dia em turnos
(domingo das 9h às 12h, das 13h às 16h e das 17h às 23h). Mora no lado de leitura
porque a loja (``storefront/presentation``) lê os turnos e não pode importar serviço;
o ``business_calendar`` usa as mesmas funções para o estado da loja e o iFood.
"""

from __future__ import annotations

import logging
from datetime import time

from shopman.utils.formatting import format_clock

logger = logging.getLogger(__name__)


def _time(value) -> time | None:
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def day_breaks(entry) -> list[tuple[time, time]]:
    """Os intervalos de um dia da grade (``{"open", "close", "breaks": [...]}``).

    Cada intervalo é ``{"start": "12:00", "end": "13:00"}``. Só vale intervalo
    inteiro DENTRO do expediente, sem sobrepor outro: o formulário do Admin recusa
    o resto (``clean_breaks``). Se um intervalo inválido chegar por outro caminho,
    ele é ignorado e o log grita, em vez de inventar um turno.
    """
    if not isinstance(entry, dict):
        return []
    try:
        opens_at = time.fromisoformat(str(entry["open"]))
        closes_at = time.fromisoformat(str(entry["close"]))
    except (KeyError, TypeError, ValueError):
        return []
    raw = entry.get("breaks") or []
    if not isinstance(raw, list):
        logger.error("business_calendar: breaks fora do formato (lista esperada): %r", raw)
        return []
    out: list[tuple[time, time]] = []
    for item in raw:
        start = _time((item or {}).get("start")) if isinstance(item, dict) else None
        end = _time((item or {}).get("end")) if isinstance(item, dict) else None
        if start is None or end is None or not (opens_at < start < end < closes_at):
            logger.error("business_calendar: intervalo inválido ignorado: %r", item)
            continue
        out.append((start, end))
    out.sort()
    clean: list[tuple[time, time]] = []
    for start, end in out:
        if clean and start < clean[-1][1]:
            logger.error("business_calendar: intervalo sobreposto ignorado: %s-%s", start, end)
            continue
        clean.append((start, end))
    return clean


def split_by_breaks(window: tuple[time, time], entry) -> list[tuple[time, time]]:
    """O expediente ``window`` partido pelos intervalos de ``entry``."""
    opens_at, closes_at = window
    shifts: list[tuple[time, time]] = []
    cursor = opens_at
    for start, end in day_breaks(entry):
        if start <= cursor or end >= closes_at:
            continue
        shifts.append((cursor, start))
        cursor = end
    shifts.append((cursor, closes_at))
    return shifts


def format_shifts(shifts: list[tuple[time, time]]) -> str:
    """``"9h às 12h, 13h às 16h e 17h às 23h"`` — a frase do horário de um dia."""
    parts = [f"{format_clock(start)} às {format_clock(end)}" for start, end in shifts]
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} e {parts[-1]}"


def entry_shifts(entry) -> list[tuple[time, time]]:
    """Os turnos de uma linha crua da grade (``{"open", "close", "breaks"}``)."""
    if not isinstance(entry, dict):
        return []
    opens_at = _time(entry.get("open"))
    closes_at = _time(entry.get("close"))
    if opens_at is None or closes_at is None or opens_at >= closes_at:
        return []
    return split_by_breaks((opens_at, closes_at), entry)


__all__ = ["day_breaks", "entry_shifts", "format_shifts", "split_by_breaks"]
