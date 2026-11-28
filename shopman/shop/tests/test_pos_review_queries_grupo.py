"""Revisão do PDV com cliente identificado em GRUPO: o custo não cresce com as linhas.

O ``test_pos_review_queries`` mede a venda sem cliente. Com cliente de grupo a
revisão liga mais caminhos: os grupos do cliente, o desconto do grupo (promoção
``grupo-<ref>``, melhor entre os grupos, sem somar) e, na entrega, o frete grátis
do grupo. Cada um é lido uma vez por revisão; dez linhas custam o mesmo que uma.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier, PriceTierAdvantage

from shopman.shop.models import DeliveryZone, Promotion, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.tests.test_pos_review_queries import LINHAS, _skus, balcao  # noqa: F401

pytestmark = pytest.mark.django_db

ENDERECO = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "postal_code": "86010-000",
    "neighborhood": "Centro",
}


@pytest.fixture
def membro(balcao):  # noqa: F811
    DeliveryZone.objects.create(
        shop=Shop.objects.get(), name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=800, is_active=True,
    )
    now = timezone.now()
    tiers = []
    for ref, name, value in (("alianca", "Aliança Francesa", 15), ("equipe", "Equipe", 30)):
        tier = PriceTier.objects.create(ref=ref, name=name)
        Promotion.objects.create(
            ref=f"grupo-{ref}", name=name, type=Promotion.PERCENT, value=value, customer_segments=[ref],
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        PriceTierAdvantage.objects.create(
            tier=tier, kind=PriceTierAdvantage.Kind.FREE_SHIPPING, config={"min_order_q": 0},
        )
        tiers.append(tier)
    customer = Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990001")
    customer.price_tiers.set(tiers)
    return customer


def _payload(skus: list[str], *, delivery: bool) -> dict:
    payload = {
        "items": [{"sku": sku, "name": sku, "qty": 2, "unit_price_q": 900} for sku in skus],
        "fulfillment_type": "delivery" if delivery else "pickup",
        "payment_method": "cash",
        "customer_ref": "CLI-ANA",
    }
    if delivery:
        payload["delivery_address"] = ENDERECO["formatted_address"]
        payload["delivery_address_structured"] = dict(ENDERECO)
    return payload


def _measure(skus: list[str], *, delivery: bool):
    def review():
        return pos_service.review_sale(
            channel_ref="pdv", payload=_payload(skus, delivery=delivery), operator_username="marina",
        )

    review()  # aquece caches de processo
    with CaptureQueriesContext(connection) as ctx:
        result = review()
    return len(ctx.captured_queries), result


@pytest.mark.parametrize("delivery", [False, True], ids=["retirada", "entrega"])
def test_revisao_do_membro_de_grupo_nao_cresce_com_as_linhas(membro, delivery):
    medidas = {n: _measure(_skus(n), delivery=delivery) for n in (1, 5, LINHAS)}
    for n, (queries, _) in medidas.items():
        print(f"\nreview_sale membro {'entrega' if delivery else 'retirada'} {n:>2} linha(s): {queries} consultas")

    uma = medidas[1][0]
    assert medidas[5][0] == uma
    assert medidas[LINHAS][0] == uma, (
        f"review_sale do membro com {LINHAS} linhas fez {medidas[LINHAS][0]} consultas contra {uma} com 1: "
        "algum caminho de grupo voltou a ir ao banco por linha"
    )
    # O desconto do grupo entrou (a mercadoria sai abaixo do preço cheio): sem ele o
    # teste mediria a venda de um anônimo.
    review = medidas[LINHAS][1]
    assert review.total_q - review.delivery_fee_q < LINHAS * 2 * 900, review
