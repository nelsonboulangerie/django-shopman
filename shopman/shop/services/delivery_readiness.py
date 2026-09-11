"""Verifiable delivery readiness for every Marketing platform.

Readiness is a four-state fact, not a truthy shortcut.  ``unknown`` means the
system could not verify the provider now; it never masquerades as an empty
catalog or permission to mutate configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from django.conf import settings
from django.utils import timezone

PUBLICATION = "publication"
DIRECT_MESSAGE = "direct_message"
logger = logging.getLogger(__name__)

PLATFORM_KIND: dict[str, str] = {
    "instagram": PUBLICATION,
    "facebook": PUBLICATION,
    "google_business": PUBLICATION,
    "whatsapp": DIRECT_MESSAGE,
}
ReadinessState = Literal["ready", "degraded", "blocked", "unknown"]


@dataclass(frozen=True, slots=True)
class PlatformReadiness:
    platform: str
    kind: str
    state: ReadinessState
    reason_code: str
    checked_at: datetime
    facts_as_of: datetime | None = None
    fresh_until: datetime | None = None
    source_status: str = ""
    version: int = 1
    reason: str = ""
    action: str = ""
    limitation: str = ""

    @property
    def ready(self) -> bool:
        """Legacy compatibility: degraded can deliver, blocked/unknown cannot."""

        return self.state in {"ready", "degraded"}


def readiness_for(
    platforms,
    *,
    now: datetime | None = None,
) -> tuple[PlatformReadiness, ...]:
    """Return each requested platform in order, with one shared check instant."""

    clock = _aware_now(now)
    out = []
    for platform in platforms or []:
        kind = PLATFORM_KIND.get(platform)
        if kind is None:
            out.append(
                PlatformReadiness(
                    platform=platform,
                    kind="unknown",
                    state="unknown",
                    reason_code="platform_unknown",
                    checked_at=clock,
                    source_status="unavailable",
                    reason="Plataforma desconhecida pelo sistema.",
                    action="Revisar as plataformas da campanha",
                )
            )
        elif pipeline_block := _pipeline_block(platform, kind=kind, now=clock):
            out.append(pipeline_block)
        elif simulated := _local_simulation_readiness(platform, kind=kind, now=clock):
            out.append(simulated)
        elif kind == PUBLICATION:
            out.append(_publication_readiness(platform, now=clock))
        else:
            out.append(_direct_message_readiness(platform, now=clock))
    result = tuple(out)
    from shopman.shop.services.marketing_observability import record_readiness

    record_readiness(result, now=clock)
    return result


def _pipeline_block(
    platform: str,
    *,
    kind: str,
    now: datetime,
) -> PlatformReadiness | None:
    """Never call a lane ready when its durable handoff cannot run."""

    if _isolated_publication_canary(kind=kind):
        # A public canary has its own exact-ref handoff and target claim. It is
        # safe only while both broad consumers remain off; provider readiness
        # is still verified by ``_publication_readiness`` below.
        return None
    if not getattr(settings, "SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED", False):
        return PlatformReadiness(
            platform=platform,
            kind=kind,
            state="blocked",
            reason_code="delivery_handoff_disabled",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason="A preparação das entregas está pausada neste ambiente.",
            action="Pedir à operação para ativar o processamento de Marketing",
        )
    if not getattr(settings, "SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED", False):
        return PlatformReadiness(
            platform=platform,
            kind=kind,
            state="blocked",
            reason_code="delivery_worker_disabled",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason="O envio para as plataformas está pausado neste ambiente.",
            action="Pedir à operação para ativar o worker de entregas",
        )
    return None


def _isolated_publication_canary(*, kind: str) -> bool:
    return bool(
        kind == PUBLICATION
        and getattr(settings, "SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED", False)
        and not getattr(settings, "SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED", False)
        and not getattr(settings, "SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED", False)
    )


def _local_simulation_readiness(
    platform: str,
    *,
    kind: str,
    now: datetime,
) -> PlatformReadiness | None:
    """Expose a truthful local rehearsal state without claiming provider health."""

    from shopman.shop.services.marketing_delivery_runtime import delivery_provider

    try:
        provider = delivery_provider(platform, require_available=False)
        if provider is None or not getattr(provider, "SIMULATION_ONLY", False):
            return None
        probe = getattr(provider, "is_available", None)
        if probe is None or not bool(probe()):
            return None
    except Exception:
        logger.warning(
            "marketing.local_simulation_probe_failed platform=%s",
            platform,
            exc_info=True,
        )
        return None
    return PlatformReadiness(
        platform=platform,
        kind=kind,
        state="ready",
        reason_code="local_simulation",
        checked_at=now,
        facts_as_of=now,
        source_status="simulated",
        reason="Simulação local ativa; nenhum conteúdo sai deste computador.",
        limitation=(
            "Exercita aprovação, fila, registro de entrega e comprovante local — não comprova a "
            "credencial nem a entrega da plataforma real."
        ),
    )


def _publication_readiness(platform: str, *, now: datetime) -> PlatformReadiness:
    from shopman.shop.services.marketing_delivery_runtime import delivery_provider

    adapter = delivery_provider(platform, require_available=False)
    if adapter is None:
        return PlatformReadiness(
            platform=platform,
            kind=PUBLICATION,
            state="blocked",
            reason_code="publication_adapter_missing",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason="Não há integração de publicação configurada para esta plataforma.",
            action="Configurar as credenciais da plataforma",
        )

    probe = getattr(adapter, "is_available", None)
    if probe is None:
        return PlatformReadiness(
            platform=platform,
            kind=PUBLICATION,
            state="unknown",
            reason_code="publication_probe_missing",
            checked_at=now,
            source_status="unavailable",
            reason="A integração não oferece uma verificação segura de disponibilidade.",
            action="Pedir ao responsável do canal para verificar a integração",
        )
    try:
        available = bool(probe())
    except Exception:  # provider adapters are an availability boundary
        logger.warning(
            "marketing.publication_probe_failed platform=%s",
            platform,
            exc_info=True,
        )
        return PlatformReadiness(
            platform=platform,
            kind=PUBLICATION,
            state="unknown",
            reason_code="publication_probe_unavailable",
            checked_at=now,
            source_status="unavailable",
            reason="Não foi possível verificar a integração agora.",
            action="Tentar a verificação novamente",
        )
    if not available:
        return PlatformReadiness(
            platform=platform,
            kind=PUBLICATION,
            state="blocked",
            reason_code="publication_credential_missing",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason="A integração existe, mas está sem credencial neste ambiente.",
            action="Conferir as credenciais da plataforma",
        )

    canary_only = _isolated_publication_canary(kind=PUBLICATION)
    return PlatformReadiness(
        platform=platform,
        kind=PUBLICATION,
        state="ready",
        reason_code="publication_canary_ready" if canary_only else "",
        checked_at=now,
        facts_as_of=now,
        source_status="fresh",
        reason=(
            "A integração está pronta para uma postagem canário isolada."
            if canary_only
            else ""
        ),
        limitation=(
            "Somente a consequência pública exata confirmada no canário será executada."
            if canary_only
            else ""
        ),
    )


def _direct_message_readiness(platform: str, *, now: datetime) -> PlatformReadiness:
    from shopman.shop.handlers.campaign import _whatsapp_backend
    from shopman.shop.models import NotificationTemplate
    from shopman.shop.services import manychat_flows

    try:
        backend = _whatsapp_backend()
    except Exception:  # adapter probes must degrade the page, never break it
        logger.warning(
            "marketing.direct_message_probe_failed platform=%s",
            platform,
            exc_info=True,
        )
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="unknown",
            reason_code="whatsapp_transport_probe_unavailable",
            checked_at=now,
            source_status="unavailable",
            reason="Não foi possível verificar o transporte do WhatsApp agora.",
            action="Tentar a verificação novamente",
        )
    if backend is None:
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="blocked",
            reason_code="whatsapp_transport_missing",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason="Nenhum transporte configurado — o envio falharia para todos.",
            action="Conferir a credencial do canal neste ambiente",
        )
    if backend != "manychat":
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="blocked",
            reason_code="whatsapp_manychat_transport_missing",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason="Marketing por WhatsApp exige o transporte ManyChat da ADR-009.",
            action="Configurar a credencial ManyChat deste ambiente",
        )

    # The legacy campaign backend and the durable delivery worker have different
    # provider contracts.  A healthy ManyChat credential alone cannot make the
    # v2 outbox deliver: the worker needs a registered ``marketing_delivery``
    # adapter for this exact lane.  Reporting ready without it leaves approved
    # messages queued forever.
    from shopman.shop.services.marketing_delivery_runtime import delivery_provider

    durable_provider = delivery_provider(platform, require_available=False)
    if durable_provider is None:
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="blocked",
            reason_code="whatsapp_durable_provider_missing",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason=(
                "A integração de campanhas do WhatsApp ainda não está conectada "
                "à fila segura de envio."
            ),
            action="Concluir e verificar a integração durável do WhatsApp",
        )
    durable_probe = getattr(durable_provider, "is_available", None)
    try:
        durable_available = bool(durable_probe is not None and durable_probe())
    except Exception:
        logger.warning("marketing.whatsapp_durable_provider_probe_failed", exc_info=True)
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="unknown",
            reason_code="whatsapp_durable_provider_probe_unavailable",
            checked_at=now,
            source_status="unavailable",
            reason="Não foi possível verificar a fila segura do WhatsApp agora.",
            action="Tentar a verificação novamente",
        )
    if not durable_available:
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="blocked",
            reason_code="whatsapp_durable_provider_unavailable",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            reason="A fila segura do WhatsApp está configurada, mas indisponível.",
            action="Conferir a integração durável do WhatsApp",
        )

    template = NotificationTemplate.objects.filter(
        event="announcement_published"
    ).only("whatsapp_flow_ns", "is_active", "version").first()
    version = template.version if template is not None else 1
    flow_ns = (template.whatsapp_flow_ns or "") if template is not None else ""
    if not flow_ns:
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="degraded",
            reason_code="whatsapp_flow_not_selected",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            version=version,
            limitation=(
                "Só alcança quem conversou com a loja nas últimas 24 horas. Quem não "
                "conversou não recebe — é regra da plataforma, não falha do envio."
            ),
            action="Escolher um fluxo aprovado e ativo para o anúncio",
        )
    if not template.is_active:
        return PlatformReadiness(
            platform=platform,
            kind=DIRECT_MESSAGE,
            state="blocked",
            reason_code="whatsapp_template_inactive",
            checked_at=now,
            facts_as_of=now,
            source_status="fresh",
            version=version,
            reason="O modelo que referencia o fluxo está inativo.",
            action="Escolher novamente um fluxo aprovado para ativar esta configuração",
        )

    catalog = manychat_flows.flow_catalog(now=now)
    common = {
        "platform": platform,
        "kind": DIRECT_MESSAGE,
        "checked_at": catalog.checked_at,
        "facts_as_of": catalog.facts_as_of,
        "fresh_until": catalog.fresh_until,
        "source_status": catalog.state,
        "version": version,
    }
    if catalog.mutation_safe and catalog.contains(flow_ns):
        from shopman.shop.services import manychat_marketing_safety

        safety = manychat_marketing_safety.safety_state()
        if not safety.safe:
            return PlatformReadiness(
                **common,
                state="blocked",
                reason_code=safety.reason_code,
                reason=safety.reason,
                action=safety.action,
            )
        return PlatformReadiness(
            **common,
            state="ready",
            reason_code="",
        )
    if catalog.mutation_safe:
        return PlatformReadiness(
            **common,
            state="blocked",
            reason_code="whatsapp_flow_not_active",
            reason="O fluxo escolhido não aparece entre os fluxos ativos da plataforma.",
            action="Escolher um fluxo ativo da lista atual",
        )
    return PlatformReadiness(
        **common,
        state="unknown",
        reason_code=(catalog.reason_code or "whatsapp_flow_verification_unavailable"),
        reason="Não foi possível confirmar se o fluxo escolhido continua ativo.",
        action="Atualizar a verificação da plataforma; nenhuma configuração foi alterada",
    )


def _has_approved_template(event: str = "announcement_published") -> bool:
    """Compatibility helper with the corrected active-record semantics."""

    from shopman.shop.models import NotificationTemplate

    return (
        NotificationTemplate.objects.filter(event=event, is_active=True)
        .exclude(whatsapp_flow_ns="")
        .exists()
    )


def _aware_now(value: datetime | None) -> datetime:
    clock = value or timezone.now()
    return timezone.make_aware(clock) if timezone.is_naive(clock) else clock
