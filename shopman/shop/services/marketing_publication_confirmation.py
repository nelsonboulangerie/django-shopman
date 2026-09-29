"""Depois do aceite, o estado real da publicação — só leitura, nunca reenvio.

O Google aceita o post e decide depois: ``LIVE``, ``REJECTED`` pela política de
conteúdo, ou ``PROCESSING`` enquanto isso (a foto aparece ~1–2 min depois do
texto). Parar em ``accepted`` escondia a recusa. Esta passada roda no mesmo ciclo
da entrega, consulta o post pelo recibo e leva o destino a ``confirmed`` ou
``failed_final``; ``PROCESSING`` fica ``accepted`` para a próxima passada.

Só entra o adapter que declara ``CONFIRMS_PUBLICATION_STATE`` (a consulta dele diz
o estado, não só que o post existe). A consulta é idempotente e não publica nada;
apagar um post é outra ação pública e não existe aqui.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta

from django.db import transaction

from shopman.shop.models import DeliveryTarget
from shopman.shop.services.marketing_contracts import (
    DeliveryState,
    ProviderOutcomeKind,
    ensure_delivery_transition,
)

logger = logging.getLogger(__name__)

#: Depois disso o destino aceito deixa de ser consultado: a decisão do Google sai em
#: minutos, e o operador ainda pode pedir a consulta pelo cockpit.
CONFIRMATION_WINDOW = timedelta(hours=48)


def confirm_accepted_publications(
    *,
    providers: dict,
    now: datetime,
    limit: int = 20,
) -> Counter[str]:
    platforms = [
        platform
        for platform, provider in providers.items()
        if getattr(provider, "CONFIRMS_PUBLICATION_STATE", False)
    ]
    outcomes: Counter[str] = Counter()
    if not platforms:
        return outcomes
    candidates = list(
        DeliveryTarget.objects.filter(
            platform__in=platforms,
            delivery_kind="publication",
            state=DeliveryState.ACCEPTED.value,
            last_attempt_at__gte=now - CONFIRMATION_WINDOW,
        )
        .exclude(provider_receipt_ref="")
        .order_by("last_attempt_at", "pk")
        .values_list("pk", "platform", "target_fingerprint", "provider_receipt_ref")[:limit]
    )
    for pk, platform, fingerprint, receipt in candidates:
        try:
            outcome = providers[platform].lookup(
                target_key=fingerprint,
                idempotency_token="",
                provider_receipt_ref=receipt,
            )
        except Exception:
            logger.warning(
                "marketing.publication_confirmation_lookup_failed platform=%s", platform
            )
            outcomes["deferred"] += 1
            continue
        outcomes[_apply(pk, outcome=outcome, now=now)] += 1
    return outcomes


def _apply(pk: int, *, outcome, now: datetime) -> str:
    resolved = {
        ProviderOutcomeKind.CONFIRMED: DeliveryState.CONFIRMED,
        ProviderOutcomeKind.FAILED_FINAL: DeliveryState.FAILED_FINAL,
    }.get(outcome.kind)
    if resolved is None:
        return "still_accepted"
    with transaction.atomic():
        target = DeliveryTarget.objects.select_for_update().get(pk=pk)
        if target.state != DeliveryState.ACCEPTED.value:
            return "already_moved"
        ensure_delivery_transition(DeliveryState.ACCEPTED, resolved)
        target.state = resolved.value
        target.last_error_code = (
            "" if resolved == DeliveryState.CONFIRMED else str(outcome.code)[:64]
        )
        target.settled_at = now
        target.version += 1
        target.updated_at = now
        target.save(
            update_fields=["state", "last_error_code", "settled_at", "version", "updated_at"]
        )
        from shopman.shop.services.marketing_delivery_aggregate import (
            schedule_delivery_refresh,
        )

        schedule_delivery_refresh(target.announcement_id)
    return resolved.value
