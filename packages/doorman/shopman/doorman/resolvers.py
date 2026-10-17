"""
Built-in identity resolvers for Doorman.

The default resolver (NoopIdentityResolver) raises NotImplementedError, which
forces the integrator to configure a real resolver via DOORMAN["IDENTITY_RESOLVER_CLASS"].

When using Guestman, set:

    DOORMAN = {
        "IDENTITY_RESOLVER_CLASS": "shopman.guestman.adapters.auth.IdentityResolver",
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols.identity import IdentityView


class NoopIdentityResolver:
    """
    Default resolver — raises NotImplementedError on every call.

    Replace via DOORMAN["IDENTITY_RESOLVER_CLASS"] with a real implementation.
    When using shopman-guestman, use "shopman.guestman.adapters.auth.IdentityResolver".
    """

    _msg = (
        "No IdentityResolver configured. "
        "Set DOORMAN['IDENTITY_RESOLVER_CLASS'] to a class implementing "
        "shopman.doorman.protocols.identity.IdentityResolver. "
        "If you are using shopman-guestman, use "
        "'shopman.guestman.adapters.auth.IdentityResolver'."
    )

    def resolve(self, kind: str, value: str, *, purpose: str = "login") -> IdentityView | None:
        raise NotImplementedError(self._msg)

    def get(self, subject_id, *, purpose: str) -> IdentityView | None:
        raise NotImplementedError(self._msg)

    def lock_active(self, subject_id, *, purpose: str) -> IdentityView | None:
        raise NotImplementedError(self._msg)

    def create(self, kind: str, value: str) -> IdentityView:
        raise NotImplementedError(self._msg)

    def bind_verified_handle(
        self,
        subject_id,
        kind: str,
        value: str,
        *,
        proof: str,
    ) -> IdentityView:
        raise NotImplementedError(self._msg)
