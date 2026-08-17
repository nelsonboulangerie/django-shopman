"""As portas do cupom, no orquestrador — e valendo para QUALQUER canal.

As cinco validações moravam em `storefront/cart.py`, e era por isso que o PDV não tinha
cupom: para ganhá-lo teria de reimplementar as mesmas portas, e duas implementações da
mesma pergunta divergem por construção ("uma pergunta, um dono").

O teste que importa aqui é `test_the_pos_gets_coupons_for_free`: ele exerce as portas
pelo canal `pdv` sem uma linha de código de PDV. É a prova da afirmação da F6, em vez
da afirmação sozinha.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Channel, Coupon, Promotion, Shop
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop():
    Shop.objects.get_or_create(name="Test Shop")
    web, _ = Channel.objects.get_or_create(ref="web", defaults={"name": "Loja online"})
    pdv, _ = Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
    Product.objects.create(
        sku="PAO", name="Pão", base_price_q=1000, is_published=True, is_sellable=True
    )
    return web, pdv


def _promotion(ref: str, *, channels=(), value: int = 10, active: bool = True, expired: bool = False):
    now = timezone.now()
    promo = Promotion.objects.create(
        ref=ref,
        name=ref,
        type=Promotion.PERCENT,
        value=value,
        valid_from=now - timedelta(days=2),
        valid_until=now - timedelta(days=1) if expired else now + timedelta(days=1),
        is_active=active,
    )
    if channels:
        promo.channels.set(channels)
    return promo


def _cart(channel_ref: str) -> str:
    session = sessions.create_session(channel_ref)
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref=channel_ref,
        ops=[
            {"op": "add_line", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1000},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )
    return session.session_key


def _apply(channel_ref: str, code: str, *, customer=None):
    return cart_service.validate_and_apply_coupon(
        session_key=_cart(channel_ref), channel_ref=channel_ref, code=code, customer=customer
    )


def test_the_pos_gets_coupons_for_free(shop):
    """O valor prometido pela F6: o cupom funciona no `pdv` sem código de PDV.

    Nenhuma linha em `shop/services/pos.py` foi escrita para isto. As portas moram no
    orquestrador, e canal é parâmetro.
    """
    promo = _promotion("dez-por-cento")
    Coupon.objects.create(code="DEZ", promotion=promo, max_uses=0, is_active=True)

    session, name = _apply("pdv", "DEZ")
    assert name == "dez-por-cento"
    assert (session.data or {}).get("coupon_code") == "DEZ"
    assert int((session.pricing or {})["discount"]["total_discount_q"]) == 100


def test_a_web_only_coupon_is_refused_at_the_counter(shop):
    """Porta NOVA: antes de `Promotion.channels` o cupom da web descontava no balcão."""
    web, _pdv = shop
    promo = _promotion("so-web", channels=[web])
    Coupon.objects.create(code="SOWEB", promotion=promo, max_uses=0, is_active=True)

    session, _ = _apply("web", "SOWEB")
    assert int((session.pricing or {})["discount"]["total_discount_q"]) == 100

    with pytest.raises(cart_service.CouponRejected) as exc:
        _apply("pdv", "SOWEB")
    assert exc.value.code == "coupon_wrong_channel"


def test_unknown_code_is_invalid(shop):
    with pytest.raises(cart_service.CouponRejected) as exc:
        _apply("web", "NAOEXISTE")
    assert exc.value.code == "invalid_coupon"


def test_exhausted_coupon_says_so(shop):
    promo = _promotion("uma-vez")
    Coupon.objects.create(
        code="UMAVEZ", promotion=promo, max_uses=1, uses_count=1, is_active=True
    )
    with pytest.raises(cart_service.CouponRejected) as exc:
        _apply("web", "UMAVEZ")
    assert exc.value.code == "coupon_exhausted"


def test_expired_promotion_says_expired_not_invalid(shop):
    """A distinção existe para a copy poder ser específica, não genérica."""
    promo = _promotion("acabou", expired=True)
    Coupon.objects.create(code="ACABOU", promotion=promo, max_uses=0, is_active=True)
    with pytest.raises(cart_service.CouponRejected) as exc:
        _apply("web", "ACABOU")
    assert exc.value.code == "coupon_expired"


def test_segment_gated_coupon_refuses_the_anonymous_visitor(shop):
    """Recusar na porta em vez de gravar um cupom MUDO (desconto 0) sem avisar."""
    promo = _promotion("staff")
    promo.customer_segments = ["staff"]
    promo.save(update_fields=["customer_segments"])
    Coupon.objects.create(code="FUNCIONARIO", promotion=promo, max_uses=0, is_active=True)

    with pytest.raises(cart_service.CouponRejected) as exc:
        _apply("web", "FUNCIONARIO", customer=None)
    assert exc.value.code == "coupon_not_eligible"


def test_the_code_is_normalized_before_the_lookup(shop):
    """Minúscula com espaço acha o cupom: normalizar é do dono, não da superfície."""
    promo = _promotion("dez")
    Coupon.objects.create(code="DEZ", promotion=promo, max_uses=0, is_active=True)

    _session, name = _apply("web", "  dez  ")
    assert name == "dez"
