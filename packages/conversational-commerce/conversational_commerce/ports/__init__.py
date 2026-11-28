"""As oito portas do núcleo, como ``typing.Protocol``, e a forma da guarda de efeito.

Especificação: ``spec/03-ports.md``. Adaptador falso de cada porta:
``conversational_commerce.testing.fakes``.
"""

from . import channel, clock, commerce_execute, commerce_read, model, outcomes, staff, store
from .channel import ChannelPort, HandoffRequest, PreparedMessage
from .clock import ClockPort
from .commerce_execute import CommerceExecutePort
from .commerce_read import CommerceReadPort, ItemSummary, PromiseReading
from .common import PORT_NAMES, Capabilities, PortError, TrustedContext
from .guard import EffectGuard, EffectState
from .model import (
    AdjudicateRequest,
    Adjudication,
    Budget,
    Consumption,
    Draft,
    InterpretRequest,
    KnownCost,
    ModelPort,
    ModelRequest,
    PendingQuestion,
    ReadingContext,
    RecentTurn,
    ScoreRequest,
    Scores,
)
from .outcomes import OutcomesPort
from .staff import ConversationReturn, StaffPort, StaffQuestion, StaffTicket
from .store import Claim, StorePort, Transition, WorkItem

# Porta → (Protocol, operações obrigatórias).
PORTS = {
    "channel": (ChannelPort, channel.OPERATIONS),
    "model": (ModelPort, model.OPERATIONS),
    "commerce_read": (CommerceReadPort, commerce_read.OPERATIONS),
    "commerce_execute": (CommerceExecutePort, commerce_execute.OPERATIONS),
    "staff": (StaffPort, staff.OPERATIONS),
    "store": (StorePort, store.OPERATIONS),
    "clock": (ClockPort, clock.OPERATIONS),
    "outcomes": (OutcomesPort, outcomes.OPERATIONS),
}

__all__ = [
    "PORTS",
    "PORT_NAMES",
    "AdjudicateRequest",
    "Adjudication",
    "Budget",
    "Capabilities",
    "ChannelPort",
    "Claim",
    "ClockPort",
    "CommerceExecutePort",
    "CommerceReadPort",
    "Consumption",
    "ConversationReturn",
    "Draft",
    "EffectGuard",
    "EffectState",
    "HandoffRequest",
    "InterpretRequest",
    "ItemSummary",
    "KnownCost",
    "ModelPort",
    "ModelRequest",
    "OutcomesPort",
    "PendingQuestion",
    "PortError",
    "PreparedMessage",
    "PromiseReading",
    "ReadingContext",
    "RecentTurn",
    "ScoreRequest",
    "Scores",
    "StaffPort",
    "StaffQuestion",
    "StaffTicket",
    "StorePort",
    "Transition",
    "TrustedContext",
    "WorkItem",
]
