"""PDV: entrega abaixo do mínimo é recusa com frase — nunca 500.

Medido no alpha (28/09/2026): fechar uma entrega de R$ 12 com mínimo de R$ 25
dava 500 em ``pos/sale/close``. O ``DeliveryZoneRule`` levantava a recusa dentro
do ``CommitService`` e ninguém a traduzia; o PDV lia o 500 como "o pedido pode
ter nascido" e acendia a trava contra cobrança dupla ("Resultado da cobrança não
confirmado") por um pedido que nunca existiu.

Três camadas, provadas aqui: a review avisa com a frase do commit; o fechamento
recusa antes do commit; e qualquer recusa das regras do commit que escape vira
``PosIntentError`` (4xx), com a transação desfeita.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from shopman.orderman.exceptions import ValidationError as OrderValidationError
from shopman.orderman.models import Order

from shopman.shop.models import Shop
from shopman.shop.services import fiscal
from shopman.shop.services import pos as pos_service
from shopman.shop.services import sessions as session_service
from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_change_for_delivery import _close, _delivery_payload, counter  # noqa: F401

pytestmark = pytest.mark.django_db

MINIMUM = "Pedido mínimo para entrega: R$ 25,00."


@pytest.fixture
def minimum(counter, monkeypatch, settings):  # noqa: F811
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    # Sem nota prevista (dinheiro no balcão, só "a pedido"): o CPF da nota não entra no caminho.
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    shop = Shop.objects.get()
    shop.defaults = {**(shop.defaults or {}), "rules": {"delivery_minimum_q": 2500}}
    shop.save()
    return counter


def _payload(shift, request_id, **overrides):
    payload = {"payment_collection": "terminal", "tendered_q": 5000, **overrides}
    return _delivery_payload(shift, client_request_id=request_id, **payload)


def test_review_avisa_o_minimo_com_a_frase_do_commit(minimum):
    operator, shift = minimum
    review = pos_service.review_sale(channel_ref="pdv", payload=_payload(shift, "min-1"), operator_username=operator.username)
    warning = next(w for w in review.warnings if w["code"] == "below_delivery_minimum")
    assert warning["message"] == MINIMUM
    assert warning["field"] == "items"


def test_review_calada_quando_alcanca_o_minimo_ou_e_retirada(minimum):
    operator, shift = minimum
    above = _payload(shift, "min-2", items=[{"sku": "PAO", "name": "Pão", "qty": 3, "unit_price_q": 1200}])
    pickup = _payload(shift, "min-3", fulfillment_type="pickup")
    for payload in (above, pickup):
        review = pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)
        assert not [w for w in review.warnings if w["code"] == "below_delivery_minimum"]


def test_fechar_abaixo_do_minimo_recusa_antes_do_commit(minimum):
    operator, shift = minimum
    with pytest.raises(PosIntentError) as exc:
        _close(operator, _payload(shift, "min-4"))
    assert exc.value.code == "below_delivery_minimum"
    assert exc.value.message == MINIMUM
    assert exc.value.status == 422
    assert exc.value.focus == "cart"
    assert not Order.objects.exists()


def test_recusa_da_regra_no_commit_vira_recusa_do_pdv(minimum, monkeypatch):
    """A rede: sem o aviso antecipado, a regra do commit ainda recusa — e em 4xx."""
    operator, shift = minimum
    monkeypatch.setattr(pos_service, "_require_delivery_minimum", lambda payload: None)
    with pytest.raises(PosIntentError) as exc:
        _close(operator, _payload(shift, "min-5"))
    assert exc.value.code == "below_delivery_minimum"
    assert exc.value.message == MINIMUM
    assert exc.value.status == 422
    assert not Order.objects.exists()


@pytest.mark.parametrize(
    ("code", "context", "field", "focus", "status"),
    [
        ("delivery_zone_not_covered", {}, "delivery_address", "delivery_address", 422),
        ("delivery_zone_unverified", {}, "delivery_address", "delivery_address", 422),
        ("delivery_address_mismatch", {}, "delivery_address", "delivery_address", 422),
        ("delivery_tax_id_required", {"field": "fiscal_tax_id"}, "fiscal_tax_id", "receipt", 422),
        ("price_missing", {}, "items", "cart", 422),
        ("stale_checks", {}, "", "cart", 409),
    ],
)
def test_toda_regra_do_commit_chega_ao_campo_que_conserta(code, context, field, focus, status):
    refusal = pos_service._commit_refusal(OrderValidationError(code=code, message="Frase da regra.", context=context))
    assert (refusal.code, refusal.message, refusal.field, refusal.focus, refusal.status) == (
        code, "Frase da regra.", field, focus, status,
    )


def test_a_porta_http_devolve_422_com_a_frase(minimum, client, monkeypatch):
    """Pela porta do balcão: 422 com ``detail`` + ``error.code`` — o PDV libera a trava."""
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from shopman.cashman.models import Shift

    from shopman.backstage.tests.pos_test_runtime import bind_station
    from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

    operator, shift = minimum
    operator.is_staff = True
    operator.save()
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    bind_station(client, shift.terminal.ref)

    def refuse(**kwargs):
        raise OrderValidationError(code="below_delivery_minimum", message=MINIMUM)

    monkeypatch.setattr(pos_service, "_require_delivery_minimum", lambda payload: None)
    monkeypatch.setattr(session_service, "commit_session", refuse)
    response = client.post(
        "/api/v1/backstage/pos/sale/close/",
        data={**_payload(shift, "min-6"), "intent_version": POS_SALE_INTENT_VERSION},
        content_type="application/json",
    )
    assert response.status_code == 422, response.content
    body = response.json()
    assert body["detail"] == MINIMUM
    assert body["error"]["code"] == "below_delivery_minimum"
    assert not Order.objects.exists()
