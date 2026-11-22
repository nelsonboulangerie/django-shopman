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

Os compromissos (``commitments``) são a peça 3b: o livro guarda campos que o contrato não
leva (o ticket da equipe, se já avisou, se já subiu), e por isso precisam de um registro
próprio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conversational_commerce.contracts import ActionCommand, ActionReceipt, ExposureEvent, MemoryItem
from conversational_commerce.ledger.decisions import LedgerError
from conversational_commerce.ledger.exposures import ExposureLedger
from conversational_commerce.ledger.receipts import ReceiptLedger
from conversational_commerce.memory.store import MemoryStore
from conversational_commerce.ports import TrustedContext

from shopman.shop.models import ConversationalRecord

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


__all__ = ["DurableExposureLedger", "exposure_ledger", "memory_store", "receipt_ledger"]
