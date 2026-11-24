"""O espelho da nota em ``Order.data``: derivado do ``FiscalDocument``, com um escritor só.

A autoridade da nota é o ``fiscalman.FiscalDocument`` (D-037, #3428). As chaves
``nfce_*`` abaixo existem para os leitores que ainda as usam, e saem daqui,
sempre a partir do documento e dentro da transação que gravou o documento.
Nenhum outro módulo grava essas chaves: a trava é
``shop/tests/test_documento_fiscal_espelho.py``. A troca dos leitores para o
documento e o fim do espelho têm issue própria, com prazo antes da tag
``go-live-v1`` (antes do go-live não há legado).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

#: As chaves do espelho. ``nfce_email_sent_at`` e ``nfce_return_notes`` não são da
#: nota (são do envio e da pendência de estorno) e ficam fora.
MIRROR_KEYS = (
    "nfce_access_key",
    "nfce_authorized_at",
    "nfce_number",
    "nfce_series",
    "nfce_protocol",
    "nfce_xml_url",
    "nfce_danfe_url",
    "nfce_qrcode_url",
    "nfce_status",
    "nfce_cancelled",
    "nfce_cancellation_protocol",
)


def mirror_values(document) -> dict:
    """O que o espelho diz, a partir do documento. Função pura: é o que os testes comparam."""
    values = {
        "nfce_access_key": document.access_key,
        # O relógio do cancelamento conta da AUTORIZAÇÃO DE USO (RICMS/PR, Anexo
        # III, Subanexo I, art. 35). Vazio quando o provedor não disse (ou disse
        # algo ilegível): vazio tem caminho próprio ("não deu para medir o prazo").
        # No fuso da loja: o mesmo instante sai com o mesmo texto, venha do objeto
        # recém-gravado (com o fuso do provedor) ou relido do banco (em UTC).
        "nfce_authorized_at": timezone.localtime(document.authorized_at).isoformat() if document.authorized_at else "",
        "nfce_number": document.number,
        "nfce_series": document.series,
        "nfce_protocol": document.protocol_number,
        "nfce_xml_url": document.xml_url,
        "nfce_danfe_url": document.danfe_url,
        "nfce_qrcode_url": document.qrcode_url,
        "nfce_status": document.status,
    }
    if document.status == document.Status.CANCELLED:
        values["nfce_cancelled"] = True
        values["nfce_cancellation_protocol"] = document.cancellation_protocol
    return values


def write(order, document) -> dict:
    """Grava o espelho do documento no pedido, relendo a linha SOB LOCK.

    ``order.data`` é um JSON com muitos donos (pagamento, PDV, lifecycle):
    gravar o dicionário lido antes é last-write-wins sobre o que os outros
    escreveram no meio. Relê ``select_for_update`` e escreve a partir do valor
    fresco. Chamado dentro da transação que gravou o documento; o ``atomic``
    daqui só vira savepoint. Devolve o ``data`` gravado e o põe no ``order``.
    """
    from shopman.orderman.models import Order

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        data = dict(locked.data or {})
        data.update(mirror_values(document))
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])
    order.data = data
    return data


__all__ = ["MIRROR_KEYS", "mirror_values", "write"]
