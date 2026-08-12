"""O envio do pedido não pode apagar a identidade do cliente na sessão.

Regressão do smoke de alpha (2026-08-11, staging, cliente `Maria Santos`): o
desconto de aniversário aparecia no checkout (total R$ 25,30) e **sumia** no
"Enviar pedido" (R$ 26,60), a guarda de integridade recusava com
``total_changed`` — e, pior, todas as leituras seguintes da projeção também
vinham sem o desconto, porque a sessão já tinha sido corrompida.

Causa: ``CheckoutView`` montava ``checkout_data["customer"]`` do zero com
nome+telefone, e ``_build_ops_from_data`` transforma isso num ``set_data`` em
``customer``, que **substitui o bloco inteiro**. O ``ref`` ia junto; sem ``ref``,
o ``_resolve_customer_ctx`` do discount modifier retorna cedo e nunca avalia
``is_birthday``.

⚠️ O fix preserva **só o ``ref``**. A primeira versão preservava ``price_tier``
junto e ligou o desconto de funcionário (20%) na loja pública — quem pegou foi
``storefront/tests/e2e/test_persona_3_employee.py``. Faixa de preço é mecanismo
do PDV; a loja não propaga.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.orderman.models import Session

from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db


def _add_item(client) -> None:
    resp = client.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data={"qty": 1},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content


def _link_identity(client, **identity) -> Session:
    """Grava a identidade na sessão do carrinho, como o login/cupom fazem."""
    session_key = client.session["cart_session_key"]
    session = Session.objects.get(session_key=session_key)
    data = dict(session.data or {})
    data["customer"] = {**(data.get("customer") or {}), **identity}
    session.data = data
    session.save(update_fields=["data"])
    return session


def _seed_delivery_zone() -> None:
    """Entrega (em vez de retirada) evita depender da janela de horário do dia."""
    from shopman.shop.models import DeliveryZone, Shop

    DeliveryZone.objects.create(
        shop=Shop.objects.first(),
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=600,
    )


def _checkout(client):
    return client.post(
        "/api/v1/checkout/",
        data={
            "name": "Maria Santos",
            "phone": "+5543991111111",
            "fulfillment_type": "delivery",
            "delivery_address": "Rua das Flores, 1",
            "delivery_address_structured": {
                "formatted_address": "Rua das Flores, 1 - Centro, Londrina - PR",
                "route": "Rua das Flores",
                "street_number": "1",
                "city": "Londrina",
                "state_code": "PR",
                "postal_code": "86050-270",
                "neighborhood": "Centro",
            },
            "delivery_date": timezone.localdate().isoformat(),
        },
        content_type="application/json",
    )


def test_checkout_preserves_customer_ref(client):
    """O commit mescla nome/telefone SEM derrubar o ``ref``."""
    _seed_surface()
    _seed_delivery_zone()
    _add_item(client)
    session = _link_identity(client, ref="CLI-001", price_tier="atacado")

    resp = _checkout(client)
    assert resp.status_code in (200, 201), resp.content

    session.refresh_from_db()
    customer = (session.data or {}).get("customer") or {}
    # A identidade sobrevive — é ela que decide preço e elegibilidade de promoção.
    assert customer.get("ref") == "CLI-001"
    # ⚠️ `price_tier` NÃO é preservado de propósito: propagar faixa de preço pela
    # loja pública liga o desconto de funcionário no site. Ver
    # `storefront/tests/e2e/test_persona_3_employee.py`.
    assert "price_tier" not in customer
    # E o que o formulário mandou continua chegando.
    assert customer.get("name") == "Maria Santos"
    assert customer.get("phone") == "+5543991111111"


def test_checkout_without_prior_identity_still_works(client):
    """Visitante sem identidade na sessão: o envio segue normal, sem chaves vazias."""
    _seed_surface()
    _seed_delivery_zone()
    _add_item(client)

    resp = _checkout(client)
    assert resp.status_code in (200, 201), resp.content

    session_key = client.session.get("cart_session_key")
    if session_key is None:  # a sessão do carrinho é encerrada no commit
        return
    session = Session.objects.filter(session_key=session_key).first()
    if session is None:
        return
    customer = (session.data or {}).get("customer") or {}
    assert customer.get("name") == "Maria Santos"
    # Nada de `ref`/`price_tier` inventados quando não havia identidade.
    assert "ref" not in customer
    assert "price_tier" not in customer
