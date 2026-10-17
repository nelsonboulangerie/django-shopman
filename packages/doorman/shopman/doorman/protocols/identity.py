"""Canonical authentication identity contracts owned by Doorman."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID


class IdentityConflict(RuntimeError):
    """Identity ownership is ambiguous or violates its global invariant."""


@dataclass(frozen=True)
class IdentityHandle:
    kind: str
    value: str = field(repr=False)
    verified: bool
    primary: bool


@dataclass(frozen=True)
class IdentityView:
    """Doorman's purpose-limited view of an authentication subject."""

    subject_id: UUID
    name: str = field(repr=False)
    handles: tuple[IdentityHandle, ...] = field(repr=False)
    is_active: bool

    def handle(self, kind: str, *, verified: bool | None = None) -> IdentityHandle | None:
        candidates = [
            handle
            for handle in self.handles
            if handle.kind == kind and (verified is None or handle.verified is verified)
        ]
        primary = [handle for handle in candidates if handle.primary]
        if len(primary) > 1:
            raise IdentityConflict(f"multiple_primary_handles:{kind}")
        if primary:
            return primary[0]
        if len(candidates) == 1:
            return candidates[0]
        return None


@runtime_checkable
class IdentityResolver(Protocol):
    """Guest identity port consumed and owned by Doorman."""

    def resolve(self, kind: str, value: str, *, purpose: str = "login") -> IdentityView | None: ...

    def get(self, subject_id: UUID, *, purpose: str) -> IdentityView | None: ...

    def lock_active(self, subject_id: UUID, *, purpose: str) -> IdentityView | None:
        """Lock and revalidate the active subject in the caller transaction."""
        ...

    def create(self, kind: str, value: str) -> IdentityView: ...

    def bind_verified_handle(
        self,
        subject_id: UUID,
        kind: str,
        value: str,
        *,
        proof: str,
    ) -> IdentityView:
        """Atomically bind a verified handle without changing existing primacy."""
        ...


@runtime_checkable
class ManychatIdentityBridge(Protocol):
    """Explicit optional bridge for ManyChat enrichment and lookup."""

    def upsert_access_link_subject(self, subject_id: UUID, payload: dict) -> IdentityView | None: ...

    def upsert_subscriber(self, subscriber_data: dict) -> IdentityView | None: ...

    def last_input_text(self, subscriber_id: str) -> str: ...

    def phone(self, subscriber_id: str) -> str: ...
