"""Catálogo canônico dos destinos e formatos de Marketing.

Este módulo é deliberadamente puro: não lê settings, banco ou provider.  Assim,
prévia, aprovação, ledger, worker e projeções podem compartilhar a mesma
identidade ``{platform, delivery_kind, format}`` sem transformar a presença de
uma credencial em autorização para produzir um efeito externo.

Adicionar uma entrada aqui torna o destino reconhecível pelo domínio, mas não o
ativa. Registro de adapter, credencial, readiness, autorização e canário
continuam gates independentes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from shopman.shop.services.marketing_contracts import MarketingContractError

DeliveryKind = Literal["publication", "direct_message"]
CAPABILITY_IDENTITY_SCHEMA_VERSION = 4


@dataclass(frozen=True, slots=True)
class MarketingFormatCapability:
    """Schema fechado dos campos que realmente chegam a um provider."""

    ref: str
    label: str
    provider_fields: frozenset[str]
    required_provider_fields: frozenset[str]
    media_required: bool = False


@dataclass(frozen=True, slots=True)
class MarketingPlatformCapability:
    """Uma consequência de Marketing com formatos explicitamente suportados."""

    platform: str
    label: str
    delivery_kind: DeliveryKind
    formats: tuple[MarketingFormatCapability, ...]
    default_format: str

    def format(self, ref: str) -> MarketingFormatCapability | None:
        normalized = str(ref or "").strip().lower()
        return next((item for item in self.formats if item.ref == normalized), None)


_PUBLICATION_FIELD = frozenset({"publication_format"})
_DESTINATIONS = (
    MarketingPlatformCapability(
        platform="instagram",
        label="Instagram",
        delivery_kind="publication",
        formats=(
            MarketingFormatCapability(
                ref="story",
                label="Story",
                provider_fields=_PUBLICATION_FIELD,
                required_provider_fields=_PUBLICATION_FIELD,
                media_required=True,
            ),
            MarketingFormatCapability(
                ref="feed",
                label="Feed",
                provider_fields=_PUBLICATION_FIELD,
                required_provider_fields=_PUBLICATION_FIELD,
                media_required=True,
            ),
        ),
        # Decisão de produto MKT-CAP-01: urgência/FOMO usa Story.
        default_format="story",
    ),
    MarketingPlatformCapability(
        platform="facebook",
        label="Facebook",
        delivery_kind="publication",
        formats=(
            MarketingFormatCapability(
                ref="feed",
                label="Feed",
                provider_fields=_PUBLICATION_FIELD,
                required_provider_fields=_PUBLICATION_FIELD,
            ),
        ),
        default_format="feed",
    ),
    MarketingPlatformCapability(
        platform="google_business",
        label="Google Meu Negócio",
        delivery_kind="publication",
        formats=(
            MarketingFormatCapability(
                ref="standard",
                label="Atualização padrão",
                provider_fields=_PUBLICATION_FIELD,
                required_provider_fields=_PUBLICATION_FIELD,
            ),
        ),
        default_format="standard",
    ),
    MarketingPlatformCapability(
        platform="whatsapp",
        label="WhatsApp",
        delivery_kind="direct_message",
        formats=(
            MarketingFormatCapability(
                ref="message",
                label="Mensagem",
                provider_fields=frozenset({"template_name"}),
                required_provider_fields=frozenset(),
            ),
        ),
        default_format="message",
    ),
)

DESTINATIONS: tuple[MarketingPlatformCapability, ...] = _DESTINATIONS
DESTINATIONS_BY_PLATFORM: Mapping[str, MarketingPlatformCapability] = MappingProxyType(
    {item.platform: item for item in DESTINATIONS}
)


def platform_refs() -> tuple[str, ...]:
    return tuple(item.platform for item in DESTINATIONS)


def platform_choices() -> tuple[tuple[str, str], ...]:
    return tuple((item.platform, item.label) for item in DESTINATIONS)


def platform_labels() -> Mapping[str, str]:
    return MappingProxyType({item.platform: item.label for item in DESTINATIONS})


def publication_platform_refs() -> tuple[str, ...]:
    return tuple(item.platform for item in DESTINATIONS if item.delivery_kind == "publication")


def platform_kind(platform: str) -> DeliveryKind | None:
    destination = DESTINATIONS_BY_PLATFORM.get(str(platform or "").strip())
    return destination.delivery_kind if destination is not None else None


def format_refs(platform: str) -> frozenset[str]:
    destination = DESTINATIONS_BY_PLATFORM.get(str(platform or "").strip())
    if destination is None:
        return frozenset()
    return frozenset(item.ref for item in destination.formats)


def default_format(platform: str) -> str:
    destination = DESTINATIONS_BY_PLATFORM.get(str(platform or "").strip())
    return destination.default_format if destination is not None else ""


def format_capability(
    platform: str,
    format_ref: str,
) -> MarketingFormatCapability | None:
    destination = DESTINATIONS_BY_PLATFORM.get(str(platform or "").strip())
    return destination.format(format_ref) if destination is not None else None


def default_format_capability(platform: str) -> MarketingFormatCapability | None:
    destination = DESTINATIONS_BY_PLATFORM.get(str(platform or "").strip())
    if destination is None:
        return None
    return destination.format(destination.default_format)


def resolve_identity(
    platform: str,
    *,
    delivery_kind: str = "",
    format_ref: str = "",
    allow_legacy_missing: bool = False,
) -> tuple[DeliveryKind, str]:
    """Validate or complete one persisted destination identity.

    Missing dimensions are accepted only for rows/artifacts explicitly known to
    predate MKT-CAP-01.  New writes must carry all three dimensions.
    """

    normalized_platform = str(platform or "").strip()
    destination = DESTINATIONS_BY_PLATFORM.get(normalized_platform)
    if destination is None:
        raise MarketingContractError(
            code="unknown_platform",
            detail="A plataforma da entrega não é reconhecida.",
        )
    normalized_kind = str(delivery_kind or "").strip()
    normalized_format = str(format_ref or "").strip().lower()
    if not normalized_kind or not normalized_format:
        if not allow_legacy_missing:
            raise MarketingContractError(
                code="delivery_identity_missing",
                detail="A modalidade ou o formato da entrega não foi registrado.",
            )
        normalized_kind = normalized_kind or destination.delivery_kind
        normalized_format = normalized_format or destination.default_format
    if normalized_kind != destination.delivery_kind:
        raise MarketingContractError(
            code="delivery_kind_mismatch",
            detail="A modalidade não corresponde à plataforma escolhida.",
        )
    if destination.format(normalized_format) is None:
        raise MarketingContractError(
            code="delivery_format_mismatch",
            detail="O formato não corresponde à plataforma escolhida.",
        )
    return destination.delivery_kind, normalized_format


def persisted_identity(row: object) -> tuple[DeliveryKind, str]:
    """Read a row identity, permitting omission only on legacy artifacts."""

    artifact = getattr(row, "artifact", None)
    schema_version = int(getattr(artifact, "schema_version", 0) or 0)
    return resolve_identity(
        str(getattr(row, "platform", "") or ""),
        delivery_kind=str(getattr(row, "delivery_kind", "") or ""),
        format_ref=str(getattr(row, "format", "") or ""),
        allow_legacy_missing=schema_version < CAPABILITY_IDENTITY_SCHEMA_VERSION,
    )
