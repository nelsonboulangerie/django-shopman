"""Populate the empty stock book through its canonical movement writer."""
from decimal import Decimal
from unittest.mock import patch

from shopman.stockman.models import Move, Position, PositionKind
from shopman.stockman.services.movements import StockMovements

with patch("shopman.orderman.dispatch._on_commit_callback"):
    position, _ = Position.objects.get_or_create(ref="lab-restore-stock", defaults={
        "name": "Estoque sintético do restore", "kind": PositionKind.PHYSICAL,
    })
    if not Move.objects.filter(quant__sku="LAB-RESTORE-STOCK").exists():
        quant = StockMovements.receive(quantity=Decimal("2.500"), sku="LAB-RESTORE-STOCK",
            position=position, batch="lab-restore", reason="Synthetic restore receipt", kind=Move.Kind.BUY)
        StockMovements.issue(quantity=Decimal("0.500"), quant=quant,
            reason="Synthetic fractional issue", kind=Move.Kind.SELL)
print("Canonical synthetic stock receipt and fractional issue preserved; no provider invoked.")
