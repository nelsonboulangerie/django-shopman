"""Correlação (v2 5.7): mesmo sujeito, janela de inatividade, nunca por texto."""

from __future__ import annotations

import dataclasses
import inspect

from conversational_commerce.workflow import correlate, subject_key

from .helpers import episode_in

DAY = 24 * 3600


def test_subject_is_the_verified_customer_or_the_channel_binding():
    assert subject_key(verified_subject="customer-1", channel="c", conversation_ref="x") == "subject:customer-1"
    assert subject_key(verified_subject=None, channel="c", conversation_ref="x") == "binding:c:x"


def test_continues_the_open_episode_of_the_same_subject():
    episode = episode_in("active")
    result = correlate(subject=episode.subject, now="2026-01-05T12:00:00.000000Z", episodes=[episode],
                       inactivity_seconds=DAY)
    assert (result.action, result.episode_id) == ("continue", "ep-1")


def test_opens_new_after_inactivity_or_resolution():
    quiet = episode_in("active")
    later = "2026-01-07T09:00:00.000000Z"
    assert correlate(subject=quiet.subject, now=later, episodes=[quiet], inactivity_seconds=DAY).action == "open_new"
    assert correlate(subject=quiet.subject, now=later, episodes=[episode_in("resolved")],
                     inactivity_seconds=DAY).action == "open_new"


def test_open_wait_need_or_commitment_keeps_the_episode_past_the_window():
    later = "2026-01-07T09:00:00.000000Z"
    waiting = episode_in("waiting_input")
    assert correlate(subject=waiting.subject, now=later, episodes=[waiting], inactivity_seconds=DAY).action == "continue"
    with_need = dataclasses.replace(episode_in("active"), needs=("n1",))
    assert correlate(subject=with_need.subject, now=later, episodes=[with_need],
                     inactivity_seconds=DAY).action == "continue"
    quiet = episode_in("active")
    assert correlate(subject=quiet.subject, now=later, episodes=[quiet], inactivity_seconds=DAY,
                     open_commitments=["ep-1"]).action == "continue"


def test_other_subjects_never_join():
    episode = episode_in("active")
    result = correlate(subject="subject:customer-2", now="2026-01-05T09:10:00.000000Z", episodes=[episode],
                       inactivity_seconds=DAY)
    assert result.action == "open_new"


def test_correlation_takes_no_text():
    assert not any("text" in name or "content" in name for name in inspect.signature(correlate).parameters)
