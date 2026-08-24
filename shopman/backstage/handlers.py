"""Receivers do backstage.

Dois assuntos:

- observar quando um produto deixa (ou volta) de estar disponível para oferecer.
  O que muda essa resposta é estoque ou reserva, então é neles que se escuta;
- anunciar no canal SSE ``cash`` os fatos de caixa que outra estação do PDV
  precisa ver sem F5: pedido de troco, devolução entregue, turno aberto/fechado.

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


def _terminal_ref(shift) -> str:
    return shift.terminal.ref if shift is not None and shift.terminal_id else ""


def on_entry_for_pos_event(sender, entry, **kwargs) -> None:
    """Anuncia no canal ``cash`` os lançamentos que outra estação precisa ver.

    Escuta ``cashman.signals.entry_recorded`` em vez de o service do balcão
    chamar o emissor na mão: o anúncio passa a ser consequência do FATO (a linha
    no livro), não de alguém lembrar de anunciar. Quem gravar o lançamento por
    outro caminho — um comando, o Admin, um fluxo novo — anuncia igual.

    Só os lançamentos CROSS-estação anunciam: pedido de troco (pedido/atendido/
    cancelado, o estado que a outra tela acompanha) e a devolução em dinheiro
    entregue (some da lista de pendentes de todo mundo). Venda, sangria e
    suprimento ficam de fora de propósito — são fatos da própria estação, e
    empurrar um refetch para o balcão inteiro a cada venda seria o poll de volta,
    só que empurrado.

    O corpo é sinal mínimo (``kind``+``ref``, ADR-016): valor e cédulas moram no
    fetch canônico da Projection, atrás do mesmo gate ``cashman.operate_pos`` do
    canal.

    ⚠️ O push NÃO substitui o operador chamar em voz alta: tela fechada não ouve
    SSE. O que ele elimina é o F5 de quem está com a tela aberta.
    """
    if entry is None:
        return

    from shopman.shop.handlers._sse_emitters import emit_cash_event

    if entry.kind in _CHANGE_REQUEST_KINDS:
        from shopman.backstage.services.pos import change_request_state

        # Atendimento e cancelamento respondem ao pedido: o que a tela acompanha
        # é sempre o estado DELE, não o da linha que acabou de entrar.
        request_id = entry.pk if entry.kind == "change_requested" else entry.parent_id
        if not request_id:
            return
        request = change_request_state(entry.shift, request_id)
        emit_cash_event(
            "change_request",
            {"ref": str(request.get("entry_id") or ""), "status": request.get("status", "")},
            terminal_ref=_terminal_ref(entry.shift),
        )
    elif entry.kind == "refund":
        emit_cash_event(
            "refund",
            {"ref": str(entry.order_ref or "")},
            terminal_ref=_terminal_ref(entry.shift),
        )


def on_shift_opened(sender, shift, **kwargs) -> None:
    """Turno aberto: a antesala das outras estações troca de mundo sem F5."""
    from shopman.shop.handlers._sse_emitters import emit_cash_event

    emit_cash_event(
        "shift_opened",
        {"ref": str(shift.pk)},
        terminal_ref=_terminal_ref(shift),
    )


def on_shift_closed(sender, shift, count=None, **kwargs) -> None:
    """Turno fechado: quem ficou na tela de venda descobre que o caixa acabou."""
    from shopman.shop.handlers._sse_emitters import emit_cash_event

    emit_cash_event(
        "shift_closed",
        {"ref": str(shift.pk)},
        terminal_ref=_terminal_ref(shift),
    )
