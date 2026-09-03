"""Inventário de receitas — contrato HTTP (``/api/v1/backstage/recipes/*``).

Cobre a porta que o app de Produção consome nas telas ``/recipes``: leitura
(inventário, receita, comparação, referência, insumos) com o gate do app de
Produção, escrita (entry, versão, rascunho, publicar) com
``shop.manage_production``, a lente e a padronização, a captura por IA (503
sem credencial, 200 com o provedor fingido) e os 404/400/409 no dialeto
canônico. As regras do inventário moram no Craftsman; aqui se prova a porta.
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeVersion
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/backstage/recipes/"


def _manage_production_perm() -> Permission:
    from shopman.shop.models import Shop

    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Shop), codename="manage_production",
    )


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Receitas")


@pytest.fixture
def viewer(shop):
    """Operador de chão: alcança o app de Produção, não gere a produção."""
    user = User.objects.create_user("recipes-viewer", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def editor(shop):
    """Cozinha/gerente: gere a produção, então escreve no inventário."""
    user = User.objects.create_user("recipes-editor", password="pw", is_staff=True)
    user = grant_production_operator(user)
    user.user_permissions.add(_manage_production_perm())
    return User.objects.get(pk=user.pk)


@pytest.fixture
def materials(db):
    rows = [
        ("FARINHA-T55", "Farinha de trigo T55", "kg"),
        ("FARINHA-T65", "Farinha de trigo T65", "kg"),
        ("AGUA-FILTRADA", "Água filtrada", "l"),
        ("LEITE", "Leite integral", "l"),
        ("SAL", "Sal", "kg"),
        ("MANTEIGA-FR", "Manteiga francesa", "kg"),
    ]
    return {sku: Material.objects.create(sku=sku, name=name, unit=unit) for sku, name, unit in rows}


def flour_formula(*, water=700, flour=1000, parts=None):
    return {
        "anchor": {"kind": "flour"},
        "basis_g": None,
        "standardized": False,
        "items": [
            {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": flour, "unit": "g"},
            {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": water, "unit": "g"},
            {"sku": "SAL", "name": "Sal", "role": "salt", "quantity": 20, "unit": "g"},
        ],
        "parts": parts or [],
    }


def version_payload(**over):
    payload = {
        "formula": flour_formula(),
        "yield_quantity": "1.7",
        "yield_unit": "kg",
        "steps": ["Mistura", "Fermentação", "Forno"],
        "notes": "",
        "label": "",
        "source": {"kind": "manual"},
    }
    payload.update(over)
    return payload


@pytest.fixture
def entry(db):
    entry = craftsman.create_entry(ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO")
    craftsman.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg",
                             steps=["Mistura", "Fermentação", "Forno"])
    return entry


@pytest.fixture
def published_levain(db):
    levain = craftsman.create_entry(ref="creme-levain", name="Levain", kind="bread", output_sku="LEVAIN")
    version = craftsman.create_version(
        levain,
        formula={
            "anchor": {"kind": "flour"},
            "items": [
                {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 500, "unit": "g"},
                {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 500, "unit": "ml"},
            ],
            "parts": [],
        },
        yield_quantity=1000, yield_unit="g",
    )
    craftsman.publish_version(version)
    return levain


def _post(client, url, body):
    return client.post(url, json.dumps(body), content_type="application/json")


def _patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type="application/json")


# ── Gate ─────────────────────────────────────────────────────────────────────


def test_reading_needs_the_production_gate(client, shop, entry):
    bare = User.objects.create_user("bare", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(LIST_URL).status_code == 403
    assert client.get(f"{LIST_URL}{entry.ref}/").status_code == 403


def test_the_access_probe_answers_without_refusing(client, shop, viewer, editor):
    bare = User.objects.create_user("bare-probe", password="pw", is_staff=True)
    client.force_login(bare)
    response = client.get(reverse("api-backstage-recipes-access"))
    assert response.status_code == 200
    assert response.json()["access"] == {"can_view": False, "can_edit": False, "capture_available": False}

    client.force_login(viewer)
    assert client.get(reverse("api-backstage-recipes-access")).json()["access"]["can_view"] is True
    client.force_login(editor)
    assert client.get(reverse("api-backstage-recipes-access")).json()["access"]["can_edit"] is True


def test_viewer_reads_but_does_not_write(client, viewer, entry):
    client.force_login(viewer)
    assert client.get(LIST_URL).status_code == 200
    assert client.get(f"{LIST_URL}{entry.ref}/").status_code == 200

    forbidden = [
        _post(client, LIST_URL, {"name": "Outra", "kind": "bread", "output_sku": "", "notes": ""}),
        _patch(client, f"{LIST_URL}{entry.ref}/", {"notes": "x"}),
        _post(client, f"{LIST_URL}{entry.ref}/versions/", version_payload()),
        _patch(client, f"{LIST_URL}{entry.ref}/versions/1/", {"label": "x"}),
        _post(client, f"{LIST_URL}{entry.ref}/versions/1/publish/", {}),
        _post(client, reverse("api-backstage-recipes-lens"), {"formula": flour_formula(), "kind": "bread"}),
        _post(client, reverse("api-backstage-recipes-standardize"), {"formula": flour_formula()}),
        _post(client, reverse("api-backstage-recipes-capture"), {"text": "x"}),
    ]
    for response in forbidden:
        assert response.status_code == 403, response.content
        assert "shop.manage_production" in response.json()["detail"]
    entry.refresh_from_db()
    assert entry.notes == ""


# ── Inventário e entry ───────────────────────────────────────────────────────


def test_list_carries_cards_kinds_and_access(client, viewer, entry):
    client.force_login(viewer)
    response = client.get(LIST_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["access"] == {"can_view": True, "can_edit": False, "capture_available": False}
    assert body["book"]["count"] == 1
    assert [kind["value"] for kind in body["book"]["kinds"]] == [
        "bread", "viennoiserie", "sweet_dough", "filling", "cream", "sauce", "beverage", "other",
    ]
    (card,) = body["book"]["entries"]
    assert card["ref"] == "massa-tradicao"
    assert card["kind_label"] == "Pão"
    assert card["has_ficha"] is False
    assert card["current_version_number"] is None
    assert card["version_count"] == 1
    assert card["draft_count"] == 1
    assert card["hydration_display"] == ""


def test_list_filters_by_text_kind_and_archived(client, viewer, entry):
    other = craftsman.create_entry(ref="creme-confeiteiro", name="Creme de Confeiteiro", kind="cream")
    archived = craftsman.create_entry(ref="ideia-velha", name="Ideia velha", kind="bread")
    archived.is_archived = True
    archived.save()
    client.force_login(viewer)

    assert [c["ref"] for c in client.get(LIST_URL, {"q": "confeit"}).json()["book"]["entries"]] == [other.ref]
    assert [c["ref"] for c in client.get(LIST_URL, {"kind": "bread"}).json()["book"]["entries"]] == [entry.ref]
    assert [c["ref"] for c in client.get(LIST_URL, {"archived": "1"}).json()["book"]["entries"]] == [archived.ref]
    assert client.get(LIST_URL, {"kind": "pizza"}).json()["field"] == "kind"


def test_create_entry_with_a_first_draft(client, editor, materials):
    client.force_login(editor)
    response = _post(client, LIST_URL, {
        "name": "Pão de Campanha",
        "kind": "bread",
        "output_sku": "PAO-CAMPANHA",
        "notes": "Do caderno.",
        "version": version_payload(source={"kind": "note", "language": "fr"}, label="primeira leitura"),
    })
    assert response.status_code == 201, response.content
    entry = response.json()["entry"]
    assert entry["ref"] == "pao-de-campanha"
    assert entry["kind_label"] == "Pão"
    assert entry["current_version_number"] is None
    assert entry["ficha_ref"] == ""
    (version,) = entry["versions"]
    assert version["number"] == 1
    assert version["status"] == "draft"
    assert version["status_label"] == "Rascunho"
    assert version["source_kind"] == "note"
    assert version["source_label"] == "Anotação"
    assert version["label"] == "primeira leitura"
    assert version["created_by"] == "recipes-editor"
    assert version["yield_quantity"] == "1.7"
    assert version["yield_display"] == "1,7 kg"
    assert version["lens"]["is_bakery"] is True
    assert version["formula"]["basis_g"] is None
    assert version["origin"]["items"][0]["sku"] == "FARINHA-T55"

    stored = RecipeEntry.objects.get(ref="pao-de-campanha")
    assert stored.versions.count() == 1
    assert stored.versions.get().created_by == "recipes-editor"


def test_create_entry_generates_a_unique_ref(client, editor, entry):
    client.force_login(editor)
    response = _post(client, LIST_URL, {"name": "Massa Tradição", "kind": "bread", "output_sku": "", "notes": ""})
    assert response.status_code == 201
    assert response.json()["entry"]["ref"] == "massa-tradicao-2"


def test_create_entry_refuses_a_bad_draft_without_leaving_an_orphan(client, editor):
    client.force_login(editor)
    bad = version_payload()
    bad["formula"]["items"][1]["quantity"] = -5
    response = _post(client, LIST_URL, {"name": "Errada", "kind": "bread", "output_sku": "", "notes": "", "version": bad})
    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "items[1].quantity"
    assert body["errors"] == {"items[1].quantity": [body["detail"]]}
    assert not RecipeEntry.objects.filter(name="Errada").exists()


def test_create_entry_validates_name_and_kind(client, editor):
    client.force_login(editor)
    assert _post(client, LIST_URL, {"name": "  ", "kind": "bread"}).json()["field"] == "name"
    assert _post(client, LIST_URL, {"name": "Ok", "kind": "pizza"}).json()["field"] == "kind"


def test_detail_carries_the_lens(client, viewer, entry):
    client.force_login(viewer)
    response = client.get(f"{LIST_URL}{entry.ref}/")
    assert response.status_code == 200
    body = response.json()
    assert body["access"]["can_edit"] is False
    lens = body["entry"]["versions"][0]["lens"]
    assert lens["is_bakery"] is True
    assert lens["anchor_label"] == "Farinhas totais"
    assert lens["anchor_total_display"] == "1 kg"
    assert lens["total_mass_display"] == "1,72 kg"
    assert [item["pct_display"] for item in lens["items"]] == ["100%", "70%", "2%"]
    assert lens["items"][0]["is_anchor"] is True
    hydration = next(metric for metric in lens["metrics"] if metric["code"] == "hydration_pct")
    assert hydration == {
        "code": "hydration_pct", "label": "Hidratação", "value_display": "70%",
        "low_display": "60%", "high_display": "85%", "max_display": "", "tone": "ok",
        "note": hydration["note"],
    }


def test_detail_404_for_a_missing_entry(client, viewer):
    client.force_login(viewer)
    response = client.get(f"{LIST_URL}nao-existe/")
    assert response.status_code == 404
    assert "nao-existe" in response.json()["detail"]


def test_patch_entry(client, editor, entry):
    client.force_login(editor)
    response = _patch(client, f"{LIST_URL}{entry.ref}/", {
        "name": "Massa Tradição 2027", "kind": "viennoiserie", "output_sku": "MASSA-NOVA", "notes": "x", "is_archived": True,
    })
    assert response.status_code == 200
    body = response.json()["entry"]
    assert body["name"] == "Massa Tradição 2027"
    assert body["kind"] == "viennoiserie"
    assert body["output_sku"] == "MASSA-NOVA"
    assert body["is_archived"] is True
    assert "access" not in response.json()

    assert _patch(client, f"{LIST_URL}{entry.ref}/", {"kind": "pizza"}).json()["field"] == "kind"
    assert _patch(client, f"{LIST_URL}{entry.ref}/", {"is_archived": "sim"}).json()["field"] == "is_archived"
    assert _patch(client, f"{LIST_URL}nao-existe/", {"notes": "x"}).status_code == 404


# ── Versões ──────────────────────────────────────────────────────────────────


def test_new_version_copied_from_another(client, editor, entry):
    client.force_login(editor)
    response = _post(client, f"{LIST_URL}{entry.ref}/versions/", {"from_version": 1, "label": ""})
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["version"]["number"] == 2
    assert body["version"]["status"] == "draft"
    assert body["version"]["steps"] == ["Mistura", "Fermentação", "Forno"]
    assert body["version"]["yield_quantity"] == "1.7"
    assert [v["number"] for v in body["entry"]["versions"]] == [2, 1]

    stored = RecipeVersion.objects.get(entry=entry, number=2)
    assert stored.formula == entry.versions.get(number=1).formula
    assert stored.source == {"kind": "manual", "copied_from": "massa-tradicao@1"}


def test_new_version_with_from_version_and_a_formula_uses_the_formula(client, editor, entry):
    client.force_login(editor)
    payload = version_payload(from_version=1, formula=flour_formula(water=750), yield_quantity="1.75")
    response = _post(client, f"{LIST_URL}{entry.ref}/versions/", payload)
    assert response.status_code == 201
    stored = RecipeVersion.objects.get(entry=entry, number=2)
    assert stored.formula["items"][1]["quantity"] == 750
    assert stored.yield_quantity == Decimal("1.750")
    assert stored.source == {"kind": "manual"}


def test_new_version_refuses_unknown_source_kind_and_missing_from_version(client, editor, entry):
    client.force_login(editor)
    bad_source = _post(client, f"{LIST_URL}{entry.ref}/versions/", version_payload(source={"kind": "dream"}))
    assert bad_source.status_code == 400
    assert bad_source.json()["field"] == "source.kind"
    assert _post(client, f"{LIST_URL}{entry.ref}/versions/", {"from_version": 9}).status_code == 404
    assert _post(client, f"{LIST_URL}{entry.ref}/versions/", {"yield_quantity": "1", "yield_unit": "kg"}).json()["field"] == "formula"


def test_patch_draft_then_publish_makes_it_immutable(client, editor, entry):
    client.force_login(editor)
    url = f"{LIST_URL}{entry.ref}/versions/1/"
    response = _patch(client, url, {"label": "mais água", "formula": flour_formula(water=750), "notes": "teste"})
    assert response.status_code == 200
    assert response.json()["version"]["label"] == "mais água"
    hydration = next(m for m in response.json()["version"]["lens"]["metrics"] if m["code"] == "hydration_pct")
    assert hydration["value_display"] == "75%"

    assert _post(client, f"{url}publish/", {}).status_code == 200
    conflict = _patch(client, url, {"notes": "tarde demais"})
    assert conflict.status_code == 409
    assert conflict.json()["error"] == {"code": "version_not_draft"}
    assert _patch(client, f"{LIST_URL}{entry.ref}/versions/7/", {"notes": "x"}).status_code == 404


def test_publish_writes_the_sheet_and_the_list_shows_it(client, editor, entry):
    client.force_login(editor)
    response = _post(client, f"{LIST_URL}{entry.ref}/versions/1/publish/", {})
    assert response.status_code == 200, response.content
    body = response.json()["entry"]
    assert body["current_version_number"] == 1
    assert body["ficha_ref"] == "massa-tradicao"
    assert body["versions"][0]["status"] == "published"
    assert body["versions"][0]["published_at_display"] != ""

    recipe = Recipe.objects.get(ref="massa-tradicao")
    assert recipe.output_sku == "MASSA-TRADICAO"
    assert recipe.meta["version_ref"] == "massa-tradicao@1"
    assert {item.input_sku for item in recipe.items.all()} == {"FARINHA-T55", "AGUA-FILTRADA", "SAL"}
    assert RecipeVersion.objects.get(entry=entry, number=1).meta["published_by"] == "recipes-editor"

    (card,) = client.get(LIST_URL).json()["book"]["entries"]
    assert card["has_ficha"] is True
    assert card["current_version_number"] == 1
    assert card["anchor_kind"] == "flour"
    assert card["hydration_display"] == "70%"
    assert card["draft_count"] == 0


def test_publish_without_sku_names_the_field(client, editor):
    knowledge = craftsman.create_entry(ref="ideia-de-pao", name="Ideia de pão", kind="bread")
    craftsman.create_version(knowledge, formula=flour_formula(), yield_quantity=1, yield_unit="kg")
    client.force_login(editor)
    response = _post(client, f"{LIST_URL}ideia-de-pao/versions/1/publish/", {})
    assert response.status_code == 400
    assert response.json()["field"] == "output_sku"
    assert not Recipe.objects.filter(ref="ideia-de-pao").exists()


def test_publish_with_an_unmatched_item_names_the_line(client, editor):
    entry = craftsman.create_entry(ref="pao-solto", name="Pão solto", kind="bread", output_sku="PAO-SOLTO")
    formula = flour_formula()
    formula["items"][2] = {"sku": "", "name": "sal grosso", "role": "salt", "quantity": 20, "unit": "g"}
    craftsman.create_version(entry, formula=formula, yield_quantity=1, yield_unit="kg")
    client.force_login(editor)
    response = _post(client, f"{LIST_URL}pao-solto/versions/1/publish/", {})
    assert response.status_code == 400
    assert response.json()["field"] == "items[2].sku"


def test_publish_twice_is_a_state_conflict(client, editor, entry):
    client.force_login(editor)
    url = f"{LIST_URL}{entry.ref}/versions/1/publish/"
    assert _post(client, url, {}).status_code == 200
    response = _post(client, url, {})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_not_draft"


# ── Lente e padronização ─────────────────────────────────────────────────────


def test_lens_preview(client, editor, published_levain):
    client.force_login(editor)
    formula = flour_formula(parts=[{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment", "flour_pct": 20}])
    response = _post(client, reverse("api-backstage-recipes-lens"), {"formula": formula, "kind": "bread"})
    assert response.status_code == 200, response.content
    lens = response.json()["lens"]
    assert lens["is_bakery"] is True
    assert [p["quantity_display"] for p in lens["parts"]] == ["400 g"]
    assert lens["parts"][0]["has_formula"] is True
    assert lens["parts"][0]["kind_label"] == "Pré-fermento"
    assert {item["sku"]: item["quantity_display"] for item in lens["final_mix"]} == {
        "FARINHA-T55": "800 g", "AGUA-FILTRADA": "500 g", "SAL": "20 g",
    }
    assert [item["sku"] for item in lens["bom"]] == ["FARINHA-T55", "AGUA-FILTRADA", "SAL", "LEVAIN"]
    prefermented = next(m for m in lens["metrics"] if m["code"] == "prefermented_flour_pct")
    assert prefermented["value_display"] == "20%"
    assert prefermented["tone"] == "ok"


def test_lens_preview_tolerates_an_unfinished_row(client, editor):
    """O editor manda a fórmula a cada tecla: uma linha em branco não pode virar 400."""
    client.force_login(editor)
    formula = flour_formula()
    formula["items"].append({"sku": "", "name": "", "role": "other", "quantity": 0, "unit": "g", "note": ""})
    response = _post(client, reverse("api-backstage-recipes-lens"), {"formula": formula, "kind": "bread"})
    assert response.status_code == 200
    assert len(response.json()["lens"]["items"]) == 4

    bad = _post(client, reverse("api-backstage-recipes-lens"), {"formula": "x"})
    assert bad.status_code == 400
    assert bad.json()["field"] == "formula"


def test_standardize_to_the_house_basis(client, editor):
    client.force_login(editor)
    informed = flour_formula(flour=3000, water=2100)
    response = _post(client, reverse("api-backstage-recipes-standardize"), {"formula": informed, "basis_g": 1000, "kind": "bread"})
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["formula"]["basis_g"] == 1000
    assert body["formula"]["standardized"] is True
    assert [item["quantity"] for item in body["formula"]["items"]] == ["1000", "700", "6.667"]
    assert body["lens"]["basis_display"] == "1000 g"
    assert body["lens"]["standardized"] is True
    assert body["lens"]["anchor_total_display"] == "1 kg"

    without_flour = {"anchor": {"kind": "flour"}, "items": [{"sku": "AGUA", "name": "Água", "role": "liquid", "quantity": 1, "unit": "kg"}], "parts": []}
    refused = _post(client, reverse("api-backstage-recipes-standardize"), {"formula": without_flour})
    assert refused.status_code == 400
    assert refused.json()["field"] == "anchor"


# ── Comparação, referência, insumos ──────────────────────────────────────────


def test_compare_two_versions(client, viewer, entry):
    craftsman.create_version(entry, formula=flour_formula(water=750), yield_quantity="1.75", yield_unit="kg")
    client.force_login(viewer)
    response = client.get(reverse("api-backstage-recipes-compare"), {"a": "massa-tradicao@1", "b": "massa-tradicao@2"})
    assert response.status_code == 200, response.content
    compare = response.json()["compare"]
    assert compare["a_title"] == "Massa Tradição (versão 1)"
    assert compare["b_title"] == "Massa Tradição (versão 2)"
    water = next(row for row in compare["rows"] if row["sku"] == "AGUA-FILTRADA")
    assert water["a_display"] == "700 g"
    assert water["b_display"] == "750 g"
    assert water["delta_display"] == "+50 g"
    assert water["delta_pct_display"] == "+5%"
    assert water["tone"] == "ok"
    flour = next(row for row in compare["rows"] if row["sku"] == "FARINHA-T55")
    assert flour["tone"] == "muted"
    metrics = {metric["label"]: metric for metric in compare["metrics"]}
    assert metrics["Hidratação"]["delta_display"] == "+5%"
    assert metrics["Rendimento"]["a_display"] == "1,7 kg"
    assert metrics["Rendimento"]["delta_display"] == "+0,05 kg"


def test_compare_validates_and_404s(client, viewer, entry):
    client.force_login(viewer)
    url = reverse("api-backstage-recipes-compare")
    assert client.get(url, {"a": "massa-tradicao@1"}).json()["field"] == "b"
    assert client.get(url, {"a": "massa-tradicao", "b": "massa-tradicao@1"}).status_code == 400
    assert client.get(url, {"a": "massa-tradicao@1", "b": "massa-tradicao@9"}).status_code == 404
    assert client.get(url, {"a": "nao-existe@1", "b": "massa-tradicao@1"}).status_code == 404


def test_reference_by_kind(client, viewer):
    client.force_login(viewer)
    bread = client.get(reverse("api-backstage-recipes-reference"), {"kind": "bread"}).json()["reference"]
    assert bread["kind_label"] == "Pão"
    ranges = {r["code"]: r for r in bread["ranges"]}
    assert ranges["hydration_pct"]["low_display"] == "60%"
    assert ranges["hydration_pct"]["high_display"] == "85%"
    assert ranges["salt_pct"]["max_display"] == "2,5%"
    assert ranges["part_flour_pct:levain"]["label"] == "Farinha na parte: Levain"

    cream = client.get(reverse("api-backstage-recipes-reference"), {"kind": "cream"}).json()["reference"]
    codes = {r["code"] for r in cream["ranges"]}
    assert "salt_pct" in codes and "hydration_pct" not in codes and "part_flour_pct:levain" not in codes

    assert client.get(reverse("api-backstage-recipes-reference"), {"kind": "pizza"}).json()["field"] == "kind"


def test_ingredient_options_mix_materials_and_parts(client, viewer, materials, published_levain):
    client.force_login(viewer)
    url = reverse("api-backstage-recipes-ingredients")
    options = client.get(url, {"q": "lev"}).json()["options"]
    part = next(option for option in options if option["sku"] == "LEVAIN")
    assert part == {"sku": "LEVAIN", "name": "Levain", "unit": "g", "role": "other", "is_part": True, "entry_ref": "creme-levain"}

    flours = client.get(url, {"q": "farinha"}).json()["options"]
    assert {option["sku"] for option in flours} >= {"FARINHA-T55", "FARINHA-T65"}
    assert all(option["is_part"] is False for option in flours)

    everything = client.get(url).json()["options"]
    assert [option["sku"] for option in everything][0] == "LEVAIN"
    assert len(everything) == 1 + len(materials)


# ── Captura ──────────────────────────────────────────────────────────────────

FRENCH_NOTE = "Pain de campagne\nFarine T65 1 kg\nEau 700 g\nSel 20 g\nLevain 200 g\nPétrir, cuire 45 min."

FRENCH_REPLY = {
    "name": "Pão de campanha",
    "kind": "bread",
    "language": "fr",
    "yield": {"quantity": 2, "unit": "un"},
    "items": [
        {"name": "Farinha de trigo T65", "original_text": "Farine T65 1 kg", "quantity": 1, "unit": "kg", "role": "flour", "note": ""},
        {"name": "Água", "original_text": "Eau 700 g", "quantity": 700, "unit": "g", "role": "liquid", "note": ""},
        {"name": "Sal", "original_text": "Sel 20 g", "quantity": 20, "unit": "g", "role": "salt", "note": ""},
        {"name": "Levain", "original_text": "Levain 200 g", "quantity": 200, "unit": "g", "role": "other", "note": ""},
        {"name": "Sementes de girassol", "original_text": "Graines", "quantity": None, "unit": "g", "role": "inclusion", "note": "q.b."},
    ],
    "steps": ["Sovar.", "Assar 45 min."],
    "notes": "",
}


class _FakeAnthropic:
    reply_text = json.dumps(FRENCH_REPLY, ensure_ascii=False)
    raise_exc: Exception | None = None

    def __init__(self, api_key):
        assert api_key
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        if type(self).raise_exc is not None:
            raise type(self).raise_exc
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=type(self).reply_text)])


@pytest.fixture
def provider(monkeypatch, settings):
    _FakeAnthropic.raise_exc = None
    monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropic)
    settings.AI_ASSIST_API_KEY = "sk-ant-teste"
    settings.AI_ASSIST_PROVIDER = "anthropic"
    settings.AI_ASSIST_MODEL = "claude-opus-5"
    return _FakeAnthropic


def test_capture_is_503_without_a_credential(client, editor, settings):
    settings.AI_ASSIST_API_KEY = ""
    client.force_login(editor)
    response = _post(client, reverse("api-backstage-recipes-capture"), {"text": FRENCH_NOTE})
    assert response.status_code == 503
    assert "AI_ASSIST_API_KEY" in response.json()["detail"]
    assert client.get(reverse("api-backstage-recipes-access")).json()["access"]["capture_available"] is False


def test_capture_needs_a_note_or_a_photo(client, editor, provider):
    client.force_login(editor)
    response = _post(client, reverse("api-backstage-recipes-capture"), {"text": "  ", "image": {"data_base64": ""}})
    assert response.status_code == 400
    assert response.json()["field"] == "text"


def test_capture_reads_a_french_note_and_matches_the_ingredients(client, editor, materials, published_levain, provider):
    client.force_login(editor)
    assert client.get(reverse("api-backstage-recipes-access")).json()["access"]["capture_available"] is True

    response = _post(client, reverse("api-backstage-recipes-capture"), {"text": FRENCH_NOTE, "language_hint": "fr"})
    assert response.status_code == 200, response.content
    draft = response.json()["draft"]
    assert draft["name"] == "Pão de campanha"
    assert draft["kind"] == "bread"
    assert draft["language"] == "fr"
    assert draft["yield_quantity"] == "2"
    assert draft["yield_unit"] == "un"
    assert draft["steps"] == ["Sovar.", "Assar 45 min."]

    items = {item["name"]: item for item in draft["items"]}
    flour = items["Farinha de trigo T65"]
    assert flour["sku"] == "FARINHA-T65"
    assert flour["role"] == "flour"
    assert flour["quantity"] == "1"
    assert flour["unit"] == "kg"
    assert flour["match_confidence"].endswith("%")
    assert flour["candidates"][0]["sku"] == "FARINHA-T65"
    assert flour["original_text"] == "Farine T65 1 kg"

    levain = items["Levain"]
    assert levain["sku"] == "LEVAIN"
    # Fermento natural não é fermento biológico: fica fora da métrica de fermento.
    assert levain["role"] == "other"
    assert any(c["sku"] == "LEVAIN" and c["is_part"] and c["entry_ref"] == "creme-levain" for c in levain["candidates"])

    seeds = items["Sementes de girassol"]
    assert seeds["sku"] == ""
    assert seeds["quantity"] == ""
    assert seeds["match_confidence"] == ""

    formula = draft["formula"]
    assert formula["anchor"] == {"kind": "flour"}
    assert formula["standardized"] is False
    assert formula["basis_g"] is None
    assert [(line["sku"], line["quantity"], line["unit"]) for line in formula["items"]] == [
        ("FARINHA-T65", "1000", "g"), ("AGUA-FILTRADA", "700", "g"), ("SAL", "20", "g"), ("LEVAIN", "200", "g"),
    ]


def test_capture_provider_failure_is_502(client, editor, provider):
    provider.raise_exc = RuntimeError("boom")
    provider.reply_text = "isso não é JSON"
    provider.raise_exc = None
    client.force_login(editor)
    response = _post(client, reverse("api-backstage-recipes-capture"), {"text": FRENCH_NOTE})
    assert response.status_code == 502
    assert "JSON" in response.json()["detail"]
    provider.reply_text = json.dumps(FRENCH_REPLY, ensure_ascii=False)


def test_publish_writes_the_sheet_in_the_materials_unit(client, editor, materials):
    """A fórmula fala em grama e mililitro; o insumo é cadastrado em kg ou L, e a ficha fala a unidade do cadastro."""
    entry = craftsman.create_entry(ref="pao-em-gramas", name="Pão em gramas", kind="bread", output_sku="PAO-EM-GRAMAS")
    formula = flour_formula()
    formula["items"][1] = {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 700, "unit": "ml"}
    craftsman.create_version(entry, formula=formula, yield_quantity="1.7", yield_unit="kg")
    client.force_login(editor)
    response = _post(client, f"{LIST_URL}pao-em-gramas/versions/1/publish/", {})
    assert response.status_code == 200, response.content
    items = {item.input_sku: (item.quantity, item.unit) for item in Recipe.objects.get(ref="pao-em-gramas").items.all()}
    assert items == {
        "FARINHA-T55": (Decimal("1"), "kg"),
        "AGUA-FILTRADA": (Decimal("0.7"), "L"),
        "SAL": (Decimal("0.02"), "kg"),
    }


def test_publish_weighs_water_in_grams_against_a_material_sold_by_litre(client, editor, materials):
    """O padeiro pesa a água (700 g sobre 1000 g de farinha); o insumo é litro. Água a 1,0 g/ml é física."""
    entry = craftsman.create_entry(ref="pao-agua-em-g", name="Pão água em g", kind="bread", output_sku="PAO-AGUA-G")
    craftsman.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg")
    client.force_login(editor)
    response = _post(client, f"{LIST_URL}pao-agua-em-g/versions/1/publish/", {})
    assert response.status_code == 200, response.content
    water = Recipe.objects.get(ref="pao-agua-em-g").items.get(input_sku="AGUA-FILTRADA")
    assert (water.quantity, water.unit) == (Decimal("0.7"), "L")


def test_publish_refuses_a_mass_line_for_a_liquid_without_declared_density_and_names_the_row(client, editor, materials):
    """Leite em grama contra insumo em litro só atravessa com densidade declarada; sem ela, recusa apontando a linha."""
    entry = craftsman.create_entry(ref="pao-de-leite", name="Pão de leite", kind="bread", output_sku="PAO-DE-LEITE")
    formula = flour_formula()
    formula["items"][1] = {"sku": "LEITE", "name": "Leite", "role": "liquid", "quantity": 680, "unit": "g"}
    craftsman.create_version(entry, formula=formula, yield_quantity="1.6", yield_unit="kg")
    client.force_login(editor)
    response = _post(client, f"{LIST_URL}pao-de-leite/versions/1/publish/", {})
    assert response.status_code == 400, response.content
    assert response.json()["field"] == "items[1].unit"
    assert "(L)" in response.json()["detail"]
    assert not Recipe.objects.filter(ref="pao-de-leite").exists()

    # Com a densidade declarada na linha, a mesma fórmula publica em litro.
    formula["items"][1]["density_g_per_ml"] = "1.03"
    version = craftsman.update_draft(entry.versions.get(number=1), formula=formula)
    response = _post(client, f"{LIST_URL}pao-de-leite/versions/{version.number}/publish/", {})
    assert response.status_code == 200, response.content
    milk = Recipe.objects.get(ref="pao-de-leite").items.get(input_sku="LEITE")
    assert (milk.quantity, milk.unit) == (Decimal("0.66"), "L")
