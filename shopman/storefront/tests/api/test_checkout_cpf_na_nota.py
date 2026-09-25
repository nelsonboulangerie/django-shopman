"""Loja: "CPF na nota" vale na retirada também, e guardar no cadastro é PERGUNTA.

Decisões do dono (25/09/2026), com a matriz do PDV adaptada ao autoatendimento:

- retirada: o CPF/CNPJ na nota é opcional (o "CPF na nota?" do balcão);
- cadastro SEM documento → "guardar no seu cadastro?", e só grava com o sim;
- IGUAL ao do cadastro → só usa;
- DIFERENTE do cadastro → vale só para esta nota, cadastro intacto;
- documento de OUTRA conta → vale para a nota, nunca grava, e a loja não diz
  que ele é de outra conta (a resposta é a mesma de qualquer "não gravou").
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.services import fiscal
from shopman.storefront.services.pickup_slots import get_slots
from shopman.storefront.tests._checkout_auth import authenticate_checkout
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

CPF = "52998224725"
OUTRO_CPF = "11144477735"


@pytest.fixture
def pickup(client, monkeypatch, settings):
    from django.core.cache import cache

    cache.clear()  # o limite de 3 checkouts/min é por IP e vaza entre testes
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = (
        "shopman.shop.fiscal_resolvers.on_request_or_tax_id,"
        "shopman.shop.fiscal_resolvers.eletronic_payment"
    )
    _seed_surface()
    customer = authenticate_checkout(client)
    add = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 2}, content_type="application/json")
    assert add.status_code == 200, add.content
    yield customer
    cache.clear()


def _post(client, **over):
    payload = {
        "name": "Ana",
        "phone": "+5543999990001",
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": get_slots()[-1]["ref"],
        "payment_method": "cash",
    }
    payload.update(over)
    return client.post("/api/v1/checkout/", data=with_baseline(client, payload), content_type="application/json")


def _order(resp) -> Order:
    return Order.objects.get(ref=resp.json()["order_ref"])


# ── Retirada: CPF na nota é opcional ──────────────────────────────────────


def test_retirada_sem_cpf_continua_sem_cpf(client, pickup):
    resp = _post(client)
    assert resp.status_code == 201, resp.content
    assert _order(resp).data["fiscal"] == {}
    assert "tax_id_saved" not in resp.json()


def test_retirada_com_cpf_leva_o_cpf_na_nota_e_nao_mexe_no_cadastro(client, pickup):
    resp = _post(client, fiscal_tax_id="529.982.247-25")
    assert resp.status_code == 201, resp.content
    assert _order(resp).data["fiscal"] == {"tax_id": CPF}
    assert fiscal.emission_resolver(_order(resp)) is True  # CPF na nota É pedir a nota
    pickup.refresh_from_db()
    assert pickup.document == ""


def test_retirada_com_cpf_errado_e_recusada_no_campo(client, pickup):
    resp = _post(client, fiscal_tax_id="529.982.247-00")
    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "fiscal_tax_id"
    assert not Order.objects.exists()


# ── A matriz de guardar no cadastro ───────────────────────────────────────


def test_cadastro_sem_documento_guarda_so_com_o_sim(client, pickup):
    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]
    assert checkout["offer_save_tax_id"] is True

    resp = _post(client, fiscal_tax_id=CPF, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    assert resp.json()["tax_id_saved"] is True
    pickup.refresh_from_db()
    assert pickup.document == CPF

    add = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 1}, content_type="application/json")
    assert add.status_code == 200, add.content
    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]
    assert (checkout["prefill_tax_id"], checkout["prefill_tax_id_source"]) == (CPF, "document")
    assert checkout["offer_save_tax_id"] is False


def test_igual_ao_cadastro_so_usa(client, pickup):
    pickup.document = CPF
    pickup.save(update_fields=["document"])
    resp = _post(client, fiscal_tax_id=CPF, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    assert resp.json()["tax_id_saved"] is True
    pickup.refresh_from_db()
    assert pickup.document == CPF


def test_diferente_do_cadastro_vale_so_para_esta_nota(client, pickup):
    pickup.document = CPF
    pickup.save(update_fields=["document"])
    resp = _post(client, fiscal_tax_id=OUTRO_CPF, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    assert resp.json()["tax_id_saved"] is False
    assert _order(resp).data["fiscal"] == {"tax_id": OUTRO_CPF}
    pickup.refresh_from_db()
    assert pickup.document == CPF


def test_cpf_de_outra_conta_nao_vaza_nem_grava(client, pickup):
    joao = Customer.objects.create(ref="JOAO", first_name="João", last_name="Dono", phone="+5543999990002", document=OUTRO_CPF)

    resp = _post(client, fiscal_tax_id=OUTRO_CPF, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    body = resp.json()
    # A resposta é a mesma de qualquer "não gravou": nada que aponte o dono.
    assert body["tax_id_saved"] is False
    assert set(body) == {"order_ref", "status", "next_url", "convenience_pending", "tax_id_saved"}
    raw = resp.content.decode()
    for leak in ("JOAO", "João", "Dono", "+5543999990002", "outra conta", "outro cadastro"):
        assert leak not in raw
    # A nota sai com o documento informado; nenhum cadastro muda.
    assert _order(resp).data["fiscal"] == {"tax_id": OUTRO_CPF}
    pickup.refresh_from_db()
    joao.refresh_from_db()
    assert pickup.document == ""
    assert joao.document == OUTRO_CPF
    # E a próxima visita não pré-preenche o documento alheio a partir do cadastro.
    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]
    assert checkout["prefill_tax_id_source"] != "document"


def test_sem_o_sim_nao_grava_nem_responde_sobre_cadastro(client, pickup):
    resp = _post(client, fiscal_tax_id=CPF)
    assert resp.status_code == 201, resp.content
    assert "tax_id_saved" not in resp.json()
    pickup.refresh_from_db()
    assert pickup.document == ""


def test_pedir_para_guardar_sem_cpf_nao_faz_nada(client, pickup):
    resp = _post(client, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    assert "tax_id_saved" not in resp.json()
    pickup.refresh_from_db()
    assert pickup.document == ""
