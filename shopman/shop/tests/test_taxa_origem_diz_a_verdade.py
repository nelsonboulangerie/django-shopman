"""A origem da taxa de entrega é a que DECIDIU a taxa (#3311).

Medido na pilha viva (22/11/2026): endereço do Centro, CEP 86020-030, com
coordenada, sem zona para o Centro. A taxa saiu pela faixa de distância (2,86 km)
e a origem saía ``zone``, porque CEP ou bairro preenchidos davam ``zone`` sempre.
O Recebimento e o Pagamento diziam "Tabela do bairro/CEP deste endereço".
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from shopman.shop.models import DeliveryDistanceBand, DeliveryZone, Shop
from shopman.shop.services.pos import resolve_delivery_fee

pytestmark = pytest.mark.django_db

# A loja na Rua Pará; o destino a uns 2,9 km.
LOJA = (Decimal("-23.3104"), Decimal("-51.1628"))
DESTINO = {"postal_code": "86020-030", "neighborhood": "Centro", "latitude": -23.335, "longitude": -51.17}


@pytest.fixture
def loja():
    shop = Shop.objects.create(name="Nelson", brand_name="Nelson", latitude=LOJA[0], longitude=LOJA[1])
    DeliveryDistanceBand.objects.create(shop=shop, max_distance_km=Decimal("5"), fee_q=500, is_active=True)
    return shop


def _origem(address: dict):
    return resolve_delivery_fee(address_structured=address, merchandise_q=3000)


def test_cep_sem_zona_e_taxa_pela_distancia_diz_distancia(loja):
    taxa = _origem(DESTINO)

    assert taxa.fee_q == 500
    assert taxa.distance_km is not None
    assert taxa.source == "distance"


def test_zona_que_casou_diz_zona(loja):
    DeliveryZone.objects.create(
        shop=loja, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=800, is_active=True,
    )

    taxa = _origem(DESTINO)

    assert (taxa.fee_q, taxa.source) == (800, "zone")


def test_sem_zona_e_sem_distancia_e_a_taxa_padrao(loja):
    taxa = _origem({"postal_code": "86020-030", "neighborhood": "Centro"})

    assert taxa.distance_km is None
    assert taxa.source == "default"
