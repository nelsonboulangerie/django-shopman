"""A caixa física da caixa presente é estoque limitado e restringe a venda do kit.

Decisão do dono (24/09/2026): "a caixa é, em si, um item de estoque limitado, e
pode restringir sim a venda do kit". A embalagem (``<SKU>-EMB``) não tem
listagem — não se vende avulsa — e mesmo assim entra na disponibilidade do kit
(mínimo dos componentes), na reserva e na baixa da venda.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.offerman.models import AvailabilityPolicy, Listing, ListingItem, Product, ProductComponent
from shopman.orderman.models import Order
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind, Quant

from shopman.shop.models import Channel
from shopman.shop.services import availability
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def kit(db):
    Channel.objects.create(ref="pdv", name="PDV")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)

    bread = Product.objects.create(
        sku="PAO-KIT", name="Pão de Campagne", base_price_q=2000, is_sellable=True,
        availability_policy=AvailabilityPolicy.STOCK_ONLY,
        metadata={"fiscal": {"profile": "standard", "ncm": "19059090"}},
    )
    packaging = Product.objects.create(
        sku="CAIXA-KIT-EMB", name="Caixa Presente (embalagem)", base_price_q=0, is_sellable=True,
        availability_policy=AvailabilityPolicy.STOCK_ONLY,
        metadata={"kit_packaging": True, "fiscal": {"profile": "standard", "ncm": "48192000"}},
    )
    box = Product.objects.create(
        sku="CAIXA-KIT", name="Caixa Presente", base_price_q=6000, is_sellable=True,
        metadata={"kit": True, "fiscal": {"profile": "standard", "ncm": "19059090"}},
    )
    ProductComponent.objects.create(parent=box, component=bread, qty=1)
    ProductComponent.objects.create(parent=box, component=packaging, qty=1)
    # Só o kit é vendido no canal: pão e caixa NÃO estão na listagem.
    ListingItem.objects.create(listing=listing, product=box, price_q=6000, is_published=True, is_sellable=True)

    stock.receive(quantity=Decimal("5"), sku="PAO-KIT", position=vitrine, reason="teste")
    stock.receive(quantity=Decimal("2"), sku="CAIXA-KIT-EMB", position=vitrine, reason="teste")
    return {"vitrine": vitrine}


def _quantity(sku: str) -> Decimal:
    return sum((q.quantity for q in Quant.objects.filter(sku=sku)), Decimal("0"))


def test_kit_disponivel_e_o_minimo_dos_componentes_inclusive_a_caixa(kit):
    result = availability.check("CAIXA-KIT", Decimal("1"), channel_ref="pdv")

    assert result["ok"] and result["is_bundle"]
    assert result["available_qty"] == Decimal("2")  # 5 pães, 2 caixas


def test_componente_fora_da_listagem_compoe_o_kit(kit):
    # A caixa não tem listagem e não se vende avulsa...
    assert availability.check("CAIXA-KIT-EMB", Decimal("1"), channel_ref="pdv")["error_code"] == "not_in_listing"
    # ...mas compõe o kit.
    assert availability.check("CAIXA-KIT", Decimal("2"), channel_ref="pdv")["ok"]


def test_componente_listado_e_pausado_no_canal_segue_recusando_o_kit(kit):
    listing = Listing.objects.get(ref="pdv")
    ListingItem.objects.create(
        listing=listing, product=Product.objects.get(sku="PAO-KIT"), price_q=2000, is_sellable=False,
    )

    result = availability.check("CAIXA-KIT", Decimal("1"), channel_ref="pdv")

    assert not result["ok"] and result["failed_sku"] == "PAO-KIT"


def test_sem_caixa_em_estoque_o_kit_fica_indisponivel(kit):
    result = availability.check("CAIXA-KIT", Decimal("3"), channel_ref="pdv")

    assert not result["ok"]
    assert result["failed_sku"] == "CAIXA-KIT-EMB"


def test_caixa_com_saldo_zero_rastreado_derruba_o_kit(kit):
    quant = Quant.objects.get(sku="CAIXA-KIT-EMB")
    stock.issue(Decimal("2"), quant, reason="teste: caixas acabaram")

    result = availability.check("CAIXA-KIT", Decimal("1"), channel_ref="pdv")

    assert not result["ok"] and result["failed_sku"] == "CAIXA-KIT-EMB"


def test_reserva_do_kit_segura_a_caixa(kit):
    result = availability.reserve("CAIXA-KIT", Decimal("1"), session_key="SESS-KIT", channel_ref="pdv")

    assert result["ok"]
    assert len(result["hold_ids"]) == 2
    held = set(Hold.objects.filter(metadata__reference="SESS-KIT").values_list("sku", flat=True))
    assert held == {"PAO-KIT", "CAIXA-KIT-EMB"}


def test_venda_do_kit_baixa_a_caixa(kit):
    order = Order.objects.create(
        ref="ORD-KIT-STOCK-1", channel_ref="pdv", status=Order.Status.NEW, total_q=6000,
        snapshot={"items": [{"sku": "CAIXA-KIT", "qty": "1", "unit_price_q": 6000, "line_total_q": 6000}]},
    )

    stock_service.hold(order)
    order.refresh_from_db()
    assert {h["sku"] for h in order.data["hold_ids"]} == {"PAO-KIT", "CAIXA-KIT-EMB"}
    stock_service.fulfill(order)

    assert _quantity("CAIXA-KIT-EMB") == Decimal("1")
    assert _quantity("PAO-KIT") == Decimal("4")
