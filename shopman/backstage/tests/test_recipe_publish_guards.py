"""Publicar ficha técnica: o que a porta recusa ou pergunta antes (beta 05/11/2026).

- PROD-01: publicar com um SKU que já tem OUTRA ficha em uso trocava a ficha da
  produção em silêncio. Agora é 409 ``sku_already_in_use`` com o nome da ficha em
  uso, e só passa com ``replace_active``. ``xyz`` e ``XYZ`` são o mesmo SKU.
- PROD-02: fórmula sem ingrediente publicava, e SKU que não existe em cadastro
  nenhum também. Agora a fórmula vazia é 400 ``formula`` e o SKU novo é 409
  ``output_sku_unknown``, que só passa com ``new_output_sku`` (o pré-preparo novo).
- PROD-03: rendimento em notação científica (``1,5e3``) virava 1500; texto com
  mais de um separador é recusado em vez de adivinhado.
- PROD-19: etapa a 9999 °C publicava.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeVersion
from shopman.craftsman.services import recipe_book as craftsman
from shopman.offerman.models import Product

from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/backstage/recipes/"


@pytest.fixture
def editor(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Publicar")
    user = grant_production_operator(User.objects.create_user("gerente-fichas", password="pw", is_staff=True))
    user.user_permissions.add(Permission.objects.get(content_type__app_label="craftsman", codename="change_recipe"))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def client_as_editor(client, editor):
    for sku, name, unit in [
        ("FARINHA-ANACONDA-PREMIUM", "Farinha de trigo T55", "kg"),
        ("AGUA-FILTRADA", "Água filtrada", "l"),
        ("SAL-REFINADO", "Sal", "kg"),
    ]:
        Material.objects.create(sku=sku, name=name, unit=unit)
    client.force_login(editor)
    return client


def _ingredient(sku, name, role, grams):
    return {
        "ref": f"ingredient-{sku.lower()}",
        "sku": sku,
        "name": name,
        "role": role,
        "recipe_version_ref": "",
        "composition": "additional",
        "quantity": {"kind": "fixed", "minimum": grams, "target": grams, "maximum": grams, "unit": "g"},
    }


def _formula(*, ingredients=True):
    return {
        "anchor": {"kind": "flour"},
        "basis_g": None,
        "standardized": False,
        "ingredients": [
            _ingredient("FARINHA-ANACONDA-PREMIUM", "Farinha T55", "flour", 1000),
            _ingredient("AGUA-FILTRADA", "Água", "liquid", 700),
            _ingredient("SAL-REFINADO", "Sal", "salt", 20),
        ] if ingredients else [],
    }


def _recipe(ref, name, sku, *, ingredients=True):
    entry = craftsman.create_entry(ref=ref, name=name, kind="bread", output_sku=sku)
    craftsman.create_version(entry, formula=_formula(ingredients=ingredients), yield_quantity="1.7", yield_unit="kg")
    return entry


def _publish(client, ref, number=1, **body):
    return client.post(
        f"{LIST_URL}{ref}/versions/{number}/publish/",
        json.dumps(body),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )


def _post(client, url, body):
    return client.post(url, json.dumps(body), content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))


# ── PROD-01: a ficha em uso não é trocada em silêncio ───────────────────────


def test_publishing_over_a_sheet_in_use_asks_and_keeps_the_current_one(client_as_editor):
    Product.objects.create(sku="PAO-JOYCE", name="Pão Joyce")
    _recipe("pao-joyce", "Pão Joyce", "PAO-JOYCE")
    assert _publish(client_as_editor, "pao-joyce").status_code == 200
    _recipe("pao-joyce-2", "Pão Joyce 2", "PAO-JOYCE")

    response = _publish(client_as_editor, "pao-joyce-2")

    assert response.status_code == 409, response.content
    body = response.json()
    assert body["error"]["code"] == "sku_already_in_use"
    assert body["field"] == "output_sku"
    assert "Pão Joyce" in body["detail"] and "tira aquela ficha de uso" in body["detail"]
    assert Recipe.objects.get(ref="pao-joyce").is_active is True
    assert not Recipe.objects.filter(ref="pao-joyce-2").exists()
    assert RecipeVersion.objects.get(entry__ref="pao-joyce-2", number=1).status == RecipeVersion.Status.DRAFT


def test_confirmed_replacement_swaps_the_sheet_in_use(client_as_editor):
    Product.objects.create(sku="PAO-JOYCE", name="Pão Joyce")
    _recipe("pao-joyce", "Pão Joyce", "PAO-JOYCE")
    _publish(client_as_editor, "pao-joyce")
    _recipe("pao-joyce-2", "Pão Joyce 2", "PAO-JOYCE")

    response = _publish(client_as_editor, "pao-joyce-2", replace_active=True)

    assert response.status_code == 200, response.content
    assert Recipe.objects.get(ref="pao-joyce-2").is_active is True
    assert Recipe.objects.get(ref="pao-joyce").is_active is False


def test_the_sku_typed_in_lowercase_is_the_same_sku(client_as_editor):
    Product.objects.create(sku="PAO-JOYCE", name="Pão Joyce")
    _recipe("pao-joyce", "Pão Joyce", "PAO-JOYCE")
    _publish(client_as_editor, "pao-joyce")
    entry = _recipe("pao-joyce-2", "Pão Joyce 2", "")

    patched = client_as_editor.patch(
        f"{LIST_URL}{entry.ref}/", json.dumps({"output_sku": " pao-joyce "}), content_type="application/json",
    )
    assert patched.status_code == 200, patched.content
    assert RecipeEntry.objects.get(ref="pao-joyce-2").output_sku == "PAO-JOYCE"
    assert _publish(client_as_editor, "pao-joyce-2").json()["error"]["code"] == "sku_already_in_use"


def test_the_list_says_who_took_the_sku(client_as_editor):
    Product.objects.create(sku="PAO-JOYCE", name="Pão Joyce")
    _recipe("pao-joyce", "Pão Joyce", "PAO-JOYCE")
    _publish(client_as_editor, "pao-joyce")
    _recipe("pao-joyce-2", "Pão Joyce 2", "PAO-JOYCE")
    _publish(client_as_editor, "pao-joyce-2", replace_active=True)

    cards = {card["ref"]: card for card in client_as_editor.get(LIST_URL).json()["book"]["entries"]}

    assert cards["pao-joyce-2"]["ficha_status"] == "in_use"
    assert cards["pao-joyce-2"]["ficha_status_label"] == ""
    assert cards["pao-joyce-2"]["ficha_status_detail"] == ""
    assert cards["pao-joyce"]["ficha_status"] == "replaced"
    # O selo é curto (sai em iniciais maiúsculas); quem tomou o SKU vai na frase ao lado.
    assert cards["pao-joyce"]["ficha_status_label"] == "Fora da produção"
    assert cards["pao-joyce"]["ficha_status_detail"] == "Pão Joyce 2 usa este SKU"


# ── PROD-02: fórmula vazia e SKU que não existe ─────────────────────────────


def test_an_empty_formula_does_not_publish(client_as_editor):
    Product.objects.create(sku="PAO-VAZIO", name="Pão vazio")
    _recipe("pao-vazio", "Pão vazio", "PAO-VAZIO", ingredients=False)

    response = _publish(client_as_editor, "pao-vazio")

    assert response.status_code == 400, response.content
    assert response.json()["field"] == "formula"
    assert response.json()["detail"] == "Adicione ao menos um ingrediente antes de publicar."
    assert not Recipe.objects.filter(ref="pao-vazio").exists()


def test_an_unknown_sku_asks_before_creating_an_item_only_production_knows(client_as_editor):
    _recipe("pao-x", "Pão X", "XYZ-NAO-EXISTE")

    asked = _publish(client_as_editor, "pao-x")
    assert asked.status_code == 409, asked.content
    assert asked.json()["error"]["code"] == "output_sku_unknown"
    assert "XYZ-NAO-EXISTE" in asked.json()["detail"]
    assert not Recipe.objects.filter(ref="pao-x").exists()

    confirmed = _publish(client_as_editor, "pao-x", new_output_sku=True)
    assert confirmed.status_code == 200, confirmed.content
    assert Recipe.objects.get(ref="pao-x").is_active is True


@pytest.mark.parametrize("register", ["product", "material", "consumed"])
def test_a_sku_the_house_already_knows_publishes_without_asking(client_as_editor, register):
    if register == "product":
        Product.objects.create(sku="CONHECIDO", name="Conhecido")
    elif register == "material":
        Material.objects.create(sku="CONHECIDO", name="Conhecido", unit="kg")
    else:
        sheet = Recipe.objects.create(ref="consome", name="Consome", output_sku="OUTRO", batch_size=Decimal("1"))
        sheet.items.create(input_sku="CONHECIDO", quantity=Decimal("100"), unit="g")
    _recipe("conhecido", "Conhecido", "CONHECIDO")

    assert _publish(client_as_editor, "conhecido").status_code == 200


# ── PROD-03: rendimento sem leitura dupla ───────────────────────────────────


@pytest.mark.parametrize("typed", ["1,5e3", "1.500,0", "1 500", "abc"])
def test_an_ambiguous_yield_is_refused_not_guessed(client_as_editor, typed):
    response = _post(
        client_as_editor,
        LIST_URL,
        {"name": "Pão rendimento", "kind": "bread", "version": {"formula": _formula(), "yield_quantity": typed, "yield_unit": "g"}},
    )

    assert response.status_code == 400, response.content
    assert response.json()["field"] == "yield_quantity"
    assert not RecipeEntry.objects.filter(name="Pão rendimento").exists()


@pytest.mark.parametrize(("typed", "stored"), [(1500, Decimal("1500")), ("1500", Decimal("1500")), ("1,5", Decimal("1.5"))])
def test_a_plain_yield_is_stored_as_typed(client_as_editor, typed, stored):
    response = _post(
        client_as_editor,
        LIST_URL,
        {"name": "Pão rendimento", "kind": "bread", "version": {"formula": _formula(), "yield_quantity": typed, "yield_unit": "g"}},
    )

    assert response.status_code == 201 or response.status_code == 200, response.content
    assert RecipeVersion.objects.get(entry__name="Pão rendimento").yield_quantity == stored


# ── PROD-19: temperatura de etapa plausível ─────────────────────────────────


def test_a_step_at_9999_degrees_is_refused(client_as_editor):
    entry = _recipe("pao-quente", "Pão quente", "PAO-QUENTE")

    response = client_as_editor.patch(
        f"{LIST_URL}{entry.ref}/versions/1/",
        json.dumps({"steps": [{"name": "Sovar", "temperature_celsius": 9999}]}),
        content_type="application/json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["detail"] == "Etapa 1: use uma temperatura entre -40 e 450 °C."
