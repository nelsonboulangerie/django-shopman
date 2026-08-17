"""Entrega grátis: renúncia da taxa por quem a calcula, nunca linha de desconto.

A distinção não é estilística. A linha `__DELIVERY_FEE__` é blindada contra desconto em
dez pontos do `modifiers.py`, e é essa invariante que mantém a taxa com **um dono**. Se
entrega grátis virasse desconto, dois donos escreveriam no mesmo número.

Duas políticas, um dono: o limiar permanente da loja (`free_delivery_above_q`) e a
promoção `free_delivery`. Vence a que renuncia mais — mesma convenção best-wins que o
projeto já usa para desconto.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Channel, Coupon, DeliveryZone, Promotion, Shop
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db

FEE_Q = 1200  # taxa da zona de entrega neste teste


@pytest.fixture
def loja():
    """Loja com taxa de entrega vinda de uma zona por CEP — como em produção."""
    shop = Shop.objects.create(name="Test Shop")
    DeliveryZone.objects.create(
        shop=shop,
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=FEE_Q,
    )
    web = Channel.objects.create(ref="web", name="Loja online")
    Product.objects.create(
        sku="PAO", name="Pão", base_price_q=2000, is_published=True, is_sellable=True
    )
    return shop, web


def _free_delivery(ref: str, *, cap_q: int = 0, **kwargs) -> Promotion:
    now = timezone.now()
    return Promotion.objects.create(
        ref=ref,
        name=ref,
        type=Promotion.FREE_DELIVERY,
        value=cap_q,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        **kwargs,
    )


def _delivery_cart(*, qty: int = 1, coupon: str = "") -> object:
    session = sessions.create_session("web")
    ops = [
        {"op": "add_line", "sku": "PAO", "name": "Pão", "qty": qty, "unit_price_q": 2000},
        {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
        {"op": "set_data", "path": "delivery_address", "value": "Rua das Flores, 1"},
        {"op": "set_data", "path": "delivery_address_structured",
         "value": {"postal_code": "86050-270", "neighborhood": "Centro"}},
    ]
    if coupon:
        ops.append({"op": "set_data", "path": "coupon_code", "value": coupon})
    sessions.modify_session(session_key=session.session_key, channel_ref="web", ops=ops)
    session.refresh_from_db()
    return session


def _fee_q(session) -> int:
    return int((session.data or {}).get("delivery_fee_q") or 0)


def _fee_lines(session) -> list:
    return [i for i in (session.items or []) if i.get("sku") == "__DELIVERY_FEE__"]


def test_without_promotion_the_fee_is_charged(loja):
    """A linha de base: sem promoção nem limiar, a taxa é cobrada."""
    session = _delivery_cart()
    assert _fee_q(session) == FEE_Q
    assert len(_fee_lines(session)) == 1


def test_automatic_promotion_waives_the_whole_fee(loja):
    _free_delivery("frete-gratis")
    session = _delivery_cart()
    assert _fee_q(session) == 0


def test_a_waived_fee_removes_the_line_instead_of_showing_zero(loja):
    """R$ 0,00 no carrinho é ruído; a linha some. Sai de graça do dono da taxa."""
    _free_delivery("frete-gratis")
    session = _delivery_cart()
    assert _fee_lines(session) == []


def test_the_waiver_never_becomes_a_discount_line(loja):
    """A prova da invariante: renúncia mexe na TAXA, não no desconto."""
    _free_delivery("frete-gratis")
    session = _delivery_cart()
    discount_q = int((session.pricing or {}).get("discount", {}).get("total_discount_q") or 0)
    assert discount_q == 0, "entrega grátis não pode aparecer como desconto"


def test_value_is_a_cap_and_the_customer_pays_the_difference(loja):
    """`value > 0` = teto: 'entrega grátis até R$ 8,00' sobre taxa de R$ 12,00."""
    _free_delivery("frete-ate-8", cap_q=800)
    session = _delivery_cart()
    assert _fee_q(session) == FEE_Q - 800


def test_a_cap_above_the_fee_waives_everything(loja):
    _free_delivery("frete-ate-50", cap_q=5000)
    session = _delivery_cart()
    assert _fee_q(session) == 0


def test_min_order_gates_the_waiver(loja):
    """Renúncia com pedido mínimo: abaixo do mínimo, a taxa continua."""
    _free_delivery("frete-acima-de-100", min_order_q=10_000)
    assert _fee_q(_delivery_cart(qty=1)) == FEE_Q  # R$ 20,00
    assert _fee_q(_delivery_cart(qty=5)) == 0      # R$ 100,00


def test_a_coupon_can_carry_the_waiver(loja):
    """Frete grátis por cupom: o encanamento já existia, sem nada novo.

    O modifier da taxa roda em `order=70`, cinquenta slots depois do desconto
    (`order=20`), então o cupom já está resolvido quando a taxa é calculada.
    """
    promo = _free_delivery("cupom-frete")
    Coupon.objects.create(code="FRETEGRATIS", promotion=promo, max_uses=0, is_active=True)

    assert _fee_q(_delivery_cart()) == FEE_Q  # sem o cupom, cobra
    assert _fee_q(_delivery_cart(coupon="FRETEGRATIS")) == 0


def test_a_coupon_only_waiver_does_not_leak_without_the_coupon(loja):
    """Promoção com cupom não é automática — só vale ativada."""
    promo = _free_delivery("cupom-frete")
    Coupon.objects.create(code="FRETEGRATIS", promotion=promo, max_uses=0, is_active=True)
    assert _fee_q(_delivery_cart()) == FEE_Q


def test_the_more_generous_policy_wins(loja):
    """Limiar permanente e promoção convivem; vence quem renuncia mais."""
    shop, _ = loja
    defaults = dict(shop.defaults or {})
    defaults["rules"] = {**(defaults.get("rules") or {}), "free_delivery_above_q": 100_000}
    shop.defaults = defaults
    shop.save(update_fields=["defaults"])

    # O limiar não alcança (pedido de R$ 20,00), mas a promoção com teto alcança.
    _free_delivery("frete-ate-5", cap_q=500)
    assert _fee_q(_delivery_cart()) == FEE_Q - 500


def test_coupon_does_not_cost_the_customer_the_free_delivery_threshold(loja):
    """Cupom promocional NÃO derruba a elegibilidade de frete grátis.

    Invariante do projeto: thresholds (mínimo/frete grátis) leem
    ``subtotal + coupon_discount`` (``threshold_base_q``) — uma cortesia não pode
    tirar um benefício. A projeção do carrinho e o gate de mínimo já respeitam
    isso; a taxa (DeliveryFeeModifier) precisa ler a MESMA base, senão a tela diz
    "frete grátis" e a cobrança aplica a taxa (ou o guard de total barra o
    checkout). Regressão da auditoria alpha.
    """
    shop, _ = loja
    defaults = dict(shop.defaults or {})
    # Frete grátis acima de R$ 50,00.
    defaults["rules"] = {**(defaults.get("rules") or {}), "free_delivery_above_q": 5000}
    shop.defaults = defaults
    shop.save(update_fields=["defaults"])

    # Cupom de 20%: R$ 60,00 de mercadoria → R$ 48,00 líquido (abaixo do limiar),
    # mas o desconto de R$ 12,00 é cortesia e não conta contra o limiar.
    now = timezone.now()
    promo = Promotion.objects.create(
        ref="cupom-20", name="Cupom 20%", type=Promotion.PERCENT, value=20,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        is_active=True,
    )
    Coupon.objects.create(code="MENOS20", promotion=promo, max_uses=0, is_active=True)

    # Sem cupom: R$ 60,00 ≥ R$ 50,00 → já é grátis (linha de base).
    assert _fee_q(_delivery_cart(qty=3)) == 0
    # Com cupom: líquido R$ 48,00, mas base do limiar = 48,00 + 12,00 = 60,00 →
    # continua grátis. Sem o add-back, o modifier veria 48,00 e cobraria a taxa.
    session = _delivery_cart(qty=3, coupon="MENOS20")
    assert _fee_q(session) == 0, (
        "cupom derrubou o frete grátis: a taxa foi cobrada mesmo com a mercadoria "
        "acima do limiar (o desconto do cupom não deveria contar contra o limiar)"
    )


def test_a_scoped_waiver_does_not_reach_another_channel(loja):
    """`Promotion.channels` vale para a renúncia também — é a mesma régua."""
    _shop, web = loja
    promo = _free_delivery("frete-so-web")
    promo.channels.set([web])

    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    assert _fee_q(_delivery_cart()) == 0  # web: renuncia

    session = sessions.create_session("ifood")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="ifood",
        ops=[
            {"op": "add_line", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 2000},
            {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
            {"op": "set_data", "path": "delivery_address", "value": "Rua das Flores, 1"},
            {"op": "set_data", "path": "delivery_address_structured",
             "value": {"postal_code": "86050-270", "neighborhood": "Centro"}},
        ],
    )
    session.refresh_from_db()
    assert _fee_q(session) == FEE_Q


def test_pickup_only_free_delivery_is_refused_at_the_edge(loja):
    """Configuração que não quer dizer nada não deve ser gravável."""
    now = timezone.now()
    promo = Promotion(
        ref="frete-gratis-retirada",
        name="incoerente",
        type=Promotion.FREE_DELIVERY,
        value=0,
        valid_from=now,
        valid_until=now + timedelta(days=1),
        fulfillment_types=["pickup"],
    )
    with pytest.raises(ValidationError) as exc:
        promo.full_clean()
    assert "fulfillment_types" in exc.value.message_dict


def test_free_delivery_for_delivery_is_valid(loja):
    now = timezone.now()
    Promotion(
        ref="ok",
        name="ok",
        type=Promotion.FREE_DELIVERY,
        value=0,
        valid_from=now,
        valid_until=now + timedelta(days=1),
        fulfillment_types=["delivery"],
    ).full_clean()
