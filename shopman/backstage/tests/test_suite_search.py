"""Busca da suíte: um campo, alcance "App" e "Toda a suíte" (SUITE-UX-V2 §2.2, FUNCTION §7).

O que se trava aqui:

- cada tipo (pedido, encomenda, cliente, produto, insumo, fornecedor, lote, receita,
  campanha, tela) aparece agrupado, com o link profundo para o lugar exato no app certo;
- permissão é por tipo, com a pergunta da tela de destino: quem não abre o app (ou a tela)
  não recebe o resultado, e o dado pessoal não vaza para quem não o veria na tela;
- app sem URL configurada não gera resultado (nunca link morto);
- termo curto é busca vazia; termo longo é recusado no dialeto ``{detail, field, errors}``;
- o endpoint pede alguém da casa.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.buyman.models import Material, Supplier
from shopman.craftsman.models import Recipe, RecipeEntry, WorkOrder
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import Order

from shopman.backstage.projections import suite_search
from shopman.shop.models import AnnouncementTemplate, Campaign

pytestmark = pytest.mark.django_db

SURFACE_URLS = {
    "pos": "https://pdv.example.test/",
    "kds": "https://kds.example.test/",
    "gestor": "https://gestor.example.test/",
    "production": "https://prod.example.test/",
    "purchase": "https://compras.example.test/",
    "marketing": "https://mkt.example.test/",
    "bi": "https://bi.example.test/",
    "loja": "https://loja.example.test/",
}

URL = "/api/v1/backstage/search/"


def _perm(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _operator(username: str, *perms: tuple[str, str]) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for app_label, codename in perms:
        user.user_permissions.add(_perm(app_label, codename))
    return User.objects.get(pk=user.pk)


def _search(client, user, q: str) -> dict:
    client.force_login(user)
    response = client.get(URL, {"q": q})
    assert response.status_code == 200, response.content
    return response.json()["search"]


def _group(search: dict, kind: str) -> list[dict]:
    return next((group["results"] for group in search["groups"] if group["type"] == kind), [])


def _admin() -> User:
    return User.objects.filter(username="dono").first() or User.objects.create_superuser("dono", "dono@example.test", "pw")


@pytest.fixture
def maria_order():
    return Order.objects.create(
        ref="WEB-20261003-X36",
        channel_ref="web",
        status="preparing",
        total_q=1300,
        data={"customer": {"name": "Maria Santos", "phone": "5543991111111"}, "fulfillment_type": "pickup"},
    )


def test_url_is_english_and_named():
    assert reverse("api-backstage-search") == URL


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_order_by_customer_name_links_to_the_order_in_the_gestor(client, maria_order):
    search = _search(client, _admin(), "maria")
    [order] = _group(search, "orders")
    assert order["app"] == "gestor"
    assert order["title"] == "X36 · Maria Santos"
    assert order["place"] == "Gestor › Pedidos"
    assert order["url"] == "https://gestor.example.test/WEB-20261003-X36"
    assert "R$\u00a013,00" in order["detail"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_order_by_ref(client, maria_order):
    search = _search(client, _admin(), "x36")
    assert [r["key"] for r in _group(search, "orders")] == ["order:WEB-20261003-X36"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_open_preorder_links_to_the_pos(client, maria_order):
    search = _search(client, _admin(), "Maria")
    [preorder] = _group(search, "preorders")
    assert preorder["app"] == "pos"
    assert preorder["title"] == "Encomenda de Maria Santos"
    assert preorder["url"] == "https://pdv.example.test/preorders/WEB-20261003-X36"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_customer_with_the_list_phone_and_order_count(client):
    Customer.objects.create(ref="CLI-MARIA", first_name="Maria", last_name="Santos", phone="+5543991111111")
    search = _search(client, _admin(), "santos")
    [customer] = _group(search, "customers")
    assert customer["title"] == "Maria Santos"
    assert customer["url"] == "https://gestor.example.test/customers/CLI-MARIA"
    assert customer["place"] == "Gestor › Clientes"
    assert "99111-1111" in customer["detail"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_customer_by_phone_digits(client):
    Customer.objects.create(ref="CLI-MARIA", first_name="Maria", phone="+5543991111111")
    search = _search(client, _admin(), "(43) 99111")
    assert [r["key"] for r in _group(search, "customers")] == ["customer:CLI-MARIA"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_product_by_name_and_sku_opens_the_catalog(client):
    Product.objects.create(sku="MADELEINE", name="Madeleine", base_price_q=650)
    by_name = _group(_search(client, _admin(), "madel"), "products")
    by_sku = _group(_search(client, _admin(), "MADELEINE"), "products")
    assert by_name == by_sku
    [product] = by_name
    assert product["url"] == "https://gestor.example.test/catalog?sku=MADELEINE"
    assert "R$\u00a06,50" in product["detail"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_material_and_supplier_open_the_purchase_base(client):
    Material.objects.create(sku="MANTEIGA-82", name="Manteiga sem sal 82%", unit="kg")
    Supplier.objects.create(ref="MOINHO-ANACONDA", name="Moinho Anaconda Ltda", trade_name="Moinho Anaconda")
    search = _search(client, _admin(), "man")
    [material] = _group(search, "materials")
    assert material["app"] == "purchase"
    assert material["url"] == "https://compras.example.test/?view=base&material=MANTEIGA-82"
    search = _search(client, _admin(), "anaconda")
    [supplier] = _group(search, "suppliers")
    assert supplier["title"] == "Moinho Anaconda"
    assert supplier["url"] == "https://compras.example.test/?view=base&supplier=MOINHO-ANACONDA"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_work_order_and_recipe_open_the_production(client):
    recipe = Recipe.objects.create(ref="croissant", name="Croissant", output_sku="CRO", batch_size=Decimal("10"))
    wo = WorkOrder.objects.create(
        recipe=recipe, output_sku="CRO", quantity=Decimal("10"), target_date=timezone.localdate(),
    )
    RecipeEntry.objects.create(ref="croissant-classico", name="Croissant clássico", output_sku="CRO")
    search = _search(client, _admin(), "croissant")
    [lot] = _group(search, "work_orders")
    assert lot["app"] == "production"
    assert lot["url"] == (
        f"https://prod.example.test/?q={wo.ref}&date={timezone.localdate().isoformat()}"
    )
    [entry] = _group(search, "recipes")
    assert entry["url"] == "https://prod.example.test/recipes/croissant-classico"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_campaign_opens_the_marketing_campaigns(client):
    template = AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu")
    Campaign.objects.create(name="Fornada de pães", trigger="production_finished", template=template)
    [campaign] = _group(_search(client, _admin(), "fornada"), "campaigns")
    assert campaign["app"] == "marketing"
    assert campaign["url"] == "https://mkt.example.test/settings/campaigns?q=Fornada+de+p%C3%A3es"
    assert campaign["detail"] == "campanha · ligada"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_screens_by_name_without_accent(client):
    search = _search(client, _admin(), "relatorios")
    [screen] = _group(search, "screens")
    assert screen["title"] == "Produção › Relatórios"
    assert screen["place"] == "tela"
    assert screen["url"] == "https://prod.example.test/reports"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_groups_follow_the_type_order_and_count_per_app(client, maria_order):
    Customer.objects.create(ref="CLI-MARIA", first_name="Maria", last_name="Santos")
    search = _search(client, _admin(), "maria")
    assert [g["type"] for g in search["groups"]] == ["orders", "preorders", "customers"]
    assert search["total"] == 3
    counts = {app["ref"]: app["count"] for app in search["apps"]}
    assert counts["gestor"] == 2 and counts["pos"] == 1 and counts["bi"] == 0
    # A Loja é a superfície do cliente: nunca é destino de busca de operador.
    assert "loja" not in counts


# ── Permissões ─────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_kitchen_operator_reaches_orders_through_the_exit_but_not_customers_or_products(client, maria_order):
    # Quem opera a Cozinha expede na Saída do Gestor (``can_expedite``): acha o pedido,
    # como o acha no quadro. Clientes, Catálogo e o PDV não são portas dele.
    Customer.objects.create(ref="CLI-MARIA", first_name="Maria", last_name="Santos", phone="+5543991111111")
    Product.objects.create(sku="MARIA-MOLE", name="Maria-mole", base_price_q=500)
    cook = _operator("cozinha", ("backstage", "operate_kds"))
    search = _search(client, cook, "maria")
    assert [g["type"] for g in search["groups"]] == ["orders"]
    assert [app["ref"] for app in search["apps"]] == ["kds", "gestor"]
    # E acha as telas dos apps que abre.
    assert [r["app"] for r in _group(_search(client, cook, "preparo"), "screens")] == ["kds"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_gestor_without_customer_permission_does_not_get_customers(client, maria_order):
    Customer.objects.create(ref="CLI-MARIA", first_name="Maria", last_name="Santos", phone="+5543991111111")
    gestor = _operator("gestor", ("shop", "manage_orders"))
    search = _search(client, gestor, "maria")
    assert [g["type"] for g in search["groups"]] == ["orders"]
    gestor_clientes = _operator("gestor2", ("shop", "manage_orders"), ("shop", "manage_customers"))
    assert _group(_search(client, gestor_clientes, "maria"), "customers")


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_products_need_the_catalog_permission(client):
    Product.objects.create(sku="MADELEINE", name="Madeleine", base_price_q=650)
    gestor = _operator("gestor", ("shop", "manage_orders"))
    assert not _group(_search(client, gestor, "madeleine"), "products")
    catalog = _operator("catalogo", ("shop", "manage_orders"), ("shop", "manage_catalog"))
    assert _group(_search(client, catalog, "madeleine"), "products")


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_purchase_results_only_for_who_operates_purchase(client):
    Material.objects.create(sku="FARINHA-T55", name="Farinha T55", unit="kg")
    pos = _operator("caixa", ("cashman", "operate_pos"))
    assert not _group(_search(client, pos, "farinha"), "materials")
    buyer = _operator("compras", ("backstage", "operate_purchase"))
    assert _group(_search(client, buyer, "farinha"), "materials")


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_bi_cash_screen_needs_the_cash_audit(client):
    viewer = _operator("bi", ("backstage", "view_bi"))
    titles = [r["title"] for r in _group(_search(client, viewer, "caixa"), "screens")]
    assert "B.I. › Caixa" not in titles
    auditor = _operator("auditor", ("backstage", "view_bi"), ("cashman", "audit_shift"))
    titles = [r["title"] for r in _group(_search(client, auditor, "caixa"), "screens")]
    assert "B.I. › Caixa" in titles


@override_settings(SHOPMAN_SURFACE_URLS={"pos": "https://pdv.example.test/"}, DEBUG=False)
def test_app_without_url_gives_no_results(client, maria_order):
    search = _search(client, _admin(), "maria")
    assert [g["type"] for g in search["groups"]] == ["preorders"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_old_orders_are_left_to_the_history(client, maria_order):
    Order.objects.filter(pk=maria_order.pk).update(
        created_at=timezone.now() - timedelta(days=suite_search.ORDER_WINDOW_DAYS + 1)
    )
    assert not _group(_search(client, _admin(), "x36"), "orders")


# ── Contrato ───────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_short_query_is_an_empty_search_not_an_error(client, maria_order):
    search = _search(client, _admin(), " m ")
    assert search == {"query": "m", "searched": False, "total": 0, "groups": [], "apps": []}


def test_long_query_is_refused_in_the_house_dialect(client):
    client.force_login(_admin())
    response = client.get(URL, {"q": "x" * (suite_search.MAX_QUERY_LENGTH + 1)})
    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "q"
    assert body["detail"]
    assert "q" in body["errors"]


def test_requires_an_operator(client):
    assert client.get(URL, {"q": "maria"}).status_code in (401, 403)
    customer = User.objects.create_user("cliente", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(URL, {"q": "maria"}).status_code == 403


def test_a_broken_source_does_not_break_the_search(client, monkeypatch, maria_order):
    def boom(*args, **kwargs):
        raise RuntimeError("fonte fora")

    monkeypatch.setattr(suite_search, "_orders", boom)
    with override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS):
        search = _search(client, _admin(), "maria")
    assert [g["type"] for g in search["groups"]] == ["preorders"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_work_orders_nearest_day_first(client):
    recipe = Recipe.objects.create(ref="baguete", name="Baguete", output_sku="BAG", batch_size=Decimal("10"))
    today = timezone.localdate()
    for offset in (30, -1, 0, 1):
        WorkOrder.objects.create(
            recipe=recipe, output_sku="BAG", quantity=Decimal("10"), target_date=today + timedelta(days=offset),
        )
    lots = _group(_search(client, _admin(), "baguete"), "work_orders")
    days = [lot["url"].split("date=")[1] for lot in lots]
    expected = [today + timedelta(days=d) for d in (0, 1, -1, 30)]
    assert days == [d.isoformat() for d in expected]
