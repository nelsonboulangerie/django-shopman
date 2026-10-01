"""Memo por request do registro de atributos e do ``ChannelConfig`` montado.

Dois miúdos do caminho quente do storefront (Onda 2c, 01/10):

- o registro de atributos era lido do cache (uma ida ao Redis, com a tupla
  desserializada) a cada ``get_many``/``for_purpose``: 3 vezes por cardápio sem
  sacola, 13 com o trilho de sugestão;
- o recorte de estoque do canal e o aspecto da fila remontavam a cascata inteira
  do ``ChannelConfig`` três vezes por leitura de estoque (e 27 vezes no PUT da
  sacola).

Os dois passam a valer uma vez por request, caem junto com o memo quando o
request grava o que os alimenta, e quem os recebe ganha cópia do que é mutável.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache

from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.config import ChannelConfig
from shopman.shop.models import AttributeDefinition, Channel, Shop
from shopman.shop.request_memo import request_memo_scope
from shopman.shop.services import attributes, waitlist

pytestmark = pytest.mark.django_db


@pytest.fixture
def web():
    Shop.load() or Shop.objects.create(name="Nelson")
    return Channel.objects.create(
        ref="web",
        name="Loja online",
        config={
            "stock": {"safety_margin": 2, "excluded_positions": ["producao"]},
            "waitlist": {"enabled": True, "horizon_days": 2},
        },
    )


class _CountingCache:
    def __init__(self):
        self.reads = 0
        self._get = cache.get

    def get(self, key, *args, **kwargs):
        if key == attributes.CACHE_KEY:
            self.reads += 1
        return self._get(key, *args, **kwargs)


# ── registro de atributos ────────────────────────────────────────────────────


def test_inside_a_request_the_registry_goes_to_the_cache_once():
    counting = _CountingCache()
    with patch.object(cache, "get", counting.get), request_memo_scope():
        attributes.for_purpose("rule")
        attributes.require("sabor")
        attributes.registry()
    assert counting.reads == 1


def test_without_scope_every_read_goes_to_the_cache():
    counting = _CountingCache()
    with patch.object(cache, "get", counting.get):
        attributes.for_purpose("rule")
        attributes.require("sabor")
    assert counting.reads == 2


def test_inside_a_request_the_registry_answers_what_the_cache_answers():
    outside = [(d.ref, d.label, d.options) for d in attributes.registry()]
    with request_memo_scope():
        inside = [(d.ref, d.label, d.options) for d in attributes.registry()]
        assert [d.ref for d in attributes.for_purpose("rule")] == [
            d.ref for d in attributes.registry() if d.serves("rule")
        ]
    assert inside == outside


def test_a_definition_saved_inside_the_request_is_seen():
    with request_memo_scope():
        assert attributes.definition("cor") is None
        AttributeDefinition.objects.create(
            ref="cor", label="Cor", type="choice", options=[{"value": "azul", "label": "Azul"}],
        )
        assert attributes.require("cor").label == "Cor"

        cor = AttributeDefinition.objects.get(ref="cor")
        cor.is_active = False
        cor.save(update_fields=["is_active"])
        assert attributes.definition("cor") is None


def test_the_next_request_reads_the_registry_again():
    with request_memo_scope():
        assert attributes.definition("cor") is None
    AttributeDefinition.objects.create(
        ref="cor", label="Cor", type="choice", options=[{"value": "azul", "label": "Azul"}],
    )
    with request_memo_scope():
        assert attributes.require("cor").label == "Cor"


# ── ChannelConfig montado ────────────────────────────────────────────────────


def test_inside_a_request_the_stock_reads_build_the_config_once(web):
    with patch.object(ChannelConfig, "for_channel", wraps=ChannelConfig.for_channel) as built:
        with request_memo_scope():
            first = stock_adapter.get_channel_scope("web")
            stock_adapter.get_channel_scope("web")
            waitlist.scope_kwargs("web")
            waitlist.config("web")
            waitlist.promise_horizon("web")
            stock_adapter.get_channel_scope("pdv")  # outro canal: outra montagem
    assert built.call_count == 2
    assert first["safety_margin"] == 2
    assert first["excluded_positions"] == ["producao"]


def test_without_scope_every_read_builds_the_config(web):
    with patch.object(ChannelConfig, "for_channel", wraps=ChannelConfig.for_channel) as built:
        stock_adapter.get_channel_scope("web")
        waitlist.config("web")
    assert built.call_count == 2


def test_inside_a_request_the_answers_are_the_ones_built_from_scratch(web):
    expected_scope = stock_adapter.get_channel_scope("web")
    expected_waitlist = waitlist.config("web")
    expected_kwargs = waitlist.scope_kwargs("web")
    with request_memo_scope():
        for _ in range(2):
            assert stock_adapter.get_channel_scope("web") == expected_scope
            assert waitlist.config("web") == expected_waitlist
            assert waitlist.scope_kwargs("web") == expected_kwargs
            assert waitlist.is_enabled("web") is True


def test_mutating_what_comes_back_does_not_leak_into_the_request(web):
    with request_memo_scope():
        scope = stock_adapter.get_channel_scope("web")
        scope["excluded_positions"].append("vitrine")
        scope["safety_margin"] = 99
        cfg = waitlist.config("web")
        cfg.enabled = False

        assert stock_adapter.get_channel_scope("web")["excluded_positions"] == ["producao"]
        assert stock_adapter.get_channel_scope("web")["safety_margin"] == 2
        assert waitlist.config("web").enabled is True
        assert waitlist.is_enabled("web") is True


def test_saving_the_channel_inside_the_request_is_seen_by_the_stock_reads(web):
    with request_memo_scope():
        assert stock_adapter.get_channel_scope("web")["safety_margin"] == 2
        assert waitlist.is_enabled("web") is True

        web.config = {**web.config, "stock": {"safety_margin": 5}, "waitlist": {"enabled": False}}
        web.save(update_fields=["config"])

        assert stock_adapter.get_channel_scope("web")["safety_margin"] == 5
        assert waitlist.is_enabled("web") is False


def test_saving_the_shop_inside_the_request_is_seen_by_the_stock_reads(web):
    web.config = {}
    web.save(update_fields=["config"])
    with request_memo_scope():
        assert stock_adapter.get_channel_scope("web")["safety_margin"] == ChannelConfig().stock.safety_margin

        shop = Shop.load()
        shop.defaults = {**(shop.defaults or {}), "stock": {"safety_margin": 4}}
        shop.save(update_fields=["defaults"])

        assert stock_adapter.get_channel_scope("web")["safety_margin"] == 4
