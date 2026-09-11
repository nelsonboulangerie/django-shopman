"""Backstage projection serialization boundary for shop orchestration."""

from __future__ import annotations

from typing import Any


def data(value: Any) -> Any:
    """Return the surface projection as JSON-safe primitives."""
    from shopman.backstage.api.projections import projection_data

    return projection_data(value)
