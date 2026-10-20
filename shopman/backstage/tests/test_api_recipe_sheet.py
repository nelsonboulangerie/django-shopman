"""Ficha de execução (craftsman.Recipe + RecipeItem) — contrato HTTP do cadastro.

Cobre a porta que o app de Produção consome em /recipes/sheets: lista com busca
e recorte, criar, editar, duplicar e o gate (ler é do app; escrever é gerir a
produção). O risco desta frente não é a porta, é o conteúdo: ficha errada
desconta estoque errado. Por isso os testes de massa cobrem os dois lados do
invariante e, de propósito, o caso que o Admin deixa passar — editar os itens
sem revalidar a soma contra o rendimento. A paridade com o Admin é provada
lendo de volta o que a ficha gravou com o MESMO formulário do Admin.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.buyman.models import Material
from shopman.craftsman.contrib.admin_unfold.admin import RecipeAdminForm
from shopman.craftsman.models import Recipe

from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

SHEETS_URL = "/api/v1/backstage/recipes/sheets/"


def _manage_production_perm() -> Permission:
    from shopman.shop.models import Shop

    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Shop), codename="manage_production",
    )


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Fichas")


@pytest.fixture
def viewer(shop):
    user = User.objects.create_user("sheets-viewer", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def editor(shop):
    user = User.objects.create_user("sheets-editor", password="pw", is_staff=True)
    user = grant_production_operator(user)
    user.user_permissions.add(_manage_production_perm())
    return User.objects.get(pk=user.pk)


@pytest.fixture
def materials(db):
    rows = [
        ("FARINHA-T55", "Farinha de trigo T55", "kg"),
        ("AGUA-FILTRADA", "Água filtrada", "kg"),
        ("SAL-REFINADO", "Sal refinado", "kg"),
        ("AZEITE", "Azeite", "kg"),
    ]
    return {sku: Material.objects.create(sku=sku, name=name, unit=unit) for sku, name, unit in rows}


@pytest.fixture
def pao_product(db):
    """O SKU de saída precisa de unidade DECLARADA para o invariante de massa opinar."""
    from shopman.offerman.models import Product

    return Product.objects.create(sku="PAO-TRADICAO", name="Pão Tradição", base_price_q=1500, unit="kg")


def sheet_payload(**over):
    payload = {
        "name": "Pão Tradição",
        "output_sku": "PAO-TRADICAO",
        "batch_size": "1.7",
        "is_active": True,
        "steps": ["Mistura", "Fermentação", "Forno"],
        "items": [
            {"input_sku": "FARINHA-T55", "quantity": "1", "unit": "kg", "usable_factor": "1", "is_optional": False, "note": ""},
            {"input_sku": "AGUA-FILTRADA", "quantity": "0.7", "unit": "kg", "usable_factor": "1", "is_optional": False, "note": ""},
            {"input_sku": "SAL-REFINADO", "quantity": "0.02", "unit": "kg", "usable_factor": "1", "is_optional": False, "note": "flor de sal"},
        ],
    }
    payload.update(over)
    return payload


def _post(client, url, body, *, key: str | None = None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key or str(uuid4())}
    return client.post(url, json.dumps(body), content_type="application/json", **headers)


def _patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type="application/json")


# ── Gate ─────────────────────────────────────────────────────────────────────


def test_reading_needs_the_production_gate(client, shop, materials):
    bare = User.objects.create_user("sheets-bare", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(SHEETS_URL).status_code == 403
    assert client.get(f"{SHEETS_URL}pao-tradicao/").status_code == 403


def test_viewer_reads_but_does_not_write(client, viewer, materials):
    recipe = Recipe.objects.create(ref="pao-tradicao", name="Pão Tradição", output_sku="PAO-TRADICAO", batch_size=Decimal("1.7"))
    client.force_login(viewer)
    assert client.get(SHEETS_URL).status_code == 200
    assert client.get(f"{SHEETS_URL}{recipe.ref}/").status_code == 200

    forbidden = [
        _post(client, SHEETS_URL, sheet_payload()),
        _patch(client, f"{SHEETS_URL}{recipe.ref}/", {"name": "Outra"}),
        _post(client, f"{SHEETS_URL}{recipe.ref}/duplicate/", {"name": "Cópia"}),
    ]
    for response in forbidden:
        assert response.status_code == 403, response.content
        assert "shop.manage_production" in response.json()["detail"]


# ── Lista ────────────────────────────────────────────────────────────────────


def test_list_carries_cards_and_access(client, viewer, materials):
    from shopman.offerman.models import Product

    Product.objects.create(sku="PAO-TRADICAO", name="Pão Tradição", base_price_q=1500, unit="kg")
    Recipe.objects.create(ref="pao-tradicao", name="Pão Tradição", output_sku="PAO-TRADICAO", batch_size=Decimal("1.7"))
    Recipe.objects.create(ref="levain", name="Levain", output_sku="LEVAIN", batch_size=Decimal("2"), is_active=False)

    client.force_login(viewer)
    response = client.get(SHEETS_URL)
    assert response.status_code == 200, response.content
    assert response.json()["access"]["can_view"] is True
    sheets = response.json()["sheets"]
    assert sheets["count"] == 2
    assert sheets["total"] == 2
    by_ref = {card["ref"]: card for card in sheets["cards"]}
    assert by_ref["pao-tradicao"]["output_name"] == "Pão Tradição"
    assert by_ref["pao-tradicao"]["batch_size"] == "1.7"
    assert by_ref["pao-tradicao"]["is_active"] is True
    assert by_ref["pao-tradicao"]["has_entry"] is False
    assert by_ref["levain"]["output_name"] == ""


def test_list_filters_text_and_active_and_sorts(client, viewer, materials):
    Recipe.objects.create(ref="pao-tradicao", name="Pão Tradição", output_sku="PAO-TRADICAO", batch_size=Decimal("1.7"))
    Recipe.objects.create(ref="levain", name="Levain", output_sku="LEVAIN", batch_size=Decimal("2"), is_active=False)

    client.force_login(viewer)
    assert [c["ref"] for c in client.get(SHEETS_URL, {"q": "leva"}).json()["sheets"]["cards"]] == ["levain"]
    assert [c["ref"] for c in client.get(SHEETS_URL, {"active": "0"}).json()["sheets"]["cards"]] == ["levain"]
    assert [c["ref"] for c in client.get(SHEETS_URL, {"active": "1"}).json()["sheets"]["cards"]] == ["pao-tradicao"]
    assert [c["ref"] for c in client.get(SHEETS_URL, {"sort": "output"}).json()["sheets"]["cards"]] == [
        "levain",
        "pao-tradicao",
    ]
    bad = client.get(SHEETS_URL, {"sort": "bogus"})
    assert bad.status_code == 400
    assert bad.json()["field"] == "sort"


def test_list_is_bounded_in_queries(client, viewer, materials):
    """Sem N+1 na camada de leitura: o número de consultas não cresce com as fichas.

    Mede a projection direto (sem o overhead de sessão/usuário do client HTTP),
    que é o número que uma tela de lista precisa controlar.
    """
    from shopman.offerman.models import Product

    from shopman.backstage.projections.recipe_book import build_recipe_sheet_list

    Product.objects.create(sku="PAO-TRADICAO", name="Pão Tradição", base_price_q=1500, unit="kg")
    for index in range(6):
        Recipe.objects.create(
            ref=f"ficha-{index}", name=f"Ficha {index}", output_sku="PAO-TRADICAO" if index == 0 else f"SKU-{index}",
            batch_size=Decimal("1.7"),
        )
    with CaptureQueriesContext(connection) as queries:
        projection = build_recipe_sheet_list(page_size=48)
    assert projection.total == 6
    assert len(queries) <= 5, [q["sql"] for q in queries]


# ── Criar ────────────────────────────────────────────────────────────────────


def test_create_sheet_writes_recipe_and_items(client, editor, materials, pao_product):
    client.force_login(editor)
    response = _post(client, SHEETS_URL, sheet_payload())
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["outcome"] == "applied"
    assert body["sheet"]["ref"] == "pao-tradicao"
    assert [item["input_sku"] for item in body["sheet"]["items"]] == ["FARINHA-T55", "AGUA-FILTRADA", "SAL-REFINADO"]
    assert body["sheet"]["mass_balance"]["status"] == "ok"

    recipe = Recipe.objects.get(ref="pao-tradicao")
    assert recipe.output_sku == "PAO-TRADICAO"
    assert recipe.is_active is True
    assert [step["name"] for step in recipe.steps] == ["Mistura", "Fermentação", "Forno"]
    assert recipe.items.count() == 3
    sal = recipe.items.get(input_sku="SAL-REFINADO")
    assert sal.meta["note"] == "flor de sal"
    assert sal.usable_factor == Decimal("1.0000")


def test_create_sheet_refuses_output_above_ingredients(client, editor, materials, pao_product):
    client.force_login(editor)
    response = _post(client, SHEETS_URL, sheet_payload(batch_size="2.5"))
    assert response.status_code == 400, response.content
    body = response.json()
    assert body["field"] == "batch_size"
    assert "Misturar não cria matéria" in body["detail"]
    assert not Recipe.objects.filter(ref="pao-tradicao").exists()


def test_create_sheet_accepts_loss(client, editor, materials, pao_product):
    """Perda passa: o forno tira água. O que a física proíbe é o contrário."""
    client.force_login(editor)
    response = _post(client, SHEETS_URL, sheet_payload(batch_size="1.5"))
    assert response.status_code == 201, response.content
    assert response.json()["sheet"]["mass_balance"]["status"] == "ok"


def test_create_sheet_needs_intention_and_edit(client, viewer, editor, materials, pao_product):
    client.force_login(viewer)
    assert _post(client, SHEETS_URL, sheet_payload()).status_code == 403
    client.force_login(editor)
    no_key = client.post(SHEETS_URL, json.dumps(sheet_payload()), content_type="application/json")
    assert no_key.status_code == 400
    assert no_key.json()["error"]["code"] == "intention_required"


def test_create_sheet_refuses_a_second_active_output(client, editor, materials, pao_product):
    client.force_login(editor)
    assert _post(client, SHEETS_URL, sheet_payload()).status_code == 201
    conflict = _post(client, SHEETS_URL, sheet_payload(name="Outro pão"))
    assert conflict.status_code == 400, conflict.content
    assert conflict.json()["field"] == "output_sku"
    assert Recipe.objects.filter(output_sku="PAO-TRADICAO", is_active=True).count() == 1


def test_create_sheet_refuses_duplicate_line_and_bad_unit(client, editor, materials, pao_product):
    client.force_login(editor)
    duplicate = sheet_payload(items=[
        {"input_sku": "FARINHA-T55", "quantity": "1", "unit": "kg"},
        {"input_sku": "FARINHA-T55", "quantity": "0.5", "unit": "kg"},
    ])
    response = _post(client, SHEETS_URL, duplicate)
    assert response.status_code == 400
    assert response.json()["field"] == "items[1].input_sku"

    bad_unit = sheet_payload(items=[{"input_sku": "FARINHA-T55", "quantity": "1", "unit": "litro"}])
    response = _post(client, SHEETS_URL, bad_unit)
    assert response.status_code == 400
    assert response.json()["field"] == "items[0].unit"


# ── Editar ───────────────────────────────────────────────────────────────────


def _created_sheet(client, editor):
    client.force_login(editor)
    response = _post(client, SHEETS_URL, sheet_payload())
    assert response.status_code == 201, response.content
    return response.json()["sheet"]


def test_update_sheet_rechecks_mass_after_items(client, editor, materials, pao_product):
    """O caso que o Admin deixa passar: baixar os itens sem revalidar a soma."""
    sheet = _created_sheet(client, editor)
    response = _patch(client, f"{SHEETS_URL}{sheet['ref']}/", {
        "expectedRevision": sheet["revision"],
        "items": [
            {"input_sku": "FARINHA-T55", "quantity": "0.5", "unit": "kg"},
            {"input_sku": "AGUA-FILTRADA", "quantity": "0.2", "unit": "kg"},
        ],
    })
    assert response.status_code == 400, response.content
    assert response.json()["field"] == "batch_size"
    recipe = Recipe.objects.get(ref="pao-tradicao")
    assert recipe.items.count() == 3  # nada foi gravado: a transação voltou


def test_update_sheet_preserves_item_meta_and_usable_factor(client, editor, materials, pao_product):
    sheet = _created_sheet(client, editor)
    recipe = Recipe.objects.get(ref="pao-tradicao")
    farinha = recipe.items.get(input_sku="FARINHA-T55")
    farinha.meta = {"allergens": ["gluten"], "diet": "vegan", "note": "velha"}
    farinha.save()
    # A revisão muda quando o item muda, então releia antes de salvar pela porta.
    sheet = client.get(f"{SHEETS_URL}{sheet['ref']}/").json()["sheet"]

    response = _patch(client, f"{SHEETS_URL}{sheet['ref']}/", {
        "expectedRevision": sheet["revision"],
        "items": [
            {"input_sku": "FARINHA-T55", "quantity": "1", "unit": "kg", "usable_factor": "0.84", "note": "peneirada"},
            {"input_sku": "AGUA-FILTRADA", "quantity": "0.7", "unit": "kg"},
        ],
    })
    assert response.status_code == 200, response.content
    items = {item["input_sku"]: item for item in response.json()["sheet"]["items"]}
    assert items["FARINHA-T55"]["usable_factor"] == "0.84"
    assert items["FARINHA-T55"]["gross_quantity"] == "1.19"
    assert items["FARINHA-T55"]["note"] == "peneirada"
    farinha.refresh_from_db()
    assert farinha.meta["allergens"] == ["gluten"]
    assert farinha.meta["diet"] == "vegan"


def test_update_sheet_refuses_a_stale_revision(client, editor, materials, pao_product):
    sheet = _created_sheet(client, editor)
    recipe = Recipe.objects.get(ref="pao-tradicao")
    recipe.name = "Mudou em outra aba"
    recipe.save()
    response = _patch(client, f"{SHEETS_URL}{sheet['ref']}/", {
        "expectedRevision": sheet["revision"],
        "name": "Nome novo",
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "recipe_changed"
    recipe.refresh_from_db()
    assert recipe.name == "Mudou em outra aba"


def test_update_sheet_can_inactivate_and_clear_operation(client, editor, materials, pao_product):
    client.force_login(editor)
    created = _post(client, SHEETS_URL, sheet_payload(
        maxStartedMinutes=90, capacityPerDay="120,5", requiresBatchTracking=True, shelfLifeDays=3, shelfLifeReviewed=True,
    ))
    assert created.status_code == 201, created.content
    sheet = created.json()["sheet"]
    assert sheet["execution"]["max_started_minutes"] == 90
    assert sheet["execution"]["capacity_per_day"] == "120.5"
    assert sheet["execution"]["shelf_life_reviewed"] is True
    assert sheet["execution"]["shelf_life_reviewed_by"] == "sheets-editor"

    response = _patch(client, f"{SHEETS_URL}{sheet['ref']}/", {
        "expectedRevision": sheet["revision"],
        "is_active": False,
        "maxStartedMinutes": None,
        "shelfLifeReviewed": False,
    })
    assert response.status_code == 200, response.content
    assert response.json()["sheet"]["is_active"] is False
    assert response.json()["sheet"]["execution"]["max_started_minutes"] is None
    assert response.json()["sheet"]["execution"]["shelf_life_reviewed"] is False
    recipe = Recipe.objects.get(ref="pao-tradicao")
    assert "max_started_minutes" not in recipe.meta
    assert "shelf_life_reviewed_by" not in recipe.meta


# ── Duplicar ─────────────────────────────────────────────────────────────────


def test_duplicate_sheet_copies_items_inactive_and_clears_review(client, editor, materials, pao_product):
    client.force_login(editor)
    created = _post(client, SHEETS_URL, sheet_payload(shelfLifeDays=3, shelfLifeReviewed=True, maxStartedMinutes=90))
    sheet = created.json()["sheet"]
    response = _post(client, f"{SHEETS_URL}{sheet['ref']}/duplicate/", {
        "name": "Pão Tradição (cópia)",
        "expectedRevision": sheet["revision"],
    })
    assert response.status_code == 201, response.content
    copy = response.json()["sheet"]
    assert copy["ref"] == "pao-tradicao-copia"
    assert copy["is_active"] is False
    assert copy["name"] == "Pão Tradição (cópia)"
    assert [item["input_sku"] for item in copy["items"]] == [item["input_sku"] for item in sheet["items"]]
    recipe = Recipe.objects.get(ref="pao-tradicao-copia")
    assert recipe.meta["max_started_minutes"] == 90
    assert recipe.meta["shelf_life_days"] == 3
    assert "shelf_life_reviewed_by" not in recipe.meta
    assert "shelf_life_reviewed_at" not in recipe.meta


def test_duplicate_sheet_needs_intention(client, editor, materials, pao_product):
    sheet = _created_sheet(client, editor)
    no_key = client.post(
        f"{SHEETS_URL}{sheet['ref']}/duplicate/",
        json.dumps({"name": "Cópia", "expectedRevision": sheet["revision"]}),
        content_type="application/json",
    )
    assert no_key.status_code == 400
    assert no_key.json()["error"]["code"] == "intention_required"


# ── Paridade com o Admin ─────────────────────────────────────────────────────


def test_admin_form_reads_back_what_the_sheet_wrote(client, editor, materials, pao_product):
    """O formulário do Admin lê de volta o que o cadastro da Produção gravou, sem tradução."""
    client.force_login(editor)
    created = _post(client, SHEETS_URL, sheet_payload(
        maxStartedMinutes=90, capacityPerDay="120,5", requiresBatchTracking=True, shelfLifeDays=3, shelfLifeReviewed=True,
    ))
    assert created.status_code == 201, created.content
    recipe = Recipe.objects.get(ref="pao-tradicao")

    form = RecipeAdminForm(instance=recipe)
    assert form.fields["max_started_minutes"].initial == 90
    assert form.fields["capacity_per_day"].initial == "120.5"
    assert form.fields["requires_batch_tracking"].initial is True
    assert form.fields["shelf_life_days"].initial == 3
    assert form.fields["shelf_life_reviewed"].initial is True
    assert recipe.meta["shelf_life_reviewed_days"] == 3
    assert recipe.meta["shelf_life_reviewed_by"] == "sheets-editor"
    assert recipe.meta["shelf_life_reviewed_at"]
    assert recipe.meta["shelf_life_source"] == "manager_review"

    # E o formulário do Admin reescreve os mesmos campos no mesmo dialeto de meta.
    data = {
        "ref": recipe.ref,
        "name": "Pão Tradição",
        "output_sku": recipe.output_sku,
        "batch_size": "1.7",
        "production_mode": "batch",
        "is_active": "on",
        "steps_text": "Mistura\nFermentação",
        "max_started_minutes": "45",
        "capacity_per_day": "80",
        "shelf_life_days": "2",
        "shelf_life_reviewed": "on",
    }
    admin_form = RecipeAdminForm(data=data, instance=recipe)
    assert admin_form.is_valid(), admin_form.errors
    saved = admin_form.save(commit=False)
    assert saved.meta["max_started_minutes"] == 45
    assert saved.meta["capacity_per_day"] == "80"
    assert saved.meta["shelf_life_reviewed_days"] == 2


def test_sheet_detail_404_and_unknown_ref(client, viewer):
    client.force_login(viewer)
    assert client.get(f"{SHEETS_URL}nao-existe/").status_code == 404
