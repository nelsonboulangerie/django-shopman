"""Compatibility proxy for the canonical Craftsman production backend.

Stockman owns the protocol, but it must not own an alternate production
writer. The installed Craftsman integration is the single implementation and
crosses the authoritative backstage production facade for every mutation.
"""

from __future__ import annotations

import threading
from datetime import date
from importlib import import_module
from importlib.util import find_spec

from shopman.stockman.protocols.production import (
    ProductionRequest,
    ProductionResult,
    ProductionStatus,
)


def _craftsman_available() -> bool:
    """Return whether the optional Craftsman integration can be imported."""
    try:
        return find_spec("shopman.craftsman.contrib.stockman.production") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


class ProductionBackend:
    """Backward-compatible proxy with no production mutation logic of its own."""

    @staticmethod
    def _canonical_backend():
        module = import_module("shopman.craftsman.contrib.stockman.production")
        return module.get_production_backend()

    def request_production(self, request: ProductionRequest) -> ProductionResult:
        if not _craftsman_available():
            return ProductionResult(success=False, message="Craftsman not available")
        return self._canonical_backend().request_production(request)

    def check_status(self, request_id: str) -> ProductionStatus | None:
        if not _craftsman_available():
            return None
        return self._canonical_backend().check_status(request_id)

    def cancel_request(
        self,
        request_id: str,
        reason: str = "cancelled",
    ) -> ProductionResult:
        if not _craftsman_available():
            return ProductionResult(success=False, message="Craftsman not available")
        return self._canonical_backend().cancel_request(request_id, reason=reason)

    def list_pending(
        self,
        sku: str | None = None,
        target_date: date | None = None,
    ) -> list[ProductionStatus]:
        if not _craftsman_available():
            return []
        return self._canonical_backend().list_pending(
            sku=sku,
            target_date=target_date,
        )


_lock = threading.Lock()
_backend_instance: ProductionBackend | None = None


def get_production_backend() -> ProductionBackend:
    """Return the compatibility proxy singleton."""
    global _backend_instance

    if _backend_instance is None:
        with _lock:
            if _backend_instance is None:
                _backend_instance = ProductionBackend()
    return _backend_instance


def reset_production_backend() -> None:
    """Reset the compatibility and canonical singletons for tests."""
    global _backend_instance
    _backend_instance = None
    if _craftsman_available():
        module = import_module("shopman.craftsman.contrib.stockman.production")
        module.reset_production_backend()
