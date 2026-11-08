"""Cartão recusado: pagar com Pix no mesmo pedido (beta 06/11, F3, decisão do dono).

Cada teste reprova sem a troca: antes dela, o degrau ``payment_card_declined``
só oferecia ``pay_card`` e não havia caminho para o Pix sem cancelar o pedido.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.orderman.models import Directive, Order
from shopman.payman import PaymentIntent as PaymanIntent
from shopman.payman import PaymentService

from shopman.shop.adapters.payment_types import PaymentResult
from shopman.shop.directives import PAYMENT_TIMEOUT
from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service
from shopman.storefront.presentation.order_tracking import build_order_tracking

pytestmark = pytest.mark.django_db

SWITCH_URL = "/api/v1/orders/{ref}/payment/switch-to-pix/"


class _CardGateway:
    """O Stripe do teste: responde a conferência e registra o cancelamento."""

    def __init__(self, *, status="declined", cancel_ok=True):
        self.status = status
        self.cancel_ok = cancel_ok
        self.cancelled: list[tuple[str, dict]] = []

    def check_gateway_status(self, intent_ref):
        return self.status

    def cancel(self, intent_ref, **config):
        self.cancelled.append((intent_ref, config))
        if self.cancel_ok:
            return PaymentResult(success=True)
        return PaymentResult(success=False, error_code="stripe_error", message="recusado")


def _route_card_to(gateway):
    original = payment_service._adapter_for_persisted_intent

    def route(intent_ref, *, method):
        if str(method).lower() == "card":
            return gateway
        return original(intent_ref, method=method)

    return patch.object(payment_service, "_adapter_for_persisted_intent", side_effect=route)


def _web_accepts(methods, *, timing="at_commit"):
    channel = Channel.objects.get(ref="web")
    channel.config = {**(channel.config or {}), "payment": {"method": methods, "timing": timing}}
    channel.save(update_fields=["config"])


def _declined_card_order(order):
    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="card")
    Order.objects.filter(pk=order.pk).update(
        data={
            **(order.data or {}),
            "payment": {
                "method": "card",
                "intent_ref": intent.ref,
                "idempotency_key": "card-key-1",
                "checkout_url": "https://checkout.example/cs_1",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "last_decline": {"code": "card_declined", "at": "2026-11-06T10:00:00+00:00"},
            },
        }
    )
    order.refresh_from_db()
    return order, intent


class TestOffer:
    def test_declined_card_offers_pix_when_channel_accepts_it(self, order_with_payment):
        _web_accepts(["pix", "card"])
        order, _ = _declined_card_order(order_with_payment)

        proj = build_order_tracking(order)

        refs = [action.ref for action in proj.promise.actions]
        assert refs == ["pay_card", "pay_with_pix"]
        pix = proj.promise.actions[1]
        assert pix.label == "Pagar com Pix"
        assert pix.kind == "mutation"
        assert pix.href == SWITCH_URL.format(ref=order.ref)
        assert pix.idempotency == "required"
        assert proj.promise.message == "Nada foi cobrado. Tente outro cartão no ambiente seguro ou pague com Pix."

    def test_channel_without_pix_does_not_offer_it(self, order_with_payment):
        _web_accepts(["card"])
        order, _ = _declined_card_order(order_with_payment)

        proj = build_order_tracking(order)

        assert [action.ref for action in proj.promise.actions] == ["pay_card"]
        assert "Pix" not in proj.promise.message
        assert payment_service.pix_switch_blocker(order) == "channel_without_pix"

    def test_card_never_declined_does_not_offer_pix(self, order_with_payment):
        _web_accepts(["pix", "card"])
        order, _ = _declined_card_order(order_with_payment)
        payment = dict(order.data["payment"])
        payment.pop("last_decline")
        Order.objects.filter(pk=order.pk).update(data={**order.data, "payment": payment})
        order.refresh_from_db()

        assert [action.ref for action in build_order_tracking(order).promise.actions] == ["pay_card"]


class TestSwitch:
    def test_cancels_card_at_gateway_then_creates_pix_with_its_own_deadline(self, order_with_payment):
        _web_accepts(["pix", "card"])
        order, card = _declined_card_order(order_with_payment)
        gateway = _CardGateway()

        with _route_card_to(gateway):
            assert payment_service.switch_declined_card_to_pix(order) is True

        order.refresh_from_db()
        payment = order.data["payment"]
        # O cartão morreu no gateway ANTES de o Pix nascer, e no Payman também.
        assert [ref for ref, _ in gateway.cancelled] == [card.ref]
        assert PaymentService.get(card.ref).status == "cancelled"
        # O pedido agora é Pix, sem resto do cartão.
        assert payment["method"] == "pix"
        assert payment["intent_ref"] != card.ref
        assert payment["copy_paste"]
        for key in ("checkout_url", "last_decline", "error"):
            assert key not in payment
        assert payment["switched_from_card"]["intent_ref"] == card.ref
        pix = PaymentService.get(payment["intent_ref"])
        assert pix.method == "pix" and pix.status == "pending"
        # O prazo do Pix passa a valer: a directive nova aponta para o Pix.
        assert payment["expires_at"] != "2099-01-01T00:00:00+00:00"
        assert Directive.objects.filter(
            topic=PAYMENT_TIMEOUT, payload__intent_ref=pix.ref
        ).exists()
        # O Gestor lê a troca na linha do tempo.
        event = order.events.get(type=payment_service.PAYMENT_SWITCHED_TO_PIX_EVENT)
        assert event.actor == "customer"
        assert event.payload["from_intent_ref"] == card.ref
        # E a tela passa a mostrar o Pix.
        assert build_order_tracking(order).promise.state == "payment_pix_ready"

    def test_second_tap_switches_once(self, order_with_payment):
        _web_accepts(["pix", "card"])
        order, _ = _declined_card_order(order_with_payment)
        gateway = _CardGateway()

        with _route_card_to(gateway):
            assert payment_service.switch_declined_card_to_pix(order) is True
            assert payment_service.switch_declined_card_to_pix(order) is True

        assert len(gateway.cancelled) == 1
        assert PaymanIntent.objects.filter(order_ref=order.ref, method="pix").count() == 1
        assert order.events.filter(type=payment_service.PAYMENT_SWITCHED_TO_PIX_EVENT).count() == 1

    def test_card_authorized_meanwhile_is_not_switched(self, order_with_payment):
        """Outro cartão concluído noutra aba: não se mata a autorização."""
        _web_accepts(["pix", "card"])
        order, card = _declined_card_order(order_with_payment)
        gateway = _CardGateway(status="requires_capture")

        with _route_card_to(gateway), patch.object(
            payment_service, "settle_from_gateway", return_value="authorized"
        ):
            assert payment_service.switch_declined_card_to_pix(order) is False

        order.refresh_from_db()
        assert gateway.cancelled == []
        assert order.data["payment"]["method"] == "card"
        assert not PaymanIntent.objects.filter(order_ref=order.ref, method="pix").exists()

    def test_gateway_refusing_the_card_cancel_keeps_the_card(self, order_with_payment):
        """Sem o sim do gateway, nada de Pix: dois meios vivos é cobrança dupla."""
        _web_accepts(["pix", "card"])
        order, card = _declined_card_order(order_with_payment)
        gateway = _CardGateway(cancel_ok=False)

        with _route_card_to(gateway):
            assert payment_service.switch_declined_card_to_pix(order) is False

        order.refresh_from_db()
        assert order.data["payment"]["method"] == "card"
        assert order.data["payment"]["intent_ref"] == card.ref
        assert PaymentService.get(card.ref).status == "pending"
        assert not PaymanIntent.objects.filter(order_ref=order.ref, method="pix").exists()

    def test_stock_holds_are_untouched(self, order_with_payment):
        _web_accepts(["pix", "card"])
        order, _ = _declined_card_order(order_with_payment)

        with _route_card_to(_CardGateway()), patch(
            "shopman.shop.services.stock.release"
        ) as release:
            assert payment_service.switch_declined_card_to_pix(order) is True

        release.assert_not_called()


class TestLateCardDecline:
    def test_decline_of_the_dead_card_does_not_reach_the_pix_order(self, order_with_payment):
        _web_accepts(["pix", "card"])
        order, card = _declined_card_order(order_with_payment)
        with _route_card_to(_CardGateway()):
            payment_service.switch_declined_card_to_pix(order)
        order.refresh_from_db()

        payment_service.record_card_decline(order, code="card_declined", intent_ref=card.ref)

        order.refresh_from_db()
        assert "last_decline" not in order.data["payment"]


class TestApi:
    def test_switch_endpoint_returns_the_pix_tracking(self, order_with_payment, client):
        _web_accepts(["pix", "card"])
        order, _ = _declined_card_order(order_with_payment)

        with _route_card_to(_CardGateway()):
            response = client.post(
                SWITCH_URL.format(ref=order.ref),
                HTTP_IDEMPOTENCY_KEY="pay_with_pix-1",
            )

        assert response.status_code == 200, response.content
        assert response.json()["promise"]["state"] == "payment_pix_ready"

    def test_switch_endpoint_refuses_when_pix_is_not_offered(self, order_with_payment, client):
        _web_accepts(["card"])
        order, _ = _declined_card_order(order_with_payment)

        with _route_card_to(_CardGateway()):
            response = client.post(SWITCH_URL.format(ref=order.ref), HTTP_IDEMPOTENCY_KEY="k-2")

        assert response.status_code == 409
        assert response.json()["error_code"] == "pix_switch_unavailable"
        order.refresh_from_db()
        assert order.data["payment"]["method"] == "card"

    def test_switch_endpoint_hides_other_peoples_orders(self, order_with_payment, client):
        _web_accepts(["pix", "card"])
        order, _ = _declined_card_order(order_with_payment)
        client.session.flush()
        other = type(client)()

        response = other.post(SWITCH_URL.format(ref=order.ref), HTTP_IDEMPOTENCY_KEY="k-3")

        assert response.status_code == 404


def test_gestor_labels_the_switch_in_portuguese():
    from shopman.backstage.projections.order_queue import _EVENT_LABELS

    assert _EVENT_LABELS[payment_service.PAYMENT_SWITCHED_TO_PIX_EVENT] == (
        "Cliente trocou o cartão recusado por Pix"
    )

