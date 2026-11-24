"""A nota autorizada de um pedido de teste, gravada onde a autoridade mora (D-037, #3428).

Desde o ``FiscalDocument``, a chave em ``Order.data`` é só espelho: os handlers
de emissão e cancelamento leem o documento. Teste que precisa de "pedido com
nota" grava o documento por aqui, pelo mesmo serviço que a emissão usa.
"""

from __future__ import annotations

from shopman.fiscalman import services as fiscal_documents
from shopman.fiscalman.contracts import FiscalDocumentResult


def authorized_note(order, *, access_key: str, authorized_at: str | None = None, protocol: str = "135250000000000"):
    return fiscal_documents.record_authorized(
        order.ref,
        FiscalDocumentResult(
            success=True,
            access_key=access_key,
            protocol_number=protocol,
            authorization_date=authorized_at,
            status="authorized",
        ),
    )
