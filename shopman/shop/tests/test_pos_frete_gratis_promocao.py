"""PDV, frete grátis por promoção: o mesmo motor da loja (P2-21 dos cenários de pedido).

Medido em 14/10/2026: a promoção ``free_delivery`` zerava a taxa na loja online e
o PDV cobrava a taxa inteira na mesma entrega. A taxa do balcão vira uma linha
MANUAL no pedido, que o ``DeliveryFeeModifier`` nunca reavalia, e a renúncia do
PDV só lia o limiar permanente da loja.

A regra agora: a revisão e o fechamento do PDV pedem a renúncia à mesma função
que o modifier usa (``modifiers.resolve_delivery_fee_waiver``), com o canal da
venda (escopo da promoção) e o cliente identificado (grupo de clientes). A
revisão diz por qual regra o frete saiu grátis.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Channel, DeliveryZone, Promotion, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.tests.test_pos_change_for_delivery import _close, _delivery_payload, counter  # noqa: F401

pytestmark = pytest.mark.django_db

FEE_Q = 800
ENDERECO = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "postal_code": "86010-000",
    "neighborhood": "Centro",
}


@pytest.fixture
def balcao(counter):  # noqa: F811
    DeliveryZone.objects.create(
        shop=Shop.objects.get(), name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=FEE_Q, is_active=True,
    )
    return counter


def _promo(ref: str = "frete-verao", *, name: str = "Frete de verão", cap_q: int = 0, channels=(), **kwargs):
    now = timezone.now()
    promo = Promotion.objects.create(
        ref=ref, name=name, type=Promotion.FREE_DELIVERY, value=cap_q,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1), **kwargs,
    )
    if channels:
        promo.channels.set(Channel.objects.filter(ref__in=channels))
    return promo


def _payload(shift, request_id, **overrides):
    return _delivery_payload(
        shift,
        client_request_id=request_id,
        delivery_address=ENDERECO["formatted_address"],
        delivery_address_structured=dict(ENDERECO),
        **overrides,
    )


def _review(operator, payload):
    return pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)


def _fee_lines(order):
    return [item for item in order.items.all() if item.sku == "__DELIVERY_FEE__"]


def test_sem_promocao_o_balcao_cobra_a_taxa(balcao):
    operator, shift = balcao
    review = _review(operator, _payload(shift, "fg-0"))
    assert review.delivery_fee_q == FEE_Q
    assert review.delivery_fee_waiver is None


def test_promocao_da_loja_zera_o_frete_no_balcao_e_diz_qual(balcao):
    operator, shift = balcao
    _promo()

    review = _review(operator, _payload(shift, "fg-1"))

    assert review.delivery_fee_q == 0
    assert review.total_q == 1200
    assert review.delivery_fee_source == "zone"
    assert review.delivery_fee_waiver == {
        "reason": "promotion", "promotion_name": "Frete de verão", "threshold_q": 0, "base_fee_q": FEE_Q,
    }


def test_o_pedido_fecha_sem_linha_de_taxa_e_o_kernel_concorda(balcao):
    """A linha que o PDV não põe, o modifier também não põe: mesma função dos dois lados."""
    operator, shift = balcao
    _promo()

    result = _close(operator, _payload(shift, "fg-2"))

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200
    assert _fee_lines(order) == []


def test_teto_da_promocao_abate_e_o_cliente_paga_a_diferenca(balcao):
    operator, shift = balcao
    _promo(cap_q=500)

    review = _review(operator, _payload(shift, "fg-3"))
    assert review.delivery_fee_q == FEE_Q - 500
    assert review.delivery_fee_waiver["reason"] == "promotion"
    assert review.delivery_fee_waiver["base_fee_q"] == FEE_Q

    result = _close(operator, _payload(shift, "fg-4"))
    order = Order.objects.get(ref=result.order_ref)
    assert [line.unit_price_q for line in _fee_lines(order)] == [FEE_Q - 500]
    assert order.total_q == 1200 + FEE_Q - 500


def test_promocao_so_da_loja_online_nao_vale_no_balcao(balcao):
    operator, shift = balcao
    Channel.objects.create(ref="web", name="Loja online")
    _promo(channels=("web",))

    review = _review(operator, _payload(shift, "fg-5"))
    assert review.delivery_fee_q == FEE_Q
    assert review.delivery_fee_waiver is None


def test_promocao_do_proprio_balcao_vale(balcao):
    operator, shift = balcao
    _promo(channels=("pdv",))
    assert _review(operator, _payload(shift, "fg-6")).delivery_fee_q == 0


def test_valor_minimo_da_promocao_e_respeitado(balcao):
    operator, shift = balcao
    _promo(min_order_q=5000)
    assert _review(operator, _payload(shift, "fg-7")).delivery_fee_q == FEE_Q


def test_promocao_so_de_retirada_nao_mexe_na_entrega(balcao):
    operator, shift = balcao
    _promo(fulfillment_types=["pickup"])
    assert _review(operator, _payload(shift, "fg-8")).delivery_fee_q == FEE_Q


def test_promocao_de_grupo_de_clientes_so_vale_para_o_cliente_do_grupo(balcao):
    from shopman.guestman.models import Customer, PriceTier

    operator, shift = balcao
    tier = PriceTier.objects.create(ref="alianca", name="Aliança Francesa")
    Customer.objects.create(ref="CLI-ALIANCA", first_name="Ana", phone="+5543999990001", price_tier=tier)
    Customer.objects.create(ref="CLI-OUTRO", first_name="Beto", phone="+5543999990002")
    _promo(customer_segments=["alianca"])

    assert _review(operator, _payload(shift, "fg-9", customer_ref="CLI-ALIANCA")).delivery_fee_q == 0
    assert _review(operator, _payload(shift, "fg-10", customer_ref="CLI-OUTRO")).delivery_fee_q == FEE_Q
    assert _review(operator, _payload(shift, "fg-11")).delivery_fee_q == FEE_Q


def test_limiar_da_loja_tambem_diz_que_e_o_limiar(balcao):
    operator, shift = balcao
    shop = Shop.objects.get()
    shop.defaults = {**(shop.defaults or {}), "rules": {"free_delivery_above_q": 1000}}
    shop.save(update_fields=["defaults"])

    review = _review(operator, _payload(shift, "fg-12"))

    assert review.delivery_fee_q == 0
    assert review.delivery_fee_waiver == {
        "reason": "threshold", "promotion_name": "", "threshold_q": 1000, "base_fee_q": FEE_Q,
    }


def test_taxa_combinada_a_mao_vence_a_promocao_e_nao_se_diz_gratis(balcao):
    operator, shift = balcao
    _promo()

    review = _review(operator, _payload(shift, "fg-13", delivery_fee_override_q=300))

    assert review.delivery_fee_q == 300
    assert review.delivery_fee_source == "manual"
    assert review.delivery_fee_waiver is None


def test_a_revisao_da_api_leva_a_promocao_com_os_valores_escritos(balcao):
    from shopman.backstage.api.operations import _pos_sale_review_payload

    operator, shift = balcao
    _promo()

    body = _pos_sale_review_payload(_review(operator, _payload(shift, "fg-14")))

    assert body["delivery_fee_waiver"] == {
        "reason": "promotion", "promotion_name": "Frete de verão", "threshold_q": 0, "base_fee_q": FEE_Q,
        "threshold_display": "R$ 0,00", "base_fee_display": "R$ 8,00",
    }
