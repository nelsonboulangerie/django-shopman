"""Single resolver for preview, approved storage and provider dispatch payloads."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from shopman.shop.models import DeliveryTarget, MarketingContentArtifact
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ResolvedDispatchArtifact,
)

SCHEMA_VERSION = 3
RESOLVED_ARTIFACT_SCHEMA_VERSION = 2
SUPPORTED_PLATFORMS = frozenset({"facebook", "google_business", "instagram", "whatsapp"})
PUBLICATION_FORMATS: dict[str, frozenset[str]] = {
    "instagram": frozenset({"story", "feed"}),
    "facebook": frozenset({"feed"}),
    "google_business": frozenset({"standard"}),
}
DEFAULT_PUBLICATION_FORMATS = {
    # Product decision (2026-09-11): urgent/FOMO content belongs in Stories.
    # Feed remains an explicit choice and is never a fallback.
    "instagram": "story",
    "facebook": "feed",
    "google_business": "standard",
}
_HASH = re.compile(r"^[a-f0-9]{64}$")
_FIELD = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FLOW_REF = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
_PLACEHOLDER = re.compile(r"\{\{\s*([\w_]+)\s*\}\}")
_RESERVED_CONTENT_FIELDS = frozenset({"body", "hashtags", "image_url", "link"})
_FORBIDDEN_PROVIDER_FIELDS = frozenset({
    "access_token",
    "credential",
    "credentials",
    "flow_id",
    "flow_ref",
    "password",
    "secret",
    "token",
})


def resolve_dispatch_artifact(
    *,
    platform: str,
    content: Mapping[str, Any],
    platform_content: Mapping[str, Any],
    content_version: int,
    facts_as_of: str = "",
    facts_hash: str = "",
    flow_ref: str = "",
    flow_version: int = 0,
    flow_catalog_hash: str = "",
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
    _assert_resolved(body, field="content.body")
    hashtags = _hashtags(merged.get("hashtags"))
    for index, hashtag in enumerate(hashtags):
        _assert_resolved(hashtag, field=f"content.hashtags.{index}")
    link = str(merged.get("link") or "").strip()
    image_url = str(merged.get("image_url") or "").strip()
    _assert_resolved(link, field="content.link")
    _assert_resolved(image_url, field="content.image_url")
    from shopman.shop.services import marketing_url_policy

    link = marketing_url_policy.validate_customer_link(
        link,
        field=(
            f"platform_content.{normalized_platform}.link"
            if "link" in variant
            else "content.link"
        ),
    )
    image_url = marketing_url_policy.validate_media_url(
        image_url,
        field=(
            f"platform_content.{normalized_platform}.image_url"
            if "image_url" in variant
            else "content.image_url"
        ),
    )
    normalized_facts_hash = str(facts_hash or "").strip().lower()
    if normalized_facts_hash and not _HASH.fullmatch(normalized_facts_hash):
        raise MarketingContractError(
            code="invalid_facts_hash",
            detail="O hash dos fatos do conteúdo é inválido.",
        )
    normalized_facts_as_of = str(facts_as_of or "").strip()
    if normalized_facts_as_of:
        try:
            parsed_as_of = datetime.fromisoformat(normalized_facts_as_of)
        except ValueError as exc:
            raise MarketingContractError(
                code="invalid_facts_as_of",
                detail="O instante dos fatos é inválido.",
            ) from exc
        if parsed_as_of.tzinfo is None or parsed_as_of.utcoffset() is None:
            raise MarketingContractError(
                code="invalid_facts_as_of",
                detail="O instante dos fatos precisa incluir timezone.",
            )
    normalized_flow_ref = str(flow_ref or "").strip()
    normalized_catalog_hash = str(flow_catalog_hash or "").strip().lower()
    has_flow_binding = bool(
        normalized_flow_ref or flow_version or normalized_catalog_hash
    )
    if has_flow_binding and normalized_platform != "whatsapp":
        raise MarketingContractError(
            code="flow_binding_platform_mismatch",
            detail="Somente o artefato do WhatsApp pode carregar um fluxo verificado.",
        )
    if has_flow_binding:
        if not _FLOW_REF.fullmatch(normalized_flow_ref):
            raise MarketingContractError(
                code="invalid_flow_ref",
                detail="A referência verificada do fluxo é inválida.",
            )
        if (
            isinstance(flow_version, bool)
            or not isinstance(flow_version, int)
            or flow_version < 1
        ):
            raise MarketingContractError(
                code="invalid_flow_version",
                detail="A versão verificada do fluxo é inválida.",
            )
        if not _HASH.fullmatch(normalized_catalog_hash):
            raise MarketingContractError(
                code="invalid_flow_catalog_hash",
                detail="O hash do catálogo de fluxos é inválido.",
            )
    provider_fields = _provider_fields(variant, platform=normalized_platform)
    _validate_publication_contract(
        platform=normalized_platform,
        provider_fields=dict(provider_fields),
        image_url=image_url,
    )
    return ResolvedDispatchArtifact(
        platform=normalized_platform,
        body=body,
        hashtags=hashtags,
        link=link,
        image_url=image_url,
        provider_fields=provider_fields,
        content_version=content_version,
        facts_as_of=normalized_facts_as_of,
        facts_hash=normalized_facts_hash,
        flow_ref=normalized_flow_ref,
        flow_version=flow_version if has_flow_binding else 0,
        flow_catalog_hash=normalized_catalog_hash,
    )


def normalize_platform_content(
    *,
    platforms: Sequence[str],
    platform_content: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Seal an explicit publication format into mutable preview/approval input.

    This is called before approval. Old immutable artifacts are never upgraded
    on read: if they do not name a format, a live adapter refuses them instead
    of guessing a new consequence.
    """

    variants = _mapping(platform_content, field="platform_content")
    normalized: dict[str, dict[str, Any]] = {}
    for raw_platform, raw_variant in variants.items():
        platform = str(raw_platform)
        normalized[platform] = _mapping(
            raw_variant,
            field=f"platform_content.{platform}",
        )

    for platform in platforms:
        if platform not in PUBLICATION_FORMATS:
            continue
        variant = normalized.setdefault(platform, {})
        legacy = str(variant.get("post_type") or "").strip().lower()
        explicit = str(variant.get("publication_format") or "").strip().lower()
        legacy_format = {
            "stories": "story",
            "story": "story",
            "feed": "feed",
            "standard": "standard",
        }.get(legacy, "")
        if legacy and not legacy_format:
            raise MarketingContractError(
                code="publication_format_invalid",
                detail="O formato antigo não corresponde a uma publicação suportada.",
                field_errors={
                    f"platform_content.{platform}.post_type": (
                        "Escolha um formato disponível.",
                    )
                },
            )
        if explicit and legacy_format and explicit != legacy_format:
            raise MarketingContractError(
                code="publication_format_conflict",
                detail="A variante contém dois formatos de publicação diferentes.",
                field_errors={
                    f"platform_content.{platform}.publication_format": (
                        "Escolha um único formato.",
                    )
                },
            )
        variant["publication_format"] = (
            explicit or legacy_format or DEFAULT_PUBLICATION_FORMATS[platform]
        )
        # ``post_type`` was an unimplemented draft field. Once interpreted, it
        # must not survive beside the canonical field and create ambiguity.
        variant.pop("post_type", None)
    return normalized


