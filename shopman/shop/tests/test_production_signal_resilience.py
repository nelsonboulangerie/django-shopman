"""A cauda não-crítica de ``production_changed`` não pode abortar o fan-out.

Contexto (ver ``packages/craftsman/.../tests/test_finish_signal_contract.py``
para os dois fatos do Core): o sinal usa ``.send()`` e o replay do ``finish``
não reemite. Logo, um receiver cosmético que estoura derruba a resposta do
``finish`` E deixa os posteriores órfãos para sempre.

A cura é ``shopman.shop.handlers._resilient.resilient_receiver`` em cada
receiver da cauda. Aqui provamos (1) que o wrapper engole sem abortar a cadeia,
e (2) a POLÍTICA: exatamente a cauda é blindada, e as pernas críticas (estoque,
sync de pedido) seguem cruas — para poderem GRITAR.
"""

from __future__ import annotations

import pytest
from django.dispatch import Signal

from shopman.shop.handlers._resilient import resilient_receiver


def test_resilient_receiver_swallows_and_preserves_identity():
    calls: list[str] = []

    @resilient_receiver
    def receiver(sender, **kwargs):
        calls.append("ran")
        raise RuntimeError("cosmético estourou")

    # Não propaga, devolve None.
    assert receiver(sender=None, action="finished") is None
    assert calls == ["ran"]
    # functools.wraps preserva a identidade (introspecção da ordem + dispatch_uid).
    assert receiver.__name__ == "receiver"
    assert receiver.__wrapped__ is not None


def test_a_wrapped_receiver_does_not_starve_the_receivers_after_it():
    """O contraponto direto de ``test_a_middle_receiver_error_starves...``.

    Mesma montagem (um receiver do meio estoura, um posterior espera para rodar),
    mas o do meio está BLINDADO: ``.send()`` chega até o posterior.
    """
    signal = Signal()
    order: list[str] = []

    @resilient_receiver
    def early(sender, **kwargs):
        order.append("early")
        raise RuntimeError("estourou, mas blindado")

    def later(sender, **kwargs):
        order.append("later")

    signal.connect(early, dispatch_uid="res-early", weak=False)
    signal.connect(later, dispatch_uid="res-later", weak=False)

    # ``.send()`` não levanta, e o posterior rodou.
    signal.send(sender=None, action="finished")
    assert order == ["early", "later"]


def test_an_unwrapped_receiver_still_aborts_send():
    """Não neutralizamos o ``.send()``: um receiver CRU ainda aborta.

    É o que garante que a perna de estoque (crua) continua podendo gritar.
    """
    signal = Signal()

    def raw_boom(sender, **kwargs):
        raise RuntimeError("perna crítica estourou")

    signal.connect(raw_boom, dispatch_uid="res-raw", weak=False)
    with pytest.raises(RuntimeError):
        signal.send(sender=None, action="finished")


def test_exactly_the_noncritical_tail_is_wrapped_and_only_stock_screams():
    """POLÍTICA fixada: só a perna de ESTOQUE grita; todo o resto é blindado.

    O sync de pedido é blindado E recuperável (rede em ``_ensure_order_links_
    closed``), então entra na cauda. Se alguém um dia blindar a perna de estoque,
    este teste cai — e deve cair: seria engolir a falha que a casa quer ALTA
    (``feedback_falhar_fechado_ou_falhar_gritando``).
    """
    from shopman.craftsman.contrib.stockman.handlers import handle_production_changed

    from shopman.shop.handlers import _sse_emitters, _stock_receivers, campaign, production_alerts
    from shopman.shop.handlers.production_order_sync import link_work_order_to_orders
    from shopman.shop.production_lifecycle import on_production_changed_receiver
    from shopman.storefront.handlers import on_production_finished_for_stock_alerts

    # Cauda não-crítica — TODA blindada (``__wrapped__`` vem de functools.wraps).
    non_critical = [
        _stock_receivers.on_production_voided,
        production_alerts.on_production_changed,
        link_work_order_to_orders,
        _sse_emitters._on_production_changed,
        campaign.on_production_changed,
        on_production_changed_receiver,
        on_production_finished_for_stock_alerts,
    ]
    for fn in non_critical:
        assert hasattr(fn, "__wrapped__"), f"{fn.__module__}.{fn.__name__} deveria ser blindado"

    # Única perna crítica — CRUA (grita): o ledger de estoque.
    assert not hasattr(handle_production_changed, "__wrapped__"), (
        "a perna de estoque NÃO pode ser blindada — precisa gritar"
    )
