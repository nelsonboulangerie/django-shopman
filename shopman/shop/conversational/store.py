"""``StorePort`` sobre o PostgreSQL do Shopman: episódio, registros e caixa de saída numa transação (N8).

Garantias da porta (v2 5.4, N13), e como o Shopman as cumpre:

- **comparar e gravar**: ``commit_transition`` trava a linha do episódio
  (``select_for_update``) e confere a versão que quem decidiu viu; versão diferente é
  ``revision_conflict``, e o banco garante que, de dois trabalhadores na mesma versão,
  só um grava (K13, no mecanismo real);
- **estado, registros e trabalho juntos**: o episódio, os registros e os itens da caixa
  de saída entram numa transação só, ou nenhum entra;
- **uma entrada, uma vez** (K01): o evento com identidade estável tem chave única no banco;
- **isolamento por inquilino**: toda leitura e escrita filtra inquilino e ambiente do
  contexto confiável;
- **quem consome aceita repetição**: ``claim_work`` reivindica com ``skip_locked`` e prazo de
  posse; trabalho cujo trabalhador morreu volta quando o prazo vence, com a tentativa somada.

A forma de cada registro é a do contrato do framework (``to_document``/``from_document``),
nunca redefinida aqui.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from conversational_commerce.contracts import REGISTRY, ActionReceipt, Episode, InteractionEvent, Record
from conversational_commerce.ports import Capabilities, Claim, PortError, Transition, TrustedContext, WorkItem
from conversational_commerce.ports.store import OPERATIONS
from django.db import IntegrityError, transaction

from shopman.shop.models import ConversationalEpisode, ConversationalRecord, ConversationalWork

FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def moment(instant: str) -> datetime:
    return datetime.strptime(instant, FORMAT).replace(tzinfo=UTC)


def instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime(FORMAT)


def _scope(ctx: TrustedContext) -> dict[str, str]:
    return {"tenant": ctx.tenant, "environment": ctx.environment}


def _dedupe_key(event: InteractionEvent) -> str | None:
    """A identidade do evento: canal, conversa e o id que o provedor garante. Sem garantia, nada."""
    identity = event.event_identity
    if identity.assurance == "none" or not identity.id:
        return None
    binding = event.channel_binding
    return f"{binding.channel}\x1f{binding.conversation_ref}\x1f{identity.id}"[:512]


class ShopmanStore:
    """A porta de armazenamento do framework sobre as tabelas ``shop.Conversational*``."""

    PORT = "store"

    def __init__(self, clock=None) -> None:
        self.clock = clock

    def _now(self) -> datetime:
        if self.clock is not None:
            return moment(self.clock.now())
        return datetime.now(UTC)

    def capabilities(self) -> Capabilities:
        return Capabilities(port="store", operations=OPERATIONS, guarantees={
            "compare_and_set": True, "atomic_outbox": True, "tenant_isolation": True,
            "claim_skip_locked": True, "mechanism": "postgresql"})

    # ── entrada ──────────────────────────────────────────────────────────────
    def record_event_once(self, ctx: TrustedContext, event: InteractionEvent) -> tuple[InteractionEvent, bool]:
        key = _dedupe_key(event)
        if key is not None:
            existing = ConversationalRecord.objects.filter(**_scope(ctx), dedupe_key=key).first()
            if existing is not None:
                return InteractionEvent.from_document(existing.document), False
        try:
            with transaction.atomic():
                ConversationalRecord.objects.create(
                    **_scope(ctx), episode_id=event.episode_id or "", schema=InteractionEvent.SCHEMA,
                    record_id=event.id, dedupe_key=key, document=event.to_document())
        except IntegrityError:
            # Corrida: outro trabalhador gravou a mesma identidade entre a leitura e a escrita.
            existing = ConversationalRecord.objects.get(**_scope(ctx), dedupe_key=key)
            return InteractionEvent.from_document(existing.document), False
        return event, True

    # ── leitura ──────────────────────────────────────────────────────────────
    def load_episode(self, ctx: TrustedContext, episode_id: str) -> Episode | None:
        row = ConversationalEpisode.objects.filter(**_scope(ctx), episode_id=episode_id).first()
        return Episode.from_document(row.document) if row is not None else None

    def latest_episode(self, ctx: TrustedContext, subject: str) -> Episode | None:
        row = (ConversationalEpisode.objects.filter(**_scope(ctx), subject=subject)
               .order_by("-occurred_at", "-pk").first())
        return Episode.from_document(row.document) if row is not None else None

    def latest_record(self, ctx: TrustedContext, episode_id: str, schema: str) -> Record | None:
        contract = REGISTRY.get(schema)
        if contract is None:
            raise PortError("invalid_content", f"contrato desconhecido: {schema}")
        row = (ConversationalRecord.objects.filter(**_scope(ctx), episode_id=episode_id, schema=schema)
               .order_by("-pk").first())
        return contract.from_document(row.document) if row is not None else None

    # ── a transição ──────────────────────────────────────────────────────────
    def commit_transition(self, ctx: TrustedContext, transition: Transition, records: tuple[Record, ...],
                          outbox: tuple[WorkItem, ...]) -> Episode:
        episode = transition.episode
        if (episode.tenant, episode.environment) != (ctx.tenant, ctx.environment):
            raise PortError("object_forbidden", "episódio de outro inquilino ou ambiente")
        if episode.version != transition.expected_version + 1:
            raise PortError("invalid_content", "a transição incrementa a versão em um")
        with transaction.atomic():
            row = (ConversationalEpisode.objects.select_for_update()
                   .filter(**_scope(ctx), episode_id=episode.episode_id).first())
            current = 0 if row is None else row.version
            if current != transition.expected_version:
                raise PortError("revision_conflict", f"versão {current}, esperada {transition.expected_version}")
            fields = {"subject": episode.subject or "", "state": episode.state, "version": episode.version,
                      "document": episode.to_document(), "occurred_at": moment(episode.occurred_at)}
            if row is None:
                try:
                    with transaction.atomic():
                        ConversationalEpisode.objects.create(**_scope(ctx), episode_id=episode.episode_id, **fields)
                except IntegrityError as conflict:
                    # Dois trabalhadores abrindo o mesmo episódio: um vence, o outro recarrega.
                    raise PortError("revision_conflict", "o episódio já foi aberto por outro trabalhador") from conflict
            else:
                ConversationalEpisode.objects.filter(pk=row.pk).update(**fields)
            ConversationalRecord.objects.bulk_create([
                ConversationalRecord(**_scope(ctx), episode_id=getattr(record, "episode_id", None) or episode.episode_id,
                                     schema=record.SCHEMA, record_id=record.id,
                                     dedupe_key=_dedupe_key(record) if isinstance(record, InteractionEvent) else None,
                                     document=record.to_document())
                for record in records if not self._recorded(ctx, record)
            ])
            ConversationalWork.objects.bulk_create([
                ConversationalWork(**_scope(ctx), work_id=work.work_id, kind=work.kind, payload=dict(work.payload),
                                   due_at=moment(work.due_at))
                for work in outbox
            ], ignore_conflicts=True)
        return episode

    def _recorded(self, ctx: TrustedContext, record: Record) -> bool:
        """O evento gravado antes por ``record_event_once`` não entra de novo na transição."""
        return ConversationalRecord.objects.filter(**_scope(ctx), record_id=record.id).exists()

    # ── caixa de saída ───────────────────────────────────────────────────────
    def claim_work(self, ctx: TrustedContext, kind: str, lease_seconds: int) -> Claim | None:
        now = self._now()
        with transaction.atomic():
            row = (ConversationalWork.objects.select_for_update(skip_locked=True)
                   .filter(**_scope(ctx), kind=kind, due_at__lte=now)
                   .exclude(lease_until__gt=now)
                   .order_by("due_at", "pk").first())
            if row is None:
                return None
            row.attempt += 1
            row.lease_until = now + timedelta(seconds=lease_seconds)
            row.save(update_fields=["attempt", "lease_until"])
        work = WorkItem(work_id=row.work_id, kind=row.kind, payload=row.payload, due_at=instant(row.due_at))
        return Claim(work=work, lease_until=instant(row.lease_until), attempt=row.attempt)

    def complete_work(self, ctx: TrustedContext, work_id: str) -> None:
        ConversationalWork.objects.filter(**_scope(ctx), work_id=work_id).delete()

    def append_receipt(self, ctx: TrustedContext, receipt: ActionReceipt) -> ActionReceipt:
        if not self._recorded(ctx, receipt):
            ConversationalRecord.objects.create(**_scope(ctx), episode_id=receipt.episode_id or "",
                                                schema=receipt.SCHEMA, record_id=receipt.id,
                                                document=receipt.to_document())
        return receipt

    # ── para o relógio ───────────────────────────────────────────────────────
    def schedule(self, ctx: TrustedContext, work: WorkItem) -> str:
        ConversationalWork.objects.get_or_create(**_scope(ctx), work_id=work.work_id, defaults={
            "kind": work.kind, "payload": dict(work.payload), "due_at": moment(work.due_at)})
        return work.work_id

    def cancel(self, ctx: TrustedContext, work_id: str) -> bool:
        """Cancela o agendado que ninguém reivindicou ainda."""
        deleted, _ = (ConversationalWork.objects.filter(**_scope(ctx), work_id=work_id)
                      .filter(lease_until__isnull=True).delete())
        return deleted > 0


def records_of(ctx: TrustedContext, episode_id: str) -> list[dict[str, Any]]:
    """Os documentos gravados no episódio, na ordem (para diagnóstico e testes)."""
    return list(ConversationalRecord.objects.filter(**_scope(ctx), episode_id=episode_id)
                .order_by("pk").values_list("document", flat=True))
