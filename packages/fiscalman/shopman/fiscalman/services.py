"""Escrita do :class:`~shopman.fiscalman.models.FiscalDocument` (D-037, #3428).

Toda gravação do documento passa por aqui. O ciclo de uma emissão:

1. :func:`open_pending`, gravado e confirmado ANTES do pedido ao provedor;
2. o pedido ao provedor, que o chamador faz;
3. :func:`record_authorized` (ou :func:`record_denied`) na MESMA linha.

Se o processo morrer entre 2 e 3, a linha fica ``pending``. Quem retoma
(retry ou reprocesso) vê a linha pendente, consulta o provedor pela mesma
referência e chama :func:`record_authorized`, que completa o documento que já
existe. Uma referência é um documento só.

Invariante: depois de autorizada, a chave de acesso e o protocolo não mudam
mais. O cancelamento grava os seus campos ao lado, e uma segunda autorização
com chave diferente falha gritando (:class:`FiscalDocumentConflict`), porque
significaria duas notas para a mesma referência.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.fiscalman.contracts import FiscalCancellationResult, FiscalDocumentResult
from shopman.fiscalman.models import FiscalDocument

logger = logging.getLogger(__name__)

NFCE = FiscalDocument.Kind.NFCE


class FiscalDocumentConflict(Exception):
    """A referência já tem documento autorizado com outra chave, ou não tem o que cancelar."""


def document_for(reference: str, *, kind: str = NFCE) -> FiscalDocument | None:
    return FiscalDocument.objects.filter(kind=kind, reference=reference).first()


def open_pending(reference: str, *, kind: str = NFCE) -> FiscalDocument:
    """A linha do documento, gravada antes do pedido ao provedor.

    Idempotente: a linha que já existe volta como está. A recusada volta a
    ``pending``, porque o provedor aceita reenviar a referência de nota que não
    foi autorizada. Precisa ser confirmada antes do pedido ao provedor: chamada
    dentro de uma transação externa, ela some junto se o processo morrer.
    """
    with transaction.atomic():
        document, _created = FiscalDocument.objects.select_for_update().get_or_create(
            kind=kind, reference=reference,
        )
        if document.status == FiscalDocument.Status.DENIED:
            document.status = FiscalDocument.Status.PENDING
            document.save(update_fields=["status", "updated_at"])
    return document


def record_authorized(reference: str, result: FiscalDocumentResult, *, kind: str = NFCE) -> FiscalDocument:
    """A nota autorizada, gravada na linha da referência (a mesma do ``open_pending``).

    Serve à emissão e à adoção por consulta. Sem linha (adoção de nota que não
    passou pelo ``open_pending``), a linha nasce aqui. A mesma chave de novo é
    inofensiva e não reescreve nada; chave diferente é
    :class:`FiscalDocumentConflict`.
    """
    access_key = str(result.access_key or "").strip()
    if not access_key:
        raise FiscalDocumentConflict(f"Autorização sem chave de acesso para {reference}.")
    with transaction.atomic():
        document, _created = FiscalDocument.objects.select_for_update().get_or_create(
            kind=kind, reference=reference,
        )
        if document.access_key:
            if document.access_key != access_key:
                raise FiscalDocumentConflict(
                    f"{reference} já tem a nota {document.access_key}; o provedor devolveu {access_key}."
                )
            return document
        document.access_key = access_key
        document.number = result.document_number
        document.series = result.document_series
        document.protocol_number = str(result.protocol_number or "")
        document.authorized_at = _parse_moment(result.authorization_date, reference)
        document.xml_url = str(result.xml_url or "")
        document.danfe_url = str(result.danfe_url or "")
        document.qrcode_url = str(result.qrcode_url or "")
        document.status = FiscalDocument.Status.AUTHORIZED
        document.save()
    return document


def record_denied(reference: str, *, kind: str = NFCE) -> FiscalDocument | None:
    """O provedor respondeu que não há nota autorizada: a linha pendente vira recusada.

    Nunca rebaixa documento autorizado ou cancelado.
    """
    with transaction.atomic():
        document = FiscalDocument.objects.select_for_update().filter(kind=kind, reference=reference).first()
        if document is None or document.status != FiscalDocument.Status.PENDING:
            return document
        document.status = FiscalDocument.Status.DENIED
        document.save(update_fields=["status", "updated_at"])
    return document


def record_cancelled(reference: str, result: FiscalCancellationResult, *, kind: str = NFCE) -> FiscalDocument:
    """O cancelamento, gravado ao lado da autorização, que fica intacta.

    Chave de acesso e protocolo de autorização não são tocados: o documento
    cancelado continua dizendo qual nota foi cancelada. Idempotente.
    """
    with transaction.atomic():
        document = FiscalDocument.objects.select_for_update().filter(kind=kind, reference=reference).first()
        if document is None or not document.access_key:
            raise FiscalDocumentConflict(f"{reference} não tem nota autorizada para cancelar.")
        if document.status == FiscalDocument.Status.CANCELLED:
            return document
        document.status = FiscalDocument.Status.CANCELLED
        document.cancellation_protocol = str(result.protocol_number or "")
        document.cancelled_at = _parse_moment(result.cancellation_date, reference) or timezone.now()
        document.save(update_fields=["status", "cancellation_protocol", "cancelled_at", "updated_at"])
    return document


def _parse_moment(raw, reference: str):
    if not raw or not isinstance(raw, str):
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        logger.warning("fiscalman.document: data ilegível %r em %s", raw, reference)
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


__all__ = [
    "FiscalDocumentConflict",
    "document_for",
    "open_pending",
    "record_authorized",
    "record_cancelled",
    "record_denied",
]
