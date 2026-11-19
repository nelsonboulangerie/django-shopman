"""Relógio falso: tempo que só anda quando o teste manda, ids em sequência, agenda em memória."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conversational_commerce.contracts import Known
from conversational_commerce.ports import Capabilities, WorkItem
from conversational_commerce.ports.clock import OPERATIONS

from .synthetic_domain import CLOSING, OPENING, START

FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def parse_instant(text: str) -> datetime:
    return datetime.strptime(text, FORMAT).replace(tzinfo=UTC)


def _minute_of_day(hhmm: str) -> int:
    """``"08:00"`` → 480. O expediente sintético é dado em HH:MM, lido por código."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def format_instant(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(FORMAT)


class FakeClock:
    PORT = "clock"

    def __init__(self, start: str = START) -> None:
        self._now = parse_instant(start)
        self._counters: dict[str, int] = {}
        self.scheduled: dict[str, tuple[str, WorkItem]] = {}

    def capabilities(self) -> Capabilities:
        return Capabilities(port="clock", operations=OPERATIONS,
                            guarantees={"deterministic": True, "monotonic": True})

    def now(self) -> str:
        return format_instant(self._now)

    def advance(self, seconds: int) -> str:
        if seconds < 0:
            raise ValueError("o relógio não volta")
        self._now += timedelta(seconds=seconds)
        return self.now()

    def at(self, seconds_from_now: int) -> str:
        return format_instant(self._now + timedelta(seconds=seconds_from_now))

    def new_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}-{self._counters[prefix]:04d}"

    def schedule(self, at: str, work: WorkItem) -> str:
        handle = self.new_id("timer")
        self.scheduled[handle] = (at, work)
        return handle

    def cancel(self, handle: str) -> bool:
        return self.scheduled.pop(handle, None) is not None

    def due(self) -> list[WorkItem]:
        """O que venceu até agora: prazo vencido vira trabalho reivindicável, não laço."""
        now = self.now()
        return [work for at, work in sorted(self.scheduled.values(), key=lambda pair: pair[0]) if at <= now]

    def business_hours(self, at: str) -> Known:
        moment = parse_instant(at)
        # Comparação em minutos do dia: horário técnico, nunca texto de tela.
        minute = moment.hour * 60 + moment.minute
        is_open = _minute_of_day(OPENING) <= minute < _minute_of_day(CLOSING)
        day_end = moment.replace(hour=int(CLOSING[:2]), minute=0, second=0, microsecond=0)
        valid_until = format_instant(day_end if moment < day_end else day_end + timedelta(days=1))
        return Known(value={"open": is_open, "opens": OPENING, "closes": CLOSING},
                     source="fake-clock", observed_at=at, valid_until=valid_until)