def resolve_all_dispatch_artifacts(
    *,
    platforms: Sequence[str],
    content: Mapping[str, Any],
    platform_content: Mapping[str, Any],
    content_version: int,
    facts_as_of: str = "",
    facts_hash: str = "",
    platform_bindings: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[ResolvedDispatchArtifact, ...]:
    """Resolve each selected platform through the exact same pure function."""

    bindings = dict(platform_bindings or {})
    unknown_bindings = sorted(set(bindings) - set(platforms))
    if unknown_bindings:
        raise MarketingContractError(
            code="orphan_platform_binding",
            detail="Existe configuração verificada para uma plataforma não escolhida.",
        )
    return tuple(
        resolve_dispatch_artifact(
            platform=platform,
            content=content,
            platform_content=platform_content,
            content_version=content_version,
            facts_as_of=facts_as_of,
            facts_hash=facts_hash,
            **_flow_binding(bindings.get(platform), platform=platform),
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

    if artifact.schema_version >= RESOLVED_ARTIFACT_SCHEMA_VERSION:
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
            provider_fields=tuple(
                _mapping(
                    payload.get("provider_fields", {}),
                    field=f"resolved_artifacts.{platform}.provider_fields",
                ).items()
            ),
            content_version=int(payload.get("content_version")),
            facts_as_of=str(payload.get("facts_as_of") or ""),
            facts_hash=str(payload.get("facts_hash") or ""),
            flow_ref=str(payload.get("flow_ref") or ""),
            flow_version=int(payload.get("flow_version") or 0),
            flow_catalog_hash=str(payload.get("flow_catalog_hash") or ""),
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
        content={
            "body": resolved.body,
            "hashtags": list(resolved.hashtags),
            "link": resolved.link,
            "image_url": resolved.image_url,
        },
        platform_content={platform: dict(resolved.provider_fields)},
        content_version=resolved.content_version,
        facts_as_of=resolved.facts_as_of,
        facts_hash=resolved.facts_hash,
        flow_ref=resolved.flow_ref,
        flow_version=resolved.flow_version,
        flow_catalog_hash=resolved.flow_catalog_hash,
    )


def _flow_binding(
    value: Mapping[str, Any] | None,
    *,
    platform: str,
) -> dict[str, Any]:
    if value is None:
        return {}
    binding = _mapping(value, field=f"platform_bindings.{platform}")
    allowed = {"flow_ref", "flow_version", "flow_catalog_hash"}
    unexpected = sorted(set(binding) - allowed)
    if unexpected:
        raise MarketingContractError(
            code="invalid_platform_binding",
            detail="A configuração verificada contém campos desconhecidos.",
            field_errors={
                f"platform_bindings.{platform}": tuple(unexpected),
            },
        )
    return {
        "flow_ref": binding.get("flow_ref", ""),
        "flow_version": binding.get("flow_version", 0),
        "flow_catalog_hash": binding.get("flow_catalog_hash", ""),
    }


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
    if any(not isinstance(item, str) for item in value):
        raise MarketingContractError(
            code="invalid_hashtags",
            detail="Cada hashtag precisa ser texto.",
            field_errors={"content.hashtags": ("Use somente textos na lista.",)},
        )
    return tuple(item.strip().lstrip("#") for item in value if item.strip())


def _provider_fields(
    variant: Mapping[str, Any],
    *,
    platform: str,
) -> tuple[tuple[str, Any], ...]:
    fields: list[tuple[str, Any]] = []
    for raw_key, value in variant.items():
        key = str(raw_key)
        if key in _RESERVED_CONTENT_FIELDS:
            continue
        if not _FIELD.fullmatch(key) or key in _FORBIDDEN_PROVIDER_FIELDS:
            raise MarketingContractError(
                code="invalid_provider_field",
                detail="A variante contém um campo de provider não permitido.",
                field_errors={
                    f"platform_content.{platform}.{key}": (
                        "Remova este campo da variante.",
                    )
                },
            )
        if not isinstance(value, str | int | float | bool) and value is not None:
            raise MarketingContractError(
                code="invalid_provider_field_value",
                detail="Campo de provider precisa ter valor escalar.",
                field_errors={
                    f"platform_content.{platform}.{key}": (
                        "Use texto, número, booleano ou nulo.",
                    )
                },
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise MarketingContractError(
                code="invalid_provider_field_value",
                detail="Campo de provider precisa ter número finito.",
            )
        if isinstance(value, str):
            _assert_resolved(value, field=f"platform_content.{platform}.{key}")
        fields.append((key, value))
    return tuple(sorted(fields))


def _validate_publication_contract(
    *,
    platform: str,
    provider_fields: Mapping[str, Any],
    image_url: str,
) -> None:
    """Validate explicit formats while keeping old sealed artifacts readable."""

    allowed = PUBLICATION_FORMATS.get(platform)
    if allowed is None:
        return
    raw_format = provider_fields.get("publication_format")
    if raw_format in (None, ""):
        # Compatibility only. Live adapters fail closed on this absence; new
        # preview/approval input always passes through normalize_platform_content.
        return
    publication_format = str(raw_format).strip().lower()
    field = f"platform_content.{platform}.publication_format"
    if publication_format not in allowed:
        raise MarketingContractError(
            code="publication_format_invalid",
            detail="O formato de publicação não é aceito por esta plataforma.",
            field_errors={field: ("Escolha um formato disponível.",)},
        )
    if platform == "instagram" and not image_url:
        raise MarketingContractError(
            code="instagram_media_required",
            detail="O Instagram precisa de uma imagem pública para publicar.",
            field_errors={
                "content.image_url": (
                    "Escolha uma imagem para o Story ou Feed do Instagram.",
                )
            },
        )


def _assert_resolved(value: str, *, field: str) -> None:
    match = _PLACEHOLDER.search(value)
    if match is None and "{{" not in value and "}}" not in value:
        return
    variable = match.group(1) if match is not None else "malformada"
    raise MarketingContractError(
        code="unresolved_template_variable",
        detail="O conteúdo ainda contém uma variável não resolvida.",
        field_errors={field: (f"Revise a variável {variable}.",)},
    )
