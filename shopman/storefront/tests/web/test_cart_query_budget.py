"""Orçamento de consultas da sacola: o custo não cresce com o número de itens.

Com sacola, ``home/``, ``menu/`` e ``shell/`` faziam ~120 a ~150 consultas a
mais que sem ela (medido no seed, 30/09), e quase tudo por item ou por produto:

- ``keywords.names()`` no motor de sugestão — no django-taggit 6.1 é um
  ``values_list`` que ignora o ``prefetch_related("keywords")``: uma consulta
  por produto do pool e da sacola;
- uma consulta de ``Hold`` por linha para saber se ela está em fila;
- três leituras de ``Product`` para os mesmos SKUs, e os produtos da sacola
  lidos duas vezes pelo motor de sugestão.

Este arquivo trava o que ficou: a sacola com 1 item e com 5 itens fazem o MESMO
número de consultas, e há um teto absoluto para a sacola e para o que ela
acrescenta a ``menu/`` e ``home/``.

Desde 01/10 (F4b) a disponibilidade é lida uma vez por request GET
(``request_memo.stock_reads_scope``): o trilho de sugestão lê candidatos e
sacola numa leitura só do Stockman, e as linhas da sacola, o cardápio e os
destaques da home reaproveitam o que já foi lido. Por isso, em ``home/``, a
sacola de 5 itens pode custar MENOS que a de 1: os pães dela são os mesmos dos
destaques, que já não vão ao Stockman de novo. A trava é "não cresce".

⚠️ O estoque aqui é todo de HOJE de propósito. A disponibilidade com fornada
futura (``waitlist.next_batch_availability_for_skus``) ainda faz uma leitura por
DATA de fornada distinta; ela é do caminho do catálogo, não da sacola, e tem
frente própria.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, ListingItem, Product

from shopman.shop.models import Channel, ProductAffinity
from shopman.shop.request_memo import request_memo_scope, stock_reads_scope
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import build_cart

pytestmark = pytest.mark.django_db

PAES = [f"PAO-{i}" for i in range(1, 6)]
BEBIDAS = ["CAFE", "SUCO", "CHA"]

#: Tetos absolutos. Medidos neste arquivo em 01/10/2026 (F4b): a sacola faz 31
#: consultas (39 antes, com uma leitura do Stockman para as linhas e outra para
#: os candidatos do trilho; 44 antes da F3) e acrescenta 27 a ``menu/`` e 37 a
#: ``home/`` com 1 item (eram 45 nos dois). A folga é para mudança honesta;
#: estourar quer dizer que voltou a haver leitura por item ou por produto, ou
#: que a sacola e o trilho voltaram a ler o estoque cada um por si — procure o
#: laço antes de subir o número.
CART_PROJECTION_CEILING = 34
CART_OVERHEAD_CEILING = 40
#: O PUT de uma linha numa sacola de 2 itens. Medido em 01/10/2026 (Onda 2c):
#: 88 consultas; eram 96, com a resposta lendo o estoque duas vezes (linhas e
#: trilho de sugestão). Sob a transação do teste o ``on_commit`` não roda, então
#: a observação de falta na prateleira (backstage) fica fora desta conta.
#: 02/10/2026 (escolhas no produto): +1, a leitura das linhas da sacola no
#: ajuste. A reserva é por SKU e o mesmo SKU pode ter duas linhas (Croque com e
#: sem ovo); mudar uma precisa somar as outras para não soltar a reserva delas.
PUT_CEILING = 91


@pytest.fixture
def catalog(listing):
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    Channel.objects.get_or_create(ref=STOREFRONT_CHANNEL_REF, defaults={"name": "Loja Online"})
    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    paes = Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=1)
    bebidas = Collection.objects.create(ref="bebidas", name="Bebidas", is_active=True, sort_order=2)

    for index, sku in enumerate(PAES + BEBIDAS):
        is_bebida = sku in BEBIDAS
        product = Product.objects.create(
            sku=sku,
            name=sku.title(),
            base_price_q=500 + index * 100,
            is_published=True,
            is_sellable=True,
            availability_policy="demand_ok" if is_bebida else "planned_ok",
        )
        product.keywords.add("bebida" if is_bebida else "pao", f"tag-{index}")
        CollectionItem.objects.create(
            collection=bebidas if is_bebida else paes, product=product, sort_order=index,
        )
        ListingItem.objects.create(
            listing=listing, product=product, price_q=product.base_price_q,
            is_published=True, is_sellable=True,
        )
        if not is_bebida:
            stock.receive(
                quantity=Decimal("50"), sku=sku, position=position,
                target_date=date.today(), reason="orçamento da sacola",
            )

    # O histórico liga cada pão às bebidas: é o que põe o trilho de sugestão
    # para trabalhar inteiro (candidatos, portões, pontuação) nas duas sacolas.
    for pao in PAES:
        for bebida in BEBIDAS:
            ProductAffinity.objects.create(
                sku_a=pao, sku_b=bebida, together_count=10, score=10.0,
                lift=2.0, window_days=365, computed_at=timezone.now(),
            )


def _client_with_cart(skus: list[str]) -> Client:
    client = Client()
    for sku in skus:
        response = client.put(
            f"/api/v1/cart/skus/{sku}/",
            data=json.dumps({"qty": 1}),
            content_type="application/json",
        )
        assert response.status_code in (200, 201), (sku, response.status_code, response.content[:300])
    return client


def _cart_queries(client: Client) -> tuple[int, object]:
    request = RequestFactory().get("/sacola/")
    request.session = client.session  # type: ignore[attr-defined]
    build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)  # aquece caches do processo
    # Os memos que o ``RequestMemoMiddleware`` abre num GET: a sacola é medida
    # como o request a monta.
    with request_memo_scope(), stock_reads_scope(), CaptureQueriesContext(connection) as ctx:
        projection = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
    return len(ctx.captured_queries), projection


def _endpoint_queries(client: Client, path: str) -> int:
    client.get(path)  # aquece caches do processo
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return len(ctx.captured_queries)


def test_cart_projection_costs_the_same_with_one_or_five_items(catalog):
    one, one_projection = _cart_queries(_client_with_cart(PAES[:1]))
    five, five_projection = _cart_queries(_client_with_cart(PAES))

    assert len(one_projection.items) == 1
    assert len(five_projection.items) == 5
    # O trilho de sugestão rodou nas duas: sem ele o teste mediria a sacola sem
    # a parte que mais custava.
    assert one_projection.upsell is not None
    assert five_projection.upsell is not None

    assert five == one, f"sacola com 5 itens fez {five} consultas; com 1 item, {one}"
    assert one <= CART_PROJECTION_CEILING, f"sacola fez {one} consultas (teto {CART_PROJECTION_CEILING})"


@pytest.mark.parametrize("path", ["/api/v1/storefront/menu/", "/api/v1/storefront/home/"])
def test_cart_adds_a_bounded_cost_to_menu_and_home(catalog, path):
    without_cart = _endpoint_queries(Client(), path)
    with_one = _endpoint_queries(_client_with_cart(PAES[:1]), path)
    with_five = _endpoint_queries(_client_with_cart(PAES), path)

    assert with_five <= with_one, f"{path}: 5 itens fizeram {with_five} consultas; 1 item, {with_one}"
    overhead = with_one - without_cart
    assert overhead <= CART_OVERHEAD_CEILING, (
        f"{path}: a sacola acrescentou {overhead} consultas (teto {CART_OVERHEAD_CEILING})"
    )


def test_put_answers_with_the_state_after_the_mutation(catalog):
    """O PUT muda a sacola e responde com ela: nada do que ele devolve é leitura de antes.

    Request que muta não abre o memo de estoque durante a mutação (só GET/HEAD
    abrem no middleware). A resposta abre o memo DEPOIS que a mutação voltou
    (``_cart_payload_after_mutation``), então toda leitura dela é posterior à
    escrita, e a resposta do PUT é o que um GET logo depois vê.
    """
    client = _client_with_cart(PAES[:2])
    for qty in (4, 1):
        put = client.put(
            f"/api/v1/cart/skus/{PAES[0]}/",
            data=json.dumps({"qty": qty}),
            content_type="application/json",
        )
        assert put.status_code == 200, put.content[:300]
        fresh = client.get("/api/v1/storefront/cart/")
        assert fresh.status_code == 200
        assert put.json()["cart"] == fresh.json()["cart"]
        line = next(line for line in put.json()["cart"]["items"] if line["sku"] == PAES[0])
        assert line["qty"] == qty


def test_put_reads_the_stock_once_to_answer(catalog):
    """Depois da mutação, a sacola e o trilho de sugestão dividem UMA leitura do Stockman.

    Antes (01/10, Onda 2c) a resposta do PUT lia o estoque duas vezes: o trilho
    lia candidatos e sacola, e as linhas da sacola liam os mesmos SKUs de novo.
    A leitura da própria mutação (a reserva) é anterior à escrita e não entra
    nesta conta: ela continua indo ao banco, sempre.
    """
    from unittest.mock import patch

    from shopman.stockman.services import availability as stockman_availability

    client = _client_with_cart(PAES[:2])
    real = stockman_availability.availability_for_skus_on_dates
    with (
        patch.object(stockman_availability, "availability_for_skus_on_dates", wraps=real) as reads,
        CaptureQueriesContext(connection) as ctx,
    ):
        put = client.put(
            f"/api/v1/cart/skus/{PAES[0]}/",
            data=json.dumps({"qty": 3}),
            content_type="application/json",
        )
    assert put.status_code == 200, put.content[:300]
    assert put.json()["cart"]["upsell"] is not None
    assert reads.call_count == 1, f"a resposta do PUT leu o estoque {reads.call_count} vezes"
    queries = len(ctx.captured_queries)
    assert queries <= PUT_CEILING, f"o PUT fez {queries} consultas (teto {PUT_CEILING})"
