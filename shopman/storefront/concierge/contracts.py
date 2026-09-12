"""Contratos puros entre o nucleo conversacional e seus transportes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

OutcomeState = Literal["accepted", "not_applied", "unknown"]


@dataclass(frozen=True)
class TransportScope:
    provider: str
    account: str
    channel: str
    subject: str
    connection_key: str


@dataclass(frozen=True)
class TransportConnection:
    key: str
    provider: str
    account: str
    channel: str
    adapter_path: str
    options: Mapping[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ChannelCapabilities:
    max_text_chars: int
    response_window: timedelta | None
    stable_event_identity_verified: bool = False
    delivery_receipts: bool = False
    supports_handoff: bool = False


@dataclass(frozen=True)
class WindowEvidence:
    """Prova normalizada da janela; nunca representa identidade do evento."""

    policy: str
    source: str
    observed_at: datetime
    valid_until: datetime
    assurance: str

    def as_dict(self) -> dict[str, str]:
        return {
            "policy": self.policy,
            "source": self.source,
            "observed_at": self.observed_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "assurance": self.assurance,
        }

    @classmethod
    def from_value(cls, value: WindowEvidence | Mapping[str, Any] | None) -> WindowEvidence | None:
        if value is None or isinstance(value, cls):
            return value
        try:
            observed_at = datetime.fromisoformat(str(value["observed_at"]))
            valid_until = datetime.fromisoformat(str(value["valid_until"]))
            if observed_at.tzinfo is None or valid_until.tzinfo is None:
                return None
            return cls(
                policy=str(value["policy"]),
                source=str(value["source"]),
                observed_at=observed_at,
                valid_until=valid_until,
                assurance=str(value["assurance"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class InboundEvent:
    """Evento autenticado e normalizado; o payload não escolhe seu escopo."""

    scope: TransportScope
    text: str
    message_type: str
    received_at: datetime
    event_id: str = ""
    event_identity_assurance: str = "unavailable"
    occurred_at: datetime | None = None
    occurred_at_assurance: str = "unavailable"
    profile: Mapping[str, str] = field(default_factory=dict)
    correlation_ref: str = ""
    authentication_assurance: str = ""
    payload_hash: str = ""
    window_evidence: WindowEvidence | None = None

    def as_envelope(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "version": 3,
            "connection_key": self.scope.connection_key,
            "provider": self.scope.provider,
            "account_id": self.scope.account,
            "transport_channel": self.scope.channel,
            "subject": self.scope.subject,
            "event_id": self.event_id,
            "event_identity_assurance": self.event_identity_assurance,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else "",
            "occurred_at_assurance": self.occurred_at_assurance,
            "received_at": self.received_at.isoformat(),
            "message_type": self.message_type,
            "correlation_ref": self.correlation_ref,
            "authentication": self.authentication_assurance,
            "payload_hash": self.payload_hash,
            "profile": dict(self.profile),
        }
        if self.window_evidence:
            envelope["window_evidence"] = self.window_evidence.as_dict()
        return envelope


class IngressRejected(Exception):
    """Recusa definitiva do adapter antes de persistir qualquer evento."""

    def __init__(self, status: int, code: str, detail: str, *, field: str = ""):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.field = field


@dataclass(frozen=True)
class ResponseAuthorization:
    allowed: bool
    code: str
    valid_until: datetime | None = None


@dataclass(frozen=True)
class SendOutcome:
    state: OutcomeState
    code: str = ""
    provider_receipt_ref: str = ""


@dataclass(frozen=True)
class HandoffOutcome:
    state: OutcomeState
    code: str = ""
    provider_receipt_ref: str = ""

    @property
    def accepted(self) -> bool:
        return self.state == "accepted"


class ConversationAdapter(Protocol):
    provider: str
    channel: str
    capabilities: ChannelCapabilities

    def authenticate_and_normalize(self, request: Any, received_at: datetime) -> InboundEvent: ...
    def window_evidence(self, envelope: Mapping[str, Any], now: datetime) -> WindowEvidence | None: ...
    def authorize_response(
        self, evidence: WindowEvidence | Mapping[str, Any] | None, now: datetime, *, purpose: str
    ) -> ResponseAuthorization: ...
    def send_text(self, subject: str, text: str) -> SendOutcome: ...
    def set_handoff(self, subject: str, on: bool) -> HandoffOutcome: ...
    def identify(self, subject: str, profile: Mapping[str, Any]): ...
