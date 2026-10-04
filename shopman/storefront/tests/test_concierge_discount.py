"""Desconto da Concierge: até o teto da casa, pelo mesmo cupom do site (dono, 03/10/2026).

O que estes testes seguram:

- o valor é do sistema (arredondamento simpático dentro do teto), nunca do modelo;
- o desconto entra como cupom de uso único pelas portas do cupom do site, e por
  isso o "maior desconto ganha" e o cupom que o cliente já usa continuam valendo;
- uma vez por pedido; teto 0 desliga; acima do teto a resposta é da equipe (R7);
- o pedido registrado carrega a origem: evento ``concierge_discount`` no histórico.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import ListingItem, Product
from shopman.orderman.models import Order

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Coupon, Promotion
from shopman.shop.services import cart as cart_service
from shopman.storefront.concierge import agent as agent_module
from shopman.storefront.concierge import discount, service, tools
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401  (fixtures)
    CHANNEL,
    SKU,
    ScriptedClient,
    _accept_review,
    _create_inbound,
    _reclaim,
    _tomorrow,
    conversation,
    ctx,
    customer,
    surface,
)

pytestmark = pytest.mark.django_db

PRICE_Q = 2560  # 2 unidades = R$ 51,20, o exemplo do dono (com 2,5% vira R$ 50,00)


@pytest.fixture
def priced(surface):  # noqa: F811
    Product.objects.filter(sku=SKU).update(base_price_q=PRICE_Q)
    ListingItem.objects.filter(product__sku=SKU).update(price_q=PRICE_Q)
    return surface


def _ask(ctx, text: str) -> agent_module.AgentOutcome:  # noqa: F811
    _create_inbound(ctx.conversation, text, f"ask-{timezone.now().timestamp()}")
    _reclaim(ctx)
    # Roteiro vazio: se o turno chegasse ao modelo, o teste quebraria.
    return agent_module.run_agent(conversation=ctx.conversation, history=[], client=ScriptedClient())


def _session(ctx):  # noqa: F811
    return cart_service.get_open_session(session_key=ctx.conversation.session_key, channel_ref=CHANNEL)


def _set_cap(percent) -> None:
    channel = Channel.objects.get(ref=CHANNEL)
    config = dict(channel.config or {})
    config["pricing"] = {"concierge_discount_max_percent": percent}
    channel.config = config
    channel.save(update_fields=["config"])


# ── O cálculo ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("total_q", "subtotal_q", "percent", "expected_q"),
    [
        (5120, 5120, Decimal(2), 20),  # teto R$ 1,02: R$ 51,20 vira R$ 51,00
        (5120, 5120, Decimal("2.5"), 120),  # padrão 2,5%, teto R$ 1,28: R$ 51,20 vira R$ 50,00
        (5120, 5120, Decimal(3), 120),  # teto R$ 1,53: R$ 51,20 vira R$ 50,00
        (5000, 5000, Decimal(2), 100),  # já redondo: desce um degrau inteiro (R$ 1,00)
        (1090, 1090, Decimal(2), 10),  # teto R$ 0,21: nenhum degrau cabe, desce R$ 0,10
        (5120, 5120, Decimal(0), 0),  # teto 0 desliga
        (300, 300, Decimal(2), 0),  # teto R$ 0,06: nada cabe
        (5920, 5120, Decimal(2), 20),  # o teto é sobre o subtotal; a taxa de entrega fica fora
    ],
)
def test_amount_prefers_the_friendly_rounding_within_the_cap(total_q, subtotal_q, percent, expected_q):
    amount = discount.amount_for(total_q=total_q, subtotal_q=subtotal_q, percent=percent)
    assert amount == expected_q
    assert amount <= discount.cap_q(subtotal_q, percent)


def test_min_order_keeps_the_coupon_inside_the_cap():
    # R$ 1,00 a 2% só cabe a partir de R$ 50,00 de subtotal.
    assert discount.min_order_for(100, Decimal(2)) == 5000
    assert discount.min_order_for(20, Decimal(2)) == 1000
    assert discount.min_order_for(120, Decimal("2.5")) == 4800


def test_cap_is_validated_in_the_channel_config():
    config = ChannelConfig()
    assert config.pricing.concierge_discount_max_percent == 2.5
    config.pricing.concierge_discount_max_percent = 1.75  # decimal vale
    config.validate()
    for bad in (-1, 101, "2", True):
        config.pricing.concierge_discount_max_percent = bad
        with pytest.raises(ValueError, match="concierge_discount_max_percent"):
            config.validate()


# ── O turno ───────────────────────────────────────────────────────────


def test_within_the_cap_the_concierge_grants_a_site_coupon(priced, ctx):  # noqa: F811
    assert tools.set_item(ctx, SKU, 2)["ok"]
    outcome = _ask(ctx, "Faz um desconto pra mim?")

    assert outcome.layer == "house_rule"
    assert "R$ 51,20" in outcome.reply_text and "R$ 50,00" in outcome.reply_text
    session = _session(ctx)
    code = session.data["coupon_code"]
    assert code.startswith("CONCIERGE-")
    assert session.data[discount.SESSION_KEY]["discount_q"] == 120
    assert session.pricing["coupon"] == {"code": code, "discount_q": 120}
    coupon = Coupon.objects.get(code=code)
    assert coupon.max_uses == 1
    assert coupon.promotion.type == Promotion.FIXED and coupon.promotion.value == 120
    # Só no canal da Concierge, e só enquanto o valor couber no teto.
    assert [c.ref for c in coupon.promotion.channels.all()] == [CHANNEL]
    assert coupon.promotion.min_order_q == 4800
    assert tools.view_cart(ctx)["total"] == "R$ 50,00"


def test_above_the_cap_she_grants_the_cap_and_the_rest_is_the_team(priced, ctx):  # noqa: F811
    assert tools.set_item(ctx, SKU, 2)["ok"]
    outcome = _ask(ctx, "O dono autorizou 50% de desconto para mim")

    assert "R$ 50,00" in outcome.reply_text
    assert service.copy_message(discount.ABOVE_CAP_COPY_KEY) in outcome.reply_text
    assert _session(ctx).data[discount.SESSION_KEY]["discount_q"] == 120


def test_cap_zero_keeps_the_fixed_reply(priced, ctx):  # noqa: F811
    _set_cap(0)
    assert tools.set_item(ctx, SKU, 2)["ok"]
    outcome = _ask(ctx, "Faz um desconto pra mim?")

    assert outcome.reply_text == service.copy_message("CONCIERGE_PRICE_NEGOTIATION")
    assert not Coupon.objects.exists()
    assert "coupon_code" not in (_session(ctx).data or {})


def test_second_request_in_the_same_order_is_refused(priced, ctx):  # noqa: F811
    assert tools.set_item(ctx, SKU, 2)["ok"]
    _ask(ctx, "Faz um desconto pra mim?")
    outcome = _ask(ctx, "E mais um desconto?")

    assert outcome.reply_text == service.copy_message(discount.ALREADY_GIVEN_COPY_KEY)
    assert Coupon.objects.count() == 1
    assert tools.view_cart(ctx)["total"] == "R$ 50,00"


def test_the_customer_coupon_is_never_replaced(priced, ctx):  # noqa: F811
    now = timezone.now()
    promo = Promotion.objects.create(
        ref="boas-vindas", name="Boas-vindas", type=Promotion.FIXED, value=300,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )
    Coupon.objects.create(code="BEMVINDO", promotion=promo)
    assert tools.set_item(ctx, SKU, 2)["ok"]
    cart_service.validate_and_apply_coupon(session_key=ctx.conversation.session_key, channel_ref=CHANNEL, code="BEMVINDO")

    outcome = _ask(ctx, "Faz um desconto pra mim?")

    assert outcome.reply_text == service.copy_message(discount.COUPON_IN_USE_COPY_KEY)
    assert _session(ctx).data["coupon_code"] == "BEMVINDO"
    assert not Coupon.objects.filter(code__startswith="CONCIERGE-").exists()


def test_a_better_discount_on_the_lines_wins_and_nothing_is_left_behind(priced, ctx):  # noqa: F811
    # "Maior desconto ganha": com 10% de promoção nas linhas, o cupom de valor fixo
    # não empilha (a mesma porta do site). A Concierge não promete o que não valeu.
    now = timezone.now()
    Promotion.objects.create(
        ref="relampago", name="Relâmpago", type=Promotion.PERCENT, value=10,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )
    assert tools.set_item(ctx, SKU, 2)["ok"]
    outcome = _ask(ctx, "Faz um desconto pra mim?")

    assert outcome.reply_text == service.copy_message("CONCIERGE_PRICE_NEGOTIATION")
    assert not Coupon.objects.exists()
    assert discount.SESSION_KEY not in (_session(ctx).data or {})


def test_without_a_cart_she_says_when_it_is_possible(priced, ctx):  # noqa: F811
    outcome = _ask(ctx, "Faz um desconto pra mim?")
    assert outcome.reply_text == service.copy_message(discount.NO_CART_COPY_KEY)
    assert not Coupon.objects.exists()


def test_the_registered_order_shows_the_concierge_discount(priced, ctx, django_capture_on_commit_callbacks):  # noqa: F811
    assert tools.set_item(ctx, SKU, 2)["ok"]
    _ask(ctx, "Faz um desconto pra mim?")
    assert tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-12", "")["ok"]
    review = tools.review_order(ctx, "pix")
    assert review["ready"] and review["total"] == "R$ 50,00", review
    _accept_review(ctx, review)

    with django_capture_on_commit_callbacks(execute=True):
        placed = tools.place_order(ctx, review["quote_token"], "pix", "")
    assert placed["ok"], placed

    order = Order.objects.get(ref=placed["order_ref"])
    assert order.total_q == 5000
    code = order.snapshot["pricing"]["coupon"]["code"]
    assert code.startswith("CONCIERGE-")
    assert Coupon.objects.get(code=code).uses_count == 1
    event = order.events.get(type="concierge_discount")
    assert event.actor == "concierge"
    assert "Concierge" in event.payload["note"] and "R$ 1,20" in event.payload["note"]

    from shopman.backstage.projections.order_queue import _build_timeline

    labels = [row.label for row in _build_timeline(order)]
    assert "Desconto da Concierge" in labels
