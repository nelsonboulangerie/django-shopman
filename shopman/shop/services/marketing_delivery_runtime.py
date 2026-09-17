"""Runtime seam from a durable Directive into the protected delivery ledger."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from shopman.shop.models import MarketingOutbox
from shopman.shop.services.marketing_capabilities import platform_refs
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_delivery_worker import (
    fanout_in_chunks,
    queue_materialized_targets,
)

SUPPORTED_PLATFORMS = platform_refs()
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StagingReport:
    outbox_ref: str
    platform: str
    targets: int
    queued: int
    replayed: bool


#: A flag de ambiente que registra o adapter de entrega de cada plataforma
#: (``config/settings.py``). Desligada, o adapter existe no código mas não entra em
#: ``SHOPMAN_MARKETING_DELIVERY_ADAPTERS``.
PLATFORM_SWITCHES: Mapping[str, str] = MappingProxyType({
    "instagram": "SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED",
    "facebook": "SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED",
    "google_business": "SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED",
    "whatsapp": "SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED",
})

#: ``registered``: há adapter registrado para a plataforma neste ambiente.
#: ``switched_off``: nada registrado e a flag da plataforma está desligada — escolha
#: de quem opera o ambiente, não defeito.
#: ``unconfigured``: nada registrado com a flag ligada (ou sem flag conhecida) —
#: configuração quebrada.
LaneState = Literal["registered", "switched_off", "unconfigured"]


@dataclass(frozen=True, slots=True)
class DeliveryLane:
    platform: str
    state: LaneState
    switch: str


def delivery_lane(platform: str) -> DeliveryLane:
    """Diz, sem chamar ``get_adapter`` nem o provedor, em que estado a plataforma está.

    Registro é a chave com caminho em ``SHOPMAN_MARKETING_DELIVERY_ADAPTERS`` (ou em
    ``Shop.integrations``, que tem prioridade). Estar registrada não diz que a
    credencial funciona: isso é o ``is_available`` do adapter, conferido por
    ``delivery_provider``.
    """

    return _lane(str(platform or ""), registered=_registered_platforms())


def delivery_lanes() -> tuple[DeliveryLane, ...]:
    """Estado de cada plataforma do catálogo, na ordem do catálogo."""

    registered = _registered_platforms()
    return tuple(_lane(platform, registered=registered) for platform in SUPPORTED_PLATFORMS)


def _registered_platforms() -> frozenset[str]:
    from shopman.shop.adapters import configured_methods

    return frozenset(configured_methods("marketing_delivery"))


def _lane(platform: str, *, registered: frozenset[str]) -> DeliveryLane:
    from django.conf import settings

    switch = PLATFORM_SWITCHES.get(platform, "")
    if platform in registered:
        state: LaneState = "registered"
    elif switch and not getattr(settings, switch, False):
        state = "switched_off"
    else:
        state = "unconfigured"
    return DeliveryLane(platform=platform, state=state, switch=switch)


def delivery_provider(platform: str, *, require_available: bool = True):
    """Resolve the provider for one lane without falling back to another lane."""

    normalized = str(platform or "")
    if normalized not in SUPPORTED_PLATFORMS:
        return None
    from shopman.shop.adapters import get_adapter

    provider = get_adapter("marketing_delivery", method=normalized)
    if provider is None:
        return None
    probe = getattr(provider, "is_available", None)
    if require_available and (probe is None or not bool(probe())):
        return None
    return provider


def is_hermetic_simulation(platform: str) -> bool:
    """Prove that one lane ends at the explicit no-I/O local adapter."""

    provider = delivery_provider(platform, require_available=False)
    if provider is None or not getattr(provider, "SIMULATION_ONLY", False):
        return False
    probe = getattr(provider, "is_available", None)
    try:
        return bool(probe is not None and probe())
    except Exception:
        logger.warning(
            "marketing.delivery_provider_probe_failed platform=%s",
            platform,
            exc_info=True,
        )
        return False


def stage_outbox_directive(*, payload: dict, topic: str) -> StagingReport:
    """Validate the sealed graph, materialize it and queue it for provider work."""

    from shopman.shop.services.marketing_outbox import directive_payload_matches

    if not isinstance(payload, dict):
        raise MarketingContractError(
            code="delivery_directive_payload_invalid",
            detail="A directive de entrega não contém um payload estruturado.",
        )
    outbox_ref = str(payload.get("outbox_ref") or "")
    try:
        outbox = MarketingOutbox.objects.select_related(
            "announcement", "artifact", "snapshot", "command"
        ).get(ref=outbox_ref)
    except (ValueError, MarketingOutbox.DoesNotExist) as exc:
        raise MarketingContractError(
            code="delivery_outbox_missing",
            detail="A directive não corresponde a uma intent durável existente.",
        ) from exc
    if not directive_payload_matches(outbox, payload=payload, topic=topic):
        raise MarketingContractError(
            code="delivery_directive_graph_mismatch",
            detail="A identidade da directive diverge do grafo aprovado.",
        )

    before = outbox.delivery_targets.count()
    fanout = fanout_in_chunks(outbox.ref, max_chunks=100)
    if not fanout.complete:
        raise MarketingContractError(
            code="delivery_fanout_incomplete",
            detail="O fan-out protegido ainda possui targets a materializar.",
            retryable=True,
        )
    queued = queue_materialized_targets(outbox.ref)
    return StagingReport(
        outbox_ref=str(outbox.ref),
        platform=outbox.platform,
        targets=fanout.requested,
        queued=queued,
        replayed=before == fanout.requested and queued == 0,
    )
