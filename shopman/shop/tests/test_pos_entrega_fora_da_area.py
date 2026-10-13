"""PDV, entrega fora da área: uma regra só, dita antes (P1-6 dos cenários de pedido).

Medido em 13/10/2026: a revisão dizia "não bloqueia, confira o combinado", o
fechamento recusava com "Não entregamos neste endereço ainda." e a taxa digitada
à mão (o combinado que a própria revisão sugeria) era recusada igual. O operador
descobria no Validar, com o cliente no telefone, que não havia saída.

A regra agora: fora da área, a entrega só fecha com a taxa combinada à mão; a
revisão diz isso com a frase do fechamento, e o pedido guarda quem combinou e
quando. Retirada segue livre.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from shopman.orderman.models import Order

from shopman.shop.models import DeliveryZone, Shop
from shopman.shop.services import fiscal
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_change_for_delivery import _close, _delivery_payload, counter  # noqa: F401

pytestmark = pytest.mark.django_db

ENDERECO = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "postal_code": "86010-000",
    "neighborhood": "Centro",
}
FORA = "Endereço fora da área de entrega."


@pytest.fixture
def fora(counter, monkeypatch, settings):  # noqa: F811
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    DeliveryZone.objects.create(
        shop=Shop.objects.get(), name="Longe", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_EXCLUDE, fee_q=0, is_active=True,
    )
    return counter


def _payload(shift, request_id, **overrides):
    return _delivery_payload(
        shift,
        client_request_id=request_id,
        delivery_address=ENDERECO["formatted_address"],
        delivery_address_structured=dict(ENDERECO),
        payment_collection="terminal",
        tendered_q=5000,
        **overrides,
    )


def _review(operator, payload):
    return pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)


def test_a_revisao_diz_a_regra_do_fechamento_com_a_saida(fora):
    operator, shift = fora
    review = _review(operator, _payload(shift, "fa-1"))

    warning = next(w for w in review.warnings if w["code"] == "delivery_out_of_area")
    assert warning["message"] == FORA
    assert warning["field"] == "delivery_address"


def test_fechar_sem_taxa_combinada_recusa_com_a_mesma_frase_antes_do_commit(fora):
    operator, shift = fora
    with pytest.raises(PosIntentError) as exc:
        _close(operator, _payload(shift, "fa-2"))

    assert exc.value.code == "delivery_out_of_area"
    assert exc.value.message == FORA
    assert exc.value.field == "delivery_address"
    assert exc.value.status == 422
    assert "retirada" in exc.value.recovery
    assert not Order.objects.exists()


@pytest.mark.parametrize("fee_q", [1500, 0])
def test_taxa_combinada_fecha_e_o_pedido_guarda_quem_e_quando(fora, fee_q):
    operator, shift = fora
    payload = _payload(shift, f"fa-3-{fee_q}", delivery_fee_override_q=fee_q)

    review = _review(operator, payload)
    assert not [w for w in review.warnings if w["code"] == "delivery_out_of_area"]
    agreed_warning = next(w for w in review.warnings if w["code"] == "delivery_out_of_area_agreed")
    assert "marina" in agreed_warning["message"]

    result = _close(operator, _payload(shift, f"fa-4-{fee_q}", delivery_fee_override_q=fee_q))

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200 + fee_q
    fee_lines = [item for item in order.items.all() if item.sku == "__DELIVERY_FEE__"]
    assert [line.unit_price_q for line in fee_lines] == ([fee_q] if fee_q else [])
    agreed = order.data["pos"]["delivery_fee_agreed"]
    assert agreed["by"] == "marina"
    assert agreed["fee_q"] == fee_q
    assert agreed["out_of_area"] is True
    assert agreed["at"]
    assert not order.data.get("delivery_zone_error")


def test_retirada_do_mesmo_cliente_fecha_sem_taxa(fora):
    operator, shift = fora
    result = _close(operator, _payload(shift, "fa-5", fulfillment_type="pickup"))
    assert Order.objects.get(ref=result.order_ref).total_q == 1200


def test_override_sem_assinatura_na_sessao_nao_desliga_a_area():
    """A chave solta (sem `pos.delivery_fee_agreed`) não vale: a área continua mandando."""
    from shopman.shop.modifiers import operator_agreed_delivery_fee_q

    assert operator_agreed_delivery_fee_q({"delivery_fee_override_q": 0}) is None
    assert operator_agreed_delivery_fee_q({
        "delivery_fee_override_q": 900, "pos": {"delivery_fee_agreed": {"by": "marina"}},
    }) == 900


def test_taxa_combinada_dentro_da_area_nao_traz_o_aviso_de_fora(counter):  # noqa: F811
    operator, shift = counter
    review = _review(operator, _payload(shift, "fa-6", delivery_fee_override_q=500))
    codes = {w["code"] for w in review.warnings}
    assert "delivery_out_of_area" not in codes
    assert "delivery_out_of_area_agreed" not in codes
