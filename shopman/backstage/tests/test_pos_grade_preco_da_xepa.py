"""A grade do PDV mostra o preço que o motor cobra AGORA (Hora da Xepa).

Com a janela de desconto por horário aberta, o tile dizia o preço cheio e a
revisão cobrava o descontado: o operador anunciava um valor e a tela de
pagamento outro. Agora o tile traz o preço da janela (``price_q``) e a etiqueta
para riscar (``list_price_q``), pela MESMA conta do ``TimeWindowDiscountModifier``
(``modifiers.time_window_offer``). A projeção também diz quando a janela abre ou
fecha (``price_window.next_change_at``), para a tela reler sozinha.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.tests.test_pos_projecao_consultas import URL, balcao  # noqa: F401
from shopman.shop.models import Channel, RuleConfig

pytestmark = pytest.mark.django_db

BRT = ZoneInfo("America/Sao_Paulo")
NA_XEPA = datetime(2026, 10, 10, 17, 40, tzinfo=BRT)
ANTES_DA_XEPA = datetime(2026, 10, 10, 16, 0, tzinfo=BRT)


@pytest.fixture
def vitrine(balcao):  # noqa: F811
    listing = Listing.objects.get(ref="pdv")
    pao = Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)
    queijo = Product.objects.create(
        sku="QUEIJO", name="Queijo", base_price_q=8000, unit="kg", is_published=True, is_sellable=True,
    )
    for product in (pao, queijo):
        ListingItem.objects.create(listing=listing, product=product, price_q=product.base_price_q)
    rule = RuleConfig.objects.create(
        ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Hora da Xepa", params={"discount_percent": 25, "start": "17:30", "end": "18:00"}, enabled=True,
    )
    rule.channels.set(Channel.objects.filter(ref="pdv"))
    cache.clear()
    yield balcao
    cache.clear()


def _read(client, at: datetime) -> dict:
    with patch("django.utils.timezone.now", return_value=at):
        response = client.get(URL)
    assert response.status_code == 200, response.content
    return response.json()["pos"]


def _tile(pos: dict, sku: str) -> dict:
    return next(product for product in pos["products"] if product["sku"] == sku)


def test_na_xepa_o_tile_mostra_o_preco_do_motor_e_a_etiqueta_riscada(vitrine):
    pos = _read(vitrine, NA_XEPA)

    pao = _tile(pos, "PAO")
    assert pao["price_q"] == 900
    assert pao["price_display"] == "R$ 9,00"
    assert pao["list_price_q"] == 1200
    assert pao["list_price_display"] == "R$ 12,00"
    # O rótulo é o do motor (copy CART_DISCOUNT_LABEL_TIME_WINDOW; o seed da casa diz "Hora da Xepa").
    assert pao["discount_label"] == "Happy Hour"
    queijo = _tile(pos, "QUEIJO")
    assert queijo["price_display"] == "R$ 60,00/kg"
    assert queijo["list_price_display"] == "R$ 80,00/kg"
    assert pos["price_window"]["active"] is True
    # Fecha às 18:00: é quando a tela relê e o preço volta ao cheio.
    assert pos["price_window"]["next_change_at"] == datetime(2026, 10, 10, 18, 0, tzinfo=BRT).isoformat()


def test_fora_da_xepa_o_tile_mostra_a_etiqueta_e_a_projecao_diz_quando_abre(vitrine):
    pos = _read(vitrine, ANTES_DA_XEPA)

    pao = _tile(pos, "PAO")
    assert pao["price_q"] == 1200
    assert pao["price_display"] == "R$ 12,00"
    assert pao["list_price_q"] == 0
    assert pao["list_price_display"] == ""
    assert pos["price_window"]["active"] is False
    assert pos["price_window"]["next_change_at"] == datetime(2026, 10, 10, 17, 30, tzinfo=BRT).isoformat()


def test_o_tile_e_o_fechamento_dao_o_mesmo_preco(vitrine):
    # A grade e o kernel leem a mesma janela: o preço do tile é o que a revisão cobra.
    from shopman.shop.services import pos as pos_service

    tile_q = _tile(_read(vitrine, NA_XEPA), "PAO")["price_q"]
    with patch("django.utils.timezone.now", return_value=NA_XEPA):
        review = pos_service.review_sale(
            channel_ref="pdv",
            payload={"items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": tile_q}], "payment_method": "cash"},
            operator_username="marina",
        )
    assert review.total_q == tile_q == 900


def test_sem_regra_para_o_pdv_nao_ha_janela(vitrine):
    RuleConfig.objects.filter(ref="happy_hour").update(enabled=False)
    cache.clear()

    pos = _read(vitrine, NA_XEPA)

    assert pos["price_window"] is None
    assert _tile(pos, "PAO")["price_q"] == 1200
