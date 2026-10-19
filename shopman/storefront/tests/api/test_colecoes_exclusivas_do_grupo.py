"""Coleções exclusivas do grupo: o cardápio mostra a coleção só ao membro identificado.

Medido em 19/10/2026: o Gestor gravava ``PriceTierAdvantage(kind="exclusive_collections")``
com ``collection_refs`` e nenhum consumidor lia; a coleção "exclusiva" aparecia para
todo mundo. Agora o cardápio (rota privada e gêmea pública), a página da coleção, a
home e o catálogo público (``/api/v1/catalog/``) escondem a coleção de quem não é do
grupo, anônimo incluído. O cardápio anônimo continua o mesmo para todos (cacheável na
borda), e a resolução é UMA consulta, qualquer que seja o tamanho do cardápio.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from shopman.guestman.models import Customer, PriceTier, PriceTierAdvantage
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.storefront.tests.api.test_account_summary import _login_as_customer
from shopman.storefront.tests.web.test_catalog_nplus1_measure import _seed_catalog

pytestmark = pytest.mark.django_db

DOCES = {"CROISSANT", "PAO-CHOCOLATE", "BOLO-CENOURA", "BRIGADEIRO", "SONHO"}


@pytest.fixture
def cardapio():
    _seed_catalog()
    alianca = PriceTier.objects.create(ref="alianca", name="Aliança Francesa")
    PriceTierAdvantage.objects.create(
        tier=alianca, kind=PriceTierAdvantage.Kind.EXCLUSIVE_COLLECTIONS, config={"collection_refs": ["doces"]},
    )
    ana = Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990001")
    ana.price_tiers.set([alianca])
    beto = Customer.objects.create(ref="CLI-BETO", first_name="Beto", phone="+5543999990002")
    return ana, beto


def _catalog(client: Client, path: str = "/api/v1/storefront/catalog/"):
    response = client.get(path)
    assert response.status_code == 200, response.content[:300]
    return response.json()["catalog"]


def _category_refs(catalog) -> set[str]:
    return {c["ref"] for c in catalog["categories"]}


def _skus(catalog) -> set[str]:
    return {item["sku"] for item in catalog["items"]}


def test_anonimo_nao_ve_a_colecao_exclusiva(cardapio):
    catalog = _catalog(Client())

    assert "doces" not in _category_refs(catalog)
    assert not (_skus(catalog) & DOCES)
    assert "doces" not in {s["ref"] for s in catalog["sections"]}


def test_membro_identificado_ve_a_colecao_do_grupo(cardapio):
    ana, _ = cardapio
    client = Client()
    _login_as_customer(client, ana)

    catalog = _catalog(client)

    assert "doces" in _category_refs(catalog)
    assert DOCES <= _skus(catalog)


def test_quem_nao_e_do_grupo_nao_ve(cardapio):
    _, beto = cardapio
    client = Client()
    _login_as_customer(client, beto)

    catalog = _catalog(client)

    assert "doces" not in _category_refs(catalog)
    assert not (_skus(catalog) & DOCES)


def test_vantagem_desligada_devolve_a_colecao_a_todos(cardapio):
    PriceTierAdvantage.objects.update(is_active=False)
    assert "doces" in _category_refs(_catalog(Client()))


def test_pagina_da_colecao_e_404_para_quem_nao_e_do_grupo(cardapio):
    ana, beto = cardapio
    assert Client().get("/api/v1/storefront/catalog/doces/").status_code == 404

    outsider = Client()
    _login_as_customer(outsider, beto)
    assert outsider.get("/api/v1/storefront/catalog/doces/").status_code == 404

    member = Client()
    _login_as_customer(member, ana)
    assert DOCES <= _skus(_catalog(member, "/api/v1/storefront/catalog/doces/"))


def test_produto_tambem_numa_colecao_comum_continua_por_ela(cardapio):
    CollectionItem.objects.create(
        collection=Collection.objects.get(ref="paes"), product=Product.objects.get(sku="CROISSANT"), sort_order=99,
    )

    catalog = _catalog(Client())

    assert "CROISSANT" in _skus(catalog)
    paes = next(s for s in catalog["sections"] if s["ref"] == "paes")
    assert "CROISSANT" in paes["skus"]


def test_gemea_publica_e_o_cardapio_anonimo_e_segue_cacheavel(cardapio):
    response = Client().get("/api/v1/storefront/public/catalog/")

    assert response.status_code == 200
    assert response["Cache-Control"].startswith("public")
    catalog = response.json()["catalog"]
    assert "doces" not in _category_refs(catalog)
    assert Client().get("/api/v1/storefront/public/catalog/doces/").status_code == 404


def test_catalogo_publico_da_api_esconde_a_colecao_exclusiva(cardapio):
    client = Client()

    collections = {row["ref"] for row in client.get("/api/v1/catalog/collections/").json()}
    assert "doces" not in collections and "paes" in collections

    body = client.get("/api/v1/catalog/products/").json()
    rows = body["results"] if isinstance(body, dict) else body
    assert not ({row["sku"] for row in rows} & DOCES)

    filtered = client.get("/api/v1/catalog/products/?collection=doces").json()
    assert (filtered["results"] if isinstance(filtered, dict) else filtered) == []


def _grow_exclusive(n: int) -> None:
    listing = Listing.objects.get(ref="web")
    doces = Collection.objects.get(ref="doces")
    for i in range(n):
        p = Product.objects.create(sku=f"EXTRA-{i}", name=f"Extra {i}", base_price_q=500, is_published=True, is_sellable=True)
        CollectionItem.objects.create(collection=doces, product=p, sort_order=100 + i)
        ListingItem.objects.create(listing=listing, product=p, price_q=500, is_published=True, is_sellable=True)
    extra = Collection.objects.create(ref=f"extra-{n}", name=f"Extra {n}", is_active=True, sort_order=50)
    PriceTierAdvantage.objects.filter(tier__ref="alianca").update(config={"collection_refs": ["doces", extra.ref]})


def _count(client: Client) -> int:
    client.get("/api/v1/storefront/catalog/")  # aquece caches de processo
    with CaptureQueriesContext(connection) as ctx:
        assert client.get("/api/v1/storefront/catalog/").status_code == 200
    return len(ctx.captured_queries)


def test_resolucao_em_lote_o_cardapio_do_membro_nao_cresce_com_a_colecao(cardapio):
    ana, _ = cardapio
    member = Client()
    _login_as_customer(member, ana)

    before = _count(member)
    _grow_exclusive(8)
    after = _count(member)

    assert after == before, f"cardápio do membro: {before} → {after} consultas com +8 produtos exclusivos"


def test_resolucao_em_lote_o_cardapio_anonimo_nao_cresce_com_a_colecao(cardapio):
    anon = Client()
    before = _count(anon)
    _grow_exclusive(8)
    assert _count(anon) == before
