"""Piloto automático de staging — o operador de mentira que aperta botões de verdade.

Cobre as três garantias que fazem esta feature ser aceitável:
  1. NUNCA age em produção (nem com a flag ligada).
  2. Avança pelos MESMOS services do gestor — sem lifecycle paralelo.
  3. Sai de fininho quando um operador de verdade encosta no pedido.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.checks import Error, Warning
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.checks import check_staging_autopilot
from shopman.shop.directives import STAGING_AUTOPILOT
from shopman.shop.handlers.staging_autopilot import StagingAutopilotHandler
from shopman.shop.services import staging_autopilot

pytestmark = pytest.mark.django_db


def _order(**overrides):
    order = MagicMock()
    order.ref = overrides.get("ref", "WEB-001")
    order.status = overrides.get("status", Order.Status.ACCEPTED)
    order.channel_ref = overrides.get("channel_ref", "web")
    order.data = overrides.get("data", {})
    return order


def _staging(**extra):
    """Settings de um staging com o piloto ligado."""
    return {
        "SHOPMAN_STAGING_AUTOPILOT": True,
        "SHOPMAN_ENVIRONMENT": "staging",
        "SHOPMAN_STAGING_AUTOPILOT_DELAY_SECONDS": 30,
        "SHOPMAN_STAGING_AUTOPILOT_CHANNELS": [],
        **extra,
    }


# ── 1. Nunca em produção ──


def test_disabled_by_default(settings):
    settings.SHOPMAN_STAGING_AUTOPILOT = False
    assert staging_autopilot.is_enabled() is False


def test_refuses_production_even_with_flag_on(settings):
    """A flag sozinha não basta: em produção o piloto se cala.

    Um pedido de cliente real avançando sozinho cobraria, baixaria estoque e
    emitiria nota sem ninguém ter encostado.
    """
    settings.SHOPMAN_STAGING_AUTOPILOT = True
    settings.SHOPMAN_ENVIRONMENT = "production"

    assert staging_autopilot.is_enabled() is False


def test_production_flag_is_a_boot_error(settings):
    settings.SHOPMAN_STAGING_AUTOPILOT = True
    settings.SHOPMAN_ENVIRONMENT = "production"

    messages = check_staging_autopilot(None)

    assert [m.id for m in messages] == ["SHOPMAN_E012"]
    assert isinstance(messages[0], Error)


def test_staging_flag_is_only_a_warning(settings):
    settings.SHOPMAN_STAGING_AUTOPILOT = True
    settings.SHOPMAN_ENVIRONMENT = "staging"

    messages = check_staging_autopilot(None)

    assert [m.id for m in messages] == ["SHOPMAN_W011"]
    assert isinstance(messages[0], Warning)


def test_no_check_noise_when_flag_is_off(settings):
    settings.SHOPMAN_STAGING_AUTOPILOT = False
    assert check_staging_autopilot(None) == []


def test_handler_refuses_orphan_directive_in_production(settings):
    """Directive sobrevivente de um staging antigo não move pedido em produção."""
    from shopman.orderman.exceptions import DirectiveTerminalError

    settings.SHOPMAN_STAGING_AUTOPILOT = False
    directive = Directive(topic=STAGING_AUTOPILOT, payload={"order_ref": "WEB-001"})

    with pytest.raises(DirectiveTerminalError):
        StagingAutopilotHandler().handle(message=directive, ctx={})


# ── 2. Agendamento ──


def test_schedules_next_step_with_configured_delay(settings):
    for key, value in _staging().items():
        setattr(settings, key, value)
    before = timezone.now()

    directive = staging_autopilot.schedule(_order())

    assert directive is not None
    assert directive.topic == STAGING_AUTOPILOT
    assert directive.payload["order_ref"] == "WEB-001"
    assert directive.payload["status"] == Order.Status.ACCEPTED
    assert directive.available_at >= before + timedelta(seconds=29)


def test_does_not_schedule_for_terminal_status(settings):
    for key, value in _staging().items():
        setattr(settings, key, value)

    assert staging_autopilot.schedule(_order(status=Order.Status.COMPLETED)) is None
    assert staging_autopilot.schedule(_order(status=Order.Status.CANCELLED)) is None


def test_dedupes_per_order_and_status(settings):
    """Dois eventos para o mesmo estado geram UMA directive viva."""
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = _order()

    first = staging_autopilot.schedule(order)
    second = staging_autopilot.schedule(order)

    assert first is not None
    assert second is None
    assert Directive.objects.filter(topic=STAGING_AUTOPILOT, status="queued").count() == 1


def test_channel_allowlist_leaves_other_channels_to_the_operator(settings):
    for key, value in _staging(SHOPMAN_STAGING_AUTOPILOT_CHANNELS=["web"]).items():
        setattr(settings, key, value)

    assert staging_autopilot.covers_channel("web") is True
    assert staging_autopilot.covers_channel("pdv") is False
    assert staging_autopilot.schedule(_order(channel_ref="pdv")) is None


def test_gives_up_after_max_deferrals(settings):
    for key, value in _staging().items():
        setattr(settings, key, value)

    result = staging_autopilot.schedule(
        _order(), deferrals=staging_autopilot.MAX_DEFERRALS
    )

    assert result is None


# ── 3. O passo usa os services do gestor ──


def test_new_order_goes_through_confirm_order(settings):
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = _order(status=Order.Status.NEW)

    with patch("shopman.shop.services.operator_orders.confirm_order") as confirm:
        result = staging_autopilot.step(order, recorded_status=Order.Status.NEW)

    confirm.assert_called_once_with(order, actor="staging.autopilot")
    assert result == Order.Status.ACCEPTED


def test_accepted_order_goes_through_advance_order(settings):
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = _order(status=Order.Status.ACCEPTED)

    with patch("shopman.shop.services.operator_orders.advance_order") as advance:
        advance.return_value = Order.Status.PREPARING
        result = staging_autopilot.step(order, recorded_status=Order.Status.ACCEPTED)

    advance.assert_called_once_with(order, actor="staging.autopilot")
    assert result == Order.Status.PREPARING


def test_preparing_bumps_kds_tickets_instead_of_the_gestor_button(settings):
    """Em preparo quem avança é a COZINHA — senão o KDS do staging enche de
    tickets abertos que ninguém fecha nunca."""
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = _order(status=Order.Status.PREPARING)
    ticket = MagicMock()

    with (
        patch("shopman.shop.adapters.kds.get_tickets") as get_tickets,
        patch("shopman.shop.services.kds.complete_ticket", return_value=True) as complete,
        patch("shopman.shop.services.operator_orders.advance_order") as advance,
    ):
        get_tickets.return_value.filter.return_value = [ticket]
        order.refresh_from_db.side_effect = lambda: setattr(
            order, "status", Order.Status.READY
        )
        result = staging_autopilot.step(order, recorded_status=Order.Status.PREPARING)

    complete.assert_called_once_with(ticket, actor="staging.autopilot")
    advance.assert_not_called()
    assert result == Order.Status.READY


def test_preparing_without_kds_falls_back_to_advance(settings):
    """Canal sem roteamento de KDS não tem cozinha para simular."""
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = _order(status=Order.Status.PREPARING)

    with (
        patch("shopman.shop.adapters.kds.get_tickets") as get_tickets,
        patch("shopman.shop.services.operator_orders.advance_order") as advance,
    ):
        get_tickets.return_value.filter.return_value = []
        advance.return_value = Order.Status.READY
        result = staging_autopilot.step(order, recorded_status=Order.Status.PREPARING)

    advance.assert_called_once_with(order, actor="staging.autopilot")
    assert result == Order.Status.READY


def test_step_noops_when_a_real_operator_moved_the_order(settings):
    """O status gravado no payload não bate mais: alguém encostou. Sai de fininho."""
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = _order(status=Order.Status.READY)

    with patch("shopman.shop.services.operator_orders.advance_order") as advance:
        result = staging_autopilot.step(order, recorded_status=Order.Status.PREPARING)

    advance.assert_not_called()
    assert result == ""


# ── 4. Bloqueio reagenda em vez de falhar ──


def test_handler_requeues_when_a_guard_blocks(settings):
    """PIX ainda não pago não é erro — é 'ainda não'."""
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = Order.objects.create(
        ref="WEB-BLOCK", channel_ref="web", status=Order.Status.ACCEPTED, total_q=1000,
    )
    directive = Directive.objects.create(
        topic=STAGING_AUTOPILOT,
        payload={"order_ref": order.ref, "status": Order.Status.ACCEPTED, "deferrals": 0},
        status="running",
    )

    with patch(
        "shopman.shop.services.staging_autopilot.step",
        side_effect=ValueError("Pagamento ainda não foi confirmado."),
    ):
        StagingAutopilotHandler().handle(message=directive, ctx={})

    directive.refresh_from_db()
    assert directive.status == "queued"
    assert directive.payload["deferrals"] == 1
    assert directive.available_at > timezone.now()


def test_handler_stops_requeuing_at_the_ceiling(settings):
    """Pedido preso num guarda para de bater no banco a cada 30s para sempre."""
    for key, value in _staging().items():
        setattr(settings, key, value)
    order = Order.objects.create(
        ref="WEB-STUCK", channel_ref="web", status=Order.Status.ACCEPTED, total_q=1000,
    )
    directive = Directive.objects.create(
        topic=STAGING_AUTOPILOT,
        payload={
            "order_ref": order.ref,
            "status": Order.Status.ACCEPTED,
            "deferrals": staging_autopilot.MAX_DEFERRALS - 1,
        },
        status="running",
    )

    with patch(
        "shopman.shop.services.staging_autopilot.step",
        side_effect=ValueError("Encomenda ainda não chegou na data."),
    ):
        StagingAutopilotHandler().handle(message=directive, ctx={})

    directive.refresh_from_db()
    assert directive.status == "running"  # o worker fecha como done; nada reagendado


def test_handler_is_a_noop_for_a_deleted_order(settings):
    for key, value in _staging().items():
        setattr(settings, key, value)
    directive = Directive.objects.create(
        topic=STAGING_AUTOPILOT,
        payload={"order_ref": "SUMIU", "status": Order.Status.ACCEPTED},
        status="running",
    )

    StagingAutopilotHandler().handle(message=directive, ctx={})  # não levanta
