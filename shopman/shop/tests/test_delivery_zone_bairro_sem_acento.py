"""Zona por bairro casa sem distinguir acento (laudo de encomendas 09/11).

O cliente digita "Bela Suica" e a zona está cadastrada como "Bela Suíça": sem a
mesma régua de cidade/UF (``normalize_locality``), a zona não casava e o pedido
pagava a taxa da faixa de distância.
"""

import pytest

from shopman.shop.models import DeliveryZone, Shop


@pytest.fixture
def zona_bela_suica(db):
    shop = Shop.objects.first() or Shop.objects.create(name="Loja")
    return DeliveryZone.objects.create(
        shop=shop,
        name="Bela Suíça",
        zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Bela Suíça",
        fee_q=0,
        is_active=True,
    )


@pytest.mark.parametrize("digitado", ["Bela Suica", "bela  suíça", " BELA SUIÇA "])
def test_bairro_digitado_sem_acento_casa_a_zona(zona_bela_suica, digitado):
    assert DeliveryZone.match(postal_code="", neighborhood=digitado) == zona_bela_suica


def test_bairro_diferente_nao_casa(zona_bela_suica):
    assert DeliveryZone.match(postal_code="", neighborhood="Bela Vista") is None
    assert DeliveryZone.match(postal_code="", neighborhood="") is None
