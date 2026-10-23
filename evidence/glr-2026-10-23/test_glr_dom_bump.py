# ruff: noqa
# Prova do laudo docs/reports/2026-10-23-laudo-adversarial-go-live.md: PASSA enquanto o defeito existe.
"""glr-dom: bump_session_hold_expiry ressuscita hold JÁ vencido -> oversell."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind

from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.services import availability

pytestmark = pytest.mark.django_db
SKU = "GLRCROI"


def test_bump_resurrects_expired_hold_and_overholds():
    Product.objects.create(sku=SKU, name="Croissant", base_price_q=500, is_published=True, is_sellable=True)
    pos = Position.objects.create(ref="loja", name="Loja", kind=PositionKind.PHYSICAL, is_saleable=True)
    quant = stock.receive(quantity=Decimal("2"), sku=SKU, position=pos, target_date=date.today(), reason="fornada")

    # Sacola A reserva os 2 (TTL 30 min)
    ra = stock_adapter.create_hold(sku=SKU, qty=Decimal("2"), reference="SESS-A")
    assert ra["success"], ra
    # A some 31 min; o release_expired (cron 5 min) ainda não passou
    Hold.objects.filter(pk=int(ra["hold_id"].split(":")[1])).update(expires_at=timezone.now() - timedelta(minutes=1))

    # Sacola B pega os 2 (o hold vencido de A não conta)
    rb = stock_adapter.create_hold(sku=SKU, qty=Decimal("2"), reference="SESS-B")
    assert rb["success"], rb

    # A volta e mexe na sacola (ou o checkout chama bump): hold vencido revive
    bumped = availability.bump_session_hold_expiry("SESS-A")
    print("bumped", bumped)
    quant.refresh_from_db()
    active = list(Hold.objects.filter(sku=SKU).active().values_list("metadata__reference", "quantity"))
    print("active holds", active, "quantity", quant._quantity, "available", quant.available)
    assert quant.available == Decimal("-2")  # 4 reservados sobre 2 físicos
