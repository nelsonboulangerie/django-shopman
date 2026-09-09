"""
Tests for planned stock holds and materialization flow.

Verifies:
- Holds against planned quants work correctly
- realize() sets TTL on materialized holds
- realize() emits holds_materialized signal
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from shopman.stockman.exceptions import StockError
from shopman.stockman.models.batch import Batch
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.models.hold import Hold
from shopman.stockman.models.move import Move
from shopman.stockman.models.quant import Quant
from shopman.stockman.services.holds import (
    QUALITY_GRADE_POLICY_VERSION,
    QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    StockHolds,
)
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning


@pytest.mark.django_db
class TestPlannedHolds:
    """Test holds against planned (future) quants."""

    def test_hold_against_planned_quant(self, product, producao, tomorrow):
        """Hold can be created against a planned quant."""
        # Create planned stock for tomorrow
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
            reason="Planned production",
        )

        # Create hold against it
        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
            expires_at=None,
        )

        assert hold_id.startswith("hold:")
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert hold.quant is not None
        assert hold.quant.target_date == tomorrow
        assert hold.expires_at is None  # No timeout
        assert hold.status == HoldStatus.PENDING
        assert (
            hold.metadata[QUALITY_GRADE_POLICY_VERSION_METADATA_KEY]
            == QUALITY_GRADE_POLICY_VERSION
        )

    def test_hold_against_planned_is_reservation(self, product, producao, tomorrow):
        """Hold against planned stock is a reservation (not demand)."""
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
        )

        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert hold.is_reservation
        assert not hold.is_demand


@pytest.mark.django_db
class TestRealizeWithHolds:
    """Test StockPlanning.realize() with hold materialization."""

    def _setup_planned_with_hold(self, product, producao, vitrine, target_date):
        """Helper: create planned quant with a hold."""
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=target_date,
            reason="Planned production",
        )

        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=target_date,
            expires_at=None,
            reference="session-123",
        )

        return hold_id

    def test_realize_sets_ttl_on_materialized_holds(self, product, producao, vitrine, tomorrow):
        """realize() sets expires_at on holds that had no timeout."""
        hold_id = self._setup_planned_with_hold(product, producao, vitrine, tomorrow)
        pk = int(hold_id.split(":")[1])

        # Before realize: hold has no expiry
        hold = Hold.objects.get(pk=pk)
        assert hold.expires_at is None

        # Realize production
        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("50"),
            to_position=vitrine,
            from_position=producao,
        )

        # After realize: hold has expiry (clock started)
        hold.refresh_from_db()
        assert hold.expires_at is not None
        assert hold.quant.target_date is None  # Now physical

    def test_realize_preserves_existing_ttl(self, product, producao, vitrine, tomorrow):
        """realize() doesn't override existing expires_at on holds."""
        from django.utils import timezone

        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        # Create hold WITH explicit TTL
        original_expiry = timezone.now() + timedelta(hours=2)
        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
            expires_at=original_expiry,
        )

        # Realize
        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("50"),
            to_position=vitrine,
            from_position=producao,
        )

        # TTL should be preserved (not overwritten)
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert abs(hold.expires_at - original_expiry) < timedelta(seconds=1)

    @pytest.mark.django_db(transaction=True)
    def test_realize_emits_holds_materialized_signal(self, product, producao, vitrine, tomorrow):
        """realize() emits holds_materialized signal for transferred holds."""
        from shopman.stockman.signals import holds_materialized

        hold_id = self._setup_planned_with_hold(product, producao, vitrine, tomorrow)

        received = []

        def handler(sender, hold_ids, sku, target_date, **kwargs):
            received.append(
                {
                    "hold_ids": hold_ids,
                    "sku": sku,
                    "target_date": target_date,
                }
            )

        holds_materialized.connect(handler)
        try:
            StockPlanning.realize(
                product=product,
                target_date=tomorrow,
                actual_quantity=Decimal("50"),
                to_position=vitrine,
                from_position=producao,
            )

            assert len(received) == 1
            assert hold_id in received[0]["hold_ids"]
            assert received[0]["sku"] == product.sku
            assert received[0]["target_date"] == tomorrow
        finally:
            holds_materialized.disconnect(handler)

    @pytest.mark.django_db(transaction=True)
    def test_realize_no_signal_without_holds(self, product, producao, vitrine, tomorrow):
        """realize() doesn't emit signal when there are no holds to transfer."""
        from shopman.stockman.signals import holds_materialized

        # Create planned stock without holds
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        received = []

        def handler(sender, **kwargs):
            received.append(True)

        holds_materialized.connect(handler)
        try:
            StockPlanning.realize(
                product=product,
                target_date=tomorrow,
                actual_quantity=Decimal("50"),
                to_position=vitrine,
                from_position=producao,
            )

            assert len(received) == 0
        finally:
            holds_materialized.disconnect(handler)

    def test_realize_hold_metadata_preserved(self, product, producao, vitrine, tomorrow):
        """realize() preserves hold metadata (reference, channel_ref)."""
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
            expires_at=None,
            reference="session-abc",
            channel_ref="whatsapp",
        )

        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("50"),
            to_position=vitrine,
            from_position=producao,
        )

        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert hold.metadata["reference"] == "session-abc"
        assert hold.metadata["channel_ref"] == "whatsapp"

    def test_realize_never_materializes_remote_hold_into_disallowed_grade(self, product, producao, vitrine, tomorrow):
        StockMovements.receive(
            quantity=Decimal("15"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )
        hold_id = StockHolds.hold(
            quantity=Decimal("5"),
            product=product,
            target_date=tomorrow,
            allowed_quality_grade_refs=("excellent", "standard"),
        )
        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        planned_quant_id = hold.quant_id
        assert hold.metadata["_allowed_quality_grade_refs"] == [
            "excellent",
            "standard",
        ]

        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("10"),
            to_position=vitrine,
            from_position=producao,
            to_batch="MIN",
            to_quality_grade_ref="minimal",
        )

        hold.refresh_from_db()
        assert hold.quant_id == planned_quant_id

        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("5"),
            to_position=vitrine,
            from_position=producao,
            to_batch="STD",
            to_quality_grade_ref="standard",
        )

        hold.refresh_from_db()
        assert hold.quant.batch == "STD"
        assert Batch.objects.get(ref="STD").quality_grade_ref == "standard"

        StockHolds.confirm(hold_id)
        move = StockHolds.fulfill(hold_id)
        assert move.delta == Decimal("-5")

    def test_realize_rejects_a_conflicting_grade_for_an_existing_batch(
        self,
        product,
        producao,
        vitrine,
        tomorrow,
    ):
        StockMovements.receive(
            quantity=Decimal("10"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )
        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("5"),
            to_position=vitrine,
            from_position=producao,
            to_batch="ONE-TRUTH",
            to_quality_grade_ref="standard",
        )

        with pytest.raises(StockError) as exc:
            StockPlanning.realize(
                product=product,
                target_date=tomorrow,
                actual_quantity=Decimal("5"),
                to_position=vitrine,
                from_position=producao,
                to_batch="ONE-TRUTH",
                to_quality_grade_ref="minimal",
            )

        assert exc.value.code == "BATCH_QUALITY_CONFLICT"
        assert Batch.objects.get(ref="ONE-TRUTH").quality_grade_ref == "standard"

    def test_realize_rejects_a_batch_owned_by_another_sku(
        self,
        product,
        producao,
        vitrine,
        tomorrow,
    ):
        planned = StockMovements.receive(
            quantity=Decimal("5"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )
        Batch.objects.create(
            ref="COLLIDE",
            sku="ANOTHER-SKU",
            quality_grade_ref="minimal",
        )
        moves_before = Move.objects.count()

        with pytest.raises(StockError) as exc:
            StockPlanning.realize(
                product=product,
                target_date=tomorrow,
                actual_quantity=Decimal("5"),
                to_position=vitrine,
                from_position=producao,
                to_batch="COLLIDE",
                to_quality_grade_ref="minimal",
            )

        planned.refresh_from_db()
        assert exc.value.code == "BATCH_SKU_CONFLICT"
        assert planned.quantity == Decimal("5")
        assert Move.objects.count() == moves_before
        assert not Quant.objects.filter(
            sku=product.sku,
            position=vitrine,
            batch="COLLIDE",
        ).exists()

    def test_legacy_hold_without_frozen_policy_fails_closed(
        self,
        product,
        producao,
        vitrine,
        tomorrow,
    ):
        planned = StockMovements.receive(
            quantity=Decimal("5"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )
        legacy = Hold.objects.create(
            sku=product.sku,
            quant=planned,
            quantity=Decimal("5"),
            target_date=tomorrow,
            status=HoldStatus.PENDING,
            metadata={},
        )

        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("5"),
            to_position=vitrine,
            from_position=producao,
            to_batch="LEGACY-MIN",
            to_quality_grade_ref="minimal",
        )

        legacy.refresh_from_db()
        assert legacy.quant_id == planned.pk
        StockHolds.confirm(legacy.hold_id)
        with pytest.raises(StockError) as exc:
            StockHolds.fulfill(legacy.hold_id)
        assert exc.value.code == "HOLD_POLICY_UNKNOWN"

    def test_fulfill_rechecks_the_frozen_grade_policy(self, product, producao, vitrine, tomorrow):
        StockMovements.receive(
            quantity=Decimal("5"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )
        hold_id = StockHolds.hold(
            quantity=Decimal("5"),
            product=product,
            target_date=tomorrow,
            allowed_quality_grade_refs=("excellent", "standard"),
        )
        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("5"),
            to_position=vitrine,
            from_position=producao,
            to_batch="STD-CORRIGIDO",
            to_quality_grade_ref="standard",
        )
        Batch.objects.filter(ref="STD-CORRIGIDO").update(quality_grade_ref="minimal")
        StockHolds.confirm(hold_id)

        with pytest.raises(StockError) as exc:
            StockHolds.fulfill(hold_id)

        assert exc.value.code == "INELIGIBLE_BATCH"
