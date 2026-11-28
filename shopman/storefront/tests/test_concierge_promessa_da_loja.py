"""A Concierge diz QUANDO fica pronto com a mesma frase da loja (issue #3267, parte 3).

O item que espera fornada aparecia na conversa como "Lista de espera", sem dia
nem hora, enquanto o cardápio da loja já dizia "Fica pronto amanhã, quarta, a
partir das 15h" (``presentation/promise``, sobre ``shop/projections/ready_promise``).
A regra é a da loja (``tileBadge`` do storefront-nuxt): o item ``planned_ok``
fala a promessa do servidor; "Lista de espera" só sobra quando a promessa não veio.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from shopman.storefront.concierge import tools
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

SP = ZoneInfo("America/Sao_Paulo")
CHANNEL = "whatsapp"
SKU = "TABAT"
# Terça, 17/11/2026, 10h: casa aberta; a fornada da Tabatière é a de amanhã, às 15h.
TUESDAY_10H = datetime(2026, 11, 17, 10, 0, tzinfo=SP)


def _frozen():
    return patch("django.utils.timezone.now", return_value=TUESDAY_10H.astimezone(ZoneInfo("UTC")))


def _world() -> ToolContext:
    """Tabatière sem pronto hoje e com fornada planejada para amanhã, no canal da Concierge."""
    from django.core.cache import cache
    from shopman.offerman.models import Listing, ListingItem, Product
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    from shopman.shop.models import Channel, Conversation, Shop

    cache.clear()
    shop = Shop.load() or Shop.objects.create(name="Casa")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "18:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
    }
    shop.save(update_fields=["opening_hours"])
    Channel.objects.update_or_create(
        ref=CHANNEL,
        defaults={"name": "WhatsApp", "config": {"waitlist": {"enabled": True, "horizon_days": 3}}},
    )
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    listing, _ = Listing.objects.get_or_create(ref=CHANNEL, defaults={"name": "WhatsApp", "is_active": True})
    product = Product.objects.create(
        sku=SKU,
        name="Tabatière",
        base_price_q=1600,
        is_published=True,
        is_sellable=True,
        metadata={"ready_from": "15:00"},
    )
    ListingItem.objects.create(listing=listing, product=product, price_q=1600)
    stock.receive(
        Decimal("10"),
        sku=SKU,
        position=vitrine,
        target_date=TUESDAY_10H.date() + timedelta(days=1),
        reason="fornada de amanhã",
    )
    conversation = Conversation.objects.create(phone="+5543981234567", channel_ref=CHANNEL)
    return ToolContext(conversation=conversation, channel_ref=CHANNEL, customer_text="tem tabatière?")


def _search(ctx: ToolContext) -> dict:
    """A leitura da busca, sem o portão de autoridade do turno (coberto em ``test_concierge_engine``)."""
    return tools.search_storefront.__wrapped__(ctx, "tabatière")


@pytest.mark.channels(CHANNEL)
def test_fornada_de_amanha_fala_a_promessa_da_loja():
    with _frozen():
        ctx = _world()
        result = _search(ctx)

    [item] = result["items"]
    assert item["availability"] == "planned_ok"
    reply = tools.render_result("search_storefront", result)
    assert "Disponível amanhã, quarta, a partir das 15h" in reply
    assert "Lista de espera" not in reply
    assert "—" not in reply


@pytest.mark.channels(CHANNEL)
def test_sem_promessa_continua_lista_de_espera(monkeypatch):
    """Prontidão que não pôde ser apurada: não há promessa, e a frase é a da loja sem ela."""
    from shopman.shop.projections.ready_promise import PromiseFacts

    monkeypatch.setattr(
        "shopman.storefront.presentation.catalog.read_promise_facts",
        lambda skus, **kwargs: PromiseFacts(
            now=TUESDAY_10H, today=TUESDAY_10H.date(), readiness_unavailable=True,
        ),
    )
    with _frozen():
        ctx = _world()
        result = _search(ctx)

    [item] = result["items"]
    assert item["availability"] == "planned_ok"
    reply = tools.render_result("search_storefront", result)
    assert "Lista de espera" in reply
    assert "a partir das" not in reply
