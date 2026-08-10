"""`Promotion.channels` — vazio vale em todos, preenchido restringe.

Estes testes existem porque campo de escopo sem leitor é escopo decorativo, e este
projeto já foi mordido por isso duas vezes: o `broadcast_optin` que nenhum caminho de
produção escrevia (F1) e o `ultimo_pedido` que nenhum escritor gravava, deixando a
janela de audiência sem filtrar ninguém. Um campo novo nasce com prova de que alguém
o lê.

A semântica é cópia exata de `RuleConfig.channels`: **vazio = todos**. Isso preserva o
comportamento de toda promoção que existia antes do campo, sem migração de dados.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Channel, Coupon, Promotion
from shopman.shop.services import promotions as promotion_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def channels():
    web, _ = Channel.objects.get_or_create(ref="web", defaults={"name": "Loja online"})
    pdv, _ = Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
    return web, pdv


@pytest.fixture
def product():
    return Product.objects.create(
        sku="PAO", name="Pão", base_price_q=1000, is_published=True, is_sellable=True
    )


def _promotion(ref: str, *, channels=()) -> Promotion:
    now = timezone.now()
    promo = Promotion.objects.create(
        ref=ref,
        name=ref,
        type=Promotion.PERCENT,
        value=10,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    if channels:
        promo.channels.set(channels)
    return promo


def test_empty_channels_applies_everywhere(channels):
    """O default preserva o comportamento anterior ao campo: vale em todo canal."""
    _promotion("geral")

    now = timezone.now()
    for ref in ("web", "pdv", "ifood", "canal-que-nem-existe"):
        found = promotion_service.get_active_promotions(now, channel_ref=ref)
        assert [p.ref for p in found] == ["geral"], f"deveria valer em {ref}"


def test_scoped_promotion_is_invisible_to_other_channels(channels):
    """A relâmpago só na web: o PDV não a vê."""
    web, _pdv = channels
    _promotion("so-na-web", channels=[web])

    now = timezone.now()
    assert [p.ref for p in promotion_service.get_active_promotions(now, channel_ref="web")] == [
        "so-na-web"
    ]
    assert promotion_service.get_active_promotions(now, channel_ref="pdv") == []


def test_no_channel_given_does_not_filter(channels):
    """Chamador que ainda não sabe o canal recebe tudo — não é 'vale em todos'."""
    web, _ = channels
    _promotion("so-na-web", channels=[web])

    found = promotion_service.get_active_promotions(timezone.now())
    assert [p.ref for p in found] == ["so-na-web"]


def test_coupon_promotion_respects_the_scope(channels):
    """Cupom de promoção escopada não ativa fora do canal dela."""
    web, _ = channels
    promo = _promotion("cupom-web", channels=[web])
    Coupon.objects.create(code="SOWEB", promotion=promo, max_uses=0, is_active=True)

    now = timezone.now()
    assert promotion_service.get_coupon_promotion("SOWEB", now, channel_ref="web") is not None
    assert promotion_service.get_coupon_promotion("SOWEB", now, channel_ref="pdv") is None


def test_scope_reaches_display_channels(channels):
    """O ponto da ADR-018 + ADR-019 juntas: a promoção alcança canal de EXIBIÇÃO.

    Antes era impossível anunciar promoção no Google/Meta/menuboard, porque o feed só
    conhecia preço de tabela. Com `commerce_policy="display"` sendo canal como qualquer
    outro, `channels` já o alcança sem campo novo.
    """
    tv = Channel.objects.create(
        ref="tv-cafe",
        name="TV do Café",
        commerce_policy=Channel.CommercePolicy.DISPLAY,
        config={"display": {"format": "", "collections": [], "prices_from": "pdv"}},
    )
    _promotion("na-tv", channels=[tv])

    now = timezone.now()
    assert [p.ref for p in promotion_service.get_active_promotions(now, channel_ref="tv-cafe")] == [
        "na-tv"
    ]
    assert promotion_service.get_active_promotions(now, channel_ref="web") == []


def test_the_discount_modifier_honors_the_scope(channels, product):
    """A prova que importa: o escopo é respeitado onde o desconto é DECIDIDO.

    Sem isto, `channels` seria um campo que a projeção mostra e o preço ignora — e o
    cliente veria um desconto que o carrinho não dá.
    """
    from shopman.shop.models import Shop
    from shopman.shop.services import sessions

    Shop.objects.get_or_create(name="Test Shop")
    web, _ = channels
    _promotion("so-na-web", channels=[web])

    for channel_ref, expect_discount in (("web", True), ("pdv", False)):
        session = sessions.create_session(channel_ref)
        sessions.modify_session(
            session_key=session.session_key,
            channel_ref=channel_ref,
            ops=[
                {"op": "add_line", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1000},
                {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
            ],
        )
        session.refresh_from_db()
        discount_q = int((session.pricing or {}).get("discount", {}).get("total_discount_q") or 0)
        if expect_discount:
            assert discount_q == 100, "a web deveria ter recebido os 10% de R$ 10,00"
        else:
            assert discount_q == 0, "o PDV não deveria ter recebido desconto nenhum"
