"""Memo do canal por request: uma leitura de ``Channel`` por request, nunca entre requests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Promotion, Shop
from shopman.shop.request_memo import RequestMemoMiddleware, request_memo_scope
from shopman.shop.services import channel_switch

pytestmark = pytest.mark.django_db


@pytest.fixture
def web():
    Shop.load() or Shop.objects.create(name="Nelson")
    return Channel.objects.create(ref="web", name="Loja online", config={"stock": {"low_stock_threshold": 7}})


def _channel_queries(ctx) -> int:
    return sum('"shop_channel"' in q["sql"] for q in ctx.captured_queries)


def test_without_scope_every_call_reads_the_channel(web):
    with CaptureQueriesContext(connection) as ctx:
        ChannelConfig.for_channel("web")
        ChannelConfig.for_channel("web")
        channel_switch.is_channel_active("web")
    assert _channel_queries(ctx) == 3


def test_inside_a_request_the_channel_is_read_once(web):
    with request_memo_scope(), CaptureQueriesContext(connection) as ctx:
        assert ChannelConfig.for_channel("web").stock.low_stock_threshold == 7
        ChannelConfig.for_channel("web")
        assert channel_switch.is_channel_active("web") is True
        ChannelConfig.for_channel("pdv")  # outro canal: outra leitura
        ChannelConfig.for_channel("pdv")
    assert _channel_queries(ctx) == 2


def test_saving_the_channel_inside_the_request_is_seen(web):
    with request_memo_scope():
        assert ChannelConfig.for_channel("web").stock.low_stock_threshold == 7
        assert channel_switch.is_channel_active("web") is True

        channel_switch.request_switch("web", False, period="open", reason="Loja cheia", actor=None)
        web.refresh_from_db()
        web.config = {**web.config, "stock": {"low_stock_threshold": 3}}
        web.save(update_fields=["config"])

        assert channel_switch.is_channel_active("web") is False
        assert ChannelConfig.for_channel("web").stock.low_stock_threshold == 3


def test_mutating_the_config_does_not_leak_into_the_memo(web):
    web.config = {**web.config, "payment": {"method": ["pix"]}}
    web.save(update_fields=["config"])
    with request_memo_scope():
        first = ChannelConfig.for_channel("web")
        assert first.payment.method == ["pix"]
        first.payment.method.append("cash")
        assert ChannelConfig.for_channel("web").payment.method == ["pix"]


def test_next_request_sees_the_toggle(client, web):
    def ordering_off() -> bool:
        response = client.get("/api/v1/storefront/shell/")
        assert response.status_code == 200
        return any(n["ref"] == "ordering_off" for n in response.json()["shell"]["notices"])

    assert ordering_off() is False
    channel_switch.request_switch("web", False, period="open", reason="Loja cheia", actor=None)
    assert ordering_off() is True


def test_promotion_channel_scope_uses_the_prefetch(web):
    from django.utils import timezone

    now = timezone.now()
    promo = Promotion.objects.create(
        name="Café", type=Promotion.PERCENT, value=10,
        valid_from=now - timezone.timedelta(days=1), valid_until=now + timezone.timedelta(days=1),
    )
    promo.channels.add(web)
    loaded = Promotion.objects.prefetch_related("channels").get(pk=promo.pk)
    with CaptureQueriesContext(connection) as ctx:
        assert loaded.applies_to_channel("web") is True
        assert loaded.applies_to_channel("pdv") is False
    assert ctx.captured_queries == []


# ── Shop.load: a mesma instância no request, relida entre requests ───────────


def _shop_queries(ctx) -> int:
    return sum('"shop_shop"' in q["sql"] for q in ctx.captured_queries)


def test_inside_a_request_the_shop_is_the_same_instance(web):
    from django.core.cache import cache

    from shopman.shop.models.shop import SHOP_CACHE_KEY

    cache.delete(SHOP_CACHE_KEY)
    with request_memo_scope(), CaptureQueriesContext(connection) as ctx:
        first = Shop.load()
        assert Shop.load() is first
        ChannelConfig.for_channel("web")  # a cascata também pergunta pela loja
        assert Shop.load() is first
    assert _shop_queries(ctx) == 1


def test_without_scope_every_call_goes_to_the_cache(web):
    with patch("shopman.shop.models.shop.cache.get", return_value=None) as cache_get:
        assert Shop.load() is not Shop.load()
    assert cache_get.call_count == 2


def test_each_request_reads_the_shop_again(rf, web):
    """Duas passagens pelo middleware: dentro, uma instância; entre elas, a gravada."""
    seen = []

    def view(request):
        seen.append((Shop.load(), Shop.load()))
        return None

    middleware = RequestMemoMiddleware(view)
    middleware(rf.get("/"))

    shop = Shop.objects.get()
    shop.name = "Nelson Boulangerie"
    shop.save()

    middleware(rf.get("/"))

    (first_a, first_b), (second_a, second_b) = seen
    assert first_a is first_b
    assert second_a is second_b
    assert first_a is not second_a
    assert first_a.name == "Nelson"
    assert second_a.name == "Nelson Boulangerie"


def test_saving_the_shop_inside_the_request_is_seen(web):
    with request_memo_scope():
        assert Shop.load().name == "Nelson"
        shop = Shop.objects.get()
        shop.name = "Nelson Boulangerie"
        shop.save()
        assert Shop.load().name == "Nelson Boulangerie"


def test_mutating_the_config_does_not_leak_into_the_shop(web):
    shop = Shop.objects.get()
    shop.defaults = {"payment": {"method": ["pix"]}}
    shop.save()
    with request_memo_scope():
        first = ChannelConfig.for_channel("web")
        assert first.payment.method == ["pix"]
        first.payment.method.append("cash")
        assert ChannelConfig.for_channel("web").payment.method == ["pix"]
        assert Shop.load().defaults == {"payment": {"method": ["pix"]}}
