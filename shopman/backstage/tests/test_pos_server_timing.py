"""As idas do PDV que o operador espera dizem onde foi o tempo (``Server-Timing``).

Em 10/10/2026 o dono esperou 24 s pelo total no alpha, e não havia como ver, de
fora, quanto era servidor, banco ou rede: o ``Server-Timing`` existia só nas
leituras da loja. Agora a leitura do terminal, o abrir e o salvar da comanda, a
revisão e o fechamento da venda carimbam o mesmo formato (``projection``, ``db``,
``connect``, ``cache``, ``gc``), e o BFF dos apps de operador o repassa.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    POSTab.objects.create(ref="00000077", label="77")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    product = Product.objects.create(sku="PAO", name="Pão", base_price_q=1000, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=listing, product=product, price_q=1000)
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="77", actor="t", operator_username="marina")
    return client, session


def _stages(response) -> set[str]:
    header = response.headers.get("Server-Timing", "")
    return {part.split(";")[0].strip() for part in header.split(",") if part.strip()}


def _intent(session) -> dict:
    return {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "77",
        "tab_session_key": session.session_key,
        "expected_revision": build_open_tab(session)["revision"],
        "items": [{"line_id": "L1", "sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 1000}],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": "server-timing-1",
    }


def test_idas_do_pdv_carimbam_server_timing(balcao):
    client, session = balcao
    esperados = {"projection", "db", "connect", "cache", "gc"}

    leitura = client.get("/api/v1/backstage/pos/")
    assert leitura.status_code == 200
    assert esperados <= _stages(leitura)

    aberta = client.post("/api/v1/backstage/pos/tabs/77/open/", "{}", content_type="application/json")
    assert aberta.status_code == 200
    assert esperados <= _stages(aberta)

    session.refresh_from_db()
    salvo = client.post("/api/v1/backstage/pos/tabs/save/", json.dumps(_intent(session)), content_type="application/json")
    assert salvo.status_code == 200, salvo.content
    assert esperados <= _stages(salvo)

    revisao = client.post(
        "/api/v1/backstage/pos/sale/review/", json.dumps(_intent(session)), content_type="application/json",
    )
    assert revisao.status_code == 200, revisao.content
    assert esperados <= _stages(revisao)
