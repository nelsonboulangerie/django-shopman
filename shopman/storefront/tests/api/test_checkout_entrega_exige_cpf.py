"""Loja: entrega com nota pede o CPF/CNPJ no checkout; na próxima ele já vem preenchido.

Decisão do dono (24/09/2026): pedir o CPF na ENTRADA do pedido; sem CPF, a
entrega não fica disponível e a retirada continua. A trava é do commit
(``DeliveryFiscalIdentityRule``); a loja manda o dado e lê a recusa no campo.

Decisão do dono (25/09/2026): sem pergunta de "guardar". Na próxima entrega o
campo vem com o documento do cadastro ou, sem ele, com o da última entrega — e
o cadastro nunca é escrito pelo checkout.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import DeliveryZone, Shop
from shopman.shop.services import fiscal
from shopman.storefront.tests._checkout_auth import authenticate_checkout
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

CPF = "52998224725"
ADDRESS = {
    "formatted_address": "Rua das Flores, 1 - Centro, Londrina - PR",
    "route": "Rua das Flores",
    "street_number": "1",
    "neighborhood": "Centro",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86050-270",
}


@pytest.fixture
def delivery_with_note(client, monkeypatch, settings):
    from django.core.cache import cache

    cache.clear()  # o limite de 3 checkouts/min é por IP e vaza entre testes
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = (
        "shopman.shop.fiscal_resolvers.on_request_or_tax_id,"
        "shopman.shop.fiscal_resolvers.eletronic_payment,"
        "shopman.shop.fiscal_resolvers.deferred_settlement"
    )
    _seed_surface()
    customer = authenticate_checkout(client)
    DeliveryZone.objects.create(
        shop=Shop.objects.first(), name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX, match_value="860", fee_q=600,
    )
    add = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 2}, content_type="application/json")
    assert add.status_code == 200, add.content
    yield customer
    cache.clear()  # e não deixa o contador para o próximo arquivo


def _payload(**over):
    payload = {
        "name": "Ana",
        "phone": "+5543999990001",
        "fulfillment_type": "delivery",
        "delivery_address": ADDRESS["formatted_address"],
        "delivery_address_structured": ADDRESS,
        "delivery_date": timezone.localdate().isoformat(),
        "payment_method": "cash",
    }
    payload.update(over)
    return payload


def _post(client, **over):
    return client.post(
        "/api/v1/checkout/", data=with_baseline(client, _payload(**over)), content_type="application/json",
    )


def test_entrega_sem_cpf_e_recusada_no_campo_do_cpf(client, delivery_with_note):
    resp = _post(client)
    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["field"] == "fiscal_tax_id"
    assert body["errors"] == {"fiscal_tax_id": "Para entregar, precisamos do CPF ou CNPJ para a nota fiscal."}
    assert not Order.objects.exists()


def test_cpf_com_digito_errado_e_recusado_antes_do_commit(client, delivery_with_note):
    resp = _post(client, fiscal_tax_id="529.982.247-00")
    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "fiscal_tax_id"
    assert resp.json()["detail"] == "Confira o CPF ou CNPJ: os números não conferem."


def test_entrega_com_cpf_vira_pedido_e_nao_mexe_no_cadastro(client, delivery_with_note):
    resp = _post(client, fiscal_tax_id="529.982.247-25")
    assert resp.status_code == 201, resp.content
    order = Order.objects.get(ref=resp.json()["order_ref"])
    assert order.data["fiscal"] == {"tax_id": CPF}
    delivery_with_note.refresh_from_db()
    assert delivery_with_note.document == ""


def test_projecao_pre_preenche_com_o_cpf_da_ultima_entrega_sem_gravar_no_cadastro(client, delivery_with_note):
    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]
    assert checkout["prefill_tax_id"] == ""
    assert checkout["prefill_tax_id_source"] == ""
    assert "delivery_requires_tax_id" not in checkout
    assert "offer_save_tax_id" not in checkout

    resp = _post(client, fiscal_tax_id=CPF)
    assert resp.status_code == 201, resp.content

    add = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 1}, content_type="application/json")
    assert add.status_code == 200, add.content
    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]
    assert checkout["prefill_tax_id"] == CPF
    assert checkout["prefill_tax_id_source"] == "last_delivery"
    delivery_with_note.refresh_from_db()
    assert delivery_with_note.document == ""


def test_projecao_prefere_o_documento_do_cadastro(client, delivery_with_note):
    delivery_with_note.document = "11144477735"
    delivery_with_note.save(update_fields=["document"])
    _post(client, fiscal_tax_id=CPF)
    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]
    assert checkout["prefill_tax_id"] == "11144477735"
    assert checkout["prefill_tax_id_source"] == "document"
