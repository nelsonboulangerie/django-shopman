"""SKU esgotado continua RASTREADO — e por isso não vende.

``is_tracked`` responde "o Stockman já controlou este SKU?", não "tem saldo agora?".
SKU não rastreado é aprovado sem limite (``available_qty = 999999``); então, se um
SKU esgotado deixasse de ser rastreado, ele passaria a vender sem limite exatamente
quando acabou.

É a trava do P7 do relatório 13 (``tracked_skus`` com ``_quantity__gt=0``): o quant
zerado não é apagado (``_quantity`` é o cache do livro de movimentos), e é ele que
mantém o SKU rastreado. Otimizar aquela consulta é bem-vindo; mudar esta resposta, não.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind, Quant
from shopman.stockman.services.availability import availability_for_sku, availability_for_skus

from shopman.shop.services import availability

pytestmark = pytest.mark.django_db

SKU = "ESGOTA"


@pytest.fixture
def sold_out():
    Product.objects.create(sku=SKU, name="Esgota", base_price_q=500, is_published=True, is_sellable=True)
    position = Position.objects.create(ref="loja", name="Loja", kind=PositionKind.PHYSICAL, is_saleable=True)
    quant = stock.receive(
        quantity=Decimal("3"), sku=SKU, position=position, target_date=date.today(), reason="entrada",
    )
    stock.adjust(quant, Decimal("0"), reason="vendeu tudo")
    assert Quant.objects.filter(sku=SKU).exists()
    assert not Quant.objects.filter(sku=SKU, _quantity__gt=0).exists()


def test_sold_out_sku_is_still_tracked(sold_out):
    assert availability_for_sku(SKU)["is_tracked"] is True
    assert availability_for_skus([SKU])[SKU]["is_tracked"] is True


def test_sold_out_sku_is_refused_not_unlimited(sold_out):
    result = availability.check(SKU, Decimal("1"))
    assert result["ok"] is False
    assert result["untracked"] is False
    assert result["available_qty"] != Decimal("999999")
