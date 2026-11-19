"""Os 17 contratos do comércio conversacional, os tipos de valor e a forma canônica.

Especificação: ``spec/01-contracts.md``. ``CONTRACTS`` lista os contratos na
ordem da especificação; ``REGISTRY`` acha o contrato pelo ``schema`` de um
documento; ``parse_document`` lê qualquer documento pelo ``schema`` dele.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .action_command import ActionCommand, Idempotency, command_content_hash
from .action_receipt import VALID_COMBINATIONS, ActionReceipt, ReceiptError, Reconciliation
from .authorization_grant import AuthorizationGrant, ConfirmationEvidence, GrantLimits
from .candidate_action import CandidateAction, PreconditionResult
from .canonical import FrozenMap, canonical_bytes, canonical_text, sha256_hash
from .commitment import Commitment, DeadlineAbsent, DeadlineSet
from .common import (
    AUTHORITY_LEVELS,
    IDENTITY_LADDER,
    Estimate,
    Fact,
    IdentityEvidence,
    Known,
    Money,
    ObservationRecord,
    Prediction,
    Producer,
    Quantity,
    Record,
    StrictRecord,
    Unavailable,
    Unknown,
    Value,
    VersionRef,
)
from .context_snapshot import ContextSnapshot, Hypothesis, IdentityClaim, NeedView
from .decision_record import (
    DecisionCandidate,
    DecisionRecord,
    ModelCall,
    NotApplicable,
    Propensity,
    Selection,
    SnapshotRef,
    Weight,
)
from .deployment_profile import (
    ActionRule,
    DeploymentProfile,
    FactSource,
    LineAbsent,
    LineSet,
    MetricDefinition,
    Privacy,
    ProfileLine,
    StaffQueue,
    TurnLimits,
)
from .episode import Episode, Ownership, Wait
from .errors import ContractError, ErrorCode
from .exposure_event import ExposureEvent
from .interaction_event import ChannelBinding, EventIdentity, InteractionEvent
from .memory_item import MemoryItem
from .need import Need
from .outcome_event import MetricRef, OutcomeEvent, Window
from .reply_plan import Claim, Finding, ReplyPart, ReplyPlan, Verification
from .terms_document import Adjustment, Condition, Fulfillment, Recipient, TermsDocument, TermsItem
from .understanding import Act, Alternative, Signals, Span, Understanding
from .validate import compute_hash, seal

CONTRACTS: tuple[type[Record], ...] = (
    InteractionEvent,
    Understanding,
    ContextSnapshot,
    CandidateAction,
    DecisionRecord,
    TermsDocument,
    AuthorizationGrant,
    ActionCommand,
    ActionReceipt,
    ReplyPlan,
    ExposureEvent,
    OutcomeEvent,
    Episode,
    Need,
    Commitment,
    MemoryItem,
    DeploymentProfile,
)

REGISTRY: Mapping[str, type[Record]] = FrozenMap({contract.SCHEMA: contract for contract in CONTRACTS})


def parse_document(document: Mapping[str, Any]) -> Record:
    """Lê um documento de qualquer contrato, escolhido pelo campo ``schema``."""
    from .errors import invalid, unsupported

    if not isinstance(document, Mapping):
        raise invalid("documento precisa ser um objeto JSON")
    contract = REGISTRY.get(document.get("schema"))  # type: ignore[arg-type]
    if contract is None:
        raise unsupported(f"schema desconhecido: {document.get('schema')!r}", "schema")
    return contract.from_document(document)


__all__ = [
    "AUTHORITY_LEVELS",
    "CONTRACTS",
    "IDENTITY_LADDER",
    "REGISTRY",
    "VALID_COMBINATIONS",
    "Act",
    "ActionCommand",
    "ActionReceipt",
    "ActionRule",
    "Adjustment",
    "Alternative",
    "AuthorizationGrant",
    "CandidateAction",
    "ChannelBinding",
    "Claim",
    "Commitment",
    "Condition",
    "ConfirmationEvidence",
    "ContextSnapshot",
    "ContractError",
    "DeadlineAbsent",
    "DeadlineSet",
    "DecisionCandidate",
    "DecisionRecord",
    "DeploymentProfile",
    "Episode",
    "ErrorCode",
    "Estimate",
    "EventIdentity",
    "ExposureEvent",
    "Fact",
    "FactSource",
    "Finding",
    "FrozenMap",
    "Fulfillment",
    "GrantLimits",
    "Hypothesis",
    "Idempotency",
    "IdentityClaim",
    "IdentityEvidence",
    "InteractionEvent",
    "Known",
    "LineAbsent",
    "LineSet",
    "MemoryItem",
    "MetricDefinition",
    "MetricRef",
    "ModelCall",
    "Money",
    "Need",
    "NeedView",
    "NotApplicable",
    "ObservationRecord",
    "OutcomeEvent",
    "Ownership",
    "PreconditionResult",
    "Prediction",
    "Privacy",
    "Producer",
    "ProfileLine",
    "Propensity",
    "Quantity",
    "ReceiptError",
    "Recipient",
    "Reconciliation",
    "Record",
    "ReplyPart",
    "ReplyPlan",
    "Selection",
    "Signals",
    "SnapshotRef",
    "Span",
    "StaffQueue",
    "StrictRecord",
    "TermsDocument",
    "TermsItem",
    "TurnLimits",
    "Unavailable",
    "Understanding",
    "Unknown",
    "Value",
    "Verification",
    "VersionRef",
    "Wait",
    "Weight",
    "Window",
    "canonical_bytes",
    "canonical_text",
    "command_content_hash",
    "compute_hash",
    "parse_document",
    "seal",
    "sha256_hash",
]
