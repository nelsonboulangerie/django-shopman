"""O "Cadastrar cliente" do PDV não grava documento nem WhatsApp inválidos.

Beta test de 05/11/2026 (PDV-03). A venda já recusava CPF com dígito errado
(``parse_pos_sale_intent``), mas o cadastro pelo modal Cliente gravava antes:
o cliente nascia com ``11111111111`` no CRM e só a venda recusava, depois. E o
WhatsApp ``123`` sumia calado, porque a normalização devolve vazio.
"""

from __future__ import annotations

import pytest
from shopman.guestman.models import Customer

from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos import resolve_or_create_customer
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _pdv():
    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})


def test_cpf_com_digito_errado_e_recusado_sem_gravar():
    with pytest.raises(PosIntentError) as refused:
        resolve_or_create_customer(name="Beta Fran", tax_id="11111111111", operator_username="joyce")
    assert refused.value.code == "invalid_customer_tax_id"
    assert refused.value.field == "customer_tax_id"
    assert not Customer.objects.exists()


def test_whatsapp_que_nao_e_telefone_e_recusado_sem_gravar():
    with pytest.raises(PosIntentError) as refused:
        resolve_or_create_customer(name="Beta Fran", phone="123", operator_username="joyce")
    assert refused.value.code == "invalid_customer_phone"
    assert refused.value.field == "customer_phone"
    assert not Customer.objects.exists()


def test_cadastro_com_cpf_e_whatsapp_validos_continua_nascendo():
    saved = resolve_or_create_customer(
        name="Beta Fran", phone="(43) 99111-1111", tax_id="529.982.247-25", operator_username="joyce",
    )
    assert saved["ref"]
    customer = Customer.objects.get(ref=saved["ref"])
    assert customer.document == "52998224725"
