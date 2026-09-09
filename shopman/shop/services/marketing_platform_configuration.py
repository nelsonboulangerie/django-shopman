"""Versioned, confirmed and audited Marketing platform configuration commands."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from shopman.shop.models import (
    MarketingCommandReceipt,
    MarketingPlatformAuditEvent,
    NotificationTemplate,
)
from shopman.shop.services import manychat_flows
from shopman.shop.services.marketing_commands import (
    MarketingCommandConflict,
    MarketingCommandRejected,
    command_fingerprints,
)
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_security import (
    ACTION_CONFIGURE_PLATFORM,
    AuthorizationContext,
    authorization_context,
    safety_state,
)

EVENT = "announcement_published"
RESOURCE_REF = "platform:whatsapp"
_RETENTION = timedelta(days=365 * 5)
_FLOW_REF_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


class MarketingPlatformUnavailable(MarketingContractError):
    def __init__(self, *, code: str, detail: str, retry_after: int = 30) -> None:
        super().__init__(code=code, detail=detail, retryable=True)
        self.status_code = 503
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class PlatformCommandExecution:
    receipt: MarketingCommandReceipt
    replayed: bool


@dataclass(frozen=True, slots=True)
class VerifiedFlowBinding:
    """Fresh server-owned flow evidence safe to seal in a content artifact."""

    flow_ref: str
    flow_name: str
    version: int
    catalog_hash: str
    catalog_as_of: str

    def artifact_payload(self) -> dict[str, object]:
        return {
            "flow_ref": self.flow_ref,
            "flow_version": self.version,
            "flow_catalog_hash": self.catalog_hash,
        }

    def display_payload(self) -> dict[str, object]:
        # The opaque provider ref is intentionally absent from operator-facing
        # preview metadata.  It remains sealed in the internal artifact.
        return {
            "configured": True,
            "name": self.flow_name,
            "version": self.version,
            "catalog_as_of": self.catalog_as_of,
        }


PlatformAuthorizer = Callable[
    [AuthorizationContext, MarketingCommandReceipt],
    None,
]


def verified_whatsapp_flow_binding(
    *,
    force: bool = False,
    now: datetime | None = None,
) -> VerifiedFlowBinding:
    """Return an active flow proven by a fresh catalog, otherwise fail closed."""

    template = (
        NotificationTemplate.objects.filter(event=EVENT)
        .only("whatsapp_flow_ns", "is_active", "version")
        .first()
    )
    if template is None or not (template.whatsapp_flow_ns or "").strip():
        raise MarketingContractError(
            code="whatsapp_flow_not_selected",
            detail=(
                "O WhatsApp ainda não tem um flow aprovado. Escolha-o em "
                "Marketing → Plataformas antes de revisar este envio."
            ),
            field_errors={
                "platforms.whatsapp": (
                    "Escolha um flow aprovado e ativo em Marketing → Plataformas.",
                )
            },
        )
    if not template.is_active:
        raise MarketingContractError(
            code="whatsapp_template_inactive",
            detail=(
                "A configuração do WhatsApp está inativa. Escolha novamente um "
                "flow em Marketing → Plataformas."
            ),
            field_errors={
                "platforms.whatsapp": (
                    "Reative a configuração escolhendo um flow aprovado.",
                )
            },
        )

    catalog = manychat_flows.flow_catalog(force=force, now=now)
    if not catalog.mutation_safe:
        raise MarketingPlatformUnavailable(
            code="whatsapp_flow_verification_unavailable",
            detail=(
                "Não foi possível confirmar o flow ativo agora. O conteúdo não foi "
                "aprovado; tente a verificação em Marketing → Plataformas."
            ),
        )
    flow_ref = template.whatsapp_flow_ns.strip()
    names = dict(catalog.flows)
    if flow_ref not in names:
        raise MarketingContractError(
            code="whatsapp_flow_not_active",
            detail=(
                "O flow configurado não aparece na lista ativa. Escolha um flow "
                "atual em Marketing → Plataformas."
            ),
            field_errors={
                "platforms.whatsapp": (
                    "Escolha um flow que esteja ativo na lista atual.",
                )
            },
        )
    return VerifiedFlowBinding(
        flow_ref=flow_ref,
        flow_name=names[flow_ref],
        version=template.version,
        catalog_hash=catalog.catalog_hash,
        catalog_as_of=(
            catalog.facts_as_of.isoformat() if catalog.facts_as_of else ""
        ),
    )


def configure_whatsapp_flow(
    *,
    actor,
    flow_ns: str,
    base_version: int,
    idempotency_key: str,
    authorize: PlatformAuthorizer,
    request_id: str = "",
) -> PlatformCommandExecution:
    """Apply one exact flow choice; provider uncertainty always fails closed."""

    safe_flow = str(flow_ns or "").strip()
    if safe_flow and not _FLOW_REF_RE.fullmatch(safe_flow):
        raise MarketingCommandRejected(
            code="invalid_flow_ref",
            detail="A referência do flow é inválida.",
            field_errors={"flow_ns": ("Escolha um flow da lista atual.",)},
        )
    safe_request_id = str(request_id or "")
    if safe_request_id and not _REQUEST_ID_RE.fullmatch(safe_request_id):
        raise MarketingCommandRejected(
            code="invalid_request_id",
            detail="Identificador da requisição inválido.",
        )
    if not getattr(actor, "pk", None):
        raise MarketingCommandRejected(
            code="invalid_actor",
            detail="O comando exige uma pessoa autenticada.",
        )

    payload = {"flow_ref": safe_flow}
    key_hash, payload_hash = command_fingerprints(
        kind=MarketingCommandReceipt.Kind.CONFIGURE_PLATFORM,
        resource_ref=RESOURCE_REF,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload=payload,
    )

    existing = MarketingCommandReceipt.objects.filter(
        actor_id=actor.pk,
        idempotency_key_hash=key_hash,
    ).first()
    if existing is not None:
        return _replay_or_raise(existing, payload_hash=payload_hash)

    # Force a live read for every new intent and again for the confirmed submit.
    # Cached/last-known flows remain diagnostic only and cannot authorize a write.
    catalog = manychat_flows.flow_catalog(force=True)
    if not catalog.mutation_safe:
        raise MarketingPlatformUnavailable(
            code="platform_catalog_unavailable",
            detail=(
                "Não foi possível confirmar a lista ativa agora. Nada foi alterado; "
                "tente a verificação novamente."
            ),
        )
    if safe_flow and not catalog.contains(safe_flow):
        raise MarketingCommandRejected(
            code="flow_not_active",
            detail="O flow escolhido não está na lista ativa atual.",
            field_errors={"flow_ns": ("Escolha um flow da lista atual.",)},
        )

    deferred_error: MarketingCommandConflict | MarketingCommandRejected | None = None
    execution: PlatformCommandExecution | None = None
    with transaction.atomic():
        try:
            actor_row = get_user_model().objects.select_for_update().get(
                pk=actor.pk,
                is_active=True,
            )
        except get_user_model().DoesNotExist as exc:
            raise MarketingCommandRejected(
                code="invalid_actor",
                detail="A sessão não representa uma pessoa ativa.",
            ) from exc

        repeated = MarketingCommandReceipt.objects.filter(
            actor=actor_row,
            idempotency_key_hash=key_hash,
        ).first()
        if repeated is not None:
            execution = _replay_or_raise(repeated, payload_hash=payload_hash)
        else:
            # One existing singleton row serializes first-create races across actors.
            safety_state(for_update=True)
            template = (
                NotificationTemplate.objects.select_for_update()
                .filter(event=EVENT)
                .first()
            )
            current_version = template.version if template is not None else 1
            now = timezone.now()
            common = {
                "kind": MarketingCommandReceipt.Kind.CONFIGURE_PLATFORM,
                "actor": actor_row,
                "actor_ref": f"user:{actor_row.pk}",
                "idempotency_key_hash": key_hash,
                "payload_hash": payload_hash,
                "base_version": base_version,
                "resource_ref": RESOURCE_REF,
                "request_id": safe_request_id,
                "retention_until": now + _RETENTION,
            }
            if current_version != base_version:
                receipt = MarketingCommandReceipt.objects.create(
                    **common,
                    state=MarketingCommandReceipt.State.CONFLICT,
                    resulting_version=current_version,
                    outcome={"code": "version_conflict"},
                    completed_at=now,
                )
                deferred_error = MarketingCommandConflict(
                    code="version_conflict",
                    detail="A configuração mudou enquanto você revisava.",
                    receipt_ref=str(receipt.ref),
                    current_version=current_version,
                    field_errors={"base_version": ("Use a versão atual.",)},
                )
                execution = PlatformCommandExecution(receipt=receipt, replayed=False)
            else:
                previous_flow = (
                    (template.whatsapp_flow_ns or "") if template is not None else ""
                )
                if previous_flow == safe_flow and (
                    template is None or template.is_active
                ):
                    receipt = MarketingCommandReceipt.objects.create(
                        **common,
                        state=MarketingCommandReceipt.State.REJECTED,
                        resulting_version=current_version,
                        outcome={"code": "flow_unchanged"},
                        completed_at=now,
                    )
                    deferred_error = MarketingCommandRejected(
                        code="flow_unchanged",
                        detail="Este flow já é a configuração atual.",
                        receipt_ref=str(receipt.ref),
                        current_version=current_version,
                    )
                    execution = PlatformCommandExecution(receipt=receipt, replayed=False)
                else:
                    receipt = MarketingCommandReceipt.objects.create(**common)
                    context = authorization_context(
                        action=ACTION_CONFIGURE_PLATFORM,
                        resource_ref=RESOURCE_REF,
                        base_version=base_version,
                        artifact_hash=catalog.catalog_hash,
                        platforms=("whatsapp",),
                        consequence=(
                            "changes_whatsapp_flow"
                            if safe_flow
                            else "limits_whatsapp_to_24h_window"
                        ),
                    )
                    authorize(context, receipt)
                    resulting_version = current_version + 1
                    if template is None:
                        template = NotificationTemplate.objects.create(
                            event=EVENT,
                            subject="Novidade na padaria",
                            body="{body}\n\n{cta} {action_url}",
                            whatsapp_flow_ns=safe_flow,
                            is_active=True,
                            version=resulting_version,
                        )
                    else:
                        template.whatsapp_flow_ns = safe_flow
                        template.is_active = True
                        template.version = resulting_version
                        template.save(
                            update_fields=["whatsapp_flow_ns", "is_active", "version"]
                        )

                    MarketingPlatformAuditEvent.objects.create(
                        event_type=(
                            MarketingPlatformAuditEvent.EventType.FLOW_CONFIGURED
                            if safe_flow
                            else MarketingPlatformAuditEvent.EventType.FLOW_CLEARED
                        ),
                        command=receipt,
                        platform="whatsapp",
                        actor=actor_row,
                        actor_ref=f"user:{actor_row.pk}",
                        base_version=base_version,
                        resulting_version=resulting_version,
                        previous_flow_ref=previous_flow,
                        resulting_flow_ref=safe_flow,
                        catalog_hash=catalog.catalog_hash,
                        catalog_as_of=catalog.facts_as_of,
                        request_id=safe_request_id,
                        occurred_at=now,
                        retention_until=now + _RETENTION,
                    )
                    receipt.state = MarketingCommandReceipt.State.COMPLETED
                    receipt.resulting_version = resulting_version
                    receipt.outcome = {
                        "platform": "whatsapp",
                        "configured": bool(safe_flow),
                        "catalog_hash": catalog.catalog_hash,
                    }
                    receipt.completed_at = now
                    receipt.save(
                        update_fields=[
                            "state",
                            "resulting_version",
                            "outcome",
                            "completed_at",
                        ]
                    )
                    execution = PlatformCommandExecution(receipt=receipt, replayed=False)

    if deferred_error is not None:
        raise deferred_error
    assert execution is not None
    return execution


def _replay_or_raise(
    receipt: MarketingCommandReceipt,
    *,
    payload_hash: str,
) -> PlatformCommandExecution:
    if receipt.payload_hash != payload_hash:
        raise MarketingCommandConflict(
            code="idempotency_conflict",
            detail="Esta chave de idempotência já pertence a outro comando.",
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
            field_errors={
                "idempotency_key": ("Gere uma nova chave para a nova intenção.",),
            },
        )
    code = str((receipt.outcome or {}).get("code") or receipt.state)
    if receipt.state == MarketingCommandReceipt.State.CONFLICT:
        raise MarketingCommandConflict(
            code=code,
            detail="A configuração continua em conflito com a versão revisada.",
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
        )
    if receipt.state == MarketingCommandReceipt.State.REJECTED:
        raise MarketingCommandRejected(
            code=code,
            detail="O comando continua recusado pelo estado atual.",
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
        )
    return PlatformCommandExecution(receipt=receipt, replayed=True)
