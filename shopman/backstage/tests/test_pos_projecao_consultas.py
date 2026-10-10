"""A leitura do terminal do PDV (``GET pos/``) não cresce com o catálogo nem com as comandas.

É a leitura mais repetida do balcão: abre a tela, volta do Pagamento e é refeita a
cada aviso de comanda (de todas as estações). Medido em 10/10/2026 com o seed: 171
consultas, 119 delas uma por produto (o "vai à cozinha" de cada item lia o produto
de cada linha da coleção) e uma por comanda aberta (as linhas de cada comanda). No
alpha cada consulta custa vários milissegundos, então o número é tempo de tela.

Este arquivo trava que o custo é constante: mais produtos, mais comandas e mais
estações não acrescentam consultas.
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
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.backstage.models import KDSInstance, POSTab
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
    Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return client


def _cresce(*, produtos: int, comandas: int, estacoes: int, inicio: int) -> None:
    listing = Listing.objects.get(ref="pdv")
    for e in range(estacoes):
        collection = Collection.objects.create(ref=f"col-{inicio}-{e}", name=f"Coleção {inicio}-{e}")
        station = KDSInstance.objects.create(ref=f"kds-{inicio}-{e}", name=f"Estação {inicio}-{e}", type="prep")
        station.collections.add(collection)
    collections = list(Collection.objects.all())
    for i in range(produtos):
        product = Product.objects.create(
            sku=f"S{inicio}-{i:03d}", name=f"Produto {inicio}-{i}", base_price_q=1000,
            is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=1000)
        CollectionItem.objects.create(collection=collections[i % len(collections)], product=product, is_primary=True)
    for t in range(comandas):
        ref = f"{inicio}{t:03d}"
        POSTab.objects.create(ref=ref.zfill(8), label=ref)
        session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref=ref, actor="t", operator_username="marina")
        session.update_items([
            {"line_id": f"L{t}-{n}", "sku": f"S{inicio}-{n:03d}", "name": "x", "qty": 1, "unit_price_q": 1000}
            for n in range(2)
        ])


def _consultas(client) -> int:
    client.get(URL)  # aquece caches de processo
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(URL)
    assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


def test_leitura_do_terminal_nao_cresce_com_catalogo_comandas_e_estacoes(balcao):
    _cresce(produtos=3, comandas=1, estacoes=1, inicio=1)
    pouco = _consultas(balcao)
    _cresce(produtos=30, comandas=6, estacoes=3, inicio=2)
    muito = _consultas(balcao)
    print(f"GET pos/: {pouco} consultas (3 produtos, 1 comanda) e {muito} (33 produtos, 7 comandas, 4 estações)")
    assert muito == pouco, (
        f"GET pos/ foi de {pouco} para {muito} consultas com mais produtos/comandas/estações: "
        "voltou a ir ao banco por item"
    )
    assert muito <= TETO_LEITURA_DO_TERMINAL


#: Medido em 10/10/2026 depois da correção (o número impresso acima), com folga
#: pequena. Subir só sabendo o que entrou no caminho.
TETO_LEITURA_DO_TERMINAL = 45
