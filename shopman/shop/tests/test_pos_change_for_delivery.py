"""O "Troco para quanto?" da entrega nasce no PDV e chega ao entregador.

Achado do QA físico: ao escolher "receber na entrega" no checkout do PDV não
havia onde dizer com quanto o cliente paga na porta. A chave canônica já
existia (``payment.change_for_q``, escrita pelo checkout da loja) e o caminho
até o entregador também (``operator_orders.change_out_suggested_q`` → linha
``courier_out`` no livro do caixa, WP-9 do CASHMAN-PLAN). O que faltava era o
PDV escrevê-la — estes testes provam o payload do balcão de ponta a ponta.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import parse_pos_sale_intent

pytestmark = pytest.mark.django_db


@pytest.fixture
def counter():
    from shopman.offerman.models import Product

    Shop.objects.create(name="Test Shop", brand_name="Test")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )
    Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)
    operator = get_user_model().objects.create_user(username="marina", password="x")
    shift = cash.open_shift(operator=operator, float_q=10000)
    return operator, shift


def _delivery_payload(shift, *, client_request_id: str, **overrides) -> dict:
    payload = {
        "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
        "customer_name": "Cliente",
        "fulfillment_type": "delivery",
        "delivery_address": "Rua Pará, 86",
        "payment_method": "cash",
        "payment_collection": "on_delivery",
        "client_request_id": client_request_id,
        "cash_shift_id": shift.pk,
    }
    payload.update(overrides)
    return payload


def _close(operator, payload):
    return pos_service.close_sale(
        channel_ref="pdv",
        payload=payload,
        actor=f"pos:{operator.username}",
        operator_username=operator.username,
    )


def test_troco_para_da_entrega_chega_ao_pedido_e_ao_despacho(counter):
    """R$ 12 de pedido, cliente paga com R$ 50: o pedido carrega change_for_q e
    o despacho sugere os R$ 38 que o entregador leva — mesmo fio do storefront."""
    operator, shift = counter
    result = _close(operator, _delivery_payload(shift, client_request_id="cf-1", change_for_q=5000))

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["payment"]["change_for_q"] == 5000
    assert operator_orders.change_out_suggested_q(order) == 5000 - order.total_q


def test_sem_troco_para_o_pedido_nao_carrega_a_chave(counter):
    operator, shift = counter
    result = _close(operator, _delivery_payload(shift, client_request_id="cf-2"))

    order = Order.objects.get(ref=result.order_ref)
    assert "change_for_q" not in order.data["payment"]
    assert operator_orders.change_out_suggested_q(order) == 0


def test_troco_para_fora_do_cod_e_descartado_pelo_intent(counter):
    """No recebimento no terminal o troco é tendered_q/change_q; change_for_q não
    tem sentido e o intent o descarta antes de qualquer escrita."""
    intent = parse_pos_sale_intent({
        "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
        "payment_method": "cash",
        "payment_collection": "terminal",
        "change_for_q": 5000,
    })
    assert intent.payload["change_for_q"] is None

    operator, shift = counter
    result = _close(
        operator,
        _delivery_payload(
            shift,
            client_request_id="cf-3",
            payment_collection="terminal",
            change_for_q=5000,
            tendered_q=5000,
        ),
    )
    order = Order.objects.get(ref=result.order_ref)
    assert "change_for_q" not in order.data["payment"]


def test_review_avisa_troco_para_menor_que_o_total_sem_bloquear(counter):
    operator, shift = counter
    review = pos_service.review_sale(
        channel_ref="pdv",
        payload=_delivery_payload(shift, client_request_id="cf-4", change_for_q=500),
        operator_username=operator.username,
    )
    codes = [w["code"] for w in review.warnings]
    assert "change_for_below_total" in codes

    ok = pos_service.review_sale(
        channel_ref="pdv",
        payload=_delivery_payload(shift, client_request_id="cf-5", change_for_q=5000),
        operator_username=operator.username,
    )
    assert "change_for_below_total" not in [w["code"] for w in ok.warnings]


def test_cpf_com_taxa_de_entrega_chega_ao_adapter_fiscal(counter, monkeypatch):
    from unittest.mock import Mock

    from shopman.fiscalman.contracts import FiscalDocumentResult
    from shopman.orderman.models import Directive

    from shopman.shop.handlers.fiscal import NFCeEmitHandler
    from shopman.shop.models import DeliveryZone
    from shopman.shop.services import fiscal

    operator, shift = counter
    shop = Shop.objects.get()
    DeliveryZone.objects.create(shop=shop, name="Centro", zone_type="neighborhood", match_value="Centro", mode="override", fee_q=600)
    backend = Mock()
    backend.emit.return_value = FiscalDocumentResult(success=True, access_key="1" * 44, status="authorized")
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: backend)
    monkeypatch.setattr(fiscal, "emission_resolver", lambda order: True)
    address = {"formatted_address": "Rua Pará, 86", "route": "Rua Pará", "street_number": "86", "neighborhood": "Centro", "postal_code": "86010000", "city": "Londrina", "state": "PR"}
    result = _close(operator, _delivery_payload(shift, client_request_id="cpf-delivery", fiscal_tax_id="52998224725", receipt_identity_choices=[{
        "field": "tax_id", "value": "52998224725", "customer_ref": "", "owner_ref": "",
        "choice": "receipt_only", "client_request_id": "cpf-delivery",
    }], delivery_address_structured=address, payment_collection="terminal", tendered_q=1800))
    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1800
    message = Directive.objects.get(topic="fiscal.emit_nfce", payload__order_ref=order.ref)
    NFCeEmitHandler(backend).handle(message=message, ctx={})
    sent = backend.emit.call_args.kwargs
    assert sent["customer"]["tax_id"] == "52998224725"
    assert sent["delivery"]["address"]["street_number"] == "86"
    assert sent["delivery"]["address"]["postal_code"] == "86010000"
