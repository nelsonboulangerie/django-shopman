"""Loja: "CPF na nota" vale na retirada também, e guardar no cadastro é PERGUNTA.

Decisões do dono (25/09/2026), com a matriz do PDV adaptada ao autoatendimento:

- retirada: o CPF/CNPJ na nota é opcional (o "CPF na nota?" do balcão);
- cadastro SEM documento → "guardar no seu cadastro?", e só grava com o sim;
- IGUAL ao do cadastro → só usa;
- DIFERENTE do cadastro → vale só para esta nota, cadastro intacto;
- documento de OUTRA conta → vale para a nota, nunca vira identidade, e a loja
  não deixa inferir que ele é de outra conta: a resposta do checkout é a MESMA,
  byte a byte, tenha gravado ou não, e a próxima visita também.
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
    pickup.refresh_from_db()
    assert pickup.document == CPF


def test_diferente_do_cadastro_vale_so_para_esta_nota(client, pickup):
    pickup.document = CPF
    pickup.save(update_fields=["document"])
    resp = _post(client, fiscal_tax_id=OUTRO_CPF, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    assert _order(resp).data["fiscal"] == {"tax_id": OUTRO_CPF}
    pickup.refresh_from_db()
    assert pickup.document == CPF


def _fingerprint(client, resp, tax_id: str) -> dict:
    """O que a pessoa consegue observar: a resposta do checkout e a próxima visita.

    O ref do pedido e o próprio documento são trocados por marcadores; todo o
    resto tem de ser idêntico entre "gravou" e "não gravou por ser de outra conta".
    """
    ref = resp.json()["order_ref"]
    body = resp.content.decode().replace(ref, "<ref>")
    add = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 1}, content_type="application/json")
    assert add.status_code == 200, add.content
    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]
    return {
        "status": resp.status_code,
        "headers": sorted(k for k in resp.headers if k.lower() not in {"date", "content-length"}),
        "body": body,
        "next_prefill": checkout["prefill_tax_id"].replace(tax_id, "<doc>"),
        "next_source": checkout["prefill_tax_id_source"],
        "next_offer": checkout["offer_save_tax_id"],
    }


def test_guardar_cpf_de_outra_conta_e_indistinguivel_de_guardar_cpf_livre(client, pickup):
    """Decisão do dono (25/09/2026): nada vaza que um CPF pertence a outra conta."""
    # Caso 1: o CPF está livre, e entra no cadastro.
    livre = _post(client, fiscal_tax_id=CPF, save_fiscal_tax_id=True)
    pickup.refresh_from_db()
    assert pickup.document == CPF
    saved = _fingerprint(client, livre, CPF)

    # Caso 2: a mesma pessoa, cadastro de novo sem documento, pede para guardar
    # um CPF que é do João.
    pickup.document = ""
    pickup.save(update_fields=["document"])
    joao = Customer.objects.create(
        ref="JOAO", first_name="João", last_name="Dono", phone="+5543999990002", document=OUTRO_CPF
    )
    alheio = _post(client, fiscal_tax_id=OUTRO_CPF, save_fiscal_tax_id=True)
    owned_by_other = _fingerprint(client, alheio, OUTRO_CPF)

    assert owned_by_other == saved
    assert set(alheio.json()) == {"order_ref", "status", "next_url", "convenience_pending"}
    for leak in ("JOAO", "João", "Dono", "+5543999990002", "outra conta", "outro cadastro", "cadastro"):
        assert leak not in alheio.content.decode()
    # A nota sai com o documento informado; a identidade de ninguém muda.
    assert _order(alheio).data["fiscal"] == {"tax_id": OUTRO_CPF}
    pickup.refresh_from_db()
    joao.refresh_from_db()
    assert pickup.document == ""
    assert joao.document == OUTRO_CPF
    assert pickup.metadata["note_tax_id"] == OUTRO_CPF


def test_conflito_fica_no_log_do_servidor_sem_dado_pessoal(client, pickup, caplog):
    Customer.objects.create(ref="JOAO", first_name="João", phone="+5543999990002", document=OUTRO_CPF)
    with caplog.at_level("INFO", logger="shopman.storefront.api.views"):
        resp = _post(client, fiscal_tax_id=OUTRO_CPF, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    conflict = [r for r in caplog.records if "owned_by_other" in r.getMessage()]
    assert len(conflict) == 1 and conflict[0].levelname == "WARNING"
    message = conflict[0].getMessage()
    for pii in (OUTRO_CPF, "111.444.777-35", "JOAO", "João", "+5543999990002"):
        assert pii not in message


def test_sem_o_sim_nao_grava(client, pickup):
    resp = _post(client, fiscal_tax_id=CPF)
    assert resp.status_code == 201, resp.content
    pickup.refresh_from_db()
    assert pickup.document == ""


def test_pedir_para_guardar_sem_cpf_nao_faz_nada(client, pickup):
    resp = _post(client, save_fiscal_tax_id=True)
    assert resp.status_code == 201, resp.content
    pickup.refresh_from_db()
    assert pickup.document == ""
