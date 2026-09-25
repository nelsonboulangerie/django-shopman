"""A DANFE da NFC-e que viaja com a sacola do pedido de entrega.

Decisão do dono (25/09/2026): pedido de ENTREGA sai com a DANFE NFC-e
impressa, dentro da sacola. O papel é o MESMO do balcão — composto por
``receipt_escpos.danfe_nfce`` a partir de ``fiscal_danfe.build_danfe`` — e o
carimbo também é o mesmo (``danfe_printed_at``): a segunda composição sai como
REIMPRESSÃO, seja qual for a tela que pediu.

## O tempo é o problema, e ele não pode virar portão

Na entrega a NFC-e nasce NO DESPACHO, e a autorização da SEFAZ chega segundos
depois. Regra dura do dono: **expedição sem NFC-e só AVISA, nunca segura a
sacola**. Então este módulo não pergunta "pode despachar?" — ele só responde,
para cada pedido, se a DANFE ainda deve sair SOZINHA (:func:`danfe_state`).

O mesmo critério cobre as duas ordens possíveis:

- **autorizada antes do despacho** → o gesto de despachar recarrega o quadro, o
  pedido aparece como ``dispatched`` e a DANFE sai na hora;
- **autorizada depois** → o handler fiscal empurra o quadro por SSE, e a DANFE
  sai quando a autorização chega.

Em ambos quem imprime é a estação do Gestor que tem agente de impressão
(``DeviceAgentConfig``, o mesmo do PDV). Se duas estações estão abertas, só
uma leva: :func:`claim_print` grava o carimbo sob lock, e a automática recusa
quem chegou depois.

## A janela da impressão automática

Depois de :data:`AUTO_PRINT_WINDOW` do despacho a sacola já foi embora, e um
Gestor aberto mais tarde não deve cuspir DANFE de pedido na rua. Fora da
janela a DANFE continua no card, para reimprimir à mão.

## O que fica de fora

- **Retirada**: a DANFE fica disponível no card (o cliente pode pedir no
  balcão), mas não sai sozinha.
- **iFood**: a sacola do iFood segue a regra do iFood; nada aqui a toca.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

#: A chave do carimbo em ``Order.data`` — a mesma do PDV (data-schemas.md).
PRINT_STAMP_KEY = "danfe_printed_at"

#: Até quando, depois do despacho, a DANFE ainda sai sozinha.
AUTO_PRINT_WINDOW = timedelta(minutes=10)


@dataclass(frozen=True)
class DanfeState:
    """O que o card do Gestor sabe da DANFE de um pedido."""

    #: Há nota autorizada e este pedido pode ter a DANFE impressa pelo Gestor.
    printable: bool = False
    #: A DANFE já saiu uma vez (a próxima é REIMPRESSÃO).
    printed: bool = False
    #: A estação com impressora deve imprimir agora, sem ninguém pedir.
    auto_print: bool = False


def _is_ifood(order) -> bool:
    from shopman.shop.services.ifood_ingest import IFOOD_CHANNEL_REF

    return (getattr(order, "channel_ref", "") or "") == IFOOD_CHANNEL_REF


def _is_delivery(order) -> bool:
    from shopman.shop.services.order_helpers import get_fulfillment_type

    return get_fulfillment_type(order) == "delivery"


def danfe_state(order, *, now=None) -> DanfeState:
    """A DANFE deste pedido: existe? já saiu? deve sair sozinha agora?"""
    from shopman.orderman.models import Order

    data = getattr(order, "data", None) or {}
    if _is_ifood(order) or not data.get("nfce_access_key") or data.get("nfce_cancelled"):
        return DanfeState()
    printed = bool(data.get(PRINT_STAMP_KEY))
    dispatched_at = getattr(order, "dispatched_at", None)
    now = now or timezone.now()
    auto_print = (
        not printed
        and order.status == Order.Status.DISPATCHED
        and _is_delivery(order)
        and dispatched_at is not None
        and now - dispatched_at <= AUTO_PRINT_WINDOW
    )
    return DanfeState(printable=True, printed=printed, auto_print=auto_print)


class DanfeRefused(Exception):
    """A DANFE não sai por esta rota — com a frase para o operador e o código."""

    def __init__(self, message: str, *, code: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


@dataclass(frozen=True)
class DanfePrint:
    payload: bytes
    reprint: bool


def claim_print(order_ref: str, *, auto: bool) -> DanfePrint:
    """Compõe a DANFE do pedido e grava o carimbo da primeira composição.

    ``auto=True`` é a impressão que ninguém pediu: ela só sai se o pedido ainda
    está dentro de :func:`danfe_state` ``.auto_print`` e SOB LOCK — a segunda
    estação que chega recebe :class:`DanfeRefused` em vez de uma REIMPRESSÃO
    que ninguém pediu. ``auto=False`` é o gesto do operador: sai sempre que a
    nota existe, carimbada REIMPRESSÃO a partir da segunda vez.
    """
    from shopman.orderman.models import Order

    from shopman.backstage.services.receipt_escpos import danfe_nfce
    from shopman.shop.views.fiscal_danfe import build_danfe

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(ref=order_ref).first()
        if order is None:
            raise DanfeRefused("Pedido não encontrado.", code="not_found", status=404)
        if _is_ifood(order):
            raise DanfeRefused(
                "A sacola do iFood segue a regra do iFood: a DANFE não sai pelo Gestor.",
                code="danfe_ifood",
            )
        state = danfe_state(order)
        if not state.printable:
            raise DanfeRefused("A NFC-e deste pedido ainda não foi autorizada.", code="danfe_not_authorized")
        if auto and not state.auto_print:
            raise DanfeRefused(
                "A DANFE deste pedido já saiu ou não sai mais sozinha. Use Reimprimir DANFE.",
                code="danfe_auto_not_due",
            )
        reprint = state.printed
        if not reprint:
            data = dict(order.data or {})
            data[PRINT_STAMP_KEY] = timezone.now().isoformat()
            order.data = data
            order.save(update_fields=["data", "updated_at"])

    doc = build_danfe(order_ref)
    return DanfePrint(payload=danfe_nfce(doc, reprint=reprint), reprint=reprint)
