"""Coleções exclusivas do grupo: o cardápio mostra a coleção só ao membro identificado.

Medido em 19/10/2026: o Gestor gravava ``PriceTierAdvantage(kind="exclusive_collections")``
com ``collection_refs`` e nenhum consumidor lia; a coleção "exclusiva" aparecia para
todo mundo. Agora o cardápio (rota privada e gêmea pública), a página da coleção, a
home e o catálogo público (``/api/v1/catalog/``) escondem a coleção de quem não é do
grupo, anônimo incluído. O cardápio anônimo continua o mesmo para todos (cacheável na
borda), e a resolução é UMA consulta, qualquer que seja o tamanho do cardápio.
"""

from __future__ import annotations

import json

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


# ── Link direto e sacola (frente 3b) ─────────────────────────────────────────
# O #1916 escondia a coleção do cardápio, mas a página do produto abria pelo link
# direto e a sacola aceitava o item. Agora a decisão do cardápio vale também ali.


def _put_sku(client: Client, sku: str, qty: int = 1):
    return client.put(f"/api/v1/cart/skus/{sku}/", data=json.dumps({"qty": qty}), content_type="application/json")


def _cart_skus(client: Client) -> set[str]:
    body = client.get("/api/v1/storefront/cart/").json()
    return {line["sku"] for line in (body.get("cart") or body)["items"]}


@pytest.mark.parametrize("suffix", ["", "recommendations/"])
def test_pagina_do_produto_exclusivo_e_404_para_quem_nao_e_do_grupo(cardapio, suffix):
    ana, beto = cardapio
    assert Client().get(f"/api/v1/storefront/products/BRIGADEIRO/{suffix}").status_code == 404
    assert Client().get("/api/v1/catalog/products/BRIGADEIRO/").status_code == 404

    outsider = Client()
    _login_as_customer(outsider, beto)
    assert outsider.get(f"/api/v1/storefront/products/BRIGADEIRO/{suffix}").status_code == 404

    member = Client()
    _login_as_customer(member, ana)
    assert member.get(f"/api/v1/storefront/products/BRIGADEIRO/{suffix}").status_code == 200

    # Produto comum segue aberto a todos.
    assert Client().get(f"/api/v1/storefront/products/PAO-FRANCES/{suffix}").status_code == 200


def test_produto_tambem_numa_colecao_comum_abre_pelo_link(cardapio):
    CollectionItem.objects.create(
        collection=Collection.objects.get(ref="paes"), product=Product.objects.get(sku="BRIGADEIRO"), sort_order=99,
    )
    assert Client().get("/api/v1/storefront/products/BRIGADEIRO/").status_code == 200


@pytest.mark.parametrize("who", ["anonimo", "fora_do_grupo"])
def test_sacola_recusa_o_exclusivo_a_quem_nao_e_do_grupo(cardapio, who):
    _, beto = cardapio
    client = Client()
    if who == "fora_do_grupo":
        _login_as_customer(client, beto)

    response = _put_sku(client, "BRIGADEIRO")

    assert response.status_code == 403, response.content[:300]
    body = response.json()
    assert body["error_code"] == "group_exclusive"
    assert body["field"] == "sku" and body["errors"]["sku"] == [body["detail"]]
    assert body["skus"] == ["BRIGADEIRO"]
    assert "exclusivo de um grupo" in body["detail"]
    assert ("entre na sua conta" in body["detail"]) is (who == "anonimo")
    assert "BRIGADEIRO" not in _cart_skus(client)


def test_sacola_com_escolhas_tambem_recusa(cardapio):
    response = Client().post(
        "/api/v1/cart/lines/",
        data={"sku": "BRIGADEIRO", "qty": 1, "options": [{"group": "sabor", "ref": "x"}]},
        content_type="application/json",
    )
    assert response.status_code == 403, response.content[:300]
    assert response.json()["error_code"] == "group_exclusive"


def test_membro_poe_o_exclusivo_na_sacola_e_o_anonimo_o_comum(cardapio):
    ana, _ = cardapio
    member = Client()
    _login_as_customer(member, ana)
    assert _put_sku(member, "BRIGADEIRO").status_code == 200
    assert "BRIGADEIRO" in _cart_skus(member)

    assert _put_sku(Client(), "PAO-FRANCES").status_code == 200


def test_checkout_recusa_o_exclusivo_de_quem_saiu_do_grupo(cardapio):
    from django.utils import timezone
    from shopman.orderman.models import Order

    from shopman.storefront.services.pickup_slots import get_slots
    from shopman.storefront.tests._checkout_baseline import with_baseline

    ana, _ = cardapio
    client = Client()
    _login_as_customer(client, ana)
    assert _put_sku(client, "BRIGADEIRO").status_code == 200
    ana.price_tiers.clear()  # saiu do grupo com o item já na sacola

    payload = with_baseline(client, {
        "name": "Ana", "phone": "+5543999990001",
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": get_slots()[-1]["ref"],
        "payment_method": "cash",
    })
    response = client.post("/api/v1/checkout/", data=payload, content_type="application/json")

    assert response.status_code == 403, response.content[:400]
    body = response.json()
    assert (body["error_code"], body["field"], body["skus"]) == ("group_exclusive", "items", ["BRIGADEIRO"])
    assert not Order.objects.exists()


def test_portao_da_sacola_tem_custo_fixo_para_o_anonimo(cardapio):
    """O anônimo não ganha consulta por item: 1 item ou 10, o portão custa o mesmo."""
    from django.test import RequestFactory

    from shopman.storefront.cart import refuse_group_exclusive

    def cost(skus) -> int:
        request = RequestFactory().get("/")
        with CaptureQueriesContext(connection) as ctx:
            refuse_group_exclusive(request, skus)
        return len(ctx.captured_queries)

    common = list(Product.objects.exclude(sku__in=DOCES).values_list("sku", flat=True))
    assert len(common) >= 10
    assert cost(common[:1]) == cost(common)


def test_pdp_publica_nao_expoe_produto_de_colecao_exclusiva(cardapio):
    hidden = Client().get("/api/v1/storefront/public/products/BRIGADEIRO/")
    common = Client().get("/api/v1/storefront/public/products/PAO-FRANCES/")
    assert hidden.status_code == 404
    assert hidden["Cache-Control"] == "private, no-store"
    assert common.status_code == 200
    assert set(common.json()) == {"product"}
