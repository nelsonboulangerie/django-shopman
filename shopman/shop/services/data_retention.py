"""Plano R01–R15 observável, sem descarte e sem ativação de jobs.

Este módulo materializa somente a primeira etapa aprovada do gate L7: um único
dry-run, com contagens por regra e nenhuma PII na saída. Aplicação destrutiva e
agendamento produtivo continuam propositalmente ausentes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.utils import timezone

from shopman.shop.adapters.data_retention import external_retention_counts
from shopman.shop.models import (
    CatalogSnapshot,
    ConversationMessage,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingSecurityEvent,
    OutboundAttempt,
    PrivacyRequestReceipt,
)


@dataclass(frozen=True)
class RetentionDryRunRow:
    rule: str
    candidates: int
    status: str
    counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _row(
    rule: str,
    *,
    status: str,
    candidates: int | None = None,
    **counts: int,
) -> RetentionDryRunRow:
    normalized = {key: int(value) for key, value in sorted(counts.items())}
    return RetentionDryRunRow(
        rule=rule,
        candidates=sum(normalized.values()) if candidates is None else int(candidates),
        status=status,
        counts=normalized,
    )


def build_retention_dry_run(
    *, now: datetime | None = None
) -> tuple[RetentionDryRunRow, ...]:
    """Conte candidatos conservadores sem alterar nem revelar registros."""

    clock = now or timezone.now()
    external = external_retention_counts(now=clock)
    one_hundred_eighty_days_ago = clock - timedelta(days=180)

    unsettled_states = (
        DeliveryTarget.State.PLANNED,
        DeliveryTarget.State.QUEUED,
        DeliveryTarget.State.SENDING,
        DeliveryTarget.State.ACCEPTED,
        DeliveryTarget.State.FAILED_RETRYABLE,
        DeliveryTarget.State.UNKNOWN,
    )
    expired_identity_links = (
        DeliveryTarget.objects.filter(
            member__isnull=False,
            identity_retention_until__lte=clock,
        )
        .exclude(state__in=unsettled_states)
        .count()
    )

    provider_refs = (
        DeliveryTarget.objects.filter(provider_ref_retention_until__lte=clock)
        .exclude(state__in=unsettled_states)
        .exclude(provider_receipt_ref="")
        .count()
    )
    attempt_refs = (
        DeliveryAttempt.objects.filter(
            state=DeliveryAttempt.State.COMPLETED,
            completed_at__lte=one_hundred_eighty_days_ago,
        )
        .exclude(target__state__in=unsettled_states)
        .exclude(provider_receipt_ref="")
        .count()
    )
    reconciliation_refs = (
        DeliveryReconciliation.objects.filter(
            state=DeliveryReconciliation.State.COMPLETED,
            completed_at__lte=one_hundred_eighty_days_ago,
        )
        .exclude(target__state__in=unsettled_states)
        .exclude(provider_receipt_ref="")
        .count()
    )
    concierge_refs = (
        OutboundAttempt.objects.filter(
            state__in=(
                OutboundAttempt.State.NOT_APPLIED,
                OutboundAttempt.State.DELIVERED,
                OutboundAttempt.State.READ,
            ),
            completed_at__lte=one_hundred_eighty_days_ago,
        )
        .exclude(provider_receipt_ref="")
        .count()
    )

    # 0056 já deu às observações passivas prazo e rotina próprios. O dry-run
    # conta exatamente o mesmo conjunto da rotina preexistente, sem chamá-la.
    # Conversas legadas continuam sem ``closed_at`` canônico; ``updated_at``
    # não pode ser inventado como marco de retenção.
    expired_passive_observations = ConversationMessage.objects.filter(
        automation_eligible=False,
        envelope__processing_mode="observe",
        retention_until__isnull=False,
        retention_until__lte=clock,
    ).count()

    incident_records = MarketingSecurityEvent.objects.filter(
        retention_until__lte=clock,
    ).count()
    expired_privacy_receipts = PrivacyRequestReceipt.objects.filter(
        retention_until__lte=clock,
    ).count()
    # 0055 guarda payload remoto bruto e imutável. R12 o inventaria somente por
    # contagem; o dry-run jamais carrega ``raw_json`` para memória ou saída.
    catalog_snapshots_with_raw_payload = CatalogSnapshot.objects.count()
    archive_root = (
        Path(__file__).resolve().parents[3]
        / "surfaces"
        / "storefront-nuxt"
        / "public"
        / "documentos-legais"
    )
    archived_legal_versions = sum(
        1 for path in archive_root.glob("*/*.html") if path.is_file()
    )

    rows = (
        _row("R01", status="revisao_legal_obrigatoria", **external["R01"]),
        _row("R02", status="legal_hold_obrigatorio", registros_vencidos=incident_records),
        _row(
            "R03",
            status="inventario_sem_marco_de_descarte_aprovado",
            candidates=0,
            **external["R03"],
        ),
        _row(
            "R04",
            status="inventario_aguardando_marco_de_remocao_do_contato",
            candidates=0,
            **external["R04"],
        ),
        _row(
            "R05",
            status="inventario_aguardando_marco_temporal_canonico",
            candidates=0,
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
            status="expurgo_passivo_0056_existente;_fechamento_canonico_pendente",
            observacoes_passivas_vencidas_0056=expired_passive_observations,
        ),
        _row(
            "R09",
            status="inventario_sem_descarte;_recibos_exigem_revisao_e_legal_hold",
            candidates=0,
            recibos_de_privacidade_elegiveis_para_revisao=expired_privacy_receipts,
            **external["R09"],
        ),
        _row("R10", status="comando_existente_sem_job_comprovado", **external["R10"]),
        _row("R11", status="somente_leitura;_nenhum_job_novo", **external["R11"]),
        _row(
            "R12",
            status="inventario_0055_sem_prazo_de_descarte_aprovado",
            candidates=0,
            snapshots_de_catalogo_brutos_sem_classificacao=(
                catalog_snapshots_with_raw_payload
            ),
        ),
        _row(
            "R13",
            status="inventario_sem_marco_de_exclusao_ou_fim_da_finalidade",
            candidates=0,
            **external["R13"],
        ),
        _row(
            "R14",
            status="arquivo_permanente",
            candidates=0,
            versoes_arquivadas=archived_legal_versions,
        ),
        _row("R15", status="evidencia_externa_obrigatoria", backups_aferidos=0),
    )
    expected_rules = tuple(f"R{index:02d}" for index in range(1, 16))
    if tuple(row.rule for row in rows) != expected_rules:
        raise RuntimeError("A saída de retenção deve cobrir R01–R15 exatamente uma vez.")
    return rows
