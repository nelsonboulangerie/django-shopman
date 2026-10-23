# ruff: noqa
# Prova do laudo docs/reports/2026-10-23-laudo-adversarial-go-live.md: PASSA enquanto o defeito existe.
"""glr-dom: gate de commit (require_all) não reparte o resto entre quants."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind

from shopman.shop.services import availability
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db
SKU = "GLRBAG"


def _order(qty):
    order = MagicMock()
    order.ref = "WEB-GLR-A01"
    order.channel_ref = "web"
    order.session_key = "SESS-GLR"
    order.data = {}
    order.snapshot = {"items": [{"sku": SKU, "qty": qty, "line_id": "l1", "meta": {}}], "data": {}}
    order.items.all.return_value = []
    return order


def test_commit_refuses_when_stock_split_across_quants():
    from shopman.shop.models import Channel
    Channel.objects.get_or_create(ref="web", defaults={"name": "web"})
    Product.objects.create(sku=SKU, name="Baguete", base_price_q=900, is_published=True, is_sellable=True)
    vit = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    dep = Position.objects.create(ref="deposito", name="Depósito", kind=PositionKind.PHYSICAL, is_saleable=True)
    stock.receive(quantity=Decimal("2"), sku=SKU, position=vit, target_date=date.today(), reason="fornada")
    stock.receive(quantity=Decimal("2"), sku=SKU, position=dep, target_date=date.today(), reason="fornada")

    chk = availability.check(SKU, Decimal("3"), channel_ref="web")
    print("check", chk["ok"], chk["available_qty"])
    # sacola expirou (ou pedido sem sacola): o gate de commit cria o resto num quant só
    assert chk["ok"] and chk["available_qty"] >= 3
    from shopman.orderman.exceptions import ValidationError
    with pytest.raises(ValidationError, match="insufficient_supply"):
        stock_service.hold(_order(3), require_all=True)
