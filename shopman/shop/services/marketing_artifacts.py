"""Single resolver for preview, approved storage and provider dispatch payloads."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping, Sequence
from typing import Any

from shopman.shop.models import DeliveryTarget, MarketingContentArtifact
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ResolvedDispatchArtifact,
)

SCHEMA_VERSION = 2
SUPPORTED_PLATFORMS = frozenset({"facebook", "google_business", "instagram", "whatsapp"})
_HASH = re.compile(r"^[a-f0-9]{64}$")


def resolve_dispatch_artifact(
    *,
    platform: str,
    content: Mapping[str, Any],
    platform_content: Mapping[str, Any],
    content_version: int,
    facts_hash: str = "",
) -> ResolvedDispatchArtifact:
    """Resolve one immutable provider payload from approved, recipient-free facts."""

    normalized_platform = str(platform or "").strip()
    if normalized_platform not in SUPPORTED_PLATFORMS:
        raise MarketingContractError(
            code="unknown_platform",
            detail="A plataforma do artefato não é reconhecida.",
            field_errors={"platform": ("Escolha uma plataforma suportada.",)},
        )
    if isinstance(content_version, bool) or not isinstance(content_version, int) or content_version < 1:
        raise MarketingContractError(
            code="invalid_content_version",
            detail="A versão do conteúdo é inválida.",
            field_errors={"content_version": ("Use um inteiro positivo.",)},
        )
    base = _mapping(content, field="content")
    variants = _mapping(platform_content, field="platform_content")
    raw_variant = variants.get(normalized_platform, {})
    variant = _mapping(
        raw_variant,
        field=f"platform_content.{normalized_platform}",
    )
    merged = {**base, **variant}
    body = str(merged.get("body") or "").strip()
    if not body:
        raise MarketingContractError(
            code="body_required",
            detail="O artefato resolvido precisa de texto.",
            field_errors={"content.body": ("Revise o texto antes de publicar.",)},
        )
    normalized_facts_hash = str(facts_hash or "").strip().lower()
    if normalized_facts_hash and not _HASH.fullmatch(normalized_facts_hash):
        raise MarketingContractError(
            code="invalid_facts_hash",
            detail="O hash dos fatos do conteúdo é inválido.",
        )
    return ResolvedDispatchArtifact(
        platform=normalized_platform,
        body=body,
        hashtags=_hashtags(merged.get("hashtags")),
        link=str(merged.get("link") or "").strip(),
        image_url=str(merged.get("image_url") or "").strip(),
        content_version=content_version,
        facts_hash=normalized_facts_hash,
    )


def resolve_all_dispatch_artifacts(
    *,
    platforms: Sequence[str],
    content: Mapping[str, Any],
    platform_content: Mapping[str, Any],
    content_version: int,
    facts_hash: str = "",
) -> tuple[ResolvedDispatchArtifact, ...]:
    """Resolve each selected platform through the exact same pure function."""

    return tuple(
        resolve_dispatch_artifact(
            platform=platform,
            content=content,
            platform_content=platform_content,
            content_version=content_version,
            facts_hash=facts_hash,
        )
        for platform in platforms
    )


def resolved_payloads(
    artifacts: Sequence[ResolvedDispatchArtifact],
) -> dict[str, dict[str, Any]]:
    return {artifact.platform: artifact.as_payload() for artifact in artifacts}


def resolve_approved_dispatch_artifact(
    artifact: MarketingContentArtifact,
    *,
    platform: str,
) -> ResolvedDispatchArtifact:
    """Load the byte-approved provider payload and reject any storage drift."""

    expected = hashlib.sha256(artifact.canonical_bytes()).hexdigest()
    if not hmac.compare_digest(expected, str(artifact.artifact_hash)):
        raise MarketingContractError(
            code="artifact_hash_mismatch",
            detail="O artefato aprovado não confere com seu hash.",
        )
    payload = _mapping(artifact.payload, field="artifact.payload")
    if (
        payload.get("schema_version") != artifact.schema_version
        or payload.get("content_version") != artifact.version
    ):
        raise MarketingContractError(
            code="artifact_version_mismatch",
            detail="A versão do payload diverge da evidência aprovada.",
        )
    platforms = payload.get("platforms")
    if (
        isinstance(platforms, str)
        or not isinstance(platforms, Sequence)
        or platform not in platforms
    ):
        raise MarketingContractError(
            code="platform_not_approved",
            detail="A plataforma não pertence ao artefato aprovado.",
        )

    if artifact.schema_version >= SCHEMA_VERSION:
        stored = _mapping(payload.get("resolved_artifacts"), field="resolved_artifacts")
        resolved = _resolved_from_payload(stored.get(platform), platform=platform)
        if resolved.content_version != artifact.version:
            raise MarketingContractError(
                code="artifact_version_mismatch",
                detail="A versão resolvida diverge da evidência aprovada.",
            )
        return resolved

    # Compatibility window for approvals created before schema v2. New
    # approvals always persist ``resolved_artifacts`` and never re-render here.
    return resolve_dispatch_artifact(
        platform=platform,
        content=_mapping(payload.get("content"), field="content"),
        platform_content=_mapping(
            payload.get("platform_content"),
            field="platform_content",
        ),
        content_version=artifact.version,
        facts_hash=str(payload.get("facts_hash") or ""),
    )


def resolve_target_dispatch_artifact(target: DeliveryTarget) -> ResolvedDispatchArtifact:
    if target.artifact_id is None or target.platform not in SUPPORTED_PLATFORMS:
        raise MarketingContractError(
            code="delivery_artifact_mismatch",
            detail="O target não aponta para um artefato e plataforma válidos.",
        )
    return resolve_approved_dispatch_artifact(
        target.artifact,
        platform=target.platform,
    )


def _resolved_from_payload(value: object, *, platform: str) -> ResolvedDispatchArtifact:
    payload = _mapping(value, field=f"resolved_artifacts.{platform}")
    try:
        resolved = ResolvedDispatchArtifact(
            platform=str(payload.get("platform") or ""),
            body=str(payload.get("body") or ""),
            hashtags=_hashtags(payload.get("hashtags")),
            link=str(payload.get("link") or ""),
            image_url=str(payload.get("image_url") or ""),
            content_version=int(payload.get("content_version")),
            facts_hash=str(payload.get("facts_hash") or ""),
        )
    except (TypeError, ValueError) as exc:
        raise MarketingContractError(
            code="invalid_resolved_artifact",
            detail="O payload resolvido aprovado é inválido.",
        ) from exc
    if resolved.platform != platform:
        raise MarketingContractError(
            code="artifact_platform_mismatch",
            detail="A plataforma resolvida diverge da evidência aprovada.",
        )
    # Round-trip through the pure resolver applies the same invariants used by
    # preview and approval without inheriting any later mutable model state.
    return resolve_dispatch_artifact(
        platform=resolved.platform,
        content=resolved.as_payload(),
        platform_content={},
        content_version=resolved.content_version,
        facts_hash=resolved.facts_hash,
    )


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MarketingContractError(
            code="invalid_artifact_content",
            detail=f"{field} precisa ser um objeto.",
            field_errors={field: ("Use um objeto JSON.",)},
        )
    return dict(value)


def _hashtags(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise MarketingContractError(
            code="invalid_hashtags",
            detail="Hashtags precisam ser uma lista.",
            field_errors={"content.hashtags": ("Envie uma lista de hashtags.",)},
        )
    return tuple(str(item).strip().lstrip("#") for item in value if str(item).strip())
