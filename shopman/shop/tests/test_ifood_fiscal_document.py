"""Only the fiscal document explicitly provided on this iFood order is requested."""

from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive

from shopman.shop.models import Channel
from shopman.shop.services import fiscal, ifood_ingest, ifood_orders

pytestmark = pytest.mark.django_db
RESOLVERS = "shopman.shop.fiscal_resolvers.on_request_or_tax_id,shopman.shop.fiscal_resolvers.on_requested_receipt"


def ingest_raw(customer):
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    payload = ifood_orders.map_order({
        "id": "fiscal-ifood-order", "orderType": "TAKEOUT", "merchant": {"id": "merchant"},
        "customer": {"name": "Cliente de teste", **customer},
        "items": [{"id": "item-1", "externalCode": "FISCAL-TEST", "quantity": 1, "unitPrice": 10, "totalPrice": 10}],
    })
    with patch.object(ifood_ingest.order_changed, "send"):
        return ifood_ingest.ingest(payload)


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=RESOLVERS)
@pytest.mark.parametrize(("document", "document_type"), [
    ("52998224725", "CPF"),
    ("529.982.247-25", ""),
    ("11.222.333/0001-81", "CNPJ"),
    ("11222333000181", ""),
])
def test_provided_national_document_reaches_fiscal_request_snapshot_and_queued_payload(document, document_type):
    order = ingest_raw({"documentNumber": document, "documentType": document_type})
    assert order.data["fiscal"] == {"tax_id": document}
    assert order.snapshot["data"]["fiscal"] == {"tax_id": document}
    assert fiscal.emission_resolver(order) is True
    # Queue only: no worker or fiscal provider is called in this test.
    with patch.object(fiscal.fiscal_pool, "get_backend", return_value=object()):
        fiscal.emit(order)
    directive = Directive.objects.get(topic="fiscal.emit_nfce", payload__order_ref=order.ref)
    assert directive.payload["customer"]["tax_id"] == document


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=RESOLVERS)
@pytest.mark.parametrize("customer", [{}, {"documentNumber": None}, {"documentNumber": ""}, {"documentNumber": "   "}])
def test_absent_order_document_does_not_request_or_queue_fiscal_document(customer):
    order = ingest_raw(customer)
    assert "fiscal" not in order.data
    assert "fiscal" not in order.snapshot["data"]
    # Even if customer resolution later enriches CRM identity, it is not a request.
    order.data["customer"]["tax_id"] = "52998224725"
    assert fiscal.emission_resolver(order) is False
    with patch.object(fiscal.fiscal_pool, "get_backend", return_value=object()):
        fiscal.emit(order)
    assert not Directive.objects.filter(topic="fiscal.emit_nfce", payload__order_ref=order.ref).exists()
    assert "tax_id" not in fiscal._fiscal_customer(order.data)


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=RESOLVERS)
def test_explicit_foreign_document_is_preserved_without_misclassifying_as_national_tax_id():
    order = ingest_raw({"documentNumber": "AB123456", "documentType": "idEstrangeiro"})
    assert order.data["customer"]["document"] == "AB123456"
    assert order.data["customer"]["document_type"] == "idEstrangeiro"
    assert "fiscal" not in order.data
    assert fiscal.emission_resolver(order) is False


def test_invalid_national_document_is_preserved_for_existing_fiscal_validation():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFePayloadError, _customer_fields

    order = ingest_raw({"documentNumber": "11111111111", "documentType": "CPF"})
    assert order.data["fiscal"]["tax_id"] == "11111111111"
    with pytest.raises(FocusNFePayloadError):
        _customer_fields(fiscal._fiscal_customer(order.data))


def test_canonical_benefits_are_preserved_in_order_and_sealed_snapshot():
    Channel.objects.create(ref="ifood", name="iFood")
    benefits = [{"target": "CART", "value_q": 300, "sponsorships": [{"sponsor": "IFOOD", "value_q": 200, "raw": {"value": 2}}, {"sponsor": "MERCHANT", "value_q": 100, "raw": {"value": 1}}], "raw": {"value": 3}}]
    payload = {"order_code": "benefit-order", "items": [{"sku": "TEST", "qty": 1, "unit_price_q": 1000}], "benefits": benefits}
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    order.refresh_from_db()
    assert order.data["ifood"]["benefits"] == benefits
    assert order.snapshot["data"]["ifood"]["benefits"] == benefits
