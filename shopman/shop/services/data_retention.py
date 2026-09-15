"""Plano de retenção R01–R15, inicialmente observável e sem descarte.

Este módulo materializa a primeira etapa aprovada do gate L7: um único dry-run,
com contagens por regra e nenhuma PII na saída. A aplicação destrutiva e o
agendamento produtivo continuam propositalmente ausentes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from shopman.shop.adapters.data_retention import external_retention_counts
from shopman.shop.models import (
    Conversation,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingSecurityEvent,
    OutboundAttempt,
)


@dataclass(frozen=True)
class RetentionDryRunRow:
    rule: str
    candidates: int
    status: str
    counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _row(rule: str, *, status: str, **counts: int) -> RetentionDryRunRow:
    normalized = {key: int(value) for key, value in sorted(counts.items())}
    return RetentionDryRunRow(
        rule=rule,
        candidates=sum(normalized.values()),
        status=status,
        counts=normalized,
    )


def build_retention_dry_run(*, now: datetime | None = None) -> tuple[RetentionDryRunRow, ...]:
    """Conta candidatos conservadores sem alterar ou revelar registros."""

    clock = now or timezone.now()
    external = external_retention_counts(now=clock)
    ninety_days_ago = clock - timedelta(days=90)
    one_hundred_eighty_days_ago = clock - timedelta(days=180)
    thirty_days_ago = clock - timedelta(days=30)

    unsettled_states = (
        DeliveryTarget.State.PLANNED,
        DeliveryTarget.State.QUEUED,
        DeliveryTarget.State.SENDING,
        DeliveryTarget.State.ACCEPTED,
        DeliveryTarget.State.FAILED_RETRYABLE,
        DeliveryTarget.State.UNKNOWN,
    )
    expired_identity_links = DeliveryTarget.objects.filter(
        member__isnull=False,
        identity_retention_until__lte=clock,
    ).exclude(state__in=unsettled_states).count()

    provider_refs = DeliveryTarget.objects.filter(
        provider_ref_retention_until__lte=clock,
    ).exclude(
        state__in=unsettled_states,
    ).exclude(provider_receipt_ref="").count()
    attempt_refs = DeliveryAttempt.objects.filter(
        state=DeliveryAttempt.State.COMPLETED,
        completed_at__lte=one_hundred_eighty_days_ago,
    ).exclude(
        target__state__in=unsettled_states,
    ).exclude(provider_receipt_ref="").count()
    reconciliation_refs = DeliveryReconciliation.objects.filter(
        state=DeliveryReconciliation.State.COMPLETED,
        completed_at__lte=one_hundred_eighty_days_ago,
    ).exclude(provider_receipt_ref="").count()
    concierge_refs = OutboundAttempt.objects.filter(
        state__in=(
            OutboundAttempt.State.ACCEPTED,
            OutboundAttempt.State.NOT_APPLIED,
            OutboundAttempt.State.DELIVERED,
            OutboundAttempt.State.READ,
        ),
        completed_at__lte=one_hundred_eighty_days_ago,
    ).exclude(provider_receipt_ref="").count()

    closed_conversations = Conversation.objects.filter(
        state=Conversation.State.CLOSED,
        updated_at__lte=ninety_days_ago,
    ).count()
    inactive_open_conversations = Conversation.objects.filter(
        state=Conversation.State.ACTIVE,
        updated_at__lte=thirty_days_ago,
    ).filter(
        Q(last_inbound_at__isnull=True) | Q(last_inbound_at__lte=thirty_days_ago),
        Q(last_outbound_at__isnull=True) | Q(last_outbound_at__lte=thirty_days_ago),
    ).count()

    incident_records = MarketingSecurityEvent.objects.filter(
        retention_until__lte=clock,
    ).count()
    archive_root = Path(__file__).resolve().parents[3] / "surfaces" / "storefront-nuxt" / "public" / "documentos-legais"
    archived_legal_versions = sum(1 for path in archive_root.glob("*/*.html") if path.is_file())

    rows = (
        _row("R01", status="revisao_legal_obrigatoria", **external["R01"]),
        _row("R02", status="legal_hold_obrigatorio", registros_vencidos=incident_records),
        _row("R03", status="prova_minima_revisao_obrigatoria", **external["R03"]),
        _row("R04", status="tombstone_revisao_obrigatoria", **external["R04"]),
        _row(
            "R05",
            status="marco_temporal_e_contracao_a_implementar",
            vinculos_pessoais=expired_identity_links,
        ),
        _row(
            "R06",
            status="contracao_a_implementar",
            recibos_de_destino=provider_refs,
            recibos_de_tentativa=attempt_refs,
            recibos_de_reconciliacao=reconciliation_refs,
            recibos_do_concierge=concierge_refs,
            **external["R06"],
        ),
        _row("R07", status="contracao_a_implementar", **external["R07"]),
        _row(
            "R08",
            status="fechamento_e_expurgo_a_implementar",
            conversas_encerradas=closed_conversations,
            conversas_a_encerrar=inactive_open_conversations,
        ),
        _row("R09", status="fluxo_existente_a_auditar", **external["R09"]),
        _row("R10", status="comando_existente_sem_job_comprovado", **external["R10"]),
        _row("R11", status="comando_existente_no_worker", **external["R11"]),
        _row("R12", status="inventario_pendente", modelos_inventariados=0),
        _row("R13", status="fluxo_existente_a_auditar", **external["R13"]),
        _row("R14", status="arquivo_permanente", versoes_arquivadas=archived_legal_versions),
        _row("R15", status="evidencia_externa_obrigatoria", backups_aferidos=0),
    )
    if tuple(row.rule for row in rows) != tuple(f"R{index:02d}" for index in range(1, 16)):
        raise RuntimeError("A saída de retenção deve cobrir R01–R15 exatamente uma vez.")
    return rows
