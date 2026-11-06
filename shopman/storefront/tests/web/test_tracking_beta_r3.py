"""Acompanhamento do pedido na Loja: achados da 3a rodada do beta (06/11/2026).

Cada teste reprova sem o conserto correspondente. O id do achado está no nome
da classe: PIXEXP-* (Pix vencendo), SMS-* (Loja por SMS), F* (cartão Stripe).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.shop.services import customer_orders
from shopman.shop.services import payment as payment_service
from shopman.storefront.presentation.order_tracking import build_order_tracking

pytestmark = pytest.mark.django_db

_TZ = ZoneInfo("America/Sao_Paulo")


def _set(order, *, status=None, **data):
    merged = {**(order.data or {}), **data}
    fields = {"data": merged}
    if status:
        fields["status"] = status
    Order.objects.filter(pk=order.pk).update(**fields)
    order.refresh_from_db()
    return order


def _captured_intent(order, *, method="pix", amount_q=None, gateway_data=None):
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=amount_q if amount_q is not None else order.total_q,
        method=method,
        gateway_data=gateway_data,
    )
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    return intent


def _open_hours(shop_instance):
    shop_instance.timezone = "America/Sao_Paulo"
    shop_instance.opening_hours = {
        day: {"open": "09:00", "close": "18:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    shop_instance.save(update_fields=["timezone", "opening_hours"])


# ── F1: a volta do Stripe confere o pagamento do pedido ainda novo ─────────


class TestF1PaymentDueOnNewOrder:
    def test_new_card_order_with_open_charge_owes_payment(self, order_with_payment):
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="card"
        )
        _set(
            order_with_payment,
            payment={"method": "card", "intent_ref": intent.ref, "checkout_url": "https://checkout.example/cs_1"},
        )

        assert customer_orders.payment_is_due(order_with_payment) is True

    def test_tracking_api_asks_the_screen_to_check_the_card(self, order_with_payment, client):
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="card"
        )
        _set(
            order_with_payment,
            payment={"method": "card", "intent_ref": intent.ref, "checkout_url": "https://checkout.example/cs_1"},
        )

        response = client.get(f"/api/v1/tracking/{order_with_payment.ref}/")

        assert response.status_code == 200
        body = response.json()
        assert body["promise"]["state"] == "payment_card_ready"
        assert body["payment_due"] is True

    def test_new_pix_without_charge_does_not_owe_yet(self, order_with_payment):
        # Pix cobrado depois do aceite: no ``new`` a cobrança ainda não nasceu.
        assert customer_orders.payment_is_due(order_with_payment) is False


# ── PIXEXP-02 e F5: o dinheiro do pedido cancelado, com valor ──────────────


class TestCancelledMoneyLine:
    def test_late_pix_refunded_is_told_with_amount(self, order_with_payment):
        dead = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="pix"
        )
        PaymentService.cancel(dead.ref, reason="payment_timeout")
        late = _captured_intent(
            order_with_payment,
            gateway_data={"booked_by": "pix_confirmation", "superseded_intent_ref": dead.ref},
        )
        PaymentService.refund(late.ref, reason="late_pix")
        _set(
            order_with_payment,
            status="cancelled",
            payment={**order_with_payment.data["payment"], "intent_ref": dead.ref},
            cancellation_reason="payment_timeout",
            payment_timeout_at="2026-11-06T08:25:10+00:00",
        )

        proj = build_order_tracking(order_with_payment)

        assert proj.promise.state == "payment_expired"
        assert proj.cancellation_money_line == (
            "Seu Pix de R$ 25,00 chegou depois do prazo, e devolvemos o valor para a mesma conta."
        )

    def test_late_pix_still_refunding_says_so(self, order_with_payment):
        dead = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="pix"
        )
        PaymentService.cancel(dead.ref, reason="payment_timeout")
        _captured_intent(order_with_payment, gateway_data={"booked_by": "pix_confirmation"})
        _set(
            order_with_payment,
            status="cancelled",
            payment={**order_with_payment.data["payment"], "intent_ref": dead.ref},
            cancellation_reason="payment_timeout",
        )

        proj = build_order_tracking(order_with_payment)

        assert proj.cancellation_money_line == (
            "Seu Pix de R$ 25,00 chegou depois do prazo. Estamos devolvendo o valor para a mesma conta."
        )

    def test_expired_pix_without_money_says_nothing_was_charged(self, order_with_payment):
        dead = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="pix"
        )
        PaymentService.cancel(dead.ref, reason="payment_timeout")
        _set(
            order_with_payment,
            status="cancelled",
            payment={**order_with_payment.data["payment"], "intent_ref": dead.ref},
            cancellation_reason="payment_timeout",
        )

        proj = build_order_tracking(order_with_payment)

        assert proj.promise.message == "O prazo para pagar acabou e cancelamos o pedido."
        assert proj.cancellation_money_line == "Nada foi cobrado."

    def test_released_card_hold_says_nothing_was_charged(self, order_with_payment):
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="card"
        )
        PaymentService.authorize(intent.ref)
        PaymentService.cancel(intent.ref, reason="store_did_not_confirm")
        _set(
            order_with_payment,
            status="cancelled",
            payment={"method": "card", "intent_ref": intent.ref},
            cancellation_reason_key="store_did_not_confirm",
        )

        proj = build_order_tracking(order_with_payment)

        assert proj.cancellation_note == "Não conseguimos confirmar seu pedido dentro do prazo."
        assert proj.cancellation_money_line == "A reserva no seu cartão foi desfeita, e nada foi cobrado."

    def test_refunded_card_says_amount_and_where(self, order_with_payment):
        intent = _captured_intent(order_with_payment, method="card")
        PaymentService.refund(intent.ref, reason="cancelled")
        _set(order_with_payment, status="cancelled", payment={"method": "card", "intent_ref": intent.ref})

        proj = build_order_tracking(order_with_payment)

        assert proj.cancellation_money_line == (
            "Estornamos os R$ 25,00 no seu cartão. O valor volta na fatura no prazo do seu banco."
        )

    def test_card_still_authorized_on_cancelled_order_claims_nothing(self, order_with_payment):
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="card"
        )
        PaymentService.authorize(intent.ref)
        _set(order_with_payment, status="cancelled", payment={"method": "card", "intent_ref": intent.ref})

        assert payment_service.cancelled_money(order_with_payment) is None
        assert build_order_tracking(order_with_payment).cancellation_money_line == ""


class TestF5CancelDialogMoney:
    def test_authorized_card_dialog_says_hold_is_released(self, order_with_payment):
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="card"
        )
        PaymentService.authorize(intent.ref)
        _set(order_with_payment, payment={"method": "card", "intent_ref": intent.ref})

        proj = build_order_tracking(order_with_payment)

        assert proj.cancel_dialog_money_line == "A reserva no seu cartão será desfeita, e nada será cobrado."

    def test_pending_pix_dialog_says_nothing_was_charged(self, order_with_payment):
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=order_with_payment.total_q, method="pix"
        )
        _set(order_with_payment, payment={**order_with_payment.data["payment"], "intent_ref": intent.ref})

        proj = build_order_tracking(order_with_payment)

        assert proj.cancel_dialog_money_line == "Nada foi cobrado até agora."


# ── PIXEXP-10: pedido cancelado sem "Como chegar" ──────────────────────────


class TestPixexp10CancelledPickup:
    def test_cancelled_pickup_has_no_directions(self, order, shop_instance):
        shop_instance.formatted_address = "Rua das Flores, 100, Londrina"
        shop_instance.save(update_fields=["formatted_address"])
        _set(order, fulfillment_type="pickup")
        assert build_order_tracking(order).pickup_info is not None

        _set(order, status="cancelled")

        assert build_order_tracking(order).pickup_info is None


# ── F3: cartão recusado ─────────────────────────────────────────────────────


class TestF3CardDeclined:
    def _card_order(self, order):
        intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="card")
        return _set(
            order,
            payment={"method": "card", "intent_ref": intent.ref, "checkout_url": "https://checkout.example/cs_1"},
        )

    def test_declined_card_says_so_and_offers_another_card(self, order_with_payment):
        order = self._card_order(order_with_payment)
        _set(order, payment={**order.data["payment"], "last_decline": {"code": "card_declined", "at": "x"}})

        proj = build_order_tracking(order)

        assert proj.promise.state == "payment_card_declined"
        assert proj.promise.tone == "warning"
        assert proj.promise.title == "O cartão não foi aprovado"
        assert "outro cartão" in proj.promise.message
        assert [action.ref for action in proj.promise.actions] == ["pay_card"]
        assert proj.promise.checkout_url == "https://checkout.example/cs_1"

    def test_gateway_check_records_the_decline(self, order_with_payment):
        order = self._card_order(order_with_payment)

        class _Adapter:
            @staticmethod
            def check_gateway_status(intent_ref):
                return "declined"

        with patch.object(payment_service, "_adapter_for_persisted_intent", return_value=_Adapter):
            state = payment_service.settle_from_gateway(order)

        order.refresh_from_db()
        assert state == "unpaid"
        assert order.data["payment"]["last_decline"]["code"] == "declined"
        assert build_order_tracking(order).promise.state == "payment_card_declined"

    def test_stripe_reads_requires_payment_method_with_error_as_declined(self, order_with_payment):
        from types import SimpleNamespace

        from shopman.shop.adapters import payment_stripe

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref, amount_q=2500, method="card", gateway_id="pi_123"
        )
        fake = SimpleNamespace(
            PaymentIntent=SimpleNamespace(
                retrieve=lambda _id: SimpleNamespace(
                    status="requires_payment_method",
                    amount_received=0,
                    last_payment_error=SimpleNamespace(code="card_declined"),
                )
            )
        )
        with patch.object(payment_stripe, "_get_stripe", return_value=fake):
            assert payment_stripe.check_gateway_status(intent.ref) == "declined"


# ── PIXEXP-06 e SMS-11: Pix pago antes de a loja aceitar ───────────────────


class TestPaidBeforeAcceptance:
    def test_paid_pix_with_store_closed_says_payment_received(self, order_with_payment, shop_instance):
        _open_hours(shop_instance)
        _captured_intent(order_with_payment)
        order_with_payment.data["payment"]["intent_ref"] = PaymentService.get_by_order(order_with_payment.ref).first().ref
        order_with_payment.save(update_fields=["data"])

        with patch(
            "shopman.shop.services.business_calendar.timezone.now",
            return_value=datetime(2026, 5, 4, 5, 40, tzinfo=_TZ),
        ):
            proj = build_order_tracking(order_with_payment)

        assert proj.promise.state == "store_closed"
        assert proj.promise.message.startswith("Pagamento recebido. Estamos fechados agora")

    def test_payment_step_comes_before_acceptance_and_is_never_current(self, order_with_payment):
        intent = _captured_intent(order_with_payment)
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])

        proj = build_order_tracking(order_with_payment)
        assert [(s.key, s.state) for s in proj.progress_steps] == [
            ("received", "completed"),
            ("payment", "completed"),
        ]

        order_with_payment.transition_status("accepted", actor="test")
        order_with_payment.refresh_from_db()
        proj = build_order_tracking(order_with_payment)

        assert [(s.key, s.state) for s in proj.progress_steps] == [
            ("received", "completed"),
            ("payment", "completed"),
            ("availability", "completed"),
        ]


# ── SMS-02: a promessa respeita a janela combinada e o expediente ─────────


class TestSms02PromisedWindow:
    def test_early_preparing_does_not_promise_before_the_delivery_window(self, order):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        _set(order, fulfillment_type="delivery", delivery_date=tomorrow, delivery_time_slot="15:00-15:30")
        order.transition_status("accepted", actor="test")
        order.transition_status("preparing", actor="test")
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.promise.message == "Entrega combinada para amanhã, 15:00 às 15:30. Avisamos quando sair."
        assert proj.eta_display == "15:00"

    def test_ready_pickup_before_the_window_says_when_to_come(self, order):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        _set(order, fulfillment_type="pickup", delivery_date=tomorrow, delivery_time_slot="slot-15")
        for status in ("accepted", "preparing", "ready"):
            order.transition_status(status, actor="test")
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.promise.state == "ready_pickup"
        assert proj.promise.message == "Já está separado. Pode retirar a partir de amanhã às 15h."


# ── SMS-14: pedido concluído ─────────────────────────────────────────────────


class TestSms14CompletedOrder:
    def test_completed_order_has_no_cancellation_request_and_thanks_in_feminine(self, order):
        _set(order, status="completed")

        proj = build_order_tracking(order)

        assert "request_cancellation" not in [action.ref for action in proj.actions]
        assert proj.promise.message == "Obrigada pela preferência!"
        assert proj.copy.rating_thanks_title == "Obrigada!"

    def test_dispatched_order_can_still_request_cancellation(self, order):
        _set(order, status="dispatched")

        assert "request_cancellation" in [action.ref for action in build_order_tracking(order).actions]


# ── F6: a ação de cancelar não carrega diálogo morto com jargão ──────────────


class TestF6CancelActionContract:
    def test_cancel_order_action_has_no_dead_confirmation(self, order):
        proj = build_order_tracking(order)

        cancel = next(action for action in proj.actions if action.ref == "cancel_order")
        assert cancel.confirmation == {}
