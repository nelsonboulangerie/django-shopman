"""Ciclo de vida da fila de espera — fermata → confirmação → liberação (WP-P2E F2).

A fila é uma compra em DUAS fases. A reserva (fermata) não cobra e não corre
relógio: espera a fornada. Quando a fornada sai, a vaga não vira pedido
sozinha — o cliente confirma dentro de um prazo. Quem não confirma perde a
vaga para o próximo, e ninguém descobre isso por acaso: liberação é anunciada
ao cliente E à loja.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant

from shopman.shop.services import waitlist

pytestmark = pytest.mark.django_db

SKU = "PAO-DE-FILA"
TOMORROW = timedelta(days=1)


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _planned_quant(qty="10", target: date | None = None):
    quant, _ = Quant.objects.get_or_create(
        sku=SKU,
        position=_position(),
        target_date=target or (date.today() + TOMORROW),
        batch="",
        defaults={"metadata": {}},
    )
    quant._quantity = Decimal(qty)
    quant.save(update_fields=["_quantity"])
    return quant


def _order_in_fermata(ref: str, qty="2", *, quant=None, created_at=None) -> Order:
    """Pedido com reserva de fila adotada — o estado que o commit deixa."""
    order = Order.objects.create(ref=ref, channel_ref="web", status="new", total_q=1000)
    hold = Hold.objects.create(
        sku=SKU,
        quant=quant or _planned_quant(),
        quantity=Decimal(qty),
        target_date=date.today() + TOMORROW,
        status=HoldStatus.PENDING,
        expires_at=None,
        metadata={"reference": f"order:{ref}", "planned": True},
    )
    if created_at is not None:
        Hold.objects.filter(pk=hold.pk).update(created_at=created_at)
    return order


class TestStateIsDerivedFromTheHold:
    def test_indefinite_planned_hold_reads_as_fermata(self):
        order = _order_in_fermata("W-1")

        assert waitlist.state_for(order) == waitlist.FERMATA

    def test_order_without_planned_hold_is_not_in_the_queue(self):
        order = Order.objects.create(ref="W-2", channel_ref="web", status="new", total_q=100)

        assert waitlist.state_for(order) == waitlist.NONE


class TestOpenWindowServesFirstComeFirstServed:
    def test_the_batch_is_served_in_arrival_order_until_it_runs_out(self):
        now = timezone.now()
        quant = _planned_quant("3")
        first = _order_in_fermata("W-A", "2", quant=quant, created_at=now - timedelta(minutes=10))
        second = _order_in_fermata("W-B", "2", quant=quant, created_at=now - timedelta(minutes=5))

        opened = waitlist.open_window(SKU, qty_available=Decimal("3"))

        assert opened == ["W-A"], "quem reservou antes é servido antes"
        first.refresh_from_db()
        second.refresh_from_db()
        assert waitlist.state_for(first) == waitlist.CONFIRMING
        assert waitlist.state_for(second) == waitlist.FERMATA, (
            "não cabe inteiro na sobra: continua na fila, não é servido pela metade"
        )

    def test_the_window_carries_a_deadline(self):
        _order_in_fermata("W-C", "1")

        waitlist.open_window(SKU, qty_available=Decimal("5"))

        order = Order.objects.get(ref="W-C")
        block = order.data["waitlist"]
        assert block["state"] == waitlist.CONFIRMING
        assert block["deadline"], "a janela tem prazo — senão a vaga fica presa"
        assert block["sku"] == SKU


class TestConfirmation:
    def test_confirming_inside_the_window_locks_the_order(self):
        order = _order_in_fermata("W-D", "1")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        assert waitlist.confirm(order) is True
        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMED

    def test_confirming_after_the_deadline_loses_the_slot(self):
        order = _order_in_fermata("W-E", "1")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()
        data = dict(order.data)
        data["waitlist"]["deadline"] = (timezone.now() - timedelta(minutes=1)).isoformat()
        Order.objects.filter(pk=order.pk).update(data=data)
        order.refresh_from_db()

        assert waitlist.confirm(order) is False
        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.RELEASED

    def test_an_order_not_in_the_window_cannot_confirm(self):
        order = _order_in_fermata("W-F", "1")

        assert waitlist.confirm(order) is False


class TestReleaseIsNeverSilent:
    def test_release_warns_the_customer_and_the_store_and_frees_the_hold(self):
        from shopman.orderman.models import Directive

        from shopman.backstage.models import OperatorAlert

        order = _order_in_fermata("W-G", "1")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        waitlist.release(order, reason="confirmation_timeout")

        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.RELEASED
        assert Hold.objects.filter(
            metadata__reference="order:W-G", status=HoldStatus.PENDING,
        ).count() == 0, "a vaga volta ao estoque"
        assert Directive.objects.filter(
            topic="notification.send", payload__template="waitlist_released",
        ).exists(), "o cliente sabe que saiu da fila"
        assert OperatorAlert.objects.filter(type="waitlist_released").exists(), (
            "a loja sabe que abriu vaga — ela decide gôndola ou fila"
        )

    def test_the_freed_slot_goes_to_the_next_in_line(self):
        now = timezone.now()
        quant = _planned_quant("2")
        first = _order_in_fermata("W-H", "2", quant=quant, created_at=now - timedelta(minutes=10))
        _order_in_fermata("W-I", "2", quant=quant, created_at=now - timedelta(minutes=5))

        waitlist.open_window(SKU, qty_available=Decimal("2"))
        first.refresh_from_db()
        waitlist.release(first, reason="confirmation_timeout")

        second = Order.objects.get(ref="W-I")
        assert waitlist.state_for(second) == waitlist.CONFIRMING, (
            "serve_next: a fila tem preferência sobre a gôndola"
        )


class TestSweep:
    def test_expired_windows_are_swept(self):
        order = _order_in_fermata("W-J", "1")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()
        data = dict(order.data)
        data["waitlist"]["deadline"] = (timezone.now() - timedelta(minutes=1)).isoformat()
        Order.objects.filter(pk=order.pk).update(data=data)

        assert waitlist.sweep_expired() == 1
        assert Order.objects.get(ref="W-J").data["waitlist"]["state"] == waitlist.RELEASED

    def test_a_live_window_is_left_alone(self):
        _order_in_fermata("W-K", "1")
        waitlist.open_window(SKU, qty_available=Decimal("5"))

        assert waitlist.sweep_expired() == 0


class TestChargeHappensAtConfirmation:
    def test_confirming_starts_the_charge_not_the_reservation(self):
        from shopman.orderman.models import Directive

        order = _order_in_fermata("W-L", "1")
        order.data = {**(order.data or {}), "payment": {"method": "pix"}}
        order.save(update_fields=["data"])
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        assert not Directive.objects.filter(
            topic="notification.send", payload__template="payment_requested",
        ).exists(), "a reserva não cobra nada — é o que torna desistir barato"

        waitlist.confirm(order)

        assert Directive.objects.filter(
            topic="notification.send", payload__template="payment_requested",
        ).exists(), "confirmou, cobra — charge_at=confirmation"


class TestPriceIsFrozenAtReservation:
    def test_the_config_says_the_reservation_price_is_the_confirmation_price(self):
        cfg = waitlist.config("web")

        assert cfg.price_frozen is True, (
            "preço congelado na reserva: confirmar não pode virar surpresa"
        )
        assert cfg.charge_at == "confirmation"


class TestQueueReport:
    def test_the_report_answers_how_many_are_waiting_and_for_how_long(self):
        now = timezone.now()
        quant = _planned_quant("10")
        _order_in_fermata("W-M", "2", quant=quant, created_at=now - timedelta(minutes=10))
        _order_in_fermata("W-N", "3", quant=quant, created_at=now - timedelta(minutes=5))

        rows = waitlist.report()

        assert len(rows) == 1
        row = rows[0]
        assert row["sku"] == SKU
        assert row["waiting"] == 2
        assert row["qty_reserved"] == "5"
        assert [e["order_ref"] for e in row["queue"]] == ["W-M", "W-N"], "ordem FCFS"
        assert row["queue"][0]["position"] == 1
        assert row["queue"][0]["batch_date"] == (date.today() + TOMORROW).isoformat()

    def test_no_queue_is_an_empty_report_not_a_crash(self):
        assert waitlist.report() == []


class TestTheOperatorCannotPrepareWhatIsNotBaked:
    """⚠️ O selo avisava e o botão continuava vivo — avisar não é barrar.

    Reserva em fermata espera pão que AINDA NÃO EXISTE. O card do Gestor já
    trazia "Na fila da fornada", mas "Iniciar preparo" seguia clicável ao lado:
    um toque mandava para o KDS uma separação impossível de fazer, e a linha da
    cozinha só descobria isso na hora de separar.

    Não é encomenda (não há data combinada com o cliente, então o bloqueio de
    encomenda não a alcança) nem falta de pagamento (o dinheiro pode já ter
    entrado). É um terceiro motivo, e por isso é um código próprio.
    """

    def _accepted(self, ref: str) -> Order:
        order = _order_in_fermata(ref, "1")
        Order.objects.filter(pk=order.pk).update(status="accepted")
        order.refresh_from_db()
        return order

    def test_the_prep_button_is_barred_while_the_batch_has_not_come_out(self):
        from shopman.shop.services import operator_orders

        order = self._accepted("W-BTN-1")

        assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.WAITLIST_FERMATA
        with pytest.raises(ValueError):
            operator_orders.advance_order(order, actor="operador")

    def test_the_bar_lifts_when_the_window_opens(self):
        """Contraprova: chamado o cliente, o pão existe e o preparo abre.

        Sem esta metade, barrar a fermata poderia virar barrar a fila inteira.
        """
        from shopman.shop.services import operator_orders

        order = self._accepted("W-BTN-2")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        assert waitlist.state_for(order) == waitlist.CONFIRMING
        assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE

    def test_an_ordinary_order_is_not_barred(self):
        from shopman.shop.services import operator_orders

        order = Order.objects.create(
            ref="W-BTN-3", channel_ref="web", status="accepted", total_q=100,
        )

        assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE
