"""Produto do catálogo sem ledger na loja online: vale a decisão do Stockman.

Antes (laudo CORE-SOVEREIGNTY, A2-1), a linha da sacola e a checagem de estoque
do checkout refaziam a promessa sobre a leitura crua do Stockman e ignoravam
``is_tracked``. Produto vendável sem estoque controlado (nenhum ``Quant``) lia
saldo zero: a sacola marcava a linha como indisponível, acendia o aviso "o
estoque mudou" e travava o "Finalizar", enquanto o Stockman e o portão de commit
aprovavam. Agora as duas leem a decisão do Stockman e não recalculam nada.

A regra do canal (``stock.allow_untracked``) é a do portão de commit, e o
contrato dela (``docs/reference/data-schemas.md``) é sobre SKU fora do
CATÁLOGO. Produto do catálogo sem ledger passa com o canal permitindo ou não,
porque é o que o Stockman decide; os dois canais estão aqui para provar isso.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db

SKU = "GELEIA-SEM-LEDGER"


def _world(*, allow_untracked: bool):
    from shopman.offerman.models import Listing, ListingItem, Product

    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="Casa", brand_name="Casa", short_name="Casa", phone="554333231997")
    Channel.objects.create(
        ref="web", name="Loja online", is_active=True,
        config={"stock": {"allow_untracked": allow_untracked}},
    )
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    product = Product.objects.create(
        sku=SKU, name="Geleia da casa", base_price_q=1800, is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=1800, is_published=True, is_sellable=True,
    )


@pytest.mark.parametrize("allow_untracked", [True, False], ids=["canal_permite", "canal_nao_permite"])
def test_catalog_sku_without_ledger_goes_from_cart_to_order(allow_untracked):
    from shopman.guestman.models import Customer
    from shopman.orderman.models import Order
    from shopman.stockman.models import Quant
    from shopman.stockman.services.availability import availability_for_sku, decision_from_availability

    from shopman.storefront.services.pickup_slots import get_slots
    from shopman.storefront.tests._checkout_baseline import with_baseline
    from shopman.storefront.tests.security.conftest import login_as_customer

    _world(allow_untracked=allow_untracked)
    assert not Quant.objects.filter(sku=SKU).exists()
    decision = decision_from_availability(SKU, Decimal("2"), availability_for_sku(SKU))
    assert decision.approved and decision.is_tracked is False

    client = Client()
    login_as_customer(client, Customer.objects.create(ref="CUST-ANA", first_name="Ana", phone="+5543999990001"))
    resp = client.put(f"/api/v1/cart/skus/{SKU}/", data=json.dumps({"qty": 2}), content_type="application/json")
    assert resp.status_code in (200, 201), resp.content[:400]

    # A sacola diz o que o Stockman disse: linha disponível, sem teto, sem aviso.
    body = client.get("/api/v1/storefront/cart/").json()
    cart = body.get("cart") or body
    [line] = cart["items"]
    assert (line["sku"], line["is_available"], line["available_qty"]) == (SKU, True, None)
    assert cart["has_unavailable_items"] is False

    payload = with_baseline(client, {
        "name": "Ana", "phone": "+5543999990001",
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": get_slots()[-1]["ref"],
        "payment_method": "cash",
    })
    resp = client.post("/api/v1/checkout/", data=payload, content_type="application/json")

    assert resp.status_code == 201, resp.content[:600]
    order = Order.objects.get()
    assert [i.sku for i in order.items.all()] == [SKU]
    assert order.data["hold_ids"] == [{"sku": SKU, "hold_id": None, "qty": 0, "is_tracked": False}]
