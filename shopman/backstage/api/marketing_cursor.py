"""Opaque, stable cursor primitives for Marketing v2 collections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.core import signing
from django.utils import timezone

_CURSOR_SALT = "shopman.backstage.marketing.cursor.v2"


class InvalidMarketingCursor(ValueError):
    """The cursor is invalid, tampered with or belongs to another collection."""


@dataclass(frozen=True, slots=True)
class MarketingCursor:
    collection: str
    as_of: datetime
    created_at: datetime | None = None
    pk: int | None = None


def encode_cursor(cursor: MarketingCursor) -> str:
    """Sign a deterministic cursor containing no operator or audience data."""

    payload = {
        "v": 2,
        "collection": cursor.collection,
        "as_of": _aware(cursor.as_of).isoformat(),
        "created_at": (
            _aware(cursor.created_at).isoformat()
            if cursor.created_at is not None
            else None
        ),
        "pk": cursor.pk,
    }
    return signing.Signer(salt=_CURSOR_SALT).sign_object(payload)


def decode_cursor(value: str, *, collection: str) -> MarketingCursor:
    """Verify and parse a cursor, binding it to the requested collection."""

    try:
        payload = signing.Signer(salt=_CURSOR_SALT).unsign_object(value)
    except signing.BadSignature as exc:
        raise InvalidMarketingCursor("invalid signature") from exc
    if not isinstance(payload, dict):
        raise InvalidMarketingCursor("invalid payload")
    if payload.get("v") != 2 or payload.get("collection") != collection:
        raise InvalidMarketingCursor("wrong cursor scope")

    as_of = _parse_datetime(payload.get("as_of"))
    created_at = _parse_datetime(payload.get("created_at"), optional=True)
    raw_pk = payload.get("pk")
    pk = raw_pk if isinstance(raw_pk, int) and not isinstance(raw_pk, bool) and raw_pk > 0 else None
    if as_of is None or (created_at is None) != (pk is None):
        raise InvalidMarketingCursor("invalid cursor position")
    if created_at is not None and created_at > as_of:
        raise InvalidMarketingCursor("position is after snapshot")
    return MarketingCursor(
        collection=collection,
        as_of=as_of,
        created_at=created_at,
        pk=pk,
    )


def first_cursor(*, collection: str, as_of: datetime | None = None) -> MarketingCursor:
    return MarketingCursor(collection=collection, as_of=_aware(as_of or timezone.now()))


def _parse_datetime(value: object, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _aware(parsed) if timezone.is_aware(parsed) else None


def _aware(value: datetime) -> datetime:
    if timezone.is_naive(value):
        raise InvalidMarketingCursor("cursor datetimes must be timezone-aware")
    return value
