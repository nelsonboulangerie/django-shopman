"""Episódio, necessidade, posse, correlação e a casca durável (F4).

Especificação: ``spec/04-episode.md``.
"""

from .correlation import Correlation, correlate, subject_key
from .dialogue import answer_refers_to, answered, ask, on_conversation_returned
from .errors import InvalidTransition, StaleVersion
from .machine import TABLE, EpisodeEvent, next_state, open_episode, transition
from .needs import actionable, held_by_blocked, update_need
from .shell import Advance, Received, advance, handle_inbound, receive

__all__ = [
    "TABLE",
    "Advance",
    "Correlation",
    "EpisodeEvent",
    "InvalidTransition",
    "Received",
    "StaleVersion",
    "actionable",
    "advance",
    "answer_refers_to",
    "answered",
    "ask",
    "correlate",
    "handle_inbound",
    "held_by_blocked",
    "next_state",
    "on_conversation_returned",
    "open_episode",
    "receive",
    "subject_key",
    "transition",
    "update_need",
]
