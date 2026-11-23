"""A taxa de entrega na tela de venda, antes do pagamento (#2402).

O Recebimento da venda dizia "A taxa deste endereço é calculada no pagamento": a
review, que resolve a taxa, só roda lá (#1209). A porta ``pos/delivery-fee/``
responde a taxa pelo MESMO motor da review (zona, faixa, frete grátis), com os
mesmos campos, para a tela mostrar o número com o cliente ainda no telefone.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.cashman.models import Shift

from shopman.shop.models import Channel, DeliveryZone, Promotion, Shop

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/pos/delivery-fee/"
ENDERECO = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "postal_code": "86010-000",
    "neighborhood": "Centro",
}


@pytest.fixture
def balcao(client):
    shop = Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True)
    DeliveryZone.objects.create(
        shop=shop, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=800, is_active=True,
    )
    fran = get_user_model().objects.create_user("fran", password="x", is_staff=True)
    fran.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(fran)
    return client


def _quote(client, **body):
    return client.post(URL, data=json.dumps(body), content_type="application/json")


def test_endereco_com_bairro_da_tabela_responde_a_taxa_da_zona(balcao):
    resposta = _quote(balcao, delivery_address_structured=ENDERECO, merchandise_q=3000)

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["delivery_fee_q"] == 800
    assert corpo["delivery_fee_source"] == "zone"
    assert corpo["delivery_fee_waiver"] is None


def test_endereco_em_branco_nao_e_frete_gratis(balcao):
    corpo = _quote(balcao, delivery_address_structured={}, merchandise_q=3000).json()

    # Zero com origem vazia é "pendente": a tela diz "Preencha o endereço".
    assert corpo["delivery_fee_q"] == 0
    assert corpo["delivery_fee_source"] == ""


def test_frete_gratis_da_promocao_vem_com_a_regra_pelo_nome(balcao):
    agora = timezone.now()
    promo = Promotion.objects.create(
        ref="frete-verao", name="Frete de verão", type=Promotion.FREE_DELIVERY, value=0,
        valid_from=agora - timedelta(days=1), valid_until=agora + timedelta(days=1),
    )
    promo.channels.set(Channel.objects.filter(ref="pdv"))

    corpo = _quote(balcao, delivery_address_structured=ENDERECO, merchandise_q=3000).json()

    assert corpo["delivery_fee_q"] == 0
    assert corpo["delivery_fee_source"] == "zone"
    assert corpo["delivery_fee_waiver"]["promotion_name"] == "Frete de verão"
    assert corpo["delivery_fee_waiver"]["base_fee_display"] == "R$ 8,00"


def test_valor_dos_produtos_ilegivel_nomeia_o_campo(balcao):
    resposta = _quote(balcao, delivery_address_structured=ENDERECO, merchandise_q="abc")

    assert resposta.status_code == 400
    assert resposta.json()["field"] == "merchandise_q"


def test_quem_nao_opera_o_caixa_nao_pergunta(client, balcao):
    cozinha = get_user_model().objects.create_user("cozinha", password="x", is_staff=True)
    client.force_login(cozinha)

    assert _quote(client, delivery_address_structured=ENDERECO, merchandise_q=3000).status_code == 403
