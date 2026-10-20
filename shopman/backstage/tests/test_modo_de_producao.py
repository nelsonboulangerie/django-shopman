"""Modo de produção da ficha: "Em lote" × "Na hora" (ADR-040, dono 20/10/2026).

Uma leitura só (``Recipe.production_mode``, lida em lote por
``production_modes_for_output_skus``) decide três coisas: o planejamento só vê o
que é em lote; a venda baixa os insumos do que é na hora; o KDS manda o na hora à
estação de preparo. ``is_active`` é só vigente × arquivada.

Cobre a escrita (Produção pela ficha e pela operação da receita, Admin), as
recusas, o filtro e o selo do inventário, o aviso só de leitura do Gestor e as
travas do Core (o suggest e a ordem de produção).
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.craftsman.contrib.admin_unfold.admin import RecipeAdminForm
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.models import ProductionMode, Recipe, RecipeEntry, RecipeItem
from shopman.craftsman.services import production_modes_for_output_skus

from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

SHEETS_URL = "/api/v1/backstage/recipes/sheets/"
RECIPES_URL = "/api/v1/backstage/recipes/"


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Modo de Produção")


@pytest.fixture
def editor(shop):
    from shopman.shop.models import Shop

    user = grant_production_operator(User.objects.create_user("modo-editor", password="pw", is_staff=True))
    user.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shop), codename="manage_production")
    )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def viewer(shop):
    return grant_production_operator(User.objects.create_user("modo-viewer", password="pw", is_staff=True))


@pytest.fixture
def fichas(db):
    from shopman.buyman.models import Material
    from shopman.offerman.models import Product

    Material.objects.create(sku="CAFE-GRAO", name="Café em grão", unit="kg")
    Material.objects.create(sku="FARINHA", name="Farinha", unit="kg")
    Product.objects.create(sku="SP", name="Espresso", base_price_q=700, unit="un")
    Product.objects.create(sku="BAT", name="Bâtard", base_price_q=1500, unit="un")
    espresso = Recipe.objects.create(
        ref="espresso", name="Espresso", output_sku="SP", batch_size=Decimal("1"),
        production_mode=ProductionMode.MADE_TO_ORDER,
    )
    RecipeItem.objects.create(recipe=espresso, input_sku="CAFE-GRAO", quantity=Decimal("0.007"), unit="kg")
    batard = Recipe.objects.create(ref="batard", name="Bâtard", output_sku="BAT", batch_size=Decimal("10"))
    RecipeItem.objects.create(recipe=batard, input_sku="FARINHA", quantity=Decimal("3"), unit="kg")
    return {"espresso": espresso, "batard": batard}


def _patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type="application/json")


# ── A leitura única ──────────────────────────────────────────────────────────


def test_a_leitura_em_lote_e_so_da_ficha_vigente(fichas):
    arquivada = Recipe.objects.create(
        ref="espresso-velho", name="Espresso velho", output_sku="AGUA", batch_size=Decimal("1"),
        is_active=False, production_mode=ProductionMode.MADE_TO_ORDER,
    )
    assert arquivada.pk
    modes = production_modes_for_output_skus(["SP", "BAT", "AGUA", "SEM-FICHA"])
    assert modes == {"SP": ProductionMode.MADE_TO_ORDER, "BAT": ProductionMode.BATCH}


# ── Core: o feito na hora nunca é planejado ──────────────────────────────────


def test_ordem_de_producao_de_ficha_na_hora_e_recusada(fichas):
    from shopman.craftsman.services import CraftPlanning

    with pytest.raises(CraftError) as exc:
        CraftPlanning.plan(fichas["espresso"], 10)
    assert exc.value.code == "MADE_TO_ORDER_RECIPE"
    assert CraftPlanning.plan(fichas["batard"], 10).output_sku == "BAT"


def test_a_sugestao_de_producao_so_ve_o_que_e_em_lote(fichas, monkeypatch):
    from datetime import date

    from django.utils import module_loading
    from shopman.craftsman import conf
    from shopman.craftsman.services import CraftQueries

    seen: list[str] = []

    class Backend:
        def history(self, sku, **kwargs):
            seen.append(sku)
            return []

    real_get_setting = conf.get_setting
    monkeypatch.setattr(
        conf, "get_setting", lambda key: "teste.Backend" if key == "DEMAND_BACKEND" else real_get_setting(key)
    )
    monkeypatch.setattr(module_loading, "import_string", lambda path: Backend)
    CraftQueries.suggest(date(2026, 10, 21))
    assert seen == ["BAT"]


# ── Produção: a ficha e a operação da receita ────────────────────────────────


def test_a_ficha_troca_o_modo_e_a_projecao_le(client, editor, fichas):
    client.force_login(editor)
    resp = _patch(client, f"{SHEETS_URL}batard/", {"productionMode": "made_to_order"})
    assert resp.status_code == 200, resp.content
    assert resp.json()["sheet"]["execution"]["production_mode"] == "made_to_order"
    options = resp.json()["sheet"]["execution"]["production_mode_options"]
    assert [(o["value"], o["label"]) for o in options] == [("batch", "Em lote"), ("made_to_order", "Na hora")]
    fichas["batard"].refresh_from_db()
    assert fichas["batard"].production_mode == ProductionMode.MADE_TO_ORDER
    assert fichas["batard"].is_active is True


def test_modo_desconhecido_e_recusado(client, editor, fichas):
    client.force_login(editor)
    resp = _patch(client, f"{SHEETS_URL}batard/", {"productionMode": "fornada"})
    assert resp.status_code == 400
    assert resp.json()["field"] == "productionMode"


def test_quem_so_le_nao_troca_o_modo(client, viewer, fichas):
    client.force_login(viewer)
    assert _patch(client, f"{SHEETS_URL}batard/", {"productionMode": "made_to_order"}).status_code == 403


def test_a_operacao_da_receita_troca_o_modo(client, editor, fichas):
    RecipeEntry.objects.create(ref="espresso", name="Espresso", output_sku="SP")
    client.force_login(editor)
    resp = _patch(client, f"{RECIPES_URL}espresso/execution/", {"productionMode": "batch"})
    assert resp.status_code == 200, resp.content
    fichas["espresso"].refresh_from_db()
    assert fichas["espresso"].production_mode == ProductionMode.BATCH


def test_a_copia_da_ficha_herda_o_modo(client, editor, fichas):
    client.force_login(editor)
    resp = client.post(
        f"{SHEETS_URL}espresso/duplicate/", json.dumps({"name": "Espresso teste"}),
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert resp.status_code == 201, resp.content
    copy = Recipe.objects.get(ref=resp.json()["resource"]["ref"])
    assert copy.production_mode == ProductionMode.MADE_TO_ORDER
    assert copy.is_active is False


def test_selo_e_filtro_nas_fichas_e_no_inventario(client, viewer, fichas):
    RecipeEntry.objects.create(ref="espresso", name="Espresso", output_sku="SP")
    RecipeEntry.objects.create(ref="batard", name="Bâtard", output_sku="BAT")
    client.force_login(viewer)

    cards = client.get(SHEETS_URL).json()["sheets"]["cards"]
    assert {c["ref"]: (c["production_mode"], c["production_mode_label"]) for c in cards} == {
        "espresso": ("made_to_order", "Na hora"),
        "batard": ("batch", "Em lote"),
    }
    only = client.get(SHEETS_URL, {"mode": "made_to_order"}).json()["sheets"]["cards"]
    assert [c["ref"] for c in only] == ["espresso"]
    assert client.get(SHEETS_URL, {"mode": "fornada"}).status_code == 400

    entries = client.get(RECIPES_URL).json()["book"]["entries"]
    assert {e["ref"]: e["production_mode_label"] for e in entries} == {"espresso": "Na hora", "batard": "Em lote"}
    only = client.get(RECIPES_URL, {"mode": "batch"}).json()["book"]["entries"]
    assert [e["ref"] for e in only] == ["batard"]


# ── Admin: o mesmo campo ─────────────────────────────────────────────────────


def test_admin_grava_o_modo(fichas):
    data = {
        "ref": "batard",
        "name": "Bâtard",
        "output_sku": "BAT",
        "batch_size": "10",
        "is_active": "on",
        "production_mode": "made_to_order",
        "steps_text": "",
    }
    form = RecipeAdminForm(data=data, instance=fichas["batard"])
    assert form.is_valid(), form.errors
    form.save()
    fichas["batard"].refresh_from_db()
    assert fichas["batard"].production_mode == ProductionMode.MADE_TO_ORDER


# ── Gestor: só leitura no produto ────────────────────────────────────────────


def test_o_gestor_le_o_modo_e_a_estacao(fichas, settings):
    from shopman.offerman.models import Collection, CollectionItem, Product

    from shopman.backstage.models import KDSInstance
    from shopman.backstage.services.catalog import get_product_detail

    settings.SHOPMAN_SURFACE_URLS = {"production": "https://prod.example.test"}
    bebidas = Collection.objects.create(ref="bebidas-quentes", name="Bebidas quentes")
    CollectionItem.objects.create(collection=bebidas, product=Product.objects.get(sku="SP"), is_primary=True)

    sem_estacao = get_product_detail("SP")["production"]
    assert sem_estacao["mode"] == "made_to_order"
    assert sem_estacao["station"] == ""
    assert "nenhuma estação de preparo" in sem_estacao["summary"]

    cafes = KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")
    cafes.collections.add(bebidas)
    assert get_product_detail("SP")["production"] == {
        "mode": "made_to_order",
        "mode_label": "Na hora",
        "station": "Cafés",
        "summary": "Feito na hora na estação Cafés: os insumos baixam a cada venda.",
        "recipe_ref": "espresso",
        "recipe_name": "Espresso",
        "url": "https://prod.example.test/recipes/sheets?open=espresso",
    }
    assert get_product_detail("BAT")["production"]["summary"] == "Produzido em lote: planejado e estocado pela Produção."
    assert "—" not in sem_estacao["summary"]
