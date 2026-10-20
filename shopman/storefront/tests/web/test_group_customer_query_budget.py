"""Orçamento de consultas com cliente IDENTIFICADO em grupo: sacola e checkout.

O ``test_cart_query_budget`` mede a sacola do visitante. O cliente de grupo
comercial liga caminhos que o anônimo não percorre: os grupos do cliente
(``Customer.price_tiers``), o desconto do grupo (promoção ``grupo-<ref>``), o
frete grátis do grupo e as coleções exclusivas (``PriceTierAdvantage``). Cada um
deles é lido UMA vez por pedido, nunca por item.

A trava: a sacola e o checkout do membro com 1 item e com 5 itens fazem o MESMO
número de consultas, na retirada e na entrega. Estourar quer dizer que algum
caminho de grupo voltou a perguntar ao banco por linha.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier, PriceTierAdvantage

from shopman.shop.models import DeliveryZone, Promotion, Shop
from shopman.shop.services import sessions
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.tests.web.test_cart_query_budget import PAES, catalog  # noqa: F401
from shopman.storefront.tests.web.test_order_idor_regression import _login_as_customer

pytestmark = pytest.mark.django_db

ENDERECO = {"postal_code": "86050-270", "neighborhood": "Centro"}


@pytest.fixture
def membro(catalog):  # noqa: F811
    shop = Shop.load() or Shop.objects.create(name="Loja")
    DeliveryZone.objects.create(
        shop=shop, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX, match_value="860", fee_q=800,
    )
    alianca = PriceTier.objects.create(ref="alianca", name="Aliança Francesa", priority=1)
    equipe = PriceTier.objects.create(ref="equipe", name="Equipe", priority=5)
    now = timezone.now()
    for tier, value in ((alianca, 15), (equipe, 30)):
        Promotion.objects.create(
            ref=f"grupo-{tier.ref}", name=tier.name, type=Promotion.PERCENT, value=value,
            customer_segments=[tier.ref], valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        PriceTierAdvantage.objects.create(
            tier=tier, kind=PriceTierAdvantage.Kind.FREE_SHIPPING, config={"min_order_q": 0},
        )
    PriceTierAdvantage.objects.create(
        tier=alianca, kind=PriceTierAdvantage.Kind.EXCLUSIVE_COLLECTIONS, config={"collection_refs": ["bebidas"]},
    )
    customer = Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990001")
    customer.price_tiers.set([alianca, equipe])
    return customer


def _member_cart(customer, skus: list[str], *, delivery: bool) -> Client:
    client = Client()
    _login_as_customer(client, customer)
    for sku in skus:
        response = client.put(
            f"/api/v1/cart/skus/{sku}/", data=json.dumps({"qty": 1}), content_type="application/json",
        )
        assert response.status_code in (200, 201), (sku, response.status_code, response.content[:300])
    session_key = client.session.get("cart_session_key")
    ops = [{"op": "set_data", "path": "customer", "value": {
        "ref": customer.ref, "price_tiers": [t.ref for t in customer.price_tiers.all()],
    }}]
    if delivery:
        ops += [
            {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
            {"op": "set_data", "path": "delivery_address", "value": "Rua das Flores, 1"},
            {"op": "set_data", "path": "delivery_address_structured", "value": dict(ENDERECO)},
        ]
    sessions.modify_session(session_key=session_key, channel_ref=STOREFRONT_CHANNEL_REF, ops=ops)
    return client


def _queries(client: Client, path: str) -> tuple[int, dict]:
    client.get(path)  # aquece caches do processo
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(path)
    assert response.status_code == 200, (path, response.status_code, response.content[:300])
    return len(ctx.captured_queries), response.json()


@pytest.mark.parametrize("delivery", [False, True], ids=["retirada", "entrega"])
@pytest.mark.parametrize("path", ["/api/v1/storefront/cart/", "/api/v1/storefront/checkout/"])
def test_membro_de_grupo_custa_o_mesmo_com_um_ou_cinco_itens(membro, path, delivery):
    one, one_body = _queries(_member_cart(membro, PAES[:1], delivery=delivery), path)
    five, five_body = _queries(_member_cart(membro, PAES, delivery=delivery), path)
    print(f"\n{path} {'entrega' if delivery else 'retirada'}: 1 item={one} consultas, 5 itens={five}")

    assert five <= one, f"{path}: membro de grupo com 5 itens fez {five} consultas; com 1 item, {one}"


def test_o_cenario_exercita_o_desconto_do_grupo(membro):
    """Sem o desconto do grupo na conta, o teste mediria a sacola de um anônimo."""
    _, body = _queries(_member_cart(membro, PAES[:2], delivery=True), "/api/v1/storefront/cart/")
    cart = body["cart"]
    assert cart["discount_total_q"] > 0, cart
