"""Signed freshness tokens shared by production reads and mutations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from django.core import signing

PRODUCTION_CONTRACT_VERSION = 1
# The slowest operational fallback poll is the planning board at 60 seconds.
# Keep a full 30-second interaction margin after that refresh; otherwise the
# board would be deliberately read-only for half of every polling cycle.
PRODUCTION_FRESHNESS_SECONDS = 90
PRODUCTION_MAX_FRESHNESS_SECONDS = 120
PRODUCTION_CLOCK_SKEW_SECONDS = 5
_SIGNING_SALT = "shopman.backstage.production-projection.v1"
_ACTION_SIGNING_SALT = "shopman.backstage.production-action.v1"
_OVERRIDE_SIGNING_SALT = "shopman.backstage.production-override.v1"


def signed_source_revision(
    *,
    digest: str,
    generated_at: datetime,
    fresh_until: datetime,
    contract_version: int = PRODUCTION_CONTRACT_VERSION,
    projection_kind: str = "",
    selected_date: str = "",
    subject_ref: str = "",
) -> str:
    source = ":".join(
        (
            "sha256",
            digest,
            projection_kind,
            selected_date,
            subject_ref,
        )
    )
    value = _signed_value(
        source=source,
        generated_at=generated_at,
        fresh_until=fresh_until,
        contract_version=contract_version,
    )
    signature = signing.Signer(salt=_SIGNING_SALT).signature(value)
    return f"{source}:{signature}"


def projection_revision_scope(source_revision: str) -> tuple[str, str, str] | None:
    """Return the signed projection kind/date/subject without trusting it yet."""
    try:
        source, _signature = str(source_revision).rsplit(":", 1)
        algorithm, _digest, projection_kind, selected_date, subject_ref = source.split(":", 4)
    except ValueError:
        return None
    if algorithm != "sha256":
        return None
    return projection_kind, selected_date, subject_ref


def signed_action_proof(
    *,
    action_ref: str,
    action_kind: str,
    href: str,
    expected_rev: int | None,
    source_revision: str,
    projection_generated_at: datetime,
    fresh_until: datetime,
    contract_version: int,
    projection_kind: str,
    selected_date: str,
    subject_ref: str,
) -> str:
    """Sign one enabled action from one immutable projection response."""
    return signing.dumps(
        {
            "action_ref": action_ref,
            "action_kind": action_kind,
            "href": href,
            "expected_rev": expected_rev,
            "source_revision": source_revision,
            "projection_generated_at": _utc_seconds(projection_generated_at),
            "fresh_until": _utc_seconds(fresh_until),
            "contract_version": contract_version,
            "projection_kind": projection_kind,
            "selected_date": selected_date,
            "subject_ref": subject_ref,
        },
        salt=_ACTION_SIGNING_SALT,
        compress=True,
    )


def validate_action_proof(
    *,
    action_proof: str,
    action_ref: str,
    action_kind: str,
    href: str,
    expected_rev: int | None,
    source_revision: str,
    projection_generated_at: datetime,
    fresh_until: datetime,
    contract_version: int,
    projection_kind: str,
    selected_date: str,
    subject_ref: str,
) -> dict[str, str]:
    """Reject a mutation not backed by the exact enabled projected action."""
    expected = {
        "action_ref": action_ref,
        "action_kind": action_kind,
        "href": href,
        "expected_rev": expected_rev,
        "source_revision": source_revision,
        "projection_generated_at": _utc_seconds(projection_generated_at),
        "fresh_until": _utc_seconds(fresh_until),
        "contract_version": contract_version,
        "projection_kind": projection_kind,
        "selected_date": selected_date,
        "subject_ref": subject_ref,
    }
    try:
        actual = signing.loads(action_proof, salt=_ACTION_SIGNING_SALT)
    except (ValueError, signing.BadSignature):
        return {"action_proof": "Comprovante da ação projetada inválido."}
    if actual != expected:
        return {
            "action_proof": ("A ação não pertence a esta projeção, alvo ou revisão. Atualize o painel antes de agir.")
        }
    return {}


def override_attempt_digest(body: dict) -> str:
    """Hash the attempted effect, allowing only force/reason proof fields to change."""
    canonical = {
        key: value
        for key, value in body.items()
        if key
        not in {
            "_approved_shortage_snapshot",
            "_committed_replay",
            "force",
            "reason",
            "override_proof",
        }
    }
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signed_override_proof(
    *,
    action_proof: str,
    idempotency_key: str,
    attempt_digest: str,
    shortage_snapshot: dict,
) -> str:
    """Authorize only the force retry offered by a real shortage response."""
    return signing.dumps(
        {
            "action_proof": action_proof,
            "idempotency_key": idempotency_key,
            "attempt_digest": attempt_digest,
            "shortage_snapshot": shortage_snapshot,
        },
        salt=_OVERRIDE_SIGNING_SALT,
        compress=True,
    )


def validate_override_proof(
    *,
    override_proof: str,
    action_proof: str,
    idempotency_key: str,
    attempt_digest: str,
) -> dict[str, str]:
    expected = {
        "action_proof": action_proof,
        "idempotency_key": idempotency_key,
        "attempt_digest": attempt_digest,
    }
    try:
        actual = signing.loads(override_proof, salt=_OVERRIDE_SIGNING_SALT)
    except (ValueError, signing.BadSignature):
        return {"override_proof": "Autorização de exceção inválida."}
    if (
        not isinstance(actual, dict)
        or {key: actual.get(key) for key in expected} != expected
        or not isinstance(actual.get("shortage_snapshot"), dict)
    ):
        return {"override_proof": ("A autorização de exceção pertence a outra ação ou tentativa.")}
    return {}


def override_shortage_snapshot(override_proof: str) -> dict | None:
    """Return the signed shortage impact after normal proof validation."""
    try:
        actual = signing.loads(override_proof, salt=_OVERRIDE_SIGNING_SALT)
    except (ValueError, signing.BadSignature):
        return None
    snapshot = actual.get("shortage_snapshot") if isinstance(actual, dict) else None
    return dict(snapshot) if isinstance(snapshot, dict) else None


def validate_projection_metadata(
    *,
    projection_generated_at: datetime,
    source_revision: str,
    fresh_until: datetime,
    contract_version: int,
    now: datetime,
) -> dict[str, str]:
    """Return field errors for forged, impossible or incompatible metadata."""
    errors: dict[str, str] = {}
    if contract_version != PRODUCTION_CONTRACT_VERSION:
        errors["contract_version"] = "Versão do contrato de produção incompatível."
    if projection_generated_at > now + timedelta(seconds=PRODUCTION_CLOCK_SKEW_SECONDS):
        errors["projection_generated_at"] = "A projeção está no futuro."
    lifetime = (fresh_until - projection_generated_at).total_seconds()
    if lifetime <= 0 or lifetime > PRODUCTION_MAX_FRESHNESS_SECONDS:
        errors["fresh_until"] = "Janela de frescor da projeção inválida."

    try:
        source, signature = str(source_revision).rsplit(":", 1)
        if projection_revision_scope(source_revision) is None:
            raise signing.BadSignature
        signed_value = _signed_value(
            source=source,
            generated_at=projection_generated_at,
            fresh_until=fresh_until,
            contract_version=contract_version,
        )
        signing.Signer(salt=_SIGNING_SALT).unsign(f"{signed_value}:{signature}")
    except (ValueError, signing.BadSignature):
        errors["source_revision"] = "Revisão da projeção inválida."
    return errors


def _signed_value(
    *,
    source: str,
    generated_at: datetime,
    fresh_until: datetime,
    contract_version: int,
) -> str:
    return "|".join(
        (
            source,
            generated_at.astimezone(UTC).isoformat(timespec="seconds"),
            fresh_until.astimezone(UTC).isoformat(timespec="seconds"),
            str(contract_version),
        )
    )


def _utc_seconds(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")
