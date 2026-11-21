"""O acionador: remédio da lista fechada, teto, sombra, recusa do domínio e conferência por fato."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.backstage.incidents import act, remedies
from shopman.backstage.models import IncidentAction, OperatorAlert
from shopman.shop.directives import FISCAL_EMIT_NFCE, IFOOD_STATUS_CALLBACK, INCIDENT_ACT
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop():
    return Shop.objects.create(name="Loja do acionador")


def _fiscal_order(ref="NFCE-1", status="completed"):
    return Order.objects.create(
        ref=ref, status=status, total_q=1000,
        data={"fiscal": {"issue_document": True}, "payment": {"method": "cash", "amount_q": 1000}},
    )


def _fiscal_failed(order, *, answer=""):
    payload = {"order_ref": order.ref}
    if answer:
        payload["emitter_answer"] = answer
    return Directive.objects.create(
        topic=FISCAL_EMIT_NFCE, payload=payload, status="failed", attempts=8,
        error_code="terminal", last_error="NFC-e emission transient (focus_nfe_timeout): timeout",
    )


def _alert(alert_type, order_ref):
    return OperatorAlert.objects.create(type=alert_type, severity="critical", message="Sintético", order_ref=order_ref)


def test_new_alert_with_remedy_gets_one_live_actor(shop, django_capture_on_commit_callbacks):
    order = _fiscal_order()
    with django_capture_on_commit_callbacks(execute=True):
        alert = _alert("fiscal_emit_failed", order.ref)
        _alert("webhook_failed", "")
    assert list(Directive.objects.filter(topic=INCIDENT_ACT).values_list("dedupe_key", flat=True)) == [
        f"incident.act:{alert.pk}"
    ]


def test_transient_exhaustion_is_requeued_and_confirmed_by_the_authorized_note(shop):
    order = _fiscal_order()
    fiscal = _fiscal_failed(order)
    alert = _alert("fiscal_emit_failed", order.ref)

    outcome = act.step(alert.pk)

    fiscal.refresh_from_db()
    assert fiscal.status == "queued"
    assert order.events.filter(type="fiscal_requeued", actor=remedies.ACTOR).exists()
    action = IncidentAction.objects.get()
    assert (action.outcome, action.remedy, action.decided_by) == ("ran", "fiscal_requeue", "regra")
    assert isinstance(outcome, act.Deferred) and outcome.payload == {"action_id": action.pk}

    # Ainda sem nota: a conferência volta depois.
    assert isinstance(act.step(alert.pk, action_id=action.pk), act.Deferred)
    Order.objects.filter(pk=order.pk).update(data={**order.data, "nfce_access_key": "3526" + "0" * 40})
    assert act.step(alert.pk, action_id=action.pk) is None
    action.refresh_from_db()
    assert action.outcome == "resolved" and action.verified_at is not None


def test_emitter_refusal_is_not_decided_by_rule(shop):
    order = _fiscal_order()
    fiscal = _fiscal_failed(order, answer="Rejeição 778: NCM inexistente")
    alert = _alert("fiscal_emit_failed", order.ref)

    assert act.step(alert.pk) is None

    fiscal.refresh_from_db()
    assert fiscal.status == "failed"
    action = IncidentAction.objects.get()
    assert action.outcome == "skipped" and "pede leitura" in action.detail
    # Uma linha só, por mais que a repescagem passe de novo.
    act.step(alert.pk)
    assert IncidentAction.objects.count() == 1


def test_shadow_only_records_and_off_does_nothing(shop):
    order = _fiscal_order()
    fiscal = _fiscal_failed(order)
    alert = _alert("fiscal_emit_failed", order.ref)

    shop.incident_remedies_mode = "off"
    shop.save()
    assert act.step(alert.pk) is None
    assert not IncidentAction.objects.exists()

    shop.incident_remedies_mode = "shadow"
    shop.save()
    act.step(alert.pk)
    fiscal.refresh_from_db()
    assert fiscal.status == "failed"
    assert IncidentAction.objects.get().outcome == "would_run"


def test_ceiling_stops_the_fourth_attempt(shop):
    order = _fiscal_order()
    fiscal = _fiscal_failed(order)
    alert = _alert("fiscal_emit_failed", order.ref)
    for _ in range(3):
        IncidentAction.objects.create(alert_type=alert.type, target=order.ref, remedy="fiscal_requeue", outcome="not_resolved")

    act.step(alert.pk)

    fiscal.refresh_from_db()
    assert fiscal.status == "failed"
    assert IncidentAction.objects.filter(outcome="ceiling").count() == 1


def test_domain_refusal_is_recorded_not_forced(shop):
    order = _fiscal_order(status="cancelled")
    _fiscal_failed(order)
    alert = _alert("fiscal_emit_failed", order.ref)

    act.step(alert.pk)

    action = IncidentAction.objects.get()
    assert action.outcome == "refused"
    assert "cancelado" in action.detail.lower()


def test_sweep_expires_a_stale_check_as_not_resolved(shop):
    order = _fiscal_order()
    action = IncidentAction.objects.create(alert_type="fiscal_emit_failed", target=order.ref, remedy="fiscal_requeue", outcome="ran")
    IncidentAction.objects.filter(pk=action.pk).update(created_at=timezone.now() - timedelta(hours=2))
    counts = act.sweep()
    action.refresh_from_db()
    assert counts["expired"] == 1
    assert action.outcome == "not_resolved"


def test_sweep_recreates_a_lost_actor_once(shop):
    order = _fiscal_order()
    _alert("fiscal_emit_failed", order.ref)
    Directive.objects.filter(topic=INCIDENT_ACT).delete()
    assert act.sweep()["enqueued"] == 1
    assert act.sweep()["enqueued"] == 0


def test_handler_reschedules_itself_without_spending_an_attempt(shop):
    order = _fiscal_order()
    _fiscal_failed(order)
    alert = _alert("fiscal_emit_failed", order.ref)
    message = Directive.objects.create(topic=INCIDENT_ACT, payload={"alert_id": alert.pk}, status="running", attempts=1)

    act.IncidentActHandler().handle(message=message, ctx={})

    message.refresh_from_db()
    assert message.status == "queued"
    assert message.attempts == 0
    assert message.payload["action_id"] == IncidentAction.objects.get().pk
    assert message.available_at > timezone.now()


# ── A2: o aceite do iFood ────────────────────────────────────────────────────


@pytest.fixture
def ifood():
    from shopman.shop.config import ChannelConfig

    config = ChannelConfig(
        payment=ChannelConfig.Payment(method="external", timing="external"),
        fulfillment=ChannelConfig.Fulfillment(prep_start="operator"),
    )
    with (
        override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}),
        patch.object(ChannelConfig, "for_channel", return_value=config),
    ):
        yield


def _ifood_order(minutes_left=6):
    from shopman.shop.services import ifood_accept_sync

    order = Order.objects.create(
        ref="IFD-ACT", channel_ref="ifood", external_ref="remote-order", status="accepted",
        data={
            "fulfillment_type": "delivery",
            "payment": {"method": "external", "gateway": "ifood", "status": "paid"},
            "ifood": {"delivered_by": "IFOOD", "confirm_by": (timezone.now() + timedelta(minutes=minutes_left)).isoformat()},
        },
    )
    return order, ifood_accept_sync.dedupe_key(order.ref)


def _accept_directive(key, order, *, status, available_in=0):
    return Directive.objects.create(
        topic=IFOOD_STATUS_CALLBACK, status=status, attempts=5, last_error="iFood 503", error_code="terminal",
        dedupe_key=key if status in {"queued", "running"} else "",
        available_at=timezone.now() + timedelta(seconds=available_in),
        payload={"order_ref": order.ref, "ifood_order_id": order.external_ref, "status": "accepted"},
    )


def test_accept_that_stopped_trying_before_the_deadline_is_resent(shop, ifood):
    order, key = _ifood_order()
    directive = _accept_directive(key, order, status="failed")
    Directive.objects.filter(pk=directive.pk).update(dedupe_key=key)
    alert = _alert("ifood_accept_not_delivered", order.ref)

    act.step(alert.pk)

    directive.refresh_from_db()
    assert directive.status == "queued" and directive.attempts == 0
    assert IncidentAction.objects.get().outcome == "ran"


def test_accept_still_retrying_in_time_waits_for_the_domain(shop, ifood):
    order, key = _ifood_order(minutes_left=6)
    _accept_directive(key, order, status="queued", available_in=30)
    alert = _alert("ifood_accept_not_delivered", order.ref)

    outcome = act.step(alert.pk)

    assert isinstance(outcome, act.Deferred)
    assert not IncidentAction.objects.exists()


def test_accept_past_the_ifood_deadline_stays_with_people(shop, ifood):
    order, key = _ifood_order(minutes_left=-1)
    directive = _accept_directive(key, order, status="failed")
    Directive.objects.filter(pk=directive.pk).update(dedupe_key=key)
    alert = _alert("ifood_accept_not_delivered", order.ref)

    act.step(alert.pk)

    directive.refresh_from_db()
    assert directive.status == "failed"
    action = IncidentAction.objects.get()
    assert action.outcome == "skipped" and "prazo" in action.detail


def test_closed_list_never_touches_money_or_infrastructure():
    forbidden = ("refund", "estorno", "capture", "courier", "payment", "restart", "scale", "reseed", "delete")
    for remedy in remedies.REMEDIES:
        assert not any(word in remedy.key or word in remedy.alert_type for word in forbidden), remedy.key
