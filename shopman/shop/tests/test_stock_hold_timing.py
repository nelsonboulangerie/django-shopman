"""Reserva no tempo certo (laudo adversarial de go-live, 23/10/2026: E1, E2, E3).

- E1: mexer na sacola não ressuscita reserva já vencida.
- E2: o gate de commit reparte o que falta entre saldos, tudo ou nada.
- E3: o prazo-limite da reserva de encomenda conta a partir do dia do
  compromisso, não do commit.
- Baixa concorrente do mesmo hold é sucesso idempotente, sem alerta.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import HoldStatus, StockError
from shopman.stockman import stock as stockman_stock
from shopman.stockman.models import Hold, Position, PositionKind

from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.services import availability
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db


def _pk(hold_id: str) -> int:
    return int(hold_id.split(":")[1])


def _product(sku: str, name: str):
    return Product.objects.create(sku=sku, name=name, base_price_q=500, is_published=True, is_sellable=True)


def _position(ref: str):
    return Position.objects.create(ref=ref, name=ref.title(), kind=PositionKind.PHYSICAL, is_saleable=True)


def _receive(sku: str, qty: str, position_ref: str = "loja"):
    return stockman_stock.receive(
        quantity=Decimal(qty), sku=sku, position=_position(position_ref), reason="fornada",
    )


def _channel():
    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="web", defaults={"name": "web"})


def _order(sku: str, qty, *, ref: str, data: dict | None = None):
    order = MagicMock()
    order.ref = ref
    order.channel_ref = "web"
    order.session_key = f"SESS-{ref}"
    order.data = dict(data or {})
    order.snapshot = {"items": [{"sku": sku, "qty": qty, "line_id": "l1", "meta": {}}], "data": order.data}
    order.items.all.return_value = []
    return order


# ── E1 ───────────────────────────────────────────────────────────────


def test_bump_does_not_revive_expired_cart_hold():
    sku = "T1CROI"
    _product(sku, "Croissant")
    quant = _receive(sku, "2")
    first = stock_adapter.create_hold(sku=sku, qty=Decimal("2"), reference="SESS-A")
    assert first["success"], first
    Hold.objects.filter(pk=_pk(first["hold_id"])).update(expires_at=timezone.now() - timedelta(minutes=1))
    second = stock_adapter.create_hold(sku=sku, qty=Decimal("2"), reference="SESS-B")
    assert second["success"], second

    assert availability.bump_session_hold_expiry("SESS-A") == 0

    quant.refresh_from_db()
    assert quant.available == Decimal("0")
    active_refs = set(Hold.objects.filter(sku=sku).active().values_list("metadata__reference", flat=True))
    assert active_refs == {"SESS-B"}


def test_bump_still_extends_live_cart_hold():
    sku = "T1BRIO"
    _product(sku, "Brioche")
    _receive(sku, "2")
    result = stock_adapter.create_hold(sku=sku, qty=Decimal("1"), reference="SESS-LIVE", ttl_minutes=5)
    assert result["success"], result

    assert availability.bump_session_hold_expiry("SESS-LIVE", ttl_minutes=30) == 1
    hold = Hold.objects.get(pk=_pk(result["hold_id"]))
    assert hold.expires_at > timezone.now() + timedelta(minutes=25)


# ── E2 ───────────────────────────────────────────────────────────────


def _split_stock(sku: str):
    _channel()
    _product(sku, "Baguete")
    _receive(sku, "2", "vitrine")
    _receive(sku, "2", "deposito")


def test_commit_gate_splits_remainder_across_quants():
    sku = "T1BAG"
    _split_stock(sku)
    order = _order(sku, 3, ref="WEB-T1-A01")

    stock_service.hold(order, require_all=True)

    entries = order.data["hold_ids"]
    assert sum(Decimal(str(e["qty"])) for e in entries) == Decimal("3")
    assert len(entries) == 2
    holds = Hold.objects.filter(pk__in=stock_service.hold_pks(entries))
    assert {h.metadata["reference"] for h in holds} == {"order:WEB-T1-A01"}
    assert len({h.quant_id for h in holds}) == 2


def test_commit_gate_split_is_all_or_nothing():
    from shopman.orderman.exceptions import ValidationError

    sku = "T1BAGX"
    _split_stock(sku)

    with pytest.raises(ValidationError, match="insufficient_supply"):
        stock_service.hold(_order(sku, 5, ref="WEB-T1-A02"), require_all=True)

    assert not Hold.objects.filter(sku=sku).active().exists()


# ── E3 ───────────────────────────────────────────────────────────────


def test_preorder_hold_backstop_counts_from_commitment_date():
    sku = "T1GELEIA"
    _channel()
    _product(sku, "Geleia")
    stockman_stock.receive(quantity=Decimal("1"), sku=sku, position=_position("loja"), reason="compra")
    target = timezone.localdate() + timedelta(days=5)
    order = _order(sku, 1, ref="WEB-T1-B01", data={"delivery_date": target.isoformat()})

    stock_service.hold(order, require_all=True)

    hold = Hold.objects.get(pk=_pk(order.data["hold_ids"][0]["hold_id"]))
    assert hold.quant_id is not None
    day_start = timezone.make_aware(datetime.combine(target, time.min))
    hours = stock_service._ORDER_HOLD_BACKSTOP_HOURS
    assert hold.expires_at >= day_start + timedelta(hours=hours) - timedelta(minutes=1)


def test_same_day_order_keeps_48h_backstop():
    sku = "T1PAO"
    _channel()
    _product(sku, "Pão")
    _receive(sku, "2")
    order = _order(sku, 1, ref="WEB-T1-B02")
    before = timezone.now()

    stock_service.hold(order, require_all=True)

    hold = Hold.objects.get(pk=_pk(order.data["hold_ids"][0]["hold_id"]))
    expected = before + timedelta(hours=stock_service._ORDER_HOLD_BACKSTOP_HOURS)
    assert abs(hold.expires_at - expected) < timedelta(minutes=2)


def test_order_hold_backstop_for_future_date_and_today():
    today = timezone.localdate()
    now = timezone.now()
    hours = stock_service._ORDER_HOLD_BACKSTOP_HOURS
    assert abs(stock_service._order_hold_backstop(today) - (now + timedelta(hours=hours))) < timedelta(seconds=5)
    assert abs(stock_service._order_hold_backstop(None) - (now + timedelta(hours=hours))) < timedelta(seconds=5)
    future = today + timedelta(days=3)
    assert stock_service._order_hold_backstop(future) == timezone.make_aware(
        datetime.combine(future, time.min)
    ) + timedelta(hours=hours)


# ── baixa concorrente ────────────────────────────────────────────────


def test_concurrent_fulfill_of_same_hold_is_idempotent_success():
    from shopman.stockman.service import Stock

    sku = "T1BOLO"
    _product(sku, "Bolo")
    _receive(sku, "2")
    hold_id = stock_adapter.create_hold(sku=sku, qty=Decimal("1"), reference="order:WEB-T1-C01")["hold_id"]
    real_fulfill = Stock.fulfill

    def _racing_fulfill(hid, **kwargs):
        # A outra chamada baixa primeiro; esta chega na trava e acha FULFILLED.
        real_fulfill(hid, **kwargs)
        raise StockError("INVALID_STATUS")

    with patch.object(Stock, "fulfill", side_effect=_racing_fulfill):
        outcome = stock_adapter.fulfill_hold(hold_id, qty=Decimal("1"))

    assert outcome == {"success": True, "error_code": None, "message": None}
    assert Hold.objects.get(pk=_pk(hold_id)).status == HoldStatus.FULFILLED


def test_fulfill_of_released_hold_still_fails():
    sku = "T1TORTA"
    _product(sku, "Torta")
    _receive(sku, "2")
    hold_id = stock_adapter.create_hold(sku=sku, qty=Decimal("1"), reference="order:WEB-T1-C02")["hold_id"]
    stock_adapter.release_holds([hold_id])

    outcome = stock_adapter.fulfill_hold(hold_id, qty=Decimal("1"))

    assert outcome["success"] is False
    assert outcome["error_code"] == "INVALID_STATUS"
