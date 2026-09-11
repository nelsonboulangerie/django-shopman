"""JSON helpers for immutable backstage projections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from django.utils import timezone

from shopman.backstage.api.production_freshness import (
    PRODUCTION_FRESHNESS_SECONDS,
    signed_action_proof,
    signed_source_revision,
)
from shopman.shop.middleware import API_VERSION

_PRODUCTION_META_FIELDS = {
    "generated_at",
    "source_revision",
    "fresh_until",
    "contract_version",
}

# Runtime delivery health must not invalidate an otherwise unchanged operator
# intent. A relay can heartbeat between GET and POST; that changes the helpful
# preflight label, not the recipes, quantities or selected tickets being signed.
_NON_REVISION_FIELDS = {"print_destination"}


def _projected_actions(value: Any):
    """Yield every action nested in a projection without assuming its layout."""
    if isinstance(value, Mapping):
        actions = value.get("actions")
        if isinstance(actions, list | tuple):
            yield from (action for action in actions if isinstance(action, Mapping))
        for key, item in value.items():
            if key != "actions":
                yield from _projected_actions(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _projected_actions(item)


def projection_data(
    value: Any,
    *,
    freshness_context: tuple[str, str, str] | None = None,
) -> Any:
    """Convert projection dataclasses into JSON-safe primitives."""
    if type(value) in (str, int, float, bool, type(None)):
        return value
    if is_dataclass(value):
        data = {field.name: projection_data(getattr(value, field.name)) for field in fields(value)}
        if _PRODUCTION_META_FIELDS <= data.keys():
            now = timezone.now().replace(microsecond=0)
            revision_source = {
                key: item
                for key, item in data.items()
                if key not in _PRODUCTION_META_FIELDS | _NON_REVISION_FIELDS
            }
            digest = hashlib.sha256(
                json.dumps(
                    revision_source,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
            generated_at = data["generated_at"] or now.isoformat()
            fresh_until = data["fresh_until"] or (now + timedelta(seconds=PRODUCTION_FRESHNESS_SECONDS)).isoformat()
            data.update(
                generated_at=generated_at,
                source_revision=data["source_revision"]
                or signed_source_revision(
                    digest=digest,
                    generated_at=datetime.fromisoformat(generated_at),
                    fresh_until=datetime.fromisoformat(fresh_until),
                    contract_version=int(data["contract_version"]),
                    projection_kind=(freshness_context or ("", "", ""))[0],
                    selected_date=(freshness_context or ("", "", ""))[1],
                    subject_ref=(freshness_context or ("", "", ""))[2],
                ),
                fresh_until=fresh_until,
            )
            projection_kind, selected_date, subject_ref = freshness_context or ("", "", "")
            for action in _projected_actions(data):
                if action.get("enabled"):
                    action["proof"] = signed_action_proof(
                        action_ref=action["ref"],
                        action_kind=action["kind"],
                        href=action["href"],
                        expected_rev=action["expected_rev"],
                        source_revision=data["source_revision"],
                        projection_generated_at=datetime.fromisoformat(generated_at),
                        fresh_until=datetime.fromisoformat(fresh_until),
                        contract_version=int(data["contract_version"]),
                        projection_kind=projection_kind,
                        selected_date=selected_date,
                        subject_ref=subject_ref,
                    )
        return data
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): projection_data(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [projection_data(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [projection_data(item) for item in value]
    return value


def read_data(**payload: Any) -> dict:
    """Metadata of a useful read, separate from command preconditions and SSE."""
    return {**payload, "generated_at": timezone.now().isoformat(), "contract_version": int(API_VERSION)}
