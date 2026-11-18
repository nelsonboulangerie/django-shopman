"""O dia que vai ao Google é o dia que a Loja promete (WP-G14a, issue #2652).

O Google cruza o inventário local (``pickupSla``) com a página do produto; a
divergência sozinha nega a "retirada no mesmo dia". Aqui, para os mesmos SKUs e o
mesmo instante, o dia do ``pickupSla`` de cada item é comparado com o dia da
promessa que o cardápio e a página do produto mostram, antes e depois do corte.
"""

from __future__ import annotations

from datetime import date

import pytest

from shopman.storefront.tests.test_ready_promise import CLOCKS, QA_SKUS, _frozen, _promises_from_api, _qa_world

#: O ``pickupSla`` esperado em cada momento do perfil qa (relógio de São Paulo).
EXPECTED_SLA = {
    # terça 10h: o Melonpan está pronto agora; a Tabatière, na fornada de amanhã.
    "aberta": {"MELON": "SAME_DAY", "TABAT": "NEXT_DAY", "FENDU": None, "MDLN": None},
    # terça 19h, depois do corte: o Melonpan também só amanhã.
    "fechada": {"MELON": "NEXT_DAY", "TABAT": "NEXT_DAY", "FENDU": None, "MDLN": None},
    # domingo, dia sem expediente: os dois na segunda.
    "domingo": {"MELON": "NEXT_DAY", "TABAT": "NEXT_DAY", "FENDU": None, "MDLN": None},
}


def _google_channel():
    from shopman.offerman.models import Collection, CollectionItem, Product

    from shopman.shop.tests._display import display_channel

    vitrine = Collection.objects.create(ref="vitrine-google", name="Vitrine", is_active=True)
    for product in Product.objects.filter(sku__in=QA_SKUS):
        product.image_url = f"https://cdn.test/{product.sku}.jpg"
        product.save(update_fields=["image_url"])
        CollectionItem.objects.create(collection=vitrine, product=product)
    display_channel("google", "Google", collections=[vitrine.ref], fmt="google_merchant", prices_from="web")


@pytest.mark.django_db
@pytest.mark.channels("web")
@pytest.mark.parametrize("moment", list(CLOCKS))
def test_o_pickup_sla_de_cada_item_e_o_dia_da_promessa_da_loja(moment, settings):
    from django.core.cache import cache
    from django.test import Client

    from shopman.shop.adapters.catalog_projection_google import build_local_inventory, pickup_sla
    from shopman.shop.services import display_catalog

    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://www.loja.test"
    cache.clear()
    with _frozen(CLOCKS[moment]):
        _qa_world()
        _google_channel()
        today = CLOCKS[moment].date()
        promises = _promises_from_api(Client())
        items = {item.sku: item for item in display_catalog.display_items("google")}

        for sku in QA_SKUS:
            promise = promises[sku]
            item = items[sku]
            if promise is None:
                assert item.ready_in_days is None, sku
            else:
                assert item.ready_in_days == (date.fromisoformat(promise["date"]) - today).days, sku
            assert pickup_sla(item.ready_in_days) == EXPECTED_SLA[moment][sku], sku

        sent = build_local_inventory(items["MELON"], {"store_code": "123"})["localInventoryAttributes"]
        assert sent["pickupSla"] == EXPECTED_SLA[moment]["MELON"]


#: O contrato do campo ``promise`` que a API da Loja publica (card, produto e
#: sacola). O WP-L02 consome exatamente estas chaves; mover o fato para o
#: ``shop`` (WP-G14a) não pode mudar nenhuma.
PROMISE_KEYS = {"kind", "date", "ready_at", "day_label", "text"}


@pytest.mark.django_db
@pytest.mark.channels("web")
def test_o_contrato_do_campo_promise_da_api_fica_identico():
    from django.core.cache import cache
    from django.test import Client

    from shopman.storefront.tests.test_ready_promise import _cart_promise

    cache.clear()
    with _frozen(CLOCKS["aberta"]):
        _qa_world()
        promises = _promises_from_api(Client())  # card e produto, iguais entre si
        assert promises["MELON"] is not None and promises["TABAT"] is not None
        for sku in ("MELON", "TABAT"):
            promise = promises[sku]
            assert set(promise) == PROMISE_KEYS, sku
            assert all(isinstance(promise[key], str) for key in PROMISE_KEYS), sku
            date.fromisoformat(promise["date"])
            assert len(promise["ready_at"]) == 5 and promise["ready_at"][2] == ":", sku
            assert set(_cart_promise(Client(), sku)) == PROMISE_KEYS, sku
