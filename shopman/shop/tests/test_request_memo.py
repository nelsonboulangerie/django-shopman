"""Memo do canal por request: uma leitura de ``Channel`` por request, nunca entre requests."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Promotion, Shop
from shopman.shop.request_memo import request_memo_scope
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
