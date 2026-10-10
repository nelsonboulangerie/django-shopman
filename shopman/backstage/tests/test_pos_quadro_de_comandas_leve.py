"""O aviso de comanda relê só o quadro (``GET pos/?only=tabs``), não a projeção inteira.

Cada salvar de comanda, em qualquer balcão, avisa todas as estações pelo SSE
``backstage-tabs-update`` (inclusive o autosave de quem está vendendo, a cada
pausa). Cada estação relia a projeção inteira do terminal: catálogo com
disponibilidade, turno, operadores. Com três ou quatro dispositivos abertos, era
CPU do servidor na frente da próxima ida de quem estava no balcão.

Trava: o quadro sozinho é o mesmo da projeção inteira, e custa uma fração dela.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.models import POSTab
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/pos/"


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    for i in range(12):
        product = Product.objects.create(
            sku=f"S{i:02d}", name=f"Produto {i}", base_price_q=1000, is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=1000)
    for t in range(3):
        POSTab.objects.create(ref=f"0000010{t}", label=f"10{t}")
        session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref=f"10{t}", actor="t", operator_username="marina")
        session.update_items([{"line_id": f"L{t}", "sku": "S00", "name": "x", "qty": 1, "unit_price_q": 1000}])
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return client


def _get(client, url):
    client.get(url)  # aquece caches de processo
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, response.content
    return response.json(), len(ctx.captured_queries)


def test_o_quadro_sozinho_e_o_mesmo_da_projecao_e_custa_uma_fracao(balcao):
    inteira, consultas_inteira = _get(balcao, URL)
    quadro, consultas_quadro = _get(balcao, f"{URL}?only=tabs")

    assert set(quadro) == {"tabs"}
    assert quadro["tabs"] == inteira["tabs"]
    print(f"GET pos/: {consultas_inteira} consultas; ?only=tabs: {consultas_quadro}")
    assert consultas_quadro <= 12
    assert consultas_quadro * 3 <= consultas_inteira


def test_o_quadro_sozinho_respeita_o_mesmo_portao(client, balcao):
    client.logout()
    response = client.get(f"{URL}?only=tabs")
    assert response.status_code in (401, 403)
