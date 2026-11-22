"""A grade do PDV mostra o preço da promoção automática no ar (P2-2, WP-E8).

Na Semana do Pão o tile dizia R$ 16,00 e a linha cobrava R$ 13,60: o operador
anunciava ao cliente o preço errado. Só a Hora da Xepa riscava a etiqueta. Agora o
tile traz o preço que a linha de uma venda de balcão sem cliente ganha, pela mesma
régua do cartão da loja (``catalog_context.contextual_price``), e a promoção
compete com a Xepa em "maior desconto ganha", como no motor.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.tests.test_pos_projecao_consultas import URL, balcao  # noqa: F401
from shopman.shop.models import Channel, Promotion, RuleConfig

pytestmark = pytest.mark.django_db

BRT = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 10, 10, 16, 0, tzinfo=BRT)
NA_XEPA = datetime(2026, 10, 10, 17, 40, tzinfo=BRT)


def _promocao(ref: str, value: int, **extra) -> Promotion:
    promo = Promotion.objects.create(
        ref=ref,
        name=extra.pop("name", "Semana do Pão"),
        type=Promotion.PERCENT,
        value=value,
        valid_from=AGORA - timedelta(days=1),
        valid_until=AGORA + timedelta(days=6),
        **extra,
    )
    return promo


@pytest.fixture
def vitrine(balcao):  # noqa: F811
    listing = Listing.objects.get(ref="pdv")
    pao = Product.objects.create(sku="PAO", name="Pão", base_price_q=1600, is_published=True, is_sellable=True)
    cafe = Product.objects.create(sku="CAFE", name="Café", base_price_q=800, is_published=True, is_sellable=True)
    for product in (pao, cafe):
        ListingItem.objects.create(listing=listing, product=product, price_q=product.base_price_q)
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


def test_na_semana_do_pao_o_tile_mostra_o_preco_da_linha_e_a_etiqueta_riscada(vitrine):
    _promocao("semana-do-pao", 15, skus=["PAO"])

    pos = _read(vitrine, AGORA)

    pao = _tile(pos, "PAO")
    assert pao["price_q"] == 1360
    assert pao["price_display"] == "R$ 13,60"
    assert pao["list_price_q"] == 1600
    assert pao["list_price_display"] == "R$ 16,00"
    assert pao["discount_label"] == "Semana do Pão"
    # Fora da promoção, a etiqueta é o preço.
    cafe = _tile(pos, "CAFE")
    assert (cafe["price_q"], cafe["list_price_q"], cafe["discount_label"]) == (800, 0, "")


def test_o_tile_e_a_revisao_dao_o_mesmo_preco(vitrine):
    from shopman.shop.services import pos as pos_service

    _promocao("semana-do-pao", 15, skus=["PAO"])
    tile_q = _tile(_read(vitrine, AGORA), "PAO")["price_q"]
    with patch("django.utils.timezone.now", return_value=AGORA):
        review = pos_service.review_sale(
            channel_ref="pdv",
            payload={"items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": tile_q}], "payment_method": "cash"},
            operator_username="marina",
        )
    assert review.total_q == tile_q == 1360


def test_com_a_xepa_aberta_o_maior_desconto_ganha(vitrine):
    _promocao("semana-do-pao", 15, skus=["PAO"])
    rule = RuleConfig.objects.create(
        ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Hora da Xepa", params={"discount_percent": 25, "start": "17:30", "end": "18:00"}, enabled=True,
    )
    rule.channels.set(Channel.objects.filter(ref="pdv"))
    cache.clear()

    pao = _tile(_read(vitrine, NA_XEPA), "PAO")

    assert pao["price_q"] == 1200
    assert pao["list_price_q"] == 1600
    assert pao["discount_label"] == "Happy Hour"


@pytest.mark.parametrize(
    "condicao",
    [
        {"min_order_q": 5000},
        {"birthday_only": True},
        {"customer_segments": ["vip"]},
        {"fulfillment_types": ["delivery"]},
    ],
    ids=["pedido-minimo", "aniversario", "grupo", "so-entrega"],
)
def test_promocao_que_a_venda_sem_cliente_nao_ganha_nao_entra_no_tile(vitrine, condicao):
    _promocao("condicionada", 15, skus=["PAO"], **condicao)

    pao = _tile(_read(vitrine, AGORA), "PAO")

    assert (pao["price_q"], pao["list_price_q"], pao["discount_label"]) == (1600, 0, "")


def test_promocao_de_outro_canal_nao_entra_no_tile(vitrine):
    promo = _promocao("so-na-loja", 15, skus=["PAO"])
    loja = Channel.objects.exclude(ref="pdv").first() or Channel.objects.create(ref="web", name="Loja")
    promo.channels.set([loja])

    pao = _tile(_read(vitrine, AGORA), "PAO")

    assert pao["price_q"] == 1600
