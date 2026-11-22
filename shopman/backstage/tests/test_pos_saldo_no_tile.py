"""O saldo em número no tile da grade (#2610, WP-E8 do plano de excelência do PDV).

O WP-E4 fez o selo "Esgotado" mudar ao vivo; o número de unidades ficou de fora.
Agora a mesma leitura do Stockman que decide o selo dá também quantas unidades a
casa ainda promete hoje (``units_left``), na projeção inteira e no ``?only=
availability`` que o aviso de estoque relê. O número só aparece quando quer dizer
"restam": há pronto na prateleira, o item não é vendido por peso, não está
esgotado e o estoque é rastreado.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/pos/"

# O que o Stockman responde por SKU (o formato de ``availability_for_skus``).
PRATELEIRA = {"is_tracked": True, "total_promisable": Decimal("3"), "available": Decimal("3")}
SO_FORNADA = {"is_tracked": True, "total_promisable": Decimal("12"), "available": Decimal("0"), "is_planned": True}
ESGOTADO = {"is_tracked": True, "total_promisable": Decimal("0"), "availability_policy": "stock_only"}
SEM_RASTREIO = {"is_tracked": False}
QUILO = {"is_tracked": True, "total_promisable": Decimal("4"), "available": Decimal("4")}

STOCK = {"PAO": PRATELEIRA, "BRIOCHE": SO_FORNADA, "CROISSANT": ESGOTADO, "CAFE": SEM_RASTREIO, "QUEIJO": QUILO}


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref=POS_CHANNEL_REF, name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    listing = Listing.objects.create(ref=POS_CHANNEL_REF, name="PDV", is_active=True)
    for sku in STOCK:
        product = Product.objects.create(
            sku=sku, name=sku.title(), base_price_q=1000, is_published=True, is_sellable=True,
            unit="kg" if sku == "QUEIJO" else "un",
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=1000)
    operator = get_user_model().objects.create_user(username="fran", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos")
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return client


def _stock(overrides: dict | None = None):
    table = {**STOCK, **(overrides or {})}

    def availability(skus, *, channel_ref, target_date=None):
        return {sku: table[sku] for sku in skus if sku in table}

    return mock.patch("shopman.shop.projections.catalog_context.availability_for_skus", side_effect=availability)


def _units_left(client, url: str) -> dict:
    response = client.get(url)
    assert response.status_code == 200, response.content
    body = response.json()
    rows = body["availability"] if "availability" in body else body["pos"]["products"]
    return {row["sku"]: row["units_left"] for row in rows}


def test_o_tile_diz_quantas_restam_so_quando_o_numero_quer_dizer_restam(balcao):
    with _stock():
        left = _units_left(balcao, URL)

    assert left["PAO"] == 3
    # Só a fornada de mais tarde: "Restam 12" de pão que ainda não saiu mentiria.
    assert left["BRIOCHE"] is None
    # Esgotado: quem fala é o selo.
    assert left["CROISSANT"] is None
    # Sem rastreio: o zero é ausência de dado.
    assert left["CAFE"] is None
    # Vendido por peso: o teto é em quilo, e "Restam 4" não diz nada ao balcão.
    assert left["QUEIJO"] is None


def test_o_aviso_de_estoque_traz_o_mesmo_numero_da_projecao(balcao):
    with _stock():
        projection = _units_left(balcao, URL)
        availability = _units_left(balcao, f"{URL}?only=availability")

    assert availability == projection


def test_a_venda_de_outro_balcao_baixa_o_numero(balcao):
    with _stock():
        before = _units_left(balcao, f"{URL}?only=availability")
    with _stock({"PAO": {**PRATELEIRA, "total_promisable": Decimal("2"), "available": Decimal("2")}}):
        after = _units_left(balcao, f"{URL}?only=availability")

    assert (before["PAO"], after["PAO"]) == (3, 2)
