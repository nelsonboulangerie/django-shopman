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


def _fixed_coupon(code: str, value_q: int, *, min_order_q: int = 0) -> Coupon:
    now = timezone.now()
    promo = Promotion.objects.create(
        ref=f"cupom-{code.lower()}", name=code, type=Promotion.FIXED, value=value_q, min_order_q=min_order_q,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1), is_active=True,
    )
    return Coupon.objects.create(code=code, promotion=promo, max_uses=1, is_active=True)


def _cart_with(channel_ref: str, lines: list[tuple[str, str, int, int]]) -> str:
    session = sessions.create_session(channel_ref)
    ops = [
        {"op": "add_line", "sku": sku, "name": name, "qty": qty, "unit_price_q": price_q}
        for sku, name, qty, price_q in lines
    ]
    ops.append({"op": "set_data", "path": "fulfillment_type", "value": "pickup"})
    sessions.modify_session(session_key=session.session_key, channel_ref=channel_ref, ops=ops)
    return session.session_key


def test_cupom_fixo_maior_que_o_desconto_por_item_entra_no_lugar_dele(web):
    """O maior desconto ganha também para o cupom de valor fixo: R$ 5,00 contra os 10%
    de aniversário de 3 Croissants (R$ 3,90) é o cupom. O desconto por item sai das
    linhas (preço e transparência), e os R$ 5,00 são rateados nelas."""
    from shopman.storefront.api.surface import coupon_replaced_notice

    _promotion("aniversario", "Desconto de aniversário", 10)
    _fixed_coupon("PRIMEIRACOMPRA", 500, min_order_q=3000)
    key = _cart_with(web, [("CRO", "Croissant", 3, 1300)])

    session, _name = cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")

    assert all(item["meta"]["_disc"]["type"] == "coupon" for item in session.items)
    assert session.coupon_replaced == {"label": "Desconto de aniversário", "total_q": 390}
    assert coupon_replaced_notice(session.coupon_replaced) == (
        "Cupom aplicado no lugar do desconto que já valia (Desconto de aniversário, R$ 3,90), porque dá mais."
    )
    session = Session.objects.get(session_key=key)
    # 3 unidades não repartem R$ 5,00 em centavos inteiros por unidade (1,666…): o rateio
    # de valor fixo entrega o mínimo acima do prometido (``_spread_order_discount`` com
    # ``at_least=True``), R$ 1,67 por unidade, e registra o que de fato aplicou.
    assert session.items[0]["unit_price_q"] == 1133
    assert session.items[0]["line_total_q"] == 3399
    assert session.pricing["coupon"] == {"code": "PRIMEIRACOMPRA", "discount_q": 501}
    records = session.pricing["discount"]["items"]
    assert [(r["type"], r["sku"], r["discount_q"]) for r in records] == [("coupon", "", 501)]
    assert session.pricing["discount"]["total_discount_q"] == 501


def test_cupom_fixo_que_empata_com_o_desconto_por_item_nao_entra(web):
    """R$ 3,90 contra os 10% de 3 Croissants (R$ 3,90): no empate fica o que já valia."""
    _promotion("aniversario", "Desconto de aniversário", 10)
    coupon = _fixed_coupon("EMPATE", 390)
    key = _cart_with(web, [("CRO", "Croissant", 3, 1300)])

    with pytest.raises(cart_service.CouponNotBetter) as refused:
        cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="EMPATE")

    assert (refused.value.standing_label, refused.value.standing_q) == ("Desconto de aniversário", 390)
    session = Session.objects.get(session_key=key)
    assert "coupon_code" not in (session.data or {})
    assert session.items[0]["meta"]["_disc"]["type"] == "promotion"
    assert session.items[0]["line_total_q"] == 3510
    coupon.refresh_from_db()
    assert coupon.is_available


def test_cupom_fixo_menor_que_o_desconto_por_item_nao_entra(web):
    _promotion("aniversario", "Desconto de aniversário", 10)
    _fixed_coupon("TRES", 300)
    key = _cart_with(web, [("CRO", "Croissant", 3, 1300)])

    with pytest.raises(cart_service.CouponNotBetter) as refused:
        cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="TRES")

    assert refused.value.standing_q == 390
    session = Session.objects.get(session_key=key)
    assert session.items[0]["meta"]["_disc"] == {"type": "promotion", "amount_q": 130, "label": "Desconto de aniversário"}
    assert session.items[0]["line_total_q"] == 3510
    assert [r["type"] for r in session.pricing["discount"]["items"]] == ["promotion"]


def test_cupom_fixo_fica_nas_linhas_sem_desconto_quando_trocar_daria_menos(web):
    """Croissants com 10% (R$ 3,90) e um pão sem desconto: o cupom de R$ 5,00 no pão
    soma R$ 8,90; trocar os 10% pelo cupom daria R$ 5,00. Fica o que dá mais: os 10%
    seguem nos Croissants e o cupom vai só para o pão."""
    Product.objects.create(sku="PAO", name="Pão de campanha", base_price_q=2000, is_published=True, is_sellable=True)
    aniversario = _promotion("aniversario", "Desconto de aniversário", 10)
    aniversario.skus = ["CRO"]
    aniversario.save(update_fields=["skus"])
    _fixed_coupon("CINCO", 500)
    key = _cart_with(web, [("CRO", "Croissant", 3, 1300), ("PAO", "Pão de campanha", 1, 2000)])

    session, _name = cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="CINCO")

    assert getattr(session, "coupon_replaced", None) is None
    session = Session.objects.get(session_key=key)
    by_sku = {item["sku"]: item for item in session.items}
    assert by_sku["CRO"]["meta"]["_disc"]["type"] == "promotion"
    assert by_sku["CRO"]["line_total_q"] == 3510
    assert by_sku["PAO"]["meta"]["_disc"]["type"] == "coupon"
    assert by_sku["PAO"]["line_total_q"] == 1500
    assert session.pricing["coupon"] == {"code": "CINCO", "discount_q": 500}
    assert session.pricing["discount"]["total_discount_q"] == 890


def test_promocao_automatica_de_valor_fixo_nao_desloca_o_desconto_por_item(web):
    """Só o CUPOM fixo troca de lugar com o desconto por item. A promoção automática de
    valor fixo segue fora das linhas com desconto: o PDV mostra no botão o preço por
    item e nunca o fixo de pedido, e a troca faria a cobrança divergir do botão."""
    _promotion("aniversario", "Desconto de aniversário", 10)
    now = timezone.now()
    Promotion.objects.create(
        ref="cinco-reais", name="Cinco reais", type=Promotion.FIXED, value=500,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1), is_active=True,
    )
    key = _cart_with(web, [("CRO", "Croissant", 3, 1300)])

    session = Session.objects.get(session_key=key)
    assert session.items[0]["meta"]["_disc"]["type"] == "promotion"
    assert session.items[0]["line_total_q"] == 3510
    assert [(r["type"], r["sku"]) for r in session.pricing["discount"]["items"]] == [("promotion", "CRO")]
