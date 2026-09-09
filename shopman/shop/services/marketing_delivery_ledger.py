"""Protected DeliveryTarget/Attempt ledger primitives.

This module creates logical targets only.  It never resolves a telephone, calls
an adapter or serializes cohort membership.  Target identity is a versioned
HMAC scoped to snapshot + platform, so a database reader cannot dictionary-hash
phone numbers and campaigns are not linkable by a stable plain digest.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from shopman.shop.models import (
    AudienceSnapshotMember,
    DeliveryTarget,
    MarketingOutbox,
)
from shopman.shop.services.marketing_contracts import MarketingContractError

MAX_TARGETS_PER_COMMAND = 5_000
IDENTITY_RETENTION = timedelta(days=90)
RECORD_RETENTION = timedelta(days=365 * 5)


def ensure_targets(
    outbox_ref,
    *,
    member_ids: Iterable[int] | None = None,
    now: datetime | None = None,
) -> tuple[DeliveryTarget, ...]:
    """Create one target per approved identity, safely replayable by two workers.

    WhatsApp receives an explicit, already-selected member set from the
    canonical wave selector. Public posting platforms create exactly one target
    with ``member=None``.
    """

    clock = _aware_now(now)
    with transaction.atomic():
        outbox = (
            MarketingOutbox.objects.select_for_update()
            .select_related("announcement", "snapshot", "artifact", "command")
            .get(ref=outbox_ref)
        )
        if outbox.state != MarketingOutbox.State.DISPATCHED:
            raise MarketingContractError(
                code="outbox_not_dispatched",
                detail="A intent ainda não foi entregue à fila durável.",
            )
        if (
            outbox.snapshot.announcement_id != outbox.announcement_id
            or outbox.artifact.announcement_id != outbox.announcement_id
            or outbox.command.resulting_version != outbox.snapshot.version
            or outbox.command.resulting_version != outbox.artifact.version
            or outbox.platform not in outbox.artifact.payload.get("platforms", [])
        ):
            raise MarketingContractError(
                code="delivery_graph_mismatch",
                detail="O grafo aprovado não corresponde à intent de entrega.",
            )

        if outbox.platform == "whatsapp":
            members = _members(outbox, member_ids)
            identities = [(member, f"member:{member.target_key}") for member in members]
        else:
            if member_ids is not None and tuple(member_ids):
                raise MarketingContractError(
                    code="public_target_has_member",
                    detail="Publicação pública não aceita membro de audiência.",
                )
            identities = [(None, f"publication:{outbox.announcement_id}")]

        if len(identities) > MAX_TARGETS_PER_COMMAND:
            raise MarketingContractError(
                code="delivery_target_cap_exceeded",
                detail=f"O comando excede o limite de {MAX_TARGETS_PER_COMMAND} targets.",
            )

        key_version, secret = _fingerprint_secret()
        fingerprints = {
            member.pk if member is not None else None: _target_fingerprint(
                secret=secret,
                key_version=key_version,
                snapshot_ref=str(outbox.snapshot.ref),
                platform=outbox.platform,
                identity=identity,
            )
            for member, identity in identities
        }
        member_keys = [member.pk for member, _identity in identities if member is not None]
        existing = list(
            DeliveryTarget.objects.select_for_update().filter(
                snapshot=outbox.snapshot,
                platform=outbox.platform,
                member_id__in=member_keys,
            )
        )
        if not member_keys:
            existing = list(
                DeliveryTarget.objects.select_for_update().filter(
                    snapshot=outbox.snapshot,
                    platform=outbox.platform,
                    member__isnull=True,
                )
            )
        collision = [target for target in existing if target.outbox_id != outbox.pk]
        if collision:
            raise MarketingContractError(
                code="delivery_wave_collision",
                detail="Um target aprovado já pertence a outra lane desta plataforma.",
            )

        existing_member_ids = {target.member_id for target in existing}
        retention_base = max(clock, outbox.available_at)
        pending = []
        for member, _identity in identities:
            member_id = member.pk if member is not None else None
            if member_id in existing_member_ids:
                continue
            pending.append(DeliveryTarget(
                outbox=outbox,
                announcement=outbox.announcement,
                snapshot=outbox.snapshot,
                artifact=outbox.artifact,
                member=member,
                platform=outbox.platform,
                wave_key=outbox.wave_key,
                target_fingerprint=fingerprints[member_id],
                fingerprint_key_version=key_version,
                next_attempt_at=outbox.available_at,
                identity_retention_until=retention_base + IDENTITY_RETENTION,
                record_retention_until=retention_base + RECORD_RETENTION,
            ))
        DeliveryTarget.objects.bulk_create(pending, ignore_conflicts=True)

        target_query = DeliveryTarget.objects.filter(
            snapshot=outbox.snapshot,
            platform=outbox.platform,
        )
        if member_keys:
            target_query = target_query.filter(member_id__in=member_keys)
        else:
            target_query = target_query.filter(member__isnull=True)
        targets = tuple(target_query.order_by("pk"))
        if len(targets) != len(identities):
            raise MarketingContractError(
                code="delivery_target_materialization_incomplete",
                detail="Nem todos os targets foram materializados; tente reconciliar.",
                retryable=True,
            )
        if any(target.outbox_id != outbox.pk for target in targets):
            raise MarketingContractError(
                code="delivery_wave_collision",
                detail="Um target aprovado já pertence a outra lane desta plataforma.",
            )
        return targets


def _members(
    outbox: MarketingOutbox,
    member_ids: Iterable[int] | None,
) -> tuple[AudienceSnapshotMember, ...]:
    if member_ids is None:
        raise MarketingContractError(
            code="delivery_member_selection_required",
            detail="A lane WhatsApp exige seleção protegida explícita de membros.",
        )
    normalized = tuple(dict.fromkeys(int(pk) for pk in member_ids))
    if not normalized:
        return ()
    if len(normalized) > MAX_TARGETS_PER_COMMAND:
        raise MarketingContractError(
            code="delivery_target_cap_exceeded",
            detail=f"O comando excede o limite de {MAX_TARGETS_PER_COMMAND} targets.",
        )
    members = tuple(
        AudienceSnapshotMember.objects.filter(
            snapshot=outbox.snapshot,
            pk__in=normalized,
        ).order_by("pk")
    )
    if len(members) != len(normalized):
        raise MarketingContractError(
            code="delivery_member_outside_snapshot",
            detail="A seleção contém identidade fora do snapshot aprovado.",
        )
    return members


def _fingerprint_secret() -> tuple[int, bytes]:
    version = int(settings.SHOPMAN_MARKETING_TARGET_HMAC_KEY_VERSION)
    raw = str(settings.SHOPMAN_MARKETING_TARGET_HMAC_KEY or "")
    if version <= 0 or len(raw) < 16:
        raise MarketingContractError(
            code="target_hmac_key_unavailable",
            detail="A chave protegida do ledger de Marketing não está disponível.",
        )
    return version, raw.encode("utf-8")


def _target_fingerprint(
    *,
    secret: bytes,
    key_version: int,
    snapshot_ref: str,
    platform: str,
    identity: str,
) -> str:
    canonical = (
        f"marketing-target:v{key_version}:snapshot:{snapshot_ref}:"
        f"platform:{platform}:identity:{identity}"
    )
    return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _aware_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValueError("Marketing delivery ledger requires an aware clock.")
    return value
