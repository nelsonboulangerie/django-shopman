"""Cupom de valor FIXO é desconto de PEDIDO, aplicado uma vez — nunca por unidade.

Regressão do QA exploratório (P1): PRIMEIRACOMPRA (R$5) descontava R$5 em CADA
unidade de CADA linha — 6 pães (R$90) recebiam R$30 de desconto. A intenção
(sinalizada pelo ``min_order_q``) sempre foi um desconto único por pedido.

Cupom/promoção PERCENTUAL continua per-line (uma % é intrinsecamente por unidade).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.utils.monetary import monetary_mult

from shopman.shop.models import Channel, Coupon, Promotion, Shop
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db


def _seed(*, promo_type: str, value: int, min_order_q: int = 0, code: str = "CUPOM") -> None:
    Shop.objects.get_or_create(name="Test Shop")
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    Product.objects.get_or_create(
        sku="PAO",
        defaults={"name": "Pão", "base_price_q": 1500, "is_published": True, "is_sellable": True},
    )
    now = timezone.now()
    promo = Promotion.objects.create(
        # O `ref` deriva do `code` porque é o que varia entre chamadas do helper —
        # `ref` é unique, então derivar do nome fixo colidiria na segunda promoção.
        ref=f"cupom-teste-{code.lower()}",
        name="Cupom Teste",
        type=promo_type,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        min_order_q=min_order_q,
    )
    Coupon.objects.create(code=code, promotion=promo, max_uses=0, is_active=True)


def _cart_with_coupon(*, sku: str, qty: int, unit_price_q: int, code: str):
    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": sku, "name": "Pão", "qty": qty, "unit_price_q": unit_price_q},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
            {"op": "set_data", "path": "coupon_code", "value": code},
        ],
    )
    session.refresh_from_db()
    return session


def _order_total_q(session) -> int:
    return sum(int(i.get("line_total_q", 0)) for i in (session.items or []))


def _assert_lines_are_coherent(session) -> None:
    """``qty × unit_price_q == line_total_q`` em toda linha.

    É a única conta que o cliente confere sozinho ("3 × R$ 6,34" tem que dar o total
    impresso), e os dois campos descem para o payload fiscal. Os rateios de desconto
    de pedido quebravam a igualdade: piso no unitário, valor exato no total.
    """
    for item in session.items or []:
        qty = Decimal(str(item.get("qty", 0)))
        expected = monetary_mult(qty, int(item.get("unit_price_q", 0)))
        assert int(item.get("line_total_q", 0)) == expected, (
            f"linha {item.get('sku')} incoerente: "
            f"{item.get('qty')} × {item.get('unit_price_q')} != {item.get('line_total_q')}"
        )


def test_fixed_coupon_discounts_the_order_once_not_per_unit():
    """5 un × R$15 = R$75; cupom fixo R$5 → total R$70 (não R$50)."""
    _seed(promo_type=Promotion.FIXED, value=500, min_order_q=3000, code="PRIMEIRA")
    session = _cart_with_coupon(sku="PAO", qty=5, unit_price_q=1500, code="PRIMEIRA")

    assert _order_total_q(session) == 7500 - 500
    assert session.pricing["coupon"]["discount_q"] == 500
    assert session.pricing["discount"]["total_discount_q"] == 500
    _assert_lines_are_coherent(session)


def test_fixed_coupon_keeps_the_line_coherent_when_the_split_is_not_exact():
    """6 un × R$15 e um cupom de R$5: 500/6 = 83,33… centavos por unidade.

    O desconto NÃO é representável — o preço unitário é inteiro em centavos, então
    o desconto da linha só pode ser múltiplo de 6. A versão anterior fingia que era:
    tirava 83 do unitário e 500 do total, e a sacola imprimia "6 × R$ 14,17" com
    total "R$ 85,00" (quem multiplica acha R$ 85,02).

    Agora o rateio entrega o mínimo ACIMA do prometido (84 × 6 = R$ 5,04, porque
    quem prometeu "R$ 5 de desconto" paga o centavo a mais) e a tela mostra ESSE
    valor: o registrado em ``pricing`` é o desconto de verdade, nunca o nominal.
    """
    _seed(promo_type=Promotion.FIXED, value=500, min_order_q=3000, code="PRIMEIRA")
    session = _cart_with_coupon(sku="PAO", qty=6, unit_price_q=1500, code="PRIMEIRA")

    _assert_lines_are_coherent(session)
    line = session.items[0]
    assert line["unit_price_q"] == 1500 - 84
    assert _order_total_q(session) == 9000 - 504
    # Transparência == cobrança: o que a tela promete é o que o total caiu.
    assert session.pricing["coupon"]["discount_q"] == 504
    assert session.pricing["discount"]["total_discount_q"] == 504


def test_fixed_coupon_capped_at_order_subtotal():
    """Cupom fixo nunca torna o total negativo — limita ao subtotal elegível."""
    _seed(promo_type=Promotion.FIXED, value=5000, code="GRANDE")
    session = _cart_with_coupon(sku="PAO", qty=1, unit_price_q=1500, code="GRANDE")

    assert _order_total_q(session) == 0
    assert session.pricing["coupon"]["discount_q"] == 1500


def test_fixed_coupon_below_min_order_does_not_apply():
    """Abaixo do pedido mínimo, o cupom fixo não desconta."""
    _seed(promo_type=Promotion.FIXED, value=500, min_order_q=3000, code="PRIMEIRA")
    session = _cart_with_coupon(sku="PAO", qty=1, unit_price_q=1500, code="PRIMEIRA")

    assert _order_total_q(session) == 1500
    assert int(session.pricing.get("coupon", {}).get("discount_q", 0)) == 0


def test_percent_coupon_stays_per_unit():
    """Cupom PERCENTUAL continua per-line: 10% em cada uma das 6 unidades."""
    _seed(promo_type=Promotion.PERCENT, value=10, code="DEZ")
    session = _cart_with_coupon(sku="PAO", qty=6, unit_price_q=1500, code="DEZ")

    # 10% de R$15 = R$1,50 por unidade × 6 = R$9 de desconto no pedido de R$90.
    assert _order_total_q(session) == 9000 - 900
    assert session.pricing["coupon"]["discount_q"] == 900


# ── Sem stacking (canoniza o pentest do QA) ──────────────────────────────


def _seed_auto_promo(*, value: int) -> None:
    """Promoção automática percentual para TODOS os SKUs (sem cupom)."""
    now = timezone.now()
    Promotion.objects.create(
        ref="promo-automatica",
        name="Promo Automática",
        type=Promotion.PERCENT,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )


def test_coupon_does_not_stack_with_auto_promo_best_wins():
    """Cupom % + promoção automática % na MESMA linha: só o maior aplica, nunca a
    soma. 'Maior desconto ganha' por item — sem stacking."""
    # Cupom 20% vence a promo automática de 10% na mesma linha.
    _seed(promo_type=Promotion.PERCENT, value=20, code="VINTE")
    _seed_auto_promo(value=10)
    session = _cart_with_coupon(sku="PAO", qty=2, unit_price_q=1500, code="VINTE")

    # 20% de R$30 = R$6 (não 30% = R$9). Um único desconto por linha.
    assert _order_total_q(session) == 3000 - 600
    # Exatamente um desconto registrado para a linha (o cupom venceu; sem soma).
    pao_discounts = [d for d in session.pricing["discount"]["items"] if d["sku"] == "PAO"]
    assert len(pao_discounts) == 1
    assert pao_discounts[0]["type"] == "coupon"


def test_only_one_coupon_code_is_ever_active():
    """Aplicar um segundo cupom substitui o primeiro — cupons não empilham."""
    _seed(promo_type=Promotion.PERCENT, value=10, code="DEZ")
    _seed(promo_type=Promotion.PERCENT, value=20, code="VINTE")

    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 1500},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )

    def _apply(code):
        sessions.modify_session(
            session_key=session.session_key,
            channel_ref="web",
            ops=[{"op": "set_data", "path": "coupon_code", "value": code}],
        )
        session.refresh_from_db()

    _apply("DEZ")
    _apply("VINTE")  # substitui o cupom anterior, não soma

    assert session.data["coupon_code"] == "VINTE"
    # Só o cupom VINTE (20%) conta: R$30 - R$6 = R$24.
    assert _order_total_q(session) == 3000 - 600
    assert session.pricing["coupon"]["code"] == "VINTE"
    assert session.pricing["coupon"]["discount_q"] == 600
