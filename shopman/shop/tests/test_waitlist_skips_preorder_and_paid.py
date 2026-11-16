"""Encomenda e pedido pago não são entrada da fila de espera.

⚠️ Laudo beta de 09/11 (P1, com risco P0): uma encomenda PAGA para data futura
mostrava no acompanhamento "Você está na fila... Nada foi cobrado ainda". A
causa era o carimbo: toda reserva contra fornada planejada nasce com
``metadata.planned``, a da encomenda também, e ``waitlist.state_for`` derivava
``fermata`` de qualquer hold planejado sem prazo, sem perguntar de quem era.

O mesmo carimbo levava a encomenda ao resto da máquina da fila. Quando a
fornada sai, ``StockPlanning.realize`` transfere o hold ao estoque físico e
``open_window`` chamava o cliente para "confirmar" um pedido que ele já pagou;
vencido o prazo, ``sweep_expired`` soltava as reservas do pedido e avisava
"liberamos a sua vaga. Nada foi cobrado". Pão pago devolvido à gôndola.

A fila é uma compra em duas fases que promete de graça e cobra na confirmação.
Encomenda é outra promessa (a casa produz para uma pessoa numa data combinada)
e pedido já pago não tem o que confirmar. Nenhum dos dois entra na fila, e a
fila nunca solta a reserva deles.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant
from shopman.stockman.services.holds import (
    QUALITY_GRADE_POLICY_VERSION,
    QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
)

from shopman.shop.services import waitlist

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

SKU = "PAO-ENCOMENDA-FILA"


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _order_with_planned_hold(ref: str, *, data: dict | None = None, status: str = "new") -> Order:
    target = date.today() + timedelta(days=1)
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=5000,
        handle_type="guest",
        handle_ref="teste",
        data={"fulfillment_type": "pickup", **(data or {})},
    )
    quant = Quant.objects.create(
        sku=SKU,
        position=_position(),
        target_date=target,
        batch=f"{ref}-PLAN",
        _quantity=Decimal("10"),
    )
    hold = Hold.objects.create(
        sku=SKU,
        quant=quant,
        quantity=Decimal("2"),
        target_date=target,
        status=HoldStatus.PENDING,
        expires_at=None,
        metadata={
            "reference": f"order:{ref}",
            "planned": True,
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
        },
    )
    order.data = {
        **order.data,
        "hold_ids": [{"sku": SKU, "hold_id": hold.hold_id, "qty": float(hold.quantity)}],
    }
    order.save(update_fields=["data"])
    return order


def _preorder_data() -> dict:
    return {
        "delivery_date": (date.today() + timedelta(days=1)).isoformat(),
        "delivery_time_slot": "slot-09",
        "is_preorder": True,
    }


def _pay(order: Order) -> None:
    """Pix capturado no Payman cobrindo o total do pedido."""
    from shopman.payman import PaymentService

    intent_ref = f"INT-{order.ref}"
    PaymentService.create_intent(order.ref, order.total_q, "pix", gateway="efi", ref=intent_ref)
    PaymentService.authorize(intent_ref, gateway_id=f"txid-{order.ref}")
    PaymentService.capture(intent_ref)
    order.data = {**order.data, "payment": {"method": "pix", "intent_ref": intent_ref}}
    order.save(update_fields=["data"])


def _materialize(order: Order) -> None:
    """O estado que ``StockPlanning.realize`` deixa: quant físico e TTL vivo."""
    holds = list(Hold.objects.filter(metadata__reference=f"order:{order.ref}"))
    physical = Quant.objects.create(
        sku=SKU,
        position=_position(),
        target_date=None,
        batch=f"{order.ref}-REAL",
        _quantity=sum((hold.quantity for hold in holds), Decimal("0")),
    )
    for hold in holds:
        hold.quant = physical
        hold.expires_at = timezone.now() + timedelta(hours=48)
        hold.save(update_fields=["quant", "expires_at"])


def _force_expired_window(order: Order) -> None:
    """Janela vencida gravada antes da correção (dado vivo do alpha)."""
    order.refresh_from_db()
    data = dict(order.data or {})
    data["waitlist"] = {
        "state": waitlist.CONFIRMING,
        "sku": SKU,
        "qty": "2",
        "deadline": (timezone.now() - timedelta(minutes=1)).isoformat(),
    }
    Order.objects.filter(pk=order.pk).update(data=data)
    order.refresh_from_db()


def _live_holds(order: Order) -> list[Hold]:
    return list(
        Hold.objects.filter(
            metadata__reference=f"order:{order.ref}",
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        )
    )


class TestPreorderIsNotInTheQueue:
    def test_paid_preorder_does_not_read_as_fermata(self):
        from shopman.shop.projections.order_tracking import build_tracking

        order = _order_with_planned_hold("ENC-PAGA", data=_preorder_data())
        _pay(order)

        assert waitlist.state_for(order) == waitlist.NONE
        assert waitlist.states_for([order]) == {order.ref: waitlist.NONE}
        assert waitlist.queue_for(SKU) == []
        # A tela desenha "Você está na fila... Nada foi cobrado ainda" quando lê
        # ``fermata``; ``none`` deixa a cascata da encomenda falar.
        assert build_tracking(order).waitlist_state == "none"

    def test_accepted_unpaid_preorder_does_not_read_as_fermata(self):
        order = _order_with_planned_hold(
            "ENC-ACEITA",
            data={**_preorder_data(), "payment": {"method": "cash"}},
            status="accepted",
        )

        assert waitlist.state_for(order) == waitlist.NONE

    def test_batch_out_does_not_call_the_paid_preorder_to_confirm(self):
        order = _order_with_planned_hold("ENC-FORNADA", data=_preorder_data())
        _pay(order)
        _materialize(order)

        assert waitlist.open_window(SKU, qty_available=Decimal("10")) == []
        assert waitlist.reconcile_materialized_windows() == 0
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_sweep_never_releases_the_paid_preorder_reservation(self):
        order = _order_with_planned_hold("ENC-SWEEP", data=_preorder_data())
        _pay(order)
        _materialize(order)
        _force_expired_window(order)

        assert waitlist.state_for(order) == waitlist.NONE
        assert waitlist.sweep_expired() == 0
        assert waitlist.release(order, reason="confirmation_timeout") == []
        order.refresh_from_db()
        assert order.data["waitlist"]["state"] == waitlist.CONFIRMING
        assert [hold.quantity for hold in _live_holds(order)] == [Decimal("2")]


class TestPaidOrderIsNeverReleasedByTheQueue:
    def test_batch_out_does_not_open_a_window_for_a_paid_order(self):
        order = _order_with_planned_hold("PAGO-HOJE")
        _pay(order)
        _materialize(order)

        assert waitlist.open_window(SKU, qty_available=Decimal("10")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_expired_window_of_a_paid_order_keeps_the_reservation(self):
        order = _order_with_planned_hold("PAGO-VENCIDO")
        _pay(order)
        _materialize(order)
        _force_expired_window(order)

        assert waitlist.sweep_expired() == 0
        assert waitlist.release(order, reason="confirmation_timeout") == []
        order.refresh_from_db()
        assert order.data["waitlist"]["state"] == waitlist.CONFIRMING
        assert [hold.quantity for hold in _live_holds(order)] == [Decimal("2")]

    def test_paid_order_waiting_for_the_batch_is_not_told_nothing_was_charged(self):
        from shopman.shop.projections.order_tracking import build_tracking

        order = _order_with_planned_hold("PAGO-ESPERA")
        _pay(order)

        tracking = build_tracking(order)

        assert waitlist.state_for(order) == waitlist.NONE
        assert tracking.waitlist_state == "none"
        # A espera pela fornada continua dita, pela cascata, com o pagamento.
        assert tracking.promise.fulfillment_wait_kind == "planned_batch"


class TestTheQueueStillWorksForFreeReservations:
    """Contraprova: reserva de fila sem pagamento segue o ciclo de sempre."""

    def test_unpaid_same_day_reservation_opens_and_is_released(self):
        order = _order_with_planned_hold("FILA-LIVRE")

        assert waitlist.state_for(order) == waitlist.FERMATA
        _materialize(order)
        assert waitlist.open_window(SKU, qty_available=Decimal("10")) == [order.ref]
        order.refresh_from_db()
        data = dict(order.data)
        data["waitlist"]["deadline"] = (timezone.now() - timedelta(minutes=1)).isoformat()
        Order.objects.filter(pk=order.pk).update(data=data)

        assert waitlist.sweep_expired() == 1
        order.refresh_from_db()
        assert order.data["waitlist"]["state"] == waitlist.RELEASED
        assert _live_holds(order) == []
