# ruff: noqa
# Prova do laudo docs/reports/2026-10-23-laudo-adversarial-go-live.md: PASSA enquanto o defeito existe.
"""glr-dom: encomenda para D+5 ancorada em estoque físico expira em 48h."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind
from shopman.stockman.services.holds import StockHolds

from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db
SKU = "GLRGELEIA"


def test_preorder_hold_on_physical_stock_expires_before_date():
    from shopman.shop.models import Channel
    Channel.objects.get_or_create(ref="web", defaults={"name": "web"})
    Product.objects.create(sku=SKU, name="Geleia", base_price_q=3500, is_published=True, is_sellable=True)
    pos = Position.objects.create(ref="loja", name="Loja", kind=PositionKind.PHYSICAL, is_saleable=True)
    stock.receive(quantity=Decimal("1"), sku=SKU, position=pos, reason="compra")  # mercearia, sem data

    target = timezone.localdate() + timedelta(days=5)
    order = MagicMock()
    order.ref = "WEB-GLR-B01"
    order.channel_ref = "web"
    order.session_key = "SESS-GLR-B"
    order.data = {"delivery_date": target.isoformat()}
    order.snapshot = {"items": [{"sku": SKU, "qty": 1, "line_id": "l1", "meta": {}}], "data": order.data}
    stock_service.hold(order, require_all=True)
    entry = order.data["hold_ids"][0]
    h = Hold.objects.get(pk=int(entry["hold_id"].split(":")[1]))
    print("hold", h.hold_id, "quant", h.quant_id, "target", h.target_date, "expires", h.expires_at)
    assert h.quant_id is not None and h.expires_at is not None
    assert h.expires_at < timezone.make_aware(timezone.datetime.combine(target, timezone.datetime.min.time()))
    # 49h depois: o release_expired solta, e a geleia volta a ser vendável
    Hold.objects.filter(pk=h.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    print("released", StockHolds.release_expired())
    h.refresh_from_db(); print("status", h.status)
    from shopman.shop.adapters import stock as ad
    print("fulfill on date:", ad.fulfill_hold(h.hold_id, qty=Decimal("1")))
