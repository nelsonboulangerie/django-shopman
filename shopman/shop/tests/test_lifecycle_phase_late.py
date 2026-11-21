"""Fase que chega atrasada com o pedido já adiante dela.

Alerta real do alpha (18/11/2026, IFOOD-261118-3030): no iFood o "Saiu" vem logo
depois do "Pronto", e a fase do pronto, que roda em segundo plano, encontrou o
pedido já despachado e travou ("Phase on_ready cannot resume in dispatched").
O que o pronto faz continua devido; o preparo atrasado, não.
"""

from __future__ import annotations

import pytest
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.shop import lifecycle
from shopman.shop.handlers.lifecycle_phase import LifecyclePhaseHandler
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(db):
    Shop.objects.create(name="Loja")
    return Channel.objects.create(ref="web", name="Loja online", config={})


def _order(ref: str, status: str) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=status, total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup", "payment": {"method": "cash"}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _phase_directive(order: Order, phase: str) -> Directive:
    directive = lifecycle.enqueue_phase(order, phase)
    if directive is None or not hasattr(directive, "payload"):
        directive = Directive.objects.get(payload__order_ref=order.ref, payload__phase=phase)
    directive.refresh_from_db()
    return directive


@pytest.mark.parametrize("status", ["dispatched", "delivered", "completed"])
def test_pronto_atrasado_roda_com_o_pedido_ja_adiante(channel, status):
    order = _order(f"LATE-READY-{status}", status)
    directive = _phase_directive(order, "on_ready")

    LifecyclePhaseHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    assert order.data["lifecycle"]["on_ready"] == "done"


def test_despacho_atrasado_roda_com_o_pedido_entregue(channel):
    order = _order("LATE-DISPATCH", "delivered")
    directive = _phase_directive(order, "on_dispatched")

    LifecyclePhaseHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    assert order.data["lifecycle"]["on_dispatched"] == "done"


def test_preparo_atrasado_continua_travado_com_o_pedido_despachado(channel):
    order = _order("LATE-PREP", "dispatched")
    directive = _phase_directive(order, "on_preparing")

    with pytest.raises(DirectiveTerminalError, match="cannot resume in dispatched"):
        LifecyclePhaseHandler().handle(message=directive, ctx={})


def test_pronto_nao_roda_com_o_pedido_cancelado(channel):
    order = _order("LATE-CANCEL", "cancelled")
    directive = _phase_directive(order, "on_ready")

    with pytest.raises(DirectiveTerminalError, match="cannot resume in cancelled"):
        LifecyclePhaseHandler().handle(message=directive, ctx={})


# ── Fase superada não é travamento (#3029, alertas de 19/11/2026) ─────────────


def _alerts(order: Order):
    from shopman.backstage.models import OperatorAlert

    return OperatorAlert.objects.filter(type="lifecycle_phase_stuck", order_ref=order.ref)


def _closed_by(order: Order, status: str, actor: str) -> None:
    """O fechamento como o ``transition_status`` grava: um ``status_changed`` com o ator."""
    order.emit_event("status_changed", actor=actor, payload={"old_status": "accepted", "new_status": status})


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_preparo_que_chega_com_o_pedido_fechado_pelo_reparo_termina_sem_alerta(channel, status):
    """O reparo do iFood leva o pedido a concluído num instante; o preparo chega depois."""
    order = _order(f"LATE-PREP-{status}", status)
    _closed_by(order, status, "system:ifood:CON")
    directive = _phase_directive(order, "on_preparing")

    LifecyclePhaseHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    assert "on_preparing" not in ((order.data or {}).get("lifecycle") or {})
    assert not _alerts(order).exists()


def test_preparo_obsoleto_de_pedido_real_fechado_pela_casa_segue_visivel(channel):
    """Cancelado no Gestor: a cozinha nunca recebeu o pedido, e alguém precisa saber."""
    order = _order("LATE-PREP-CASA", "cancelled")
    _closed_by(order, "cancelled", "operator:joyce")
    directive = _phase_directive(order, "on_preparing")

    with pytest.raises(DirectiveTerminalError):
        LifecyclePhaseHandler().handle(message=directive, ctx={})

    assert _alerts(order).get().severity == "critical"


def test_pedido_de_teste_nao_gera_alerta_critico(channel):
    order = _order("LATE-TESTE", "dispatched")
    order.data["ifood"] = {"is_test": True}
    order.save(update_fields=["data"])
    directive = _phase_directive(order, "on_preparing")

    LifecyclePhaseHandler().handle(message=directive, ctx={})

    assert not _alerts(order).exists()


def test_pedido_real_com_preparo_atrasado_ainda_alerta(channel):
    order = _order("LATE-PREP-REAL", "dispatched")
    directive = _phase_directive(order, "on_preparing")

    with pytest.raises(DirectiveTerminalError):
        LifecyclePhaseHandler().handle(message=directive, ctx={})

    alert = _alerts(order).get()
    assert alert.severity == "critical"


def test_o_sweeper_nao_alerta_a_fase_superada(channel):
    from shopman.shop.management.commands.sweep_stuck_orders import Command

    order = _order("SWEEP-TESTE", "completed")
    order.data["ifood"] = {"is_test": True}
    order.save(update_fields=["data"])

    Command()._alert(order, "on_ready")

    assert not _alerts(order).exists()
