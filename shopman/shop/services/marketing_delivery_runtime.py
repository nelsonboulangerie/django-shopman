"""Runtime seam from a durable Directive into the protected delivery ledger."""

from __future__ import annotations

from dataclasses import dataclass

from shopman.shop.models import MarketingOutbox
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_delivery_worker import (
    fanout_in_chunks,
    queue_materialized_targets,
)

SUPPORTED_PLATFORMS = ("instagram", "facebook", "google_business", "whatsapp")


@dataclass(frozen=True, slots=True)
class StagingReport:
    outbox_ref: str
    platform: str
    targets: int
    queued: int
    replayed: bool


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
