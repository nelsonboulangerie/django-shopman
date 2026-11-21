"""Relógio de teste da pilha local (#2585): o arquivo decide o "agora" do processo."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from config import test_clock


@pytest.fixture
def clock(tmp_path):
    """Instala o relógio num arquivo novo e devolve o Django como estava."""
    original = timezone.now
    path = tmp_path / "clock"
    test_clock.install(path)
    yield path
    timezone.now = original
    test_clock._state.update({"path": None, "mtime_ns": None, "offset": timedelta(0)})


def write(path, text: str, *, written_at: datetime | None = None) -> None:
    path.write_text(text, encoding="utf-8")
    if written_at is not None:
        stamp = written_at.timestamp()
        os.utime(path, (stamp, stamp))


def test_without_the_file_it_is_the_real_time(clock):
    before = datetime.now(UTC)
    now = timezone.now()
    assert before <= now <= datetime.now(UTC)


def test_an_empty_file_is_the_real_time(clock):
    write(clock, "")
    assert abs(timezone.now() - datetime.now(UTC)) < timedelta(seconds=1)


def test_the_file_sets_now_and_the_clock_walks_from_the_write(clock):
    written = datetime.now(UTC) - timedelta(minutes=5)
    write(clock, "2026-11-23T15:50:00-03:00", written_at=written)

    now = timezone.now()

    # Gravado há 5 min: o relógio andou 5 min a partir do instante do arquivo.
    expected = datetime.fromisoformat("2026-11-23T15:55:00-03:00")
    assert abs(now - expected) < timedelta(seconds=2)


def test_localdate_and_localtime_follow_the_clock(clock):
    write(clock, "2026-11-24T00:05:00-03:00")

    assert timezone.localdate().isoformat() == "2026-11-24"
    assert timezone.localtime().strftime("%H:%M") == "00:05"


def test_a_new_write_is_a_new_trip_without_restart(clock):
    write(clock, "2026-11-23T08:00:00-03:00")
    assert timezone.localtime().strftime("%H") == "08"

    write(clock, "2026-11-23T16:30:00-03:00", written_at=datetime.now(UTC))
    assert timezone.localtime().strftime("%H:%M") == "16:30"


def test_a_time_without_zone_fails_loud(clock):
    write(clock, "2026-11-23T15:50:00")
    with pytest.raises(test_clock.TestClockError, match="fuso"):
        timezone.now()


def test_garbage_fails_loud(clock):
    write(clock, "amanhã de manhã")
    with pytest.raises(test_clock.TestClockError, match="ISO 8601"):
        timezone.now()
