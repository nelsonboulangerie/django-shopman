"""O dinheiro às claras no acompanhamento (WP-L06 do plano EXCELENCIA-STOREFRONT).

P1-10: pedido pago e cancelado mostrava "Recebido, Cancelado" no Histórico. O
"Pago" sumia com o estorno (o passo depende do saldo capturado) e não entrava
"Devolvido"; o Resumo dizia só "Pagamento recebido", sem meio, valor nem hora.

P1-07: a encomenda paga que a loja ainda não aceitou não dizia que o valor volta
se ela não puder confirmar.

P2-10: o "Enviar resumo" levava "amanhã", num texto lido depois e por outra pessoa.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import formats, timezone
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.storefront.presentation.order_tracking import build_order_tracking

pytestmark = pytest.mark.django_db


def _set(order, *, status=None, **data):
    fields = {"data": {**(order.data or {}), **data}}
    if status:
        fields["status"] = status
    Order.objects.filter(pk=order.pk).update(**fields)
    order.refresh_from_db()
    return order


def _paid_by_pix(order):
    """Pedido pago por Pix: o intent capturado e o evento que a captura grava."""
    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="pix")
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    order.emit_event(
        event_type="payment.captured",
        actor="test",
        payload={"method": "pix", "amount_q": order.total_q, "intent_ref": intent.ref},
    )
    _set(order, payment={**order.data["payment"], "intent_ref": intent.ref, "status": "captured"})
    return intent


def _cancelled_and_refunded(order, intent, *, reason="confirmation_timeout"):
    """A ordem real: o pedido cancela, e o cancelamento devolve o dinheiro."""
    order.transition_status("cancelled", actor="test")
    order.refresh_from_db()
    _set(order, cancellation_reason=reason)
    PaymentService.refund(intent.ref, reason="cancelled")
    order.emit_event(
        event_type="payment.refunded",
        actor="test",
        payload={"method": "pix", "amount_q": order.total_q, "intent_ref": intent.ref},
    )
    return order


def _steps(proj):
    return [(step.key, step.label, step.state) for step in proj.progress_steps]


class TestHistoryKeepsTheMoney:
    def test_paid_then_cancelled_shows_paid_and_refunded_with_amount_and_time(self, order_with_payment):
        intent = _paid_by_pix(order_with_payment)
        _cancelled_and_refunded(order_with_payment, intent)

        proj = build_order_tracking(order_with_payment)

        keys = [step.key for step in proj.progress_steps]
        assert keys == ["received", "payment", "cancelled", "refunded"], _steps(proj)
        paid = next(step for step in proj.progress_steps if step.key == "payment")
        refunded = next(step for step in proj.progress_steps if step.key == "refunded")
        assert paid.label == "Pago" and paid.state == "completed"
        assert paid.timestamp_display
        assert refunded.label == "Devolvido · R$ 25,00"
        assert refunded.state == "completed"
        assert refunded.timestamp_display

    def test_paid_and_alive_keeps_the_single_paid_step(self, order_with_payment):
        _paid_by_pix(order_with_payment)

        proj = build_order_tracking(order_with_payment)

        keys = [step.key for step in proj.progress_steps]
        assert keys.count("payment") == 1
        assert "refunded" not in keys

    def test_cancelled_without_payment_has_no_money_steps(self, order_with_payment):
        order_with_payment.transition_status("cancelled", actor="test")
        order_with_payment.refresh_from_db()
        _set(order_with_payment, cancellation_reason="payment_timeout")

        proj = build_order_tracking(order_with_payment)

        keys = [step.key for step in proj.progress_steps]
        assert keys[-1] == "cancelled"
        assert "payment" not in keys and "refunded" not in keys


class TestPaymentSummarySaysMethodAmountAndTime:
    def test_pix_paid_today_says_method_and_time(self, order_with_payment):
        from datetime import UTC, datetime
        from unittest.mock import patch
        from zoneinfo import ZoneInfo

        # Relógio parado ao meio-dia: pago agora é "hoje", sem a data, em qualquer hora da rodada.
        noon = datetime(2026, 11, 20, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        with patch("django.utils.timezone.now", return_value=noon.astimezone(UTC)):
            _paid_by_pix(order_with_payment)
            label = build_order_tracking(order_with_payment).payment_status_label

        assert label.startswith("Pix")
        assert label.endswith(", pago às 12h")

    def test_amount_enters_when_the_projection_brings_it(self, order_with_payment):
        _paid_by_pix(order_with_payment)

        proj = build_order_tracking(order_with_payment)

        # ``paid_amount_q`` só vem enquanto o pedido pode ser cancelado; quando vem,
        # o resumo o diz. Sem ele, não inventa valor.
        if "R$" in proj.payment_status_label:
            assert "Pix de R$ 25,00, pago" in proj.payment_status_label
        else:
            assert proj.payment_status_label.startswith("Pix, pago")

    def test_paid_without_a_capture_event_keeps_the_plain_label(self, order_paid):
        # Pago no balcão ou por outro caminho: sem evento de captura, o meio não é
        # conhecido com certeza, e o rótulo não afirma "Cartão".
        label = build_order_tracking(order_paid).payment_status_label

        assert label in (None, "Pagamento recebido")

    def test_pending_payment_is_not_called_paid(self, order_with_payment):
        assert build_order_tracking(order_with_payment).payment_status_label == "Aguardando pagamento"


class TestPaidPreorderAwaitingTheStorePromisesTheRefund:
    @pytest.mark.parametrize("when", ["sábado, 19/07", None])
    def test_payment_confirmed_preorder_says_the_money_comes_back(self, when):
        from shopman.shop.projections.copy import build_copy
        from shopman.storefront.presentation.order_tracking import _promise_copy
        from shopman.storefront.tests.web.test_tracking_promise_cascade import _preorder_wait_data

        data = _preorder_wait_data("payment_confirmed")

        title, message = _promise_copy(
            data, status="new", is_delivery=False, copy=build_copy("TRACKING"),
            when_display=when, payment_confirmed=True,
        )

        assert title == "Pagamento recebido"
        # Com dia combinado quem nomeia a encomenda é a frase do dia; sem ele, a do aceite.
        assert message.startswith("A loja confirma e avisa" if when else "A loja confirma sua encomenda")
        assert message.count("encomenda") == 1
        assert "Se não puder, devolvemos o valor." in message
        assert "Pagamento recebido" not in message, "o título já diz; a frase não repete"
        assert "{when}" not in message
        if when:
            # O dia da encomenda vai em frase própria, depois da do aceite (#2749).
            assert message.endswith(f"Sua encomenda é para {when}.")
        else:
            assert message.endswith("Se não puder, devolvemos o valor.")

    def test_accepted_preorder_does_not_promise_a_refund(self):
        from shopman.shop.projections.copy import build_copy
        from shopman.storefront.presentation.order_tracking import _promise_copy
        from shopman.storefront.tests.web.test_tracking_promise_cascade import _preorder_wait_data

        data = _preorder_wait_data("payment_confirmed")

        _title, message = _promise_copy(
            data, status="confirmed", is_delivery=False, copy=build_copy("TRACKING"),
            when_display="sábado, 19/07", payment_confirmed=True,
        )

        assert "devolvemos" not in message


class TestShareTextDatesAreAbsolute:
    def _share(self, order_items, **data):
        Order.objects.filter(pk=order_items.pk).update(data={"fulfillment_type": "pickup", **data})
        order_items.refresh_from_db()
        return build_order_tracking(order_items).share_text

    def test_tomorrow_is_written_as_weekday_and_date(self, order_items):
        tomorrow = timezone.localdate() + timedelta(days=1)

        text = self._share(order_items, delivery_date=tomorrow.isoformat(), delivery_time_slot="09:00-09:30")

        expected = f"{formats.date_format(tomorrow, 'l').lower()}, {formats.date_format(tomorrow, 'd/m')}"
        assert f"Retirada: {expected} · " in text
        assert "amanhã" not in text and "hoje" not in text

    def test_today_is_written_as_weekday_and_date_too(self, order_items):
        today = timezone.localdate()

        text = self._share(order_items, delivery_date=today.isoformat(), delivery_time_slot="19:30-20:00")

        expected = f"{formats.date_format(today, 'l').lower()}, {formats.date_format(today, 'd/m')}"
        assert f"Retirada: {expected} · 19h30 às 20h" in text
        assert "hoje" not in text


class TestStandaloneValuesStartWithACapital:
    def test_schedule_label_of_tomorrow_is_capitalized(self, order_items):
        tomorrow = timezone.localdate() + timedelta(days=1)
        Order.objects.filter(pk=order_items.pk).update(
            data={"fulfillment_type": "pickup", "delivery_date": tomorrow.isoformat(), "delivery_time_slot": "09:00-09:30"},
        )
        order_items.refresh_from_db()

        proj = build_order_tracking(order_items)

        assert proj.schedule_display.startswith("Amanhã · ")
        assert proj.pickup_info is None or proj.pickup_info.when_display.startswith("Amanhã · ")


class TestTheAgreedTimeInsideASentence:
    """#2752: dentro de frase o combinado vai na forma de frase, nunca na de rótulo."""

    def test_preorder_message_has_no_label_separator(self, order_items):
        tomorrow = timezone.localdate() + timedelta(days=1)
        Order.objects.filter(pk=order_items.pk).update(
            status="confirmed",
            data={"fulfillment_type": "pickup", "delivery_date": tomorrow.isoformat(), "delivery_time_slot": "09:00-09:30"},
        )
        order_items.refresh_from_db()

        proj = build_order_tracking(order_items)

        assert " · " not in proj.promise.message
        assert "amanhã, " in proj.promise.message
        # O rótulo isolado continua na forma de rótulo.
        assert proj.schedule_display.startswith("Amanhã · ")

    @pytest.mark.parametrize("state", ["store_checking", "payment_confirmed", "payment_authorized", "received"])
    def test_every_waiting_sentence_takes_the_phrase_form(self, state):
        from shopman.shop.projections.copy import build_copy
        from shopman.storefront.presentation.order_tracking import _promise_copy
        from shopman.storefront.tests.web.test_tracking_promise_cascade import _preorder_wait_data

        _title, message = _promise_copy(
            _preorder_wait_data(state), status="new", is_delivery=False, copy=build_copy("TRACKING"),
            when_display="amanhã · A partir das 15h", when_phrase="amanhã, a partir das 15h",
            payment_confirmed=state in {"store_checking", "payment_confirmed"},
        )

        assert " · " not in message
        assert "amanhã, a partir das 15h" in message
