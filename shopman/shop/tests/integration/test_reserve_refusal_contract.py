"""Contrato da reserva: recusa em vocabulário FECHADO e quantidade em ``Decimal``.

Laudo de soberania 18/10 (A2-3): ``reserve()`` devolvia ``error_code`` aberto
(``hold_failed``, ``product_not_found``, o ``INSUFFICIENT_AVAILABLE`` cru do
Stockman), o portão da vitrine existia duas vezes com saídas diferentes, e a
reserva fatiada entre quants truncava kg (``int(qty)``, ``// 2``) e devolvia só
o primeiro ``hold_id``.
"""

from decimal import Decimal

import pytest
from shopman.stockman.exceptions import StockError
from shopman.stockman.models import Hold
from shopman.stockman.protocols.sku import PromiseReasonCode
from shopman.stockman.services.movements import StockMovements

from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.protocols import ReserveRefusal
from shopman.shop.services import availability

pytestmark = pytest.mark.django_db


@pytest.fixture
def position_fundo(db):
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="fundo",
        defaults={"name": "Fundo", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return position


@pytest.fixture
def pdv_channel(db):
    from shopman.shop.models import Channel

    channel, _ = Channel.objects.update_or_create(
        ref="pdv",
        defaults={"name": "Balcão", "is_active": True, "config": {"stock": {}}},
    )
    return channel


class TestHoldRefusalVocabulary:
    def test_insufficient_available_is_insufficient_supply(self):
        error = StockError("INSUFFICIENT_AVAILABLE", available=Decimal("1"), requested=Decimal("2"))
        assert stock_adapter.stock_error_code(error) is ReserveRefusal.INSUFFICIENT_SUPPLY

    def test_paused_promise_stays_paused(self):
        error = StockError("INSUFFICIENT_AVAILABLE", reason_code=PromiseReasonCode.PAUSED)
        assert stock_adapter.stock_error_code(error) is ReserveRefusal.PAUSED

    def test_invalid_quantity(self):
        assert stock_adapter.stock_error_code(StockError("INVALID_QUANTITY")) is ReserveRefusal.INVALID_QUANTITY

    def test_code_outside_the_vocabulary_raises(self):
        """Código que não é recusa de reserva é defeito: sobe, não vira "faltou estoque"."""
        with pytest.raises(StockError):
            stock_adapter.stock_error_code(StockError("QUANT_NOT_FOUND"))

    def test_unknown_sku_is_product_not_found(self):
        result = stock_adapter.create_hold("SKU-QUE-NAO-EXISTE", Decimal("1"))
        assert result["success"] is False
        assert result["error_code"] is ReserveRefusal.PRODUCT_NOT_FOUND

    def test_vocabulary_composes_the_promise_codes(self):
        assert {code.value for code in PromiseReasonCode} <= {code.value for code in ReserveRefusal}


class TestListingGateIsOne:
    @pytest.mark.channels("web")
    def test_reserve_and_check_refuse_not_in_listing_alike(self, product, monkeypatch):
        monkeypatch.setattr(availability, "_sku_in_channel_listing", lambda sku, channel_ref: False)
        reserve = availability.reserve(product.sku, Decimal("1"), session_key="s-gate", channel_ref="web")
        check = availability.check(product.sku, Decimal("1"), channel_ref="web")
        assert reserve["error_code"] is ReserveRefusal.NOT_IN_LISTING
        assert check["error_code"] == ReserveRefusal.NOT_IN_LISTING
        assert reserve["is_paused"] is check["is_paused"] is False


class TestReserveAcrossQuants:
    def test_fractional_quantity_splits_without_truncating(self, product, position_loja, position_fundo, pdv_channel):
        StockMovements.receive(Decimal("0.4"), product.sku, position=position_loja, reason="Peça A")
        StockMovements.receive(Decimal("0.3"), product.sku, position=position_fundo, reason="Peça B")

        result = availability.reserve(product.sku, Decimal("0.6"), session_key="s-kg", channel_ref="pdv")

        assert result["ok"] is True
        assert result["available_qty"] == Decimal("0.6")
        assert len(result["hold_ids"]) == 2
        held = Hold.objects.filter(pk__in=[int(h.split(":")[1]) for h in result["hold_ids"]])
        assert sum(hold.quantity for hold in held) == Decimal("0.6")

    def test_short_split_releases_everything_and_says_what_fit(
        self, product, position_loja, position_fundo, pdv_channel,
    ):
        StockMovements.receive(Decimal("0.4"), product.sku, position=position_loja, reason="Peça A")
        StockMovements.receive(Decimal("0.3"), product.sku, position=position_fundo, reason="Peça B")

        result = availability._reserve_across_quants(
            sku=product.sku,
            qty=Decimal("0.8"),
            ttl_minutes=30,
            session_key="s-kg-short",
            channel_ref="pdv",
            target_date=None,
            adapter=stock_adapter,
        )

        assert result == {"ok": False, "hold_ids": [], "available_qty": Decimal("0.7")}
        assert not Hold.objects.filter(metadata__reference="s-kg-short", status__in=["pending", "confirmed"]).exists()
