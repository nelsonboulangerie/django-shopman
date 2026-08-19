"""Receivers do backstage.

Dois assuntos:

- observar quando um produto deixa (ou volta) de estar disponível para oferecer.
  O que muda essa resposta é estoque ou reserva, então é neles que se escuta;
- anunciar o pedido de troco do balcão no SSE quando a linha entra no livro.

Os dois sempre **depois do commit**, para que a leitura enxergue o estado já
gravado e não o de meio de transação.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def on_move_for_shelf_outage(sender, instance, **kwargs) -> None:
    sku = getattr(getattr(instance, "quant", None), "sku", None)
    if sku:
        _observe_after_commit(sku)


def on_hold_for_shelf_outage(sender, instance, **kwargs) -> None:
    sku = getattr(instance, "sku", None)
    if sku:
        _observe_after_commit(sku)


def _observe_after_commit(sku: str) -> None:
    from django.db import transaction

    from shopman.backstage.services import shelf_outages

    transaction.on_commit(lambda: shelf_outages.observe(sku))


#: Os lançamentos que mudam o estado de um pedido de troco. O pedido não tem
#: coluna de status: o estado é a linha mais o filho que a resolve.
_CHANGE_REQUEST_KINDS = ("change_requested", "change_served", "change_cancelled")


def on_entry_for_change_request(sender, entry, **kwargs) -> None:
    """Anuncia o pedido de troco no canal ``alerts`` quando ele entra no livro.

    Escuta ``cashman.signals.entry_recorded`` em vez de o service do balcão
    chamar o emissor na mão: o anúncio passa a ser consequência do FATO (a linha
    no livro), não de alguém lembrar de anunciar. Quem gravar o lançamento por
    outro caminho — um comando, o Admin, um fluxo novo — anuncia igual.

    ⚠️ Isto NÃO substitui o operador chamar em voz alta. Numa padaria pequena
    ninguém está com a tela de alertas aberta esperando — e hoje as superfícies
    de operador leem alertas por POLL, não por este canal. O que o evento entrega
    é a trilha (quem pediu, o quê, quando) e o dado para o B.I. depois: quantas
    vezes por dia falta troco, e em qual horário. Prometer recado entregue seria
    mentira, e mentira de tela vira dinheiro no chão.
    """
    if entry is None or entry.kind not in _CHANGE_REQUEST_KINDS:
        return

    from shopman.backstage.services.pos import change_request_state
    from shopman.shop.handlers._sse_emitters import emit_change_request

    # Atendimento e cancelamento respondem ao pedido: o que a tela acompanha é
    # sempre o estado DELE, não o da linha que acabou de entrar.
    request_id = entry.pk if entry.kind == "change_requested" else entry.parent_id
    if not request_id:
        return
    shift = entry.shift
    request = change_request_state(shift, request_id)
    emit_change_request(
        {
            "ref": str(request.get("entry_id") or ""),
            "status": request.get("status", ""),
            "amount_q": request.get("amount_q", 0),
            "denominations": request.get("denominations", []),
            "shift_id": shift.pk,
            "terminal_ref": shift.terminal.ref if shift.terminal_id else "",
            "requested_by": request.get("requested_by", ""),
        }
    )
