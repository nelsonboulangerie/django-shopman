"""O cupom que não vence o desconto que já vale não é aplicado nem gasto.

Os descontos não se somam e o maior ganha (a régua da casa, a mesma da Xepa no PDV,
#3184). No empate fica o que já valia: o cupom saía "aplicado", com "Desconto de
R$ 1,30", trocando os 10% de aniversário pelos 10% dele. O total não mudava, e o
cupom de uso único era gasto à toa (J10, #2569). Agora ele sai da sacola sem ser
gasto, e a loja diz por quê; quando vence, entra no lugar, e a loja diz de quê.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Session

from shopman.shop.models import Channel, Coupon, Promotion, Shop
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db


@pytest.fixture
def web():
    Shop.objects.get_or_create(name="Test Shop")
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja online"})
    Product.objects.create(sku="CRO", name="Croissant", base_price_q=1300, is_published=True, is_sellable=True)
    return "web"


def _promotion(ref: str, name: str, value: int) -> Promotion:
    now = timezone.now()
    return Promotion.objects.create(
        ref=ref,
        name=name,
        type=Promotion.PERCENT,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        is_active=True,
    )


def _coupon(code: str, value: int) -> Coupon:
    return Coupon.objects.create(
        code=code, promotion=_promotion(f"cupom-{code.lower()}", code, value), max_uses=1, is_active=True
    )


def _cart(channel_ref: str) -> str:
    session = sessions.create_session(channel_ref)
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref=channel_ref,
        ops=[
            {"op": "add_line", "sku": "CRO", "name": "Croissant", "qty": 1, "unit_price_q": 1300},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )
    return session.session_key


def test_cupom_que_empata_nao_entra_nem_e_gasto_e_a_loja_diz_por_que(web):
    from shopman.storefront.api.surface import coupon_not_better_message

    _promotion("aniversario", "Desconto de aniversário", 10)
    coupon = _coupon("NELSON10", 10)
    key = _cart(web)

    with pytest.raises(cart_service.CouponNotBetter) as refused:
        cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="NELSON10")

    assert (refused.value.standing_label, refused.value.standing_q) == ("Desconto de aniversário", 130)
    session = Session.objects.get(session_key=key)
    assert "coupon_code" not in (session.data or {})
    # O desconto que já valia segue valendo, e o cupom segue disponível.
    assert session.items[0]["meta"]["_disc"]["type"] == "promotion"
    assert session.items[0]["line_total_q"] == 1170
    coupon.refresh_from_db()
    assert coupon.is_available

    message = coupon_not_better_message({
        "coupon_code": "NELSON10",
        "standing_label": refused.value.standing_label,
        "standing_q": refused.value.standing_q,
    })
    assert message == (
        "Os itens deste cupom já têm desconto de R$ 1,30 (Desconto de aniversário), igual ou maior "
        "que o do NELSON10. Os descontos não se somam: guarde o cupom para outra compra."
    )
    assert "—" not in message


def test_cupom_que_vence_entra_no_lugar_e_a_loja_diz_de_que(web):
    from shopman.storefront.api.surface import coupon_replaced_notice

    _promotion("aniversario", "Desconto de aniversário", 10)
    _coupon("QUINZE", 15)
    key = _cart(web)

    session, _name = cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="QUINZE")

    assert session.coupon_replaced == {"label": "Desconto de aniversário", "total_q": 130}
    assert session.items[0]["meta"]["_disc"]["type"] == "coupon"
    assert session.items[0]["line_total_q"] == 1105
    assert coupon_replaced_notice(session.coupon_replaced) == (
        "Cupom aplicado no lugar do desconto que já valia (Desconto de aniversário, R$ 1,30), porque dá mais."
    )


def test_cupom_sem_desconto_concorrente_entra_sem_aviso(web):
    from shopman.storefront.api.surface import coupon_replaced_notice

    _coupon("NELSON10", 10)
    key = _cart(web)

    session, _name = cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="NELSON10")

    assert getattr(session, "coupon_replaced", None) is None
    assert session.items[0]["line_total_q"] == 1170
    assert coupon_replaced_notice(getattr(session, "coupon_replaced", None)) == ""


def test_cupom_fixo_maior_que_o_desconto_por_item_nao_diz_igual_ou_maior(web):
    """O fixo de pedido não entra no lugar do desconto por item (``_fixed_eligible_lines``):
    R$ 5,00 contra 10% de 3 Croissants (R$ 3,90) é recusado, e a frase não pode afirmar
    que o desconto que fica é "igual ou maior"."""
    from shopman.storefront.api.surface import coupon_not_better_message

    _promotion("aniversario", "Desconto de aniversário", 10)
    now = timezone.now()
    fixed = Promotion.objects.create(
        ref="cupom-cinco", name="CINCO", type=Promotion.FIXED, value=500,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1), is_active=True,
    )
    Coupon.objects.create(code="CINCO", promotion=fixed, max_uses=1, is_active=True)
    session = sessions.create_session(web)
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref=web,
        ops=[
            {"op": "add_line", "sku": "CRO", "name": "Croissant", "qty": 3, "unit_price_q": 1300},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )

    with pytest.raises(cart_service.CouponNotBetter) as refused:
        cart_service.validate_and_apply_coupon(session_key=session.session_key, channel_ref=web, code="CINCO")

    assert (refused.value.standing_q, refused.value.coupon_q, refused.value.fixed) == (390, 500, True)
    message = coupon_not_better_message({
        "coupon_code": "CINCO",
        "standing_label": refused.value.standing_label,
        "standing_q": refused.value.standing_q,
        "coupon_q": refused.value.coupon_q,
        "fixed": refused.value.fixed,
    })
    assert "igual ou maior" not in message
    assert message == (
        "O CINCO é um desconto de valor fixo e não entra no lugar do desconto que os itens já têm "
        "(R$ 3,90, Desconto de aniversário). Os descontos não se somam: guarde o cupom para outra compra."
    )
