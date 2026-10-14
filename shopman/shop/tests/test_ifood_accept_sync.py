"""P1-3: o aceite que não chegou ao iFood fica visível e se tenta de novo.

O ``confirm`` ao iFood sai numa Directive com retry. Quando ela falha, a cozinha
já trabalha e o iFood cancela sozinho no prazo dele. Estes testes provam:

- a primeira falha abre um alerta ESPECÍFICO, apontando o pedido e com o prazo;
- o estado (pendente / falhou / enviado / confirmado) sai das evidências que já
  existem (Directive do aceite e ``data.ifood.remote_*``);
- o aviso fecha quando o ``confirm`` passa ou quando o iFood confirma (CFM);
- o Tentar de novo reabre a mesma Directive, uma vez por leitura.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTransientError
from shopman.orderman.models import Directive, Order

from shopman.shop.config import ChannelConfig
from shopman.shop.directives import IFOOD_STATUS_CALLBACK
from shopman.shop.handlers.ifood_status import IFoodStatusCallbackHandler
from shopman.shop.services import ifood_accept_sync, ifood_callbacks, ifood_events

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ifood_settings():
    config = ChannelConfig(
        payment=ChannelConfig.Payment(method="external", timing="external"),
        fulfillment=ChannelConfig.Fulfillment(prep_start="operator"),
    )
    with (
        override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}),
        patch.object(ChannelConfig, "for_channel", return_value=config),
    ):
        yield


def _order(status="accepted", **ifood):
    confirm_by = (timezone.now() + timedelta(minutes=6)).isoformat()
    return Order.objects.create(
        ref="IFD-ACEITE", channel_ref="ifood", external_ref="remote-order", status=status,
        data={
            "fulfillment_type": "delivery",
            "payment": {"method": "external", "gateway": "ifood", "status": "paid"},
            "ifood": {"delivered_by": "IFOOD", "confirm_by": confirm_by, **ifood},
        },
    )


def _directive(order, *, status="running", attempts=1, last_error=""):
    return Directive.objects.create(
        topic=IFOOD_STATUS_CALLBACK,
        status=status,
        attempts=attempts,
        last_error=last_error,
        dedupe_key=ifood_accept_sync.dedupe_key(order.ref),
        payload={"order_ref": order.ref, "ifood_order_id": order.external_ref, "status": "accepted"},
    )


def _alerts(order, *, active=True):
    from shopman.backstage.models import OperatorAlert

    qs = OperatorAlert.objects.filter(type=ifood_accept_sync.ALERT_TYPE, order_ref=order.ref)
    return qs.filter(resolved_at__isnull=True) if active else qs


def _fail(directive):
    with patch.object(ifood_callbacks, "send_action", side_effect=ifood_callbacks.IFoodCallbackError("iFood 503")):
        with pytest.raises(DirectiveTransientError):
            IFoodStatusCallbackHandler().handle(message=directive, ctx={})


# ── O alerta específico ───────────────────────────────────────────────────────


def test_first_failed_confirm_raises_specific_alert_pointing_to_order_with_ifood_deadline(django_capture_on_commit_callbacks):
    order = _order()
    directive = _directive(order)
    with django_capture_on_commit_callbacks(execute=True):
        _fail(directive)

    alerts = list(_alerts(order))
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == "error"
    assert alert.audience == "orders"
    assert alert.respond_by == ifood_accept_sync.deadline(order)
    assert "O iFood ainda não recebeu o aceite do pedido IFD-ACEITE" in alert.message
    assert "Tentar de novo" in alert.message
    assert "—" not in alert.message
    assert order.events.filter(type=ifood_accept_sync.EVENT_FAILED).count() == 1


def test_worker_retries_do_not_repeat_the_alert():
    order = _order()
    _fail(_directive(order, attempts=1))
    retry = Directive.objects.get(dedupe_key=ifood_accept_sync.dedupe_key(order.ref))
    retry.attempts = 2
    retry.save(update_fields=["attempts"])
    _fail(retry)
    assert _alerts(order, active=False).count() == 1
    assert order.events.filter(type=ifood_accept_sync.EVENT_FAILED).count() == 1


@pytest.mark.parametrize("status", ["preparing", "ready", "dispatched"])
def test_progress_callbacks_failing_are_not_the_accept_alert(status):
    order = _order(status=status)
    directive = Directive.objects.create(
        topic=IFOOD_STATUS_CALLBACK, status="running", attempts=1,
        dedupe_key=f"{IFOOD_STATUS_CALLBACK}:{order.ref}:{status}",
        payload={"order_ref": order.ref, "ifood_order_id": order.external_ref, "status": status,
                 "fulfillment_type": "delivery", "delivered_by": "MERCHANT"},
    )
    order.data["ifood"]["delivered_by"] = "MERCHANT"
    order.save(update_fields=["data"])
    _fail(directive)
    assert not _alerts(order, active=False).exists()


def test_confirm_that_goes_through_after_failure_closes_the_alert(django_capture_on_commit_callbacks):
    order = _order()
    with django_capture_on_commit_callbacks(execute=True):
        _fail(_directive(order))
    directive = Directive.objects.get(dedupe_key=ifood_accept_sync.dedupe_key(order.ref))
    directive.attempts = 2
    directive.save(update_fields=["attempts"])
    with django_capture_on_commit_callbacks(execute=True):
        with patch.object(ifood_callbacks, "send_action") as send:
            IFoodStatusCallbackHandler().handle(message=directive, ctx={})
    send.assert_called_once_with("remote-order", "confirm")
    assert not _alerts(order).exists()
    assert order.events.filter(type=ifood_accept_sync.EVENT_SENT).count() == 1


def test_ifood_confirmation_event_closes_the_alert(django_capture_on_commit_callbacks):
    order = _order(status="preparing")
    with django_capture_on_commit_callbacks(execute=True):
        _fail(_directive(order))
    assert _alerts(order).exists()
    with (
        django_capture_on_commit_callbacks(execute=True),
        patch.object(ifood_events, "acknowledge", return_value=True),
    ):
        ifood_events.process_events([{"id": "evt-cfm", "code": "CFM", "orderId": "remote-order", "merchantId": "test-store"}])
    order.refresh_from_db()
    assert order.data["ifood"]["remote_confirmed"]
    assert not _alerts(order).exists()
    assert ifood_accept_sync.state_for(order).state == "confirmed"


# ── O estado derivado ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(("status", "attempts", "last_error", "expected"), [
    ("queued", 0, "", "pending"),
    ("running", 1, "", "pending"),
    ("queued", 1, "iFood 503", "failed"),
    ("running", 2, "iFood 503", "failed"),
    ("failed", 5, "iFood 503", "failed"),
    ("done", 1, "", "sent"),
])
def test_state_comes_from_the_accept_directive(status, attempts, last_error, expected):
    order = _order(status="preparing")
    _directive(order, status=status, attempts=attempts, last_error=last_error)
    assert ifood_accept_sync.state_for(order).state == expected


def test_remote_confirmation_wins_over_a_failed_directive():
    order = _order(remote_confirmed={"event_id": "evt", "observed_at": "x"})
    _directive(order, status="failed", attempts=5, last_error="iFood 503")
    assert ifood_accept_sync.state_for(order).state == "confirmed"


@pytest.mark.parametrize("status", ["new", "completed", "cancelled"])
def test_state_does_not_apply_before_accept_or_after_the_end(status):
    order = _order(status=status)
    _directive(order, status="failed", attempts=5, last_error="iFood 503")
    assert ifood_accept_sync.state_for(order).state == ""


def test_batch_read_keeps_the_latest_directive_per_order():
    order = _order(status="preparing")
    _directive(order, status="failed", attempts=5, last_error="velho")
    newest = _directive(order, status="done", attempts=1)
    assert ifood_accept_sync.latest_directives([order.ref])[order.ref].pk == newest.pk


# ── Tentar de novo ────────────────────────────────────────────────────────────


def test_retry_reopens_the_failed_directive_with_a_full_window():
    order = _order(status="preparing")
    directive = _directive(order, status="failed", attempts=5, last_error="iFood 503")
    revision = ifood_accept_sync.state_for(order).revision

    reopened = ifood_accept_sync.retry(order, actor="operator:ana", expected_revision=revision)

    reopened.refresh_from_db()
    assert reopened.pk == directive.pk
    assert (reopened.status, reopened.attempts, reopened.last_error) == ("queued", 0, "")
    assert reopened.available_at <= timezone.now()
    assert Directive.objects.filter(dedupe_key=directive.dedupe_key).count() == 1
    event = order.events.get(type=ifood_accept_sync.EVENT_RETRIED)
    assert event.actor == "operator:ana"
    assert event.payload["previous_error"] == "iFood 503"
    assert ifood_accept_sync.state_for(order).state == "pending"


def test_retry_brings_a_backed_off_attempt_forward():
    order = _order(status="preparing")
    directive = _directive(order, status="queued", attempts=2, last_error="iFood 503")
    Directive.objects.filter(pk=directive.pk).update(available_at=timezone.now() + timedelta(seconds=30))
    ifood_accept_sync.retry(order, actor="operator:ana")
    directive.refresh_from_db()
    assert directive.available_at <= timezone.now()
    assert directive.attempts == 0


def test_second_tap_on_the_same_reading_is_refused():
    order = _order(status="preparing")
    _directive(order, status="failed", attempts=5, last_error="iFood 503")
    revision = ifood_accept_sync.state_for(order).revision
    ifood_accept_sync.retry(order, actor="operator:ana", expected_revision=revision)
    with pytest.raises(ifood_accept_sync.AcceptRetryRefused):
        ifood_accept_sync.retry(order, actor="operator:ana", expected_revision=revision)


@pytest.mark.parametrize(("status", "attempts", "last_error", "remote"), [
    ("done", 1, "", False),
    ("failed", 5, "iFood 503", True),
    ("running", 2, "iFood 503", False),
    ("queued", 0, "", False),
])
def test_retry_refuses_when_there_is_nothing_to_retry(status, attempts, last_error, remote):
    extra = {"remote_confirmed": {"event_id": "e"}} if remote else {}
    order = _order(status="preparing", **extra)
    _directive(order, status=status, attempts=attempts, last_error=last_error)
    with pytest.raises(ifood_accept_sync.AcceptRetryRefused):
        ifood_accept_sync.retry(order, actor="operator:ana")
