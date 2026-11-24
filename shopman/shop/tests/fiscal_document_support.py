"""A nota autorizada de um pedido de teste, gravada onde a autoridade mora (D-037, #3428).

Desde o ``FiscalDocument``, a chave em ``Order.data`` é só espelho: os handlers
de emissão e cancelamento leem o documento. Teste que precisa de "pedido com
nota" grava o documento por aqui, pelo mesmo serviço que a emissão usa.
"""

from __future__ import annotations

import hashlib

from shopman.fiscalman import services as fiscal_documents
from shopman.fiscalman.contracts import FiscalDocumentResult


def access_key_for(reference: str) -> str:
    """Uma chave de acesso de 44 dígitos, a mesma para a mesma referência.

    O documento só aceita chave de verdade (44 dígitos), e é única: provedor
    falso que devolve uma constante bateria na unicidade no segundo pedido.
    """
    digest = int(hashlib.sha256(reference.encode()).hexdigest(), 16)
    return "4126" + str(digest)[:40].rjust(40, "0")


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
