"""PDV: entrega com nota não fecha sem "CPF na nota" e endereço completo.

A trava é a mesma do commit (``DeliveryFiscalIdentityRule``), perguntada antes
para a recusa chegar ao campo que o operador conserta. A review publica a
exigência (``delivery_tax_id_required``) para a tela travar o botão ao vivo, já
que digitar o CPF não refaz a review.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from shopman.orderman.models import Order

from shopman.shop.services import fiscal
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_change_for_delivery import _close, _delivery_payload, counter  # noqa: F401

pytestmark = pytest.mark.django_db

CPF = "52998224725"
ADDRESS = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "route": "Rua Pará",
    "street_number": "86",
    "neighborhood": "Centro",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86010000",
}


@pytest.fixture
def emits(monkeypatch, settings):
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = (
        "shopman.shop.fiscal_resolvers.on_request_or_tax_id,"
        "shopman.shop.fiscal_resolvers.eletronic_payment,"
        "shopman.shop.fiscal_resolvers.deferred_settlement"
    )


def _review(operator, payload):
    return pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)


def _receipt_only(request_id):
    return [{
        "field": "tax_id", "value": CPF, "customer_ref": "", "owner_ref": "",
        "choice": "receipt_only", "client_request_id": request_id,
    }]


def test_entrega_a_receber_na_porta_sem_cpf_nao_fecha(counter, emits):  # noqa: F811
    operator, shift = counter
    with pytest.raises(PosIntentError) as exc:
        _close(operator, _delivery_payload(shift, client_request_id="cpf-1", delivery_address_structured=ADDRESS))
    assert exc.value.code == "delivery_tax_id_required"
    assert exc.value.field == "fiscal_tax_id"
    assert exc.value.focus == "receipt"
    assert "retirada continua" in exc.value.recovery
    assert not Order.objects.exists()


def test_review_publica_a_exigencia_sem_travar_a_conta(counter, emits):  # noqa: F811
    operator, shift = counter
    review = _review(operator, _delivery_payload(shift, client_request_id="cpf-2", delivery_address_structured=ADDRESS))
    assert review.delivery_tax_id_required is True
    assert review.total_q > 0

    pickup = _review(operator, _delivery_payload(shift, client_request_id="cpf-3", fulfillment_type="pickup"))
    assert pickup.delivery_tax_id_required is False


def test_review_avisa_endereco_incompleto_para_a_nota(counter, emits):  # noqa: F811
    operator, shift = counter
    review = _review(operator, _delivery_payload(
        shift, client_request_id="cpf-4", delivery_address_structured={**ADDRESS, "postal_code": ""},
    ))
    warning = next(w for w in review.warnings if w["code"] == "delivery_address_incomplete")
    assert warning["field"] == "delivery_address"
    assert warning["message"].endswith("falta no endereço: o CEP.")


def test_endereco_incompleto_nao_fecha_mesmo_com_cpf(counter, emits):  # noqa: F811
    operator, shift = counter
    with pytest.raises(PosIntentError) as exc:
        _close(operator, _delivery_payload(
            shift, client_request_id="cpf-5", fiscal_tax_id=CPF, receipt_identity_choices=_receipt_only("cpf-5"),
            delivery_address_structured={**ADDRESS, "street_number": ""},
        ))
    assert exc.value.code == "delivery_address_incomplete"
    assert exc.value.field == "delivery_address"
    assert exc.value.focus == "delivery_address"


def test_entrega_com_cpf_e_endereco_completo_fecha(counter, emits):  # noqa: F811
    operator, shift = counter
    result = _close(operator, _delivery_payload(
        shift, client_request_id="cpf-6", fiscal_tax_id=CPF, receipt_identity_choices=_receipt_only("cpf-6"),
        delivery_address_structured=ADDRESS,
    ))
    order = Order.objects.get(ref=result.order_ref)
    assert order.data["fiscal"]["tax_id"] == CPF


def test_entrega_sem_nota_prevista_fecha_sem_cpf(counter, monkeypatch, settings):  # noqa: F811
    """Regra só "a pedido" e dinheiro pago no balcão: não há nota, não há exigência."""
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    operator, shift = counter
    result = _close(operator, _delivery_payload(
        shift, client_request_id="cpf-7", payment_collection="terminal", tendered_q=1200,
    ))
    assert Order.objects.filter(ref=result.order_ref).exists()
