"""A grade do PDV ouve o estoque (WP-E4, EXCELENCIA-PDV P1-2).

O motor de disponibilidade publica ``stock-update`` no canal ``stock-<canal>`` a
cada reserva e movimento, mas o PDV não tinha porta para ele: o selo "Esgotado"
só mudava quando o próprio balcão vendia ou salvava, com o cabeçalho dizendo
"Ao vivo". Agora:

- ``events/stock/`` entrega o canal do PDV a quem opera o balcão
  (``cashman.operate_pos``), e a ninguém mais (fronteira F5, #2562);
- ``GET pos/?only=availability`` devolve só os selos da grade, iguais aos da
  projeção inteira e por uma fração do custo.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.http import HttpResponse
from django.test.utils import CaptureQueriesContext
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.handlers import _sse_emitters
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/pos/"
STREAM = "/events/stock/"


def _operate_pos():
    return Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos")


@pytest.fixture
def grade():
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref=POS_CHANNEL_REF, name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    listing = Listing.objects.create(ref=POS_CHANNEL_REF, name="PDV", is_active=True)
    for i in range(12):
        product = Product.objects.create(
            sku=f"S{i:02d}", name=f"Produto {i}", base_price_q=1000, is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=1000)
    # Fora da grade: despublicado no canal não aparece nem no selo.
    oculto = Product.objects.create(sku="OCULTO", name="Oculto", base_price_q=1000, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=listing, product=oculto, price_q=1000, is_published=False)


@pytest.fixture
def balcao(client, grade):
    operator = get_user_model().objects.create_user(username="fran", password="x", is_staff=True)
    operator.user_permissions.add(_operate_pos())
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return client


def _ultima_unidade_vendida(sold: set[str]):
    """O stockman responde: os SKUs de ``sold`` sem saldo, o resto com dez."""

    def availability(skus, *, channel_ref, target_date=None):
        sem = {"is_tracked": True, "total_promisable": Decimal("0"), "availability_policy": "stock_only"}
        com = {"is_tracked": True, "total_promisable": Decimal("10"), "available": Decimal("10")}
        return {sku: (sem if sku in sold else com) for sku in skus}

    return mock.patch("shopman.shop.projections.catalog_context.availability_for_skus", side_effect=availability)


def _get(client, url):
    client.get(url)  # aquece caches de processo
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, response.content
    return response.json(), len(ctx.captured_queries)


def test_os_selos_sozinhos_sao_os_mesmos_da_projecao_e_custam_uma_fracao(balcao):
    with _ultima_unidade_vendida({"S03"}):
        inteira, consultas_inteira = _get(balcao, URL)
        selos, consultas_selos = _get(balcao, f"{URL}?only=availability")

    assert set(selos) == {"availability"}
    da_projecao = {
        p["sku"]: {
            "sku": p["sku"], "sold_out": p["sold_out"], "sold_out_reason": p["sold_out_reason"],
            "units_left": p["units_left"],
        }
        for p in inteira["pos"]["products"]
    }
    assert {entry["sku"]: entry for entry in selos["availability"]} == da_projecao
    assert da_projecao["S03"]["sold_out"] is True
    assert "OCULTO" not in da_projecao
    print(f"GET pos/: {consultas_inteira} consultas; ?only=availability: {consultas_selos}")
    assert consultas_selos * 3 <= consultas_inteira


def test_o_selo_vira_quando_o_estoque_vira(balcao):
    with _ultima_unidade_vendida(set()):
        antes, _ = _get(balcao, f"{URL}?only=availability")
    with _ultima_unidade_vendida({"S07"}):
        depois, _ = _get(balcao, f"{URL}?only=availability")

    assert not any(entry["sold_out"] for entry in antes["availability"])
    assert [entry["sku"] for entry in depois["availability"] if entry["sold_out"]] == ["S07"]


def test_os_selos_respeitam_o_mesmo_portao(client, balcao):
    client.logout()
    response = client.get(f"{URL}?only=availability")
    assert response.status_code in (401, 403)


# ── A porta do canal de estoque (F5) ─────────────────────────────────


def _stream(client):
    with mock.patch("shopman.backstage.urls.eventstream_view", return_value=HttpResponse("ok")) as view:
        response = client.get(STREAM)
    return response, view


def test_quem_opera_o_balcao_assina_o_estoque_do_canal_do_pdv(client):
    operator = get_user_model().objects.create_user(username="fran", password="x", is_staff=True)
    operator.user_permissions.add(_operate_pos())
    client.force_login(operator)

    response, view = _stream(client)

    assert response.status_code == 200
    view.assert_called_once()
    assert view.call_args.kwargs == {"channels": [f"stock-{POS_CHANNEL_REF}"]}


@pytest.mark.parametrize("perfil", ["anonimo", "staff_sem_pdv"])
def test_sem_a_permissao_do_pdv_a_porta_nao_existe(client, perfil):
    if perfil == "staff_sem_pdv":
        client.force_login(get_user_model().objects.create_user(username="cozinha", password="x", is_staff=True))

    response, view = _stream(client)

    # 404 antes de delegar: o EventSource falha limpo e a tela segue no poll.
    assert response.status_code == 404
    view.assert_not_called()


def test_o_estoque_que_mexe_avisa_o_canal_do_pdv(grade):
    with mock.patch("django_eventstream.send_event") as send:
        _sse_emitters._publish_for_sku("S05", event_type="stock-update", payload={"sku": "S05"})

    assert mock.call(f"stock-{POS_CHANNEL_REF}", "stock-update", {"sku": "S05"}) in send.call_args_list
