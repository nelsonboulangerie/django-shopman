"""Ciclo de vida da fila de espera — fermata → confirmação → liberação (WP-P2E F2).

A fila é uma compra em DUAS fases. A reserva (fermata) não cobra e não corre
relógio: espera a fornada. Quando a fornada sai, a vaga não vira pedido
sozinha — o cliente confirma dentro de um prazo. Quem não confirma perde a
vaga para o próximo, e ninguém descobre isso por acaso: liberação é anunciada
ao cliente E à loja.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order
from shopman.stockman.models import Batch, Hold, HoldStatus, Position, PositionKind, Quant
from shopman.stockman.services.holds import (
    QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
    QUALITY_GRADE_POLICY_VERSION,
    QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
)

from shopman.shop.services import waitlist

pytestmark = pytest.mark.django_db

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)

SKU = "PAO-DE-FILA"
TOMORROW = timedelta(days=1)


class TestReservableNextBatch:
    def _channel_product(self, sku: str, *, shelf_life_days: int | None = None):
        from shopman.shop.models import Channel

        channel, _ = Channel.objects.update_or_create(
            ref="web",
            defaults={
                "name": "Web",
                "config": {
                    "waitlist": {"enabled": True, "horizon_days": 2},
                    "stock": {
                        "allowed_positions": ["vitrine"],
                        "sells_nonconforming": False,
                    },
                },
            },
        )
        product = Product.objects.create(
            sku=sku,
            name=sku,
            base_price_q=1000,
            shelf_life_days=shelf_life_days,
            is_published=True,
            is_sellable=True,
        )
        listing, _ = Listing.objects.get_or_create(
            ref="web",
            defaults={"name": "Web", "is_active": True},
        )
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=1000,
            is_published=True,
            is_sellable=True,
        )
        vitrine, _ = Position.objects.get_or_create(
            ref="vitrine",
            defaults={
                "name": "Vitrine",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        deposito, _ = Position.objects.get_or_create(
            ref="deposito",
            defaults={
                "name": "Depósito",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        return channel, product, vitrine, deposito

    def test_next_batch_date_uses_the_same_position_and_qc_scope_as_the_hold(self):
        sku = "FILA-SCOPE-QC"
        _channel, _product, vitrine, deposito = self._channel_product(sku)
        today = timezone.localdate()
        Batch.objects.create(
            ref="MINIMAL-TOMORROW",
            sku=sku,
            quality_grade_ref="minimal",
        )
        Quant.objects.create(
            sku=sku,
            position=deposito,
            target_date=today + timedelta(days=1),
            _quantity=Decimal("100"),
        )
        Quant.objects.create(
            sku=sku,
            position=vitrine,
            target_date=today + timedelta(days=1),
            batch="MINIMAL-TOMORROW",
            _quantity=Decimal("100"),
        )
        Quant.objects.create(
            sku=sku,
            position=vitrine,
            target_date=today + timedelta(days=2),
            _quantity=Decimal("7"),
        )

        next_batch = waitlist.next_batch_availability(sku, channel_ref="web")

        assert next_batch is not None
        target, info = next_batch
        assert target == today + timedelta(days=2)
        assert info["planned"] == Decimal("7")
        assert waitlist.reserve_target_date(
            sku,
            Decimal("1"),
            channel_ref="web",
        ) == target

    def test_catalog_ceiling_is_one_reservable_date_not_the_horizon_sum(self):
        from shopman.shop.projections import catalog_context
        from shopman.shop.services import availability

        sku = "FILA-UMA-DATA"
        _channel, _product, vitrine, _deposito = self._channel_product(
            sku,
            shelf_life_days=0,
        )
        today = timezone.localdate()
        Quant.objects.create(
            sku=sku,
            position=vitrine,
            _quantity=Decimal("3"),
        )
        Quant.objects.create(
            sku=sku,
            position=vitrine,
            target_date=today + timedelta(days=1),
            _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=sku,
            position=vitrine,
            target_date=today + timedelta(days=2),
            _quantity=Decimal("9"),
        )

        raw = catalog_context.availability_for_sku(sku, channel_ref="web")

        assert raw is not None
        assert raw["total_promisable"] == Decimal("5")
        assert waitlist.reserve_target_date(
            sku,
            Decimal("5"),
            channel_ref="web",
        ) == today + timedelta(days=1)
        reserved = availability.reserve(
            sku,
            Decimal("5"),
            session_key="single-date",
            channel_ref="web",
        )
        assert reserved["ok"] is True
        assert Hold.objects.get(
            pk=int(reserved["hold_id"].split(":")[1])
        ).target_date == today + timedelta(days=1)


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
        metadata={
            "reference": f"order:{ref}",
            "planned": True,
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
        },
    )
    order.data = {
        **(order.data or {}),
        "hold_ids": [{"sku": SKU, "hold_id": hold.hold_id, "qty": float(hold.quantity)}],
    }
    order.save(update_fields=["data"])
    if created_at is not None:
        Hold.objects.filter(pk=hold.pk).update(created_at=created_at)
    return order


def _materialize(*orders: Order, qty: Decimal | None = None) -> Quant:
    """Representa o estado produzido pelo StockPlanning.realize nos testes de ciclo."""
    holds = [
        hold
        for order in orders
        for hold in Hold.objects.filter(metadata__reference=f"order:{order.ref}")
    ]
    total = qty if qty is not None else sum((hold.quantity for hold in holds), Decimal("0"))
    physical, _ = Quant.objects.get_or_create(
        sku=SKU,
        position=_position(),
        target_date=None,
        batch=f"{SKU}-MATERIALIZED",
        defaults={"metadata": {}},
    )
    physical._quantity = total
    physical.save(update_fields=["_quantity"])
    expires_at = timezone.now() + timedelta(minutes=30)
    for hold in holds:
        hold.quant = physical
        hold.expires_at = expires_at
        hold.save(update_fields=["quant", "expires_at"])
    return physical


def _expire_confirmation(order: Order) -> None:
    order.refresh_from_db()
    data = dict(order.data or {})
    block = dict(data.get("waitlist") or {})
    block["deadline"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    data["waitlist"] = block
    Order.objects.filter(pk=order.pk).update(data=data)
    order.refresh_from_db()


class TestStateIsDerivedFromTheHold:
    def test_indefinite_planned_hold_reads_as_fermata(self):
        order = _order_in_fermata("W-1")

        assert waitlist.state_for(order) == waitlist.FERMATA

    def test_order_without_planned_hold_is_not_in_the_queue(self):
        order = Order.objects.create(ref="W-2", channel_ref="web", status="new", total_q=100)

        assert waitlist.state_for(order) == waitlist.NONE


class TestWaitlistReservationIntegrity:
    def test_legacy_hold_without_frozen_policy_never_enters_or_opens_the_queue(self):
        from shopman.orderman.models import Directive

        order = _order_in_fermata("W-LEGACY", "1")
        hold = Hold.objects.get(metadata__reference="order:W-LEGACY")
        hold.metadata = {"reference": "order:W-LEGACY", "planned": True}
        hold.save(update_fields=["metadata"])

        assert waitlist.state_for(order) == waitlist.NONE
        assert waitlist.queue_for(SKU) == []
        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data
        assert not Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
        ).exists()

    def test_a_valid_hold_does_not_open_before_realize_transfers_it(self):
        order = _order_in_fermata("W-NOT-YET", "1")

        assert waitlist.state_for(order) == waitlist.FERMATA
        assert waitlist.queue_for(SKU) == [order]
        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == []
        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.FERMATA

    def test_materialized_hold_on_an_over_reserved_quant_does_not_open(self):
        order = _order_in_fermata("W-NEGATIVE", "1")
        physical = _materialize(order, qty=Decimal("0"))

        assert physical.available == Decimal("-1")
        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_materialized_hold_outside_frozen_qc_allowlist_does_not_open(self):
        order = _order_in_fermata("W-QC-BLOCKED", "1")
        hold = Hold.objects.get(metadata__reference="order:W-QC-BLOCKED")
        hold.metadata[QUALITY_GRADE_ALLOWLIST_METADATA_KEY] = ["excellent", "standard"]
        hold.save(update_fields=["metadata"])
        physical = _materialize(order, qty=Decimal("1"))
        hold.refresh_from_db()
        Batch.objects.create(
            ref=physical.batch,
            sku=SKU,
            quality_grade_ref="fair",
            nonconformity_percent=15,
        )

        assert waitlist._quant_reservation_is_sound(hold) is False
        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_materialized_hold_inside_frozen_qc_allowlist_opens(self):
        order = _order_in_fermata("W-QC-ALLOWED", "1")
        hold = Hold.objects.get(metadata__reference="order:W-QC-ALLOWED")
        hold.metadata[QUALITY_GRADE_ALLOWLIST_METADATA_KEY] = ["excellent", "standard"]
        hold.save(update_fields=["metadata"])
        physical = _materialize(order, qty=Decimal("1"))
        hold.refresh_from_db()
        Batch.objects.create(
            ref=physical.batch,
            sku=SKU,
            quality_grade_ref="standard",
            nonconformity_percent=0,
        )

        assert waitlist._quant_reservation_is_sound(hold) is True
        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == [order.ref]

    def test_partial_materialization_does_not_promise_the_whole_order(self):
        order = _order_in_fermata("W-PARTIAL", "1")
        first = Hold.objects.get(metadata__reference="order:W-PARTIAL")
        second = Hold.objects.create(
            sku=SKU,
            quant=first.quant,
            quantity=Decimal("1"),
            target_date=first.target_date,
            status=HoldStatus.PENDING,
            expires_at=None,
            metadata=dict(first.metadata),
        )
        order.data["hold_ids"].append(
            {"sku": SKU, "hold_id": second.hold_id, "qty": float(second.quantity)}
        )
        order.save(update_fields=["data"])
        physical = Quant.objects.create(
            sku=SKU,
            position=_position(),
            target_date=None,
            batch=f"{SKU}-PARTIAL",
            _quantity=Decimal("2"),
        )
        first.quant = physical
        first.expires_at = timezone.now() + timedelta(minutes=30)
        first.save(update_fields=["quant", "expires_at"])

        assert waitlist.state_for(order) == waitlist.FERMATA
        assert waitlist.open_window(SKU, qty_available=Decimal("2")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_second_sku_must_also_materialize_before_the_order_is_called(self):
        from shopman.orderman.models import Directive

        second_sku = "PAO-FILA-SEGUNDO"
        order = _order_in_fermata("W-TWO-SKUS", "1")
        first = Hold.objects.get(metadata__reference="order:W-TWO-SKUS")
        second_plan = Quant.objects.create(
            sku=second_sku,
            position=_position(),
            target_date=first.target_date,
            _quantity=Decimal("1"),
        )
        second = Hold.objects.create(
            sku=second_sku,
            quant=second_plan,
            quantity=Decimal("1"),
            target_date=first.target_date,
            status=HoldStatus.PENDING,
            expires_at=None,
            metadata=dict(first.metadata),
        )
        order.data["hold_ids"].append(
            {"sku": second_sku, "hold_id": second.hold_id, "qty": 1.0}
        )
        order.save(update_fields=["data"])
        first_physical = Quant.objects.create(
            sku=SKU,
            position=_position(),
            target_date=None,
            batch=f"{SKU}-FIRST-MATERIALIZED",
            _quantity=Decimal("1"),
        )
        first.quant = first_physical
        first.expires_at = timezone.now() + timedelta(minutes=30)
        first.save(update_fields=["quant", "expires_at"])

        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == []
        assert not Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
        ).exists()

        second_physical = Quant.objects.create(
            sku=second_sku,
            position=_position(),
            target_date=None,
            batch=f"{second_sku}-MATERIALIZED",
            _quantity=Decimal("1"),
        )
        second.quant = second_physical
        second.expires_at = timezone.now() + timedelta(minutes=30)
        second.save(update_fields=["quant", "expires_at"])

        assert waitlist.open_window(second_sku, qty_available=Decimal("1")) == [order.ref]
        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMING
        assert Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="waitlist_available",
        ).count() == 1

    def test_expired_other_sku_blocks_a_later_batch_from_calling_the_order(self):
        second_sku = "PAO-FILA-ATRASADO"
        order = _order_in_fermata("W-TWO-SKUS-EXPIRED", "1")
        first = Hold.objects.get(metadata__reference="order:W-TWO-SKUS-EXPIRED")
        second_plan = Quant.objects.create(
            sku=second_sku,
            position=_position(),
            target_date=first.target_date,
            _quantity=Decimal("1"),
        )
        second = Hold.objects.create(
            sku=second_sku,
            quant=second_plan,
            quantity=Decimal("1"),
            target_date=first.target_date,
            status=HoldStatus.PENDING,
            expires_at=None,
            metadata=dict(first.metadata),
        )
        order.data["hold_ids"].append(
            {"sku": second_sku, "hold_id": second.hold_id, "qty": 1.0}
        )
        order.save(update_fields=["data"])
        first_physical = Quant.objects.create(
            sku=SKU,
            position=_position(),
            target_date=None,
            batch=f"{SKU}-EXPIRED",
            _quantity=Decimal("1"),
        )
        first.quant = first_physical
        first.expires_at = timezone.now() - timedelta(seconds=1)
        first.save(update_fields=["quant", "expires_at"])
        second_physical = Quant.objects.create(
            sku=second_sku,
            position=_position(),
            target_date=None,
            batch=f"{second_sku}-LIVE",
            _quantity=Decimal("1"),
        )
        second.quant = second_physical
        second.expires_at = timezone.now() + timedelta(minutes=30)
        second.save(update_fields=["quant", "expires_at"])

        assert waitlist.open_window(second_sku, qty_available=Decimal("1")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_expired_ready_item_also_blocks_calling_the_whole_order(self):
        order = _order_in_fermata("W-MIXED-EXPIRED", "1")
        _materialize(order)
        ready_quant = Quant.objects.create(
            sku="ITEM-JA-PRONTO",
            position=_position(),
            target_date=None,
            _quantity=Decimal("1"),
        )
        Hold.objects.create(
            sku=ready_quant.sku,
            quant=ready_quant,
            quantity=Decimal("1"),
            target_date=date.today(),
            status=HoldStatus.PENDING,
            expires_at=timezone.now() - timedelta(seconds=1),
            metadata={
                "reference": f"order:{order.ref}",
                QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            },
        )
        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_released_ready_item_also_blocks_calling_the_whole_order(self):
        order = _order_in_fermata("W-MIXED-RELEASED", "1")
        _materialize(order)
        ready_quant = Quant.objects.create(
            sku="ITEM-PRONTO-JA-LIBERADO",
            position=_position(),
            target_date=None,
            _quantity=Decimal("1"),
        )
        ready_hold = Hold.objects.create(
            sku=ready_quant.sku,
            quant=ready_quant,
            quantity=Decimal("1"),
            target_date=date.today(),
            status=HoldStatus.RELEASED,
            expires_at=timezone.now() - timedelta(seconds=1),
            metadata={
                "reference": f"order:{order.ref}",
                QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            },
        )
        order.data["hold_ids"].append(
            {"sku": ready_quant.sku, "hold_id": ready_hold.hold_id, "qty": 1.0}
        )
        order.save(update_fields=["data"])

        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == []
        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_realize_materializes_then_open_window_calls_the_customer(self):
        from shopman.offerman.models import Product
        from shopman.orderman.models import Directive
        from shopman.stockman.services.movements import StockMovements
        from shopman.stockman.services.planning import StockPlanning

        from shopman.shop.services import availability
        from shopman.shop.services import stock as stock_service

        sku = "PAO-FILA-REALIZE"
        tomorrow = date.today() + TOMORROW
        product = Product.objects.create(
            sku=sku,
            name="Pão da fila real",
            base_price_q=1000,
            is_published=True,
            is_sellable=True,
        )
        production = Position.objects.create(
            ref="producao-fila-real",
            name="Produção fila real",
            kind=PositionKind.PROCESS,
            is_saleable=False,
        )
        storefront = Position.objects.create(
            ref="vitrine-fila-real",
            name="Vitrine fila real",
            kind=PositionKind.PHYSICAL,
            is_saleable=True,
        )
        StockMovements.receive(
            quantity=Decimal("2"),
            sku=sku,
            position=production,
            target_date=tomorrow,
            reason="Plano da regressão de fila",
        )
        order = Order.objects.create(
            ref="W-REALIZE",
            channel_ref="web",
            session_key="sess-w-realize",
            status="new",
            total_q=1000,
            snapshot={"items": [{"sku": sku, "qty": "1", "price_q": 1000}]},
        )
        result = availability.reserve(
            sku=sku,
            qty=Decimal("1"),
            session_key=order.session_key,
            target_date=tomorrow,
        )
        assert result["ok"] is True
        hold = Hold.objects.get(pk=int(result["hold_id"].split(":")[1]))
        assert hold.metadata[QUALITY_GRADE_POLICY_VERSION_METADATA_KEY] == QUALITY_GRADE_POLICY_VERSION

        stock_service.hold(order, require_all=True)
        hold.refresh_from_db()
        assert hold.metadata["reference"] == f"order:{order.ref}"
        assert order.data["hold_ids"] == [
            {"sku": sku, "hold_id": hold.hold_id, "qty": 1.0},
        ]

        assert waitlist.state_for(order) == waitlist.FERMATA
        assert waitlist.open_window(sku, qty_available=Decimal("1")) == []

        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("2"),
            to_position=storefront,
            from_position=production,
            to_batch="PAO-FILA-REALIZE-LOTE",
        )
        hold.refresh_from_db()
        assert hold.quant.target_date is None
        assert hold.expires_at is not None

        assert waitlist.open_window(sku, qty_available=Decimal("2")) == [order.ref]
        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMING
        assert Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="waitlist_available",
        ).exists()

    def test_stock_realization_receiver_runs_before_waitlist_lifecycle_receiver(self):
        from shopman.craftsman.contrib.stockman.handlers import handle_production_changed
        from shopman.craftsman.signals import production_changed

        from shopman.shop.production_lifecycle import on_production_changed_receiver

        synchronous, _asynchronous = production_changed._live_receivers(sender=None)
        assert synchronous.index(handle_production_changed) < synchronous.index(
            on_production_changed_receiver
        )


class TestOpenWindowServesFirstComeFirstServed:
    def test_the_batch_is_served_in_arrival_order_until_it_runs_out(self):
        now = timezone.now()
        quant = _planned_quant("4")
        first = _order_in_fermata("W-A", "2", quant=quant, created_at=now - timedelta(minutes=10))
        second = _order_in_fermata("W-B", "2", quant=quant, created_at=now - timedelta(minutes=5))
        _materialize(first, qty=Decimal("3"))

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
        _materialize(Order.objects.get(ref="W-C"))

        waitlist.open_window(SKU, qty_available=Decimal("5"))

        order = Order.objects.get(ref="W-C")
        block = order.data["waitlist"]
        assert block["state"] == waitlist.CONFIRMING
        assert block["deadline"], "a janela tem prazo — senão a vaga fica presa"
        assert block["sku"] == SKU

    def test_each_order_gets_the_confirmation_deadline_of_its_own_channel(self, monkeypatch):
        web = _order_in_fermata("W-CHANNEL-WEB", "1")
        whatsapp = _order_in_fermata("W-CHANNEL-WA", "1")
        Order.objects.filter(pk=whatsapp.pk).update(channel_ref="whatsapp")
        whatsapp.refresh_from_db()
        _materialize(web, whatsapp)
        opened_at = timezone.now()

        monkeypatch.setattr(
            waitlist,
            "config",
            lambda channel_ref=None: SimpleNamespace(
                confirmation_minutes=5 if channel_ref == "web" else 25,
            ),
        )

        assert waitlist.open_window(SKU, qty_available=Decimal("2")) == [
            web.ref,
            whatsapp.ref,
        ]
        web.refresh_from_db()
        whatsapp.refresh_from_db()
        web_deadline = waitlist._parse_iso(web.data["waitlist"]["deadline"])
        whatsapp_deadline = waitlist._parse_iso(whatsapp.data["waitlist"]["deadline"])
        assert (
            timedelta(minutes=4, seconds=59)
            <= web_deadline - opened_at
            <= timedelta(minutes=5, seconds=1)
        )
        assert (
            timedelta(minutes=24, seconds=59)
            <= whatsapp_deadline - opened_at
            <= timedelta(minutes=25, seconds=1)
        )

    def test_explicit_channel_remains_a_compatibility_override(self, monkeypatch):
        order = _order_in_fermata("W-CHANNEL-OVERRIDE", "1")
        _materialize(order)
        opened_at = timezone.now()
        monkeypatch.setattr(
            waitlist,
            "config",
            lambda channel_ref=None: SimpleNamespace(
                confirmation_minutes=7 if channel_ref == "pos" else 99,
            ),
        )

        assert waitlist.open_window(
            SKU,
            qty_available=Decimal("1"),
            channel_ref="pos",
        ) == [order.ref]
        order.refresh_from_db()
        deadline = waitlist._parse_iso(order.data["waitlist"]["deadline"])
        assert (
            timedelta(minutes=6, seconds=59)
            <= deadline - opened_at
            <= timedelta(minutes=7, seconds=1)
        )

    def test_window_rolls_back_if_its_notification_cannot_be_queued(self, monkeypatch):
        order = _order_in_fermata("W-NOTIFY-ROLLBACK", "1")
        _materialize(order)

        def fail_to_queue(*args, **kwargs):
            raise RuntimeError("outbox unavailable")

        monkeypatch.setattr(
            "shopman.shop.services.notification.send",
            fail_to_queue,
        )

        with pytest.raises(RuntimeError, match="outbox unavailable"):
            waitlist.open_window(SKU, qty_available=Decimal("1"))

        order.refresh_from_db()
        assert "waitlist" not in order.data

    def test_sweep_recovers_a_materialized_window_lost_by_the_production_receiver(
        self,
        monkeypatch,
    ):
        """O hold físico é o receipt quando o callback pós-realize falha."""
        from shopman.orderman.models import Directive

        from shopman.shop.services import production

        order = _order_in_fermata("W-RECEIVER-RECOVERY", "1")
        _materialize(order)
        work_order = SimpleNamespace(
            ref="WO-RECEIVER-RECOVERY",
            output_sku=SKU,
            finished=Decimal("1"),
        )

        with monkeypatch.context() as context:
            context.setattr(
                "shopman.shop.services.notification.send",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("outbox unavailable")
                ),
            )
            # O receiver cosmético engole a falha depois que o realize commitou.
            production.emit_goods(work_order)

        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.NONE
        assert not Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
        ).exists()

        assert waitlist.sweep_expired() == 0

        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMING
        assert Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="waitlist_available",
        ).count() == 1


class TestConfirmation:
    def test_confirming_inside_the_window_locks_the_order(self):
        order = _order_in_fermata("W-D", "1")
        _materialize(order)
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        assert waitlist.confirm(order) is True
        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMED

    def test_confirming_after_the_deadline_loses_the_slot(self):
        order = _order_in_fermata("W-E", "1")
        _materialize(order)
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
        _materialize(order)
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()
        _expire_confirmation(order)

        waitlist.release(order, reason="confirmation_timeout")
        assert waitlist.release(order, reason="confirmation_timeout") == []

        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.RELEASED
        assert Hold.objects.filter(
            metadata__reference="order:W-G", status=HoldStatus.PENDING,
        ).count() == 0, "a vaga volta ao estoque"
        assert Directive.objects.filter(
            topic="notification.send", payload__template="waitlist_released",
        ).count() == 1, "retry não manda nem devolve a mesma vaga duas vezes"
        assert OperatorAlert.objects.filter(type="waitlist_released").exists(), (
            "a loja sabe que abriu vaga — ela decide gôndola ou fila"
        )

    def test_the_freed_slot_goes_to_the_next_in_line(
        self,
        django_capture_on_commit_callbacks,
    ):
        now = timezone.now()
        quant = _planned_quant("4")
        first = _order_in_fermata("W-H", "2", quant=quant, created_at=now - timedelta(minutes=10))
        second = _order_in_fermata("W-I", "2", quant=quant, created_at=now - timedelta(minutes=5))
        _materialize(first, second)

        waitlist.open_window(SKU, qty_available=Decimal("2"))
        first.refresh_from_db()
        _expire_confirmation(first)
        with django_capture_on_commit_callbacks(execute=True):
            assert waitlist.release(first, reason="confirmation_timeout") == []

        second = Order.objects.get(ref="W-I")
        assert waitlist.state_for(second) == waitlist.CONFIRMING, (
            "serve_next: a fila tem preferência sobre a gôndola"
        )

    def test_partial_adapter_failure_rolls_back_every_hold_and_the_release_state(
        self,
        monkeypatch,
    ):
        from shopman.orderman.models import Directive
        from shopman.stockman.service import Stock

        from shopman.shop import adapters

        order = _order_in_fermata("W-RELEASE-ROLLBACK", "1")
        first = Hold.objects.get(
            metadata__reference=f"order:{order.ref}",
        )
        second = Hold.objects.create(
            sku=SKU,
            quant=first.quant,
            quantity=Decimal("1"),
            target_date=first.target_date,
            status=HoldStatus.PENDING,
            expires_at=None,
            metadata=dict(first.metadata),
        )
        order.data["hold_ids"].append(
            {"sku": SKU, "hold_id": second.hold_id, "qty": 1.0}
        )
        order.save(update_fields=["data"])
        _materialize(order)
        waitlist.open_window(SKU, qty_available=Decimal("2"))
        _expire_confirmation(order)

        real_get_adapter = adapters.get_adapter

        def partially_release(hold_ids):
            Stock.release(hold_ids[0], reason="partial test")
            raise RuntimeError("stock adapter interrupted")

        failing_adapter = SimpleNamespace(release_holds=partially_release)
        monkeypatch.setattr(
            adapters,
            "get_adapter",
            lambda kind, **kwargs: (
                failing_adapter
                if kind == "stock"
                else real_get_adapter(kind, **kwargs)
            ),
        )

        with pytest.raises(RuntimeError, match="stock adapter interrupted"):
            waitlist.release(order, reason="confirmation_timeout")

        order.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMING
        assert first.status == HoldStatus.PENDING
        assert second.status == HoldStatus.PENDING
        assert not Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="waitlist_released",
        ).exists()

    def test_timeout_releases_every_sku_of_the_order(self):
        second_sku = "PAO-FILA-LIBERAR-TAMBEM"
        order = _order_in_fermata("W-RELEASE-TWO-SKUS", "1")
        first = Hold.objects.get(
            metadata__reference="order:W-RELEASE-TWO-SKUS",
        )
        second_plan = Quant.objects.create(
            sku=second_sku,
            position=_position(),
            target_date=first.target_date,
            _quantity=Decimal("1"),
        )
        second = Hold.objects.create(
            sku=second_sku,
            quant=second_plan,
            quantity=Decimal("1"),
            target_date=first.target_date,
            status=HoldStatus.PENDING,
            expires_at=None,
            metadata=dict(first.metadata),
        )
        order.data["hold_ids"].append(
            {"sku": second_sku, "hold_id": second.hold_id, "qty": 1.0}
        )
        order.save(update_fields=["data"])

        for hold, batch in (
            (first, "FIRST-READY"),
            (second, "SECOND-READY"),
        ):
            physical = Quant.objects.create(
                sku=hold.sku,
                position=_position(),
                target_date=None,
                batch=batch,
                _quantity=hold.quantity,
            )
            hold.quant = physical
            hold.expires_at = timezone.now() + timedelta(minutes=30)
            hold.save(update_fields=["quant", "expires_at"])

        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == [order.ref]
        _expire_confirmation(order)
        waitlist.release(order, reason="confirmation_timeout")

        assert not Hold.objects.filter(
            metadata__reference=f"order:{order.ref}",
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        ).exists()
        assert Quant.objects.get(batch="FIRST-READY").available == Decimal("1")
        assert Quant.objects.get(batch="SECOND-READY").available == Decimal("1")

    def test_timeout_also_releases_an_item_that_was_ready_before_the_batch(self):
        ready_sku = "ITEM-PRONTO-DO-PEDIDO"
        order = _order_in_fermata("W-RELEASE-MIXED", "1")
        ready_quant = Quant.objects.create(
            sku=ready_sku,
            position=_position(),
            target_date=None,
            _quantity=Decimal("2"),
        )
        ready_hold = Hold.objects.create(
            sku=ready_sku,
            quant=ready_quant,
            quantity=Decimal("1"),
            target_date=date.today(),
            status=HoldStatus.PENDING,
            expires_at=timezone.now() + timedelta(hours=1),
            metadata={
                "reference": f"order:{order.ref}",
                QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            },
        )
        order.data["hold_ids"].append(
            {"sku": ready_sku, "hold_id": ready_hold.hold_id, "qty": 1.0}
        )
        order.save(update_fields=["data"])
        _materialize(order)

        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == [order.ref]
        _expire_confirmation(order)
        waitlist.release(order, reason="confirmation_timeout")

        ready_hold.refresh_from_db()
        ready_quant.refresh_from_db()
        assert ready_hold.status == HoldStatus.RELEASED
        assert ready_quant.available == Decimal("2")

    def test_on_demand_item_is_released_but_never_becomes_serve_next_budget(
        self,
        monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        demand_sku = "ITEM-SOB-DEMANDA"
        order = _order_in_fermata("W-RELEASE-DEMAND", "1")
        _materialize(order)
        demand_hold = Hold.objects.create(
            sku=demand_sku,
            quant=None,
            quantity=Decimal("1"),
            target_date=date.today(),
            status=HoldStatus.PENDING,
            expires_at=timezone.now() + timedelta(hours=1),
            metadata={
                "reference": f"order:{order.ref}",
                "on_demand": True,
                QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            },
        )
        order.data["hold_ids"].append(
            {"sku": demand_sku, "hold_id": demand_hold.hold_id, "qty": 1.0}
        )
        order.save(update_fields=["data"])
        assert waitlist.open_window(SKU, qty_available=Decimal("1")) == [order.ref]
        _expire_confirmation(order)

        budgets = []

        def record_budget(sku, *, qty_available, channel_ref=None):
            budgets.append((sku, qty_available))
            return []

        monkeypatch.setattr(waitlist, "open_window", record_budget)
        with django_capture_on_commit_callbacks(execute=True):
            assert waitlist.release(order, reason="confirmation_timeout") == []

        demand_hold.refresh_from_db()
        assert demand_hold.status == HoldStatus.RELEASED
        assert budgets == [(SKU, Decimal("1"))]


class TestSweep:
    def test_expired_windows_are_swept(self):
        order = _order_in_fermata("W-J", "1")
        _materialize(order)
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()
        data = dict(order.data)
        data["waitlist"]["deadline"] = (timezone.now() - timedelta(minutes=1)).isoformat()
        Order.objects.filter(pk=order.pk).update(data=data)

        assert waitlist.sweep_expired() == 1
        assert Order.objects.get(ref="W-J").data["waitlist"]["state"] == waitlist.RELEASED

    def test_a_live_window_is_left_alone(self):
        order = _order_in_fermata("W-K", "1")
        _materialize(order)
        waitlist.open_window(SKU, qty_available=Decimal("5"))

        assert waitlist.sweep_expired() == 0


class TestChargeHappensAtConfirmation:
    def test_confirming_starts_the_charge_not_the_reservation(
        self,
        django_capture_on_commit_callbacks,
    ):
        from shopman.orderman.models import Directive

        order = _order_in_fermata("W-L", "1")
        _materialize(order)
        order.data = {**(order.data or {}), "payment": {"method": "pix"}}
        order.save(update_fields=["data"])
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        assert not Directive.objects.filter(
            topic="notification.send", payload__template="payment_requested",
        ).exists(), "a reserva não cobra nada — é o que torna desistir barato"

        with django_capture_on_commit_callbacks(execute=True):
            waitlist.confirm(order)

        assert Directive.objects.filter(
            topic="notification.send", payload__template="payment_requested",
        ).exists(), "confirmou, cobra — charge_at=confirmation"

    def test_sweep_recovers_charge_when_process_dies_before_on_commit_callback(
        self,
        django_capture_on_commit_callbacks,
    ):
        from shopman.orderman.models import Directive

        order = _order_in_fermata("W-CHARGE-CRASH", "1")
        _materialize(order)
        order.data = {**(order.data or {}), "payment": {"method": "pix"}}
        order.save(update_fields=["data"])
        waitlist.open_window(SKU, qty_available=Decimal("1"))
        order.refresh_from_db()

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            assert waitlist.confirm(order) is True
        assert len(callbacks) == 1

        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMED
        assert not ((order.data or {}).get("payment") or {}).get("intent_ref")
        assert not Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="payment_requested",
        ).exists()

        assert waitlist.sweep_expired() == 0

        order.refresh_from_db()
        assert ((order.data or {}).get("payment") or {}).get("intent_ref")
        assert Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="payment_requested",
        ).count() == 1

    def test_confirmed_charge_replay_converges_with_two_stale_workers(self):
        from shopman.orderman.models import Directive
        from shopman.payman import PaymentService

        order = _order_in_fermata("W-CHARGE-CONCURRENT", "1")
        _materialize(order)
        order.data = {
            **(order.data or {}),
            "payment": {"method": "pix"},
            "waitlist": {"state": waitlist.CONFIRMED},
        }
        order.save(update_fields=["data"])
        first_worker = Order.objects.get(pk=order.pk)
        second_worker = Order.objects.get(pk=order.pk)

        waitlist._charge(first_worker)
        waitlist._charge(second_worker)

        assert PaymentService.get_by_order(order.ref).count() == 1
        assert Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="payment_requested",
        ).count() == 1

    def test_sweep_recovers_notice_lost_after_the_intent_was_persisted(
        self,
        monkeypatch,
    ):
        from shopman.orderman.models import Directive

        from shopman.shop.services import notification

        order = _order_in_fermata("W-CHARGE-OUTBOX-CRASH", "1")
        _materialize(order)
        order.data = {
            **(order.data or {}),
            "payment": {"method": "pix"},
            "waitlist": {"state": waitlist.CONFIRMED},
        }
        order.save(update_fields=["data"])

        with monkeypatch.context() as context:
            context.setattr(
                notification,
                "send",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("process died before queuing the notice")
                ),
            )
            waitlist._charge(order)

        order.refresh_from_db()
        assert ((order.data or {}).get("payment") or {}).get("intent_ref")
        assert not Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="payment_requested",
        ).exists()

        assert waitlist.sweep_expired() == 0
        assert Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="payment_requested",
        ).count() == 1

    def test_stale_charge_callback_does_not_charge_a_released_order(self):
        from shopman.orderman.models import Directive
        from shopman.payman import PaymentService

        order = _order_in_fermata("W-CHARGE-STALE-RELEASED", "1")
        _materialize(order)
        order.data = {
            **(order.data or {}),
            "payment": {"method": "pix"},
            "waitlist": {"state": waitlist.CONFIRMED},
        }
        order.save(update_fields=["data"])
        stale_callback_order = Order.objects.get(pk=order.pk)
        order.data = {
            **(order.data or {}),
            "waitlist": {"state": waitlist.RELEASED},
        }
        order.save(update_fields=["data"])

        waitlist._charge(stale_callback_order)

        assert PaymentService.get_by_order(order.ref).count() == 0
        assert not Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="payment_requested",
        ).exists()


@requires_postgres
class TestConcurrentConfirmedCharge(TransactionTestCase):
    def test_two_workers_converge_on_one_intent_and_one_notice(self):
        from shopman.orderman.models import Directive
        from shopman.payman import PaymentService

        order = _order_in_fermata("W-CHARGE-REAL-CONCURRENCY", "1")
        _materialize(order)
        order.data = {
            **(order.data or {}),
            "payment": {"method": "pix"},
            "waitlist": {"state": waitlist.CONFIRMED},
        }
        order.save(update_fields=["data"])
        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                candidate = Order.objects.get(pk=order.pk)
                barrier.wait(timeout=5)
                waitlist._charge(candidate)
            except Exception as exc:  # noqa: BLE001 — collected for assertion
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not any(thread.is_alive() for thread in threads)
        assert errors == []
        assert PaymentService.get_by_order(order.ref).count() == 1
        assert Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="payment_requested",
        ).count() == 1


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
        _materialize(order)
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
