"""Os livros do motor que sobrevivem ao turno: recibos, memória e exposições (#3198, peça 3a).

O ``Engine`` do framework recebe quatro livros em memória (``ledger``, ``commitments``,
``memory``, ``exposures``). No Shopman ele é montado de novo a cada turno (N9), então o que
ficasse só na memória se perderia entre um turno e o seguinte. Aqui moram as versões
duráveis, do lado do adaptador; o ``packages/`` não muda.

- **Recibos** (``receipt_ledger``): reconstruídos do que o armazenamento já grava. O comando
  entra como ``cc.action_command`` na transição do turno, e cada recibo entra como
  ``cc.action_receipt`` pelo ``append_receipt``. A ordem é a de gravação, e o primeiro comando
  de uma chave de idempotência vence, como no livro em memória. Monte o livro DEPOIS de
  carregar o episódio: um livro que não viu o último recibo manda executar de novo com a
  mesma chave, e quem segura a repetição é o executor.
- **Memória** (``memory_store``): reconstruída dos ``cc.memory_item`` do sujeito, que a
  transição do turno já grava. O que entrou passou pelas regras de ``declare`` quando foi
  dito; a reconstrução só devolve a história, sem conferir de novo.
- **Exposições** (``DurableExposureLedger``): o livro em memória nunca era gravado. Agora cada
  registro também vira um ``cc.exposure_event``, e o mesmo registro duas vezes não duplica.
  É o que mede o que o cliente leu (decisão de 22/11/2026: o motor fala, e o registro nunca
  afirma o que não aconteceu).

- **Compromissos** (``DurableCommitmentLedger``, ``commitment_ledger``): o livro guarda o que o
  contrato ``cc.commitment`` não leva (o movimento e a necessidade de origem, o vínculo, quem
  recebe, o ticket da equipe, se o cliente já foi avisado, se já subiu, os prazos tratados e
  os eventos). Cada mudança do livro (``open``, ``advance``, ``note``, ``due``) grava a linha do
  compromisso em ``ConversationalCommitment``. O motor marca ``notified`` e ``escalated`` direto
  na entrada e chama ``note`` logo depois; é o ``note`` que grava. Só entra o que passou pelo
  ``open``: o compromisso de reconciliação (``reconcile.<comando>``), que o motor grava como
  registro mas nunca abre no livro, não aparece aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conversational_commerce.contracts import (
    ActionCommand,
    ActionReceipt,
    ChannelBinding,
    Commitment,
    ExposureEvent,
    MemoryItem,
)
from conversational_commerce.engine.state import NeedSpec
from conversational_commerce.ledger.commitments import CommitmentEvent, CommitmentLedger, Entry
from conversational_commerce.ledger.decisions import LedgerError
from conversational_commerce.ledger.exposures import ExposureLedger
from conversational_commerce.ledger.receipts import ReceiptLedger
from conversational_commerce.memory.store import MemoryStore
from conversational_commerce.ports import TrustedContext

from shopman.shop.models import ConversationalCommitment, ConversationalRecord

from .store import _scope


def receipt_ledger(ctx: TrustedContext, *, episode_id: str | None = None) -> ReceiptLedger:
    """Os comandos e recibos gravados no inquilino e ambiente do contexto (do episódio, se dado)."""
    ledger = ReceiptLedger()
    rows = ConversationalRecord.objects.filter(**_scope(ctx), schema__in=(ActionCommand.SCHEMA, ActionReceipt.SCHEMA))
    if episode_id is not None:
        rows = rows.filter(episode_id=episode_id)
    for schema, document in rows.order_by("pk").values_list("schema", "document"):
        if schema == ActionCommand.SCHEMA:
            try:
                ledger.register(ActionCommand.from_document(document))
            except LedgerError:
                continue  # mesma chave, outro conteúdo: o primeiro gravado vale
        else:
            receipt = ActionReceipt.from_document(document)
            if receipt.command_id in ledger.commands and receipt.id not in {r.id for r in ledger.history(receipt.command_id)}:
                ledger.append(receipt)
    return ledger


def memory_store(ctx: TrustedContext, subject_ref: str) -> MemoryStore:
    """A memória declarada do sujeito, na ordem em que foi dita."""
    documents = (ConversationalRecord.objects.filter(**_scope(ctx), schema=MemoryItem.SCHEMA,
                                                     document__subject_ref=subject_ref)
                 .order_by("pk").values_list("document", flat=True))
    return MemoryStore(history=[MemoryItem.from_document(document) for document in documents])


@dataclass
class DurableExposureLedger(ExposureLedger):
    """O livro das exposições que também grava cada registro (``cc.exposure_event``)."""

    ctx: TrustedContext | None = None
    history: list[ExposureEvent] = field(default_factory=list)

    def record(self, exposure: ExposureEvent) -> ExposureEvent:
        recorded = super().record(exposure)
        if self.ctx is not None and not ConversationalRecord.objects.filter(
                **_scope(self.ctx), record_id=exposure.id).exists():
            ConversationalRecord.objects.create(**_scope(self.ctx), episode_id=exposure.episode_id or "",
                                                schema=exposure.SCHEMA, record_id=exposure.id,
                                                document=exposure.to_document())
        return recorded


def exposure_ledger(ctx: TrustedContext, *, episode_id: str | None = None) -> DurableExposureLedger:
    """As exposições gravadas (do episódio, se dado), num livro que continua gravando."""
    rows = ConversationalRecord.objects.filter(**_scope(ctx), schema=ExposureEvent.SCHEMA)
    if episode_id is not None:
        rows = rows.filter(episode_id=episode_id)
    history = [ExposureEvent.from_document(document) for document in rows.order_by("pk").values_list("document", flat=True)]
    return DurableExposureLedger(ctx=ctx, history=history)


def _need_document(need: NeedSpec) -> dict:
    return {"need_id": need.need_id, "act": need.act, "readings": [dict(r) for r in need.readings],
            "answers_question": need.answers_question}


def _need_of(document: dict) -> NeedSpec:
    return NeedSpec(need_id=document["need_id"], act=document["act"],
                    readings=tuple(document.get("readings") or ({},)),
                    answers_question=document.get("answers_question"))


@dataclass
class DurableCommitmentLedger(CommitmentLedger):
    """O livro dos compromissos que grava cada mudança da entrada (``ConversationalCommitment``)."""

    ctx: TrustedContext | None = None

    def open(self, commitment: Commitment, **entry) -> Entry:
        opened = super().open(commitment, **entry)
        self._save(opened)
        return opened

    def advance(self, commitment_id: str, **kwargs) -> Commitment:
        updated = super().advance(commitment_id, **kwargs)
        self._save(self.entries[commitment_id])
        return updated

    def note(self, kind, commitment_id: str, at: str, ref: str | None = None) -> None:
        super().note(kind, commitment_id, at, ref)
        if commitment_id in self.entries:
            self._save(self.entries[commitment_id])

    def due(self, now: str, tenant: str | None = None, environment: str | None = None) -> list[Entry]:
        found = super().due(now, tenant, environment)
        for entry in found:
            self._save(entry)  # o prazo tratado vale para o próximo turno, que é outro motor
        return found

    def _save(self, entry: Entry) -> None:
        if self.ctx is None:
            return
        cid = entry.commitment_id
        ConversationalCommitment.objects.update_or_create(
            **_scope(self.ctx), commitment_id=cid,
            defaults={
                "episode_id": entry.commitment.episode_id or "",
                "is_open": entry.is_open,
                "commitment": entry.commitment.to_document(),
                "history": [record.to_document() for record in entry.history],
                "entry": {"move": entry.move, "need": _need_document(entry.need),
                          "binding": ({"channel": entry.binding.channel, "conversation_ref": entry.binding.conversation_ref}
                                      if entry.binding is not None else None),
                          "recipient": entry.recipient, "identity": entry.identity, "ticket_id": entry.ticket_id},
                "notified": entry.notified,
                "escalated": entry.escalated,
                "handled": sorted([key[1] for key in self._handled if key[0] == cid]),
                "events": [{"kind": e.kind, "at": e.at, "ref": e.ref} for e in self.events if e.commitment_id == cid],
            },
        )


def commitment_ledger(ctx: TrustedContext) -> DurableCommitmentLedger:
    """Os compromissos abertos do inquilino e ambiente, num livro que continua gravando."""
    ledger = DurableCommitmentLedger(ctx=ctx)
    rows = ConversationalCommitment.objects.filter(**_scope(ctx), is_open=True).order_by("pk")
    for row in rows:
        stored = row.entry or {}
        binding = stored.get("binding")
        entry = Entry(
            Commitment.from_document(row.commitment), move=stored.get("move", ""),
            need=_need_of(stored["need"]), binding=ChannelBinding(**binding) if binding else None,
            recipient=stored.get("recipient", "unknown"), identity=stored.get("identity", "anonymous"),
            ticket_id=stored.get("ticket_id"), history=[Commitment.from_document(d) for d in row.history],
            notified=row.notified, escalated=row.escalated)
        ledger.entries[row.commitment_id] = entry
        ledger.events.extend(CommitmentEvent(e["kind"], row.commitment_id, e["at"], e.get("ref")) for e in row.events)
        ledger._handled.update((row.commitment_id, at) for at in row.handled)
    return ledger


__all__ = [
    "DurableCommitmentLedger",
    "DurableExposureLedger",
    "commitment_ledger",
    "exposure_ledger",
    "memory_store",
    "receipt_ledger",
]
