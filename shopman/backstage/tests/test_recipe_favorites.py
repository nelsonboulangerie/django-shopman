"""Receita favorita do operador — ``POST/DELETE /api/v1/backstage/recipes/<ref>/favorite/``.

A estrela é preferência de quem lê: pede só a leitura do inventário, é de UM
operador (outro não vê a dele), marcar e desmarcar são idempotentes, e a
leitura do inventário e da receita traz ``is_favorite`` de quem pediu.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.models import OperatorRecipeFavorite
from shopman.backstage.projections.recipe_book import build_recipe_book, build_recipe_entry
from shopman.backstage.services import recipe_favorites
from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/backstage/recipes/"


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Favoritas")


@pytest.fixture
def viewer(shop):
    user = User.objects.create_user("favorita-ana", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def other_viewer(shop):
    user = User.objects.create_user("favorita-bia", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def entries(db):
    return [
        craftsman.create_entry(ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku=""),
        craftsman.create_entry(ref="creme-patissier", name="Creme pâtissier", kind="cream", output_sku=""),
    ]


def _favorite_url(ref: str) -> str:
    return f"{LIST_URL}{ref}/favorite/"


def _cards(client) -> dict[str, bool]:
    return {card["ref"]: card["is_favorite"] for card in client.get(LIST_URL).json()["book"]["entries"]}


def test_viewer_marks_and_unmarks_idempotently(client, viewer, entries):
    client.force_login(viewer)

    for _ in range(2):
        response = client.post(_favorite_url("massa-tradicao"))
        assert response.status_code == 200, response.content
        assert response.json() == {"ref": "massa-tradicao", "is_favorite": True}
    assert OperatorRecipeFavorite.objects.filter(operator_ref="favorita-ana").count() == 1
    assert _cards(client) == {"massa-tradicao": True, "creme-patissier": False}
    assert client.get(f"{LIST_URL}massa-tradicao/").json()["entry"]["is_favorite"] is True

    for _ in range(2):
        response = client.delete(_favorite_url("massa-tradicao"))
        assert response.status_code == 200, response.content
        assert response.json() == {"ref": "massa-tradicao", "is_favorite": False}
    assert not OperatorRecipeFavorite.objects.exists()
    assert client.get(f"{LIST_URL}massa-tradicao/").json()["entry"]["is_favorite"] is False


def test_the_star_belongs_to_one_operator(client, viewer, other_viewer, entries):
    client.force_login(viewer)
    client.post(_favorite_url("creme-patissier"))

    client.force_login(other_viewer)
    assert _cards(client) == {"massa-tradicao": False, "creme-patissier": False}
    assert client.get(f"{LIST_URL}creme-patissier/").json()["entry"]["is_favorite"] is False

    client.force_login(viewer)
    assert _cards(client)["creme-patissier"] is True


def test_reading_gate_applies_to_the_star(client, shop, entries):
    bare = User.objects.create_user("favorita-sem-acesso", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.post(_favorite_url("massa-tradicao")).status_code == 403
    assert client.delete(_favorite_url("massa-tradicao")).status_code == 403
    assert not OperatorRecipeFavorite.objects.exists()


def test_unknown_recipe_is_404_in_the_canonical_dialect(client, viewer, entries):
    client.force_login(viewer)
    response = client.post(_favorite_url("nao-existe"))
    assert response.status_code == 404
    assert "detail" in response.json()
    assert not OperatorRecipeFavorite.objects.exists()


def test_archived_recipe_keeps_accepting_the_star(client, viewer, entries):
    craftsman_entry = entries[0]
    craftsman_entry.is_archived = True
    craftsman_entry.save(update_fields=["is_archived"])
    client.force_login(viewer)
    assert client.post(_favorite_url("massa-tradicao")).json()["is_favorite"] is True
    archived = client.get(LIST_URL, {"archived": "1"}).json()["book"]["entries"]
    assert [(card["ref"], card["is_favorite"]) for card in archived] == [("massa-tradicao", True)]


def test_projections_without_operator_show_no_star(entries):
    recipe_favorites.mark("favorita-ana", "massa-tradicao")
    assert {card.ref: card.is_favorite for card in build_recipe_book().entries} == {
        "massa-tradicao": False,
        "creme-patissier": False,
    }
    assert build_recipe_entry("massa-tradicao").is_favorite is False
    assert build_recipe_entry("massa-tradicao", operator_ref="favorita-ana").is_favorite is True


def test_one_row_per_operator_and_recipe(db):
    OperatorRecipeFavorite.objects.create(operator_ref="favorita-ana", entry_ref="massa-tradicao")
    with pytest.raises(IntegrityError), transaction.atomic():
        OperatorRecipeFavorite.objects.create(operator_ref="favorita-ana", entry_ref="massa-tradicao")


def test_the_star_stays_out_of_the_data_vault():
    """Preferência do operador, não curadoria: o cofre (``shop/backup``) não a carrega."""
    from shopman.shop.backup import resources

    source = open(resources.__file__, encoding="utf-8").read()
    assert "OperatorRecipeFavorite" not in source
