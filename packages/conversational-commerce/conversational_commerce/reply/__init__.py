"""Resposta com prova (F6): moldes, lastro por afirmação e a verificação de saída.

Especificação: ``spec/06-reply.md``.
"""

from .compose import Composed, PartSpec, compose, plain, render_part
from .conference import CheckResult, Conference, JudgeVerdict, ReplyJudge, confer, conferred
from .evidence import Evidence
from .templates import GENERIC_TEMPLATES, TEMPLATES_BY_ID, SlotSpec, Template
from .verify import EFFECT_MOVES, Finding, PhraseRule, RenderedClaim, RenderedPart, Segment, VerifyResult, verify

__all__ = [
    "CheckResult",
    "Conference",
    "JudgeVerdict",
    "ReplyJudge",
    "confer",
    "conferred",
    "EFFECT_MOVES",
    "GENERIC_TEMPLATES",
    "TEMPLATES_BY_ID",
    "Composed",
    "Evidence",
    "Finding",
    "PartSpec",
    "PhraseRule",
    "RenderedClaim",
    "RenderedPart",
    "Segment",
    "SlotSpec",
    "Template",
    "VerifyResult",
    "compose",
    "plain",
    "render_part",
    "verify",
]
