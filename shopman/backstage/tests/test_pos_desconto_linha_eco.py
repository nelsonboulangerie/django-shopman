"""O salvar da comanda devolve o preço que cada linha COBRA.

Relato do dono (13/10/2026, no alpha): deu R$ 1,00 de desconto numa linha do PDV
e o total da linha só mudou quando recarregou a página. O desconto manual muda o
preço no SERVIDOR (``DiscountModifier``), e a gravação silenciosa da comanda só
devolvia revisão e autoria: a tela continuava com o ``charged_price_q`` velho até
reabrir a comanda. Este arquivo trava o eco: cada gravação diz, por linha, o que
ela cobra, com os mesmos números que a comanda reaberta mostraria.
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

SAVE_URL = "/api/v1/backstage/pos/tabs/save/"


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    POSTab.objects.create(ref="00000077", label="77")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    product = Product.objects.create(sku="CAFE", name="Café", base_price_q=800, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=listing, product=product, price_q=800)
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="77", actor="test", operator_username="marina")
    return {"client": client, "session": session}


def _intent(session, *, discount: dict | None, revision: str) -> dict:
    return {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "77",
        "tab_session_key": session.session_key,
        "expected_revision": revision,
        "items": [
            {
                "line_id": "L1",
                "sku": "CAFE",
                "name": "Café",
                "qty": 3,
                "unit_price_q": 800,
                **({"discount": discount} if discount else {}),
            }
        ],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": "desconto-linha-eco",
    }


def _save(client, body: dict):
    return client.post(SAVE_URL, data=json.dumps(body), content_type="application/json")


def test_o_salvar_devolve_o_preco_cobrado_da_linha_com_o_desconto_em_reais(balcao):
    client, session = balcao["client"], balcao["session"]
    first = _save(client, _intent(session, discount=None, revision=build_open_tab(session)["revision"]))
    assert first.status_code == 200, first.content
    assert first.json()["line_prices"]["L1"]["charged_price_q"] == 800

    saved = _save(
        client,
        _intent(
            session,
            discount={"type": "fixed", "value": 1, "reason": "cortesia"},
            revision=first.json()["revision"],
        ),
    )

    assert saved.status_code == 200, saved.content
    eco = saved.json()["line_prices"]["L1"]
    # R$ 1,00 por unidade: a linha de 3 cafés cobra R$ 7,00 cada, R$ 21,00 no total.
    assert eco["charged_price_q"] == 700
    assert eco["list_price_q"] == 800
    session.refresh_from_db()
    reaberta = {item["line_id"]: item for item in build_open_tab(session)["items"]}
    assert eco == {key: reaberta["L1"][key] for key in ("charged_price_q", "list_price_q", "pricing_discount")}
