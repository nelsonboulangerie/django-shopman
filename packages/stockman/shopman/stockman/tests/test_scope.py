"""
Tests for :func:`quants_eligible_for` — the canonical quant scope gate.

Validates filtering by:

- Position allowlist (``allowed_positions``)
- Position denylist (``excluded_positions``)
- Shelflife window (``product.shelf_life_days``)
- Batch expiry
- ``target_date`` gate
- Combinations of the above
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from shopman.stockman.models import Batch, Position, PositionKind, Quant
from shopman.stockman.services.scope import quants_eligible_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def perishable_validator(settings):
    settings.STOCKMAN = {
        "SKU_VALIDATOR": "shopman.stockman.tests.fakes.PerishableSkuValidator",
    }
    from shopman.stockman.adapters.sku_validation import reset_sku_validator

    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture
def ontem_position(db):
    position, _ = Position.objects.get_or_create(
        ref="ontem",
        defaults={
            "name": "Vitrine D-1",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return position


@pytest.fixture
def deposito_position(db):
    position, _ = Position.objects.get_or_create(
        ref="deposito",
        defaults={
            "name": "Depósito",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": False,
        },
    )
    return position


class TestBaseFilter:
    def test_returns_only_positive_quantities_for_sku(self, product, vitrine, today):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("10"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, target_date=today,
            _quantity=Decimal("0"),
        )
        Quant.objects.create(
            sku="OTHER-SKU", position=vitrine, _quantity=Decimal("99"),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        assert qs.count() == 1
        assert qs.first()._quantity == Decimal("10")


class TestTargetDateGate:
    def test_excludes_future_quants_beyond_target(
        self, product, vitrine, today, tomorrow,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, target_date=tomorrow,
            _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        assert qs.count() == 1
        assert qs.first()._quantity == Decimal("5")

    def test_includes_future_quants_within_target(
        self, product, vitrine, today, tomorrow,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, target_date=tomorrow,
            _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(product.sku, target_date=tomorrow)

        assert qs.count() == 1


class TestShelflife:
    def test_perishable_excludes_stale_physical_quants(
        self, perishable_product, vitrine, today, perishable_validator,
    ):
        """shelf_life_days=0 means only same-day physical stock is valid."""
        quant = Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            _quantity=Decimal("10"),
        )
        Quant.objects.filter(pk=quant.pk).update(
            created_at=quant.created_at - timedelta(days=1),
        )

        qs = quants_eligible_for(perishable_product.sku, target_date=today)

        assert qs.count() == 0

    def test_perishable_keeps_same_day_physical_quants(
        self, perishable_product, vitrine, today, perishable_validator,
    ):
        Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            _quantity=Decimal("10"),
        )

        qs = quants_eligible_for(perishable_product.sku, target_date=today)

        assert qs.count() == 1

    def test_non_perishable_keeps_old_physical_quants(
        self, product, vitrine, today,
    ):
        """shelf_life_days=None disables the shelflife window."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            _quantity=Decimal("10"),
        )
        Quant.objects.filter(pk=quant.pk).update(
            created_at=quant.created_at - timedelta(days=365),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        assert qs.count() == 1


class TestPositionScope:
    def test_allowed_positions_limits_to_listed_refs(
        self, product, vitrine, ontem_position, today,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=today, allowed_positions=["vitrine"],
        )

        assert qs.count() == 1
        assert qs.first().position.ref == "vitrine"

    def test_excluded_positions_removes_listed_refs(
        self, product, vitrine, ontem_position, today,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=today, excluded_positions=["ontem"],
        )

        assert qs.count() == 1
        assert qs.first().position.ref == "vitrine"

    def test_excluded_positions_keeps_quants_without_position(
        self, product, vitrine, ontem_position, today, tomorrow,
    ):
        """Planned quants typically have position=None and must survive a
        denylist check — the denylist only removes quants sitting at the
        listed refs."""
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, target_date=tomorrow, _quantity=Decimal("8"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=tomorrow, excluded_positions=["ontem"],
        )

        assert qs.count() == 1
        assert qs.first().position is None

    def test_allowed_and_excluded_combine(
        self, product, vitrine, ontem_position, deposito_position, today,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("7"),
        )
        Quant.objects.create(
            sku=product.sku, position=deposito_position, _quantity=Decimal("9"),
        )

        qs = quants_eligible_for(
            product.sku,
            target_date=today,
            allowed_positions=["vitrine", "ontem", "deposito"],
            excluded_positions=["ontem"],
        )

        refs = sorted(q.position.ref for q in qs)
        assert refs == ["deposito", "vitrine"]


class TestBatchExpiry:
    def test_expired_batch_is_filtered_out(
        self, product, vitrine, today,
    ):
        yesterday = today - timedelta(days=1)
        Batch.objects.create(
            sku=product.sku, ref="OLD", expiry_date=yesterday,
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="OLD",
            _quantity=Decimal("3"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="FRESH",
            _quantity=Decimal("4"),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        refs = [q.batch for q in qs]
        assert refs == ["FRESH"]


class TestShelflifeBatchPrecedence:
    """Lock the precedence contract when BOTH validity signals exist.

    ``Product.shelf_life_days`` (relative window) and ``Batch.expiry_date``
    (absolute lot date) are applied as an AND: a quant is eligible only if it
    passes both. The most restrictive wins — this removes the ambiguity noted
    in the ROADMAP by making the rule explicit and tested.
    """

    def test_expired_batch_excludes_shelflife_valid_quant(
        self, perishable_product, vitrine, today, perishable_validator,
    ):
        # Same-day quant passes the shelf_life_days=0 window, but its batch is
        # expired → excluded. Batch expiry is the more restrictive signal here.
        yesterday = today - timedelta(days=1)
        Batch.objects.create(sku=perishable_product.sku, ref="OLD", expiry_date=yesterday)
        Quant.objects.create(
            sku=perishable_product.sku, position=vitrine, batch="OLD",
            _quantity=Decimal("5"),
        )

        qs = quants_eligible_for(perishable_product.sku, target_date=today)

        assert qs.count() == 0

    def test_stale_shelflife_excludes_unexpired_batch_quant(
        self, perishable_product, vitrine, today, perishable_validator,
    ):
        # Fresh (non-expired) batch, but the quant is older than the
        # shelf_life_days=0 window → excluded. shelf_life is the more
        # restrictive signal here.
        next_week = today + timedelta(days=7)
        Batch.objects.create(sku=perishable_product.sku, ref="FRESH", expiry_date=next_week)
        quant = Quant.objects.create(
            sku=perishable_product.sku, position=vitrine, batch="FRESH",
            _quantity=Decimal("5"),
        )
        Quant.objects.filter(pk=quant.pk).update(
            created_at=quant.created_at - timedelta(days=1),
        )

        qs = quants_eligible_for(perishable_product.sku, target_date=today)

        assert qs.count() == 0

    def test_both_valid_keeps_quant(
        self, perishable_product, vitrine, today, perishable_validator,
    ):
        next_week = today + timedelta(days=7)
        Batch.objects.create(sku=perishable_product.sku, ref="FRESH", expiry_date=next_week)
        Quant.objects.create(
            sku=perishable_product.sku, position=vitrine, batch="FRESH",
            _quantity=Decimal("5"),
        )

        qs = quants_eligible_for(perishable_product.sku, target_date=today)

        assert qs.count() == 1


class TestCombinations:
    def test_denylist_plus_shelflife_plus_target(
        self, perishable_product, vitrine, ontem_position, today, tomorrow,
        perishable_validator,
    ):
        """Realistic remote-channel scenario for a daily bread:
        - vitrine today: eligible
        - ontem: excluded by denylist
        - tomorrow's planned stock: excluded by target gate (target=today)
        """
        Quant.objects.create(
            sku=perishable_product.sku, position=vitrine,
            _quantity=Decimal("25"),
        )
        Quant.objects.create(
            sku=perishable_product.sku, position=ontem_position,
            _quantity=Decimal("27"),
        )
        Quant.objects.create(
            sku=perishable_product.sku, target_date=tomorrow,
            _quantity=Decimal("30"),
        )

        qs = quants_eligible_for(
            perishable_product.sku,
            target_date=today,
            excluded_positions=["ontem"],
        )

        positions = sorted(
            (q.position.ref if q.position else None) for q in qs
        )
        assert positions == ["vitrine"]


class TestExpiryMargin:
    """``expiry_margin_days``: near-expiry sai do escopo ANTES de vencer."""

    def test_margin_zero_keeps_historical_gate(self, product, vitrine, today):
        Batch.objects.create(
            sku=product.sku, ref="AMANHA", expiry_date=today + timedelta(days=1),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="AMANHA",
            _quantity=Decimal("5"),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        assert [q.batch for q in qs] == ["AMANHA"]

    def test_margin_excludes_lot_expiring_within_window(
        self, product, vitrine, today,
    ):
        """Queijo que vence em 2 dias some com margem de 3; o de 10 dias fica."""
        Batch.objects.create(
            sku=product.sku, ref="VENCE-2D", expiry_date=today + timedelta(days=2),
        )
        Batch.objects.create(
            sku=product.sku, ref="VENCE-10D", expiry_date=today + timedelta(days=10),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="VENCE-2D",
            _quantity=Decimal("3"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="VENCE-10D",
            _quantity=Decimal("4"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=today, expiry_margin_days=3,
        )

        assert [q.batch for q in qs] == ["VENCE-10D"]

    def test_lot_expiring_exactly_on_cutoff_stays(self, product, vitrine, today):
        """A margem é 'a MENOS de N dias': vencer NO corte ainda vende."""
        Batch.objects.create(
            sku=product.sku, ref="NO-CORTE", expiry_date=today + timedelta(days=3),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="NO-CORTE",
            _quantity=Decimal("2"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=today, expiry_margin_days=3,
        )

        assert [q.batch for q in qs] == ["NO-CORTE"]


class TestNonconformingGate:
    """``include_nonconforming=False``: o LOTE decide o que o canal oferece.

    Ter motivo é ser (Batch.nonconformity_reason != "") — o core não sabe o
    que o motivo significa nem quem pode vender; só filtra quando mandam.
    """

    def _lots(self, product, vitrine, today):
        Batch.objects.create(
            sku=product.sku, ref="CONFORME",
            expiry_date=today + timedelta(days=1),
        )
        Batch.objects.create(
            sku=product.sku, ref="MARCADO",
            expiry_date=today + timedelta(days=1),
            nonconformity_reason="Assou demais",
            nonconformity_percent=20,
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="CONFORME",
            _quantity=Decimal("10"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="MARCADO",
            _quantity=Decimal("4"),
        )

    def test_default_keeps_nonconforming_visible(self, product, vitrine, today):
        self._lots(product, vitrine, today)

        qs = quants_eligible_for(product.sku, target_date=today)

        assert sorted(q.batch for q in qs) == ["CONFORME", "MARCADO"]

    def test_gate_excludes_lots_with_reason(self, product, vitrine, today):
        self._lots(product, vitrine, today)

        qs = quants_eligible_for(
            product.sku, target_date=today, include_nonconforming=False,
        )

        assert [q.batch for q in qs] == ["CONFORME"]

    def test_batchless_quants_are_untouched_by_the_gate(
        self, product, vitrine, today,
    ):
        """Quant sem lote não tem motivo — o gate é sobre LOTES marcados."""
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=today, include_nonconforming=False,
        )

        assert qs.count() == 1
