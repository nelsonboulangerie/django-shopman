"""Nota de receita (D7): critérios editáveis no Admin e a nota 0 a 5 por versão.

``PUT /api/v1/backstage/recipes/<ref>/versions/<n>/rating/`` grava a avaliação
do operador (uma por operador e versão; avaliar de novo substitui), exige uma
nota inteira de 0 a 5 para cada critério ativo, aceita rascunho (D24) e pede só
a leitura do inventário. A receita traz, por versão, as médias por
critério e a geral, só dos critérios ativos, e a nota de quem pediu; o
inventário traz a média geral da versão atual.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from shopman.craftsman.models import RecipeEntry, RecipeVersion
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.models import RecipeRatingCriterion, RecipeVersionRating, RecipeVersionRatingScore
from shopman.backstage.projections.recipe_book import build_recipe_book, build_recipe_entry
from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/backstage/recipes/"


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Notas")


def _operator(username: str) -> User:
    return grant_production_operator(User.objects.create_user(username, password="pw", is_staff=True))


@pytest.fixture
def ana(shop):
    return _operator("nota-ana")


@pytest.fixture
def bia(shop):
    return _operator("nota-bia")


@pytest.fixture
def criteria(db):
    """Os três da migração ``backstage.0080``, na ordem do Admin."""
    return {criterion.name: criterion for criterion in RecipeRatingCriterion.objects.order_by("position")}


def _version(entry: RecipeEntry, status: str) -> RecipeVersion:
    version = craftsman.create_version(
        entry, formula={"anchor": {"kind": "total"}, "items": [], "parts": []}, yield_quantity=1, yield_unit="g",
    )
    if status != RecipeVersion.Status.DRAFT:
        RecipeVersion.objects.filter(pk=version.pk).update(status=status)
        version.refresh_from_db()
    return version


@pytest.fixture
def entry(db):
    """v1 substituída, v2 publicada (a atual), v3 rascunho."""
    entry = craftsman.create_entry(ref="baguete", name="Baguete", kind="bread", output_sku="")
    _version(entry, RecipeVersion.Status.SUPERSEDED)
    current = _version(entry, RecipeVersion.Status.PUBLISHED)
    _version(entry, RecipeVersion.Status.DRAFT)
    RecipeEntry.objects.filter(pk=entry.pk).update(current_version=current)
    entry.refresh_from_db()
    return entry


def _url(number: int, ref: str = "baguete") -> str:
    return f"{LIST_URL}{ref}/versions/{number}/rating/"


def _rate(client, number: int, scores: dict, ref: str = "baguete"):
    return client.put(_url(number, ref), json.dumps({"scores": scores}), content_type="application/json")


def _scores(criteria, sabor, textura, aparencia) -> dict:
    return {
        str(criteria["Sabor"].pk): sabor,
        str(criteria["Textura"].pk): textura,
        str(criteria["Aparência"].pk): aparencia,
    }


def _rating_of(body: dict, number: int) -> dict:
    return next(item for item in body["entry"]["ratings"] if item["version_number"] == number)


def test_the_migration_seeds_three_editable_criteria(criteria):
    assert list(criteria) == ["Sabor", "Textura", "Aparência"]
    assert all(criterion.is_active and criterion.description for criterion in criteria.values())


def test_operators_rate_a_version_and_the_entry_carries_the_averages(client, ana, bia, entry, criteria):
    client.force_login(ana)
    response = _rate(client, 2, _scores(criteria, 5, 4, 3))
    assert response.status_code == 200, response.content
    client.force_login(bia)
    response = _rate(client, 2, _scores(criteria, 4, 4, 0))
    assert response.status_code == 200, response.content

    body = response.json()
    assert [item["name"] for item in body["entry"]["rating_criteria"]] == ["Sabor", "Textura", "Aparência"]
    # Toda versão aparece, o rascunho v3 incluído (D24).
    assert [item["version_number"] for item in body["entry"]["ratings"]] == [3, 2, 1]
    rating = _rating_of(body, 2)
    assert rating["version_ref"] == "baguete@2"
    assert rating["ratings_count"] == 2
    assert rating["ratings_count_display"] == "2 avaliações"
    assert rating["overall_display"] == "3,3"  # (5+4+3+4+4+0) / 6
    assert [(c["name"], c["average_display"], c["count"], c["my_score"]) for c in rating["criteria"]] == [
        ("Sabor", "4,5", 2, 4),
        ("Textura", "4", 2, 4),
        ("Aparência", "1,5", 2, 0),
    ]
    assert rating["rated_by_me"] is True
    assert rating["my_rated_at_display"]

    untouched = _rating_of(body, 1)
    assert untouched["ratings_count"] == 0
    assert untouched["ratings_count_display"] == "Nenhuma avaliação"
    assert untouched["overall_display"] == ""
    assert untouched["rated_by_me"] is False
    assert {c["my_score"] for c in untouched["criteria"]} == {None}


def test_rating_again_replaces_the_operator_rating(client, ana, entry, criteria):
    client.force_login(ana)
    assert _rate(client, 2, _scores(criteria, 1, 1, 1)).status_code == 200
    body = _rate(client, 2, _scores(criteria, 5, 5, 5)).json()

    assert RecipeVersionRating.objects.count() == 1
    assert RecipeVersionRatingScore.objects.count() == 3
    rating = _rating_of(body, 2)
    assert rating["ratings_count"] == 1
    assert rating["overall_display"] == "5"


def test_who_rated_and_when_is_recorded(client, ana, entry, criteria):
    client.force_login(ana)
    _rate(client, 1, _scores(criteria, 3, 3, 3))
    rating = RecipeVersionRating.objects.get()
    assert (rating.entry_ref, rating.version_number, rating.operator_ref) == ("baguete", 1, "nota-ana")
    assert rating.created_at and rating.updated_at
    assert rating.version_ref == "baguete@1"


def test_a_draft_is_rated_too(client, ana, entry, criteria):
    """D24 (dono, 01/10/2026): o rascunho também recebe nota."""
    client.force_login(ana)
    response = _rate(client, 3, _scores(criteria, 5, 4, 3))
    assert response.status_code == 200, response.content
    rating = _rating_of(response.json(), 3)
    assert rating["ratings_count"] == 1
    assert rating["overall_display"] == "4"


def test_deleting_a_version_takes_its_ratings_along(client, ana, entry, criteria):
    """Versão apagada (D11) leva a nota; o rascunho novo, com o mesmo número, nasce sem nota."""
    client.force_login(ana)
    assert _rate(client, 3, _scores(criteria, 5, 5, 5)).status_code == 200
    assert _rate(client, 2, _scores(criteria, 1, 1, 1)).status_code == 200
    RecipeVersion.objects.get(entry=entry, number=3).delete()
    assert list(RecipeVersionRating.objects.values_list("version_number", flat=True)) == [2]
    reborn = _version(entry, RecipeVersion.Status.DRAFT)
    assert reborn.number == 3
    assert _rating_of(client.get(f"{LIST_URL}baguete/").json(), 3)["ratings_count"] == 0
    RecipeEntry.objects.filter(pk=entry.pk).delete()
    assert not RecipeVersionRating.objects.exists()


@pytest.mark.parametrize(
    "scores_of",
    [
        lambda c: {},
        lambda c: {str(c["Sabor"].pk): 5, str(c["Textura"].pk): 5},  # falta Aparência
        lambda c: _scores(c, 6, 5, 5),
        lambda c: _scores(c, -1, 5, 5),
        lambda c: _scores(c, 4.5, 5, 5),
        lambda c: _scores(c, True, 5, 5),
        lambda c: {**_scores(c, 5, 5, 5), "999": 3},
    ],
)
def test_one_whole_score_from_0_to_5_for_each_active_criterion(client, ana, entry, criteria, scores_of):
    client.force_login(ana)
    response = _rate(client, 2, scores_of(criteria))
    assert response.status_code == 400, response.content
    assert response.json()["field"].startswith("scores")
    assert not RecipeVersionRating.objects.exists()


def test_scores_must_be_an_object(client, ana, entry, criteria):
    client.force_login(ana)
    response = client.put(_url(2), json.dumps({"scores": [5, 5, 5]}), content_type="application/json")
    assert response.status_code == 400


def test_an_inactive_criterion_leaves_the_screen_and_the_averages(client, ana, entry, criteria):
    client.force_login(ana)
    _rate(client, 2, _scores(criteria, 5, 5, 0))
    RecipeRatingCriterion.objects.filter(pk=criteria["Aparência"].pk).update(is_active=False)

    body = client.get(f"{LIST_URL}baguete/").json()
    assert [item["name"] for item in body["entry"]["rating_criteria"]] == ["Sabor", "Textura"]
    rating = _rating_of(body, 2)
    assert rating["overall_display"] == "5"
    assert [c["name"] for c in rating["criteria"]] == ["Sabor", "Textura"]
    # A nota antiga fica guardada.
    assert RecipeVersionRatingScore.objects.filter(criterion=criteria["Aparência"]).count() == 1

    # E a próxima avaliação não pede (nem aceita) o critério inativo.
    assert _rate(client, 2, {str(criteria["Sabor"].pk): 4, str(criteria["Textura"].pk): 4}).status_code == 200
    assert _rate(client, 2, _scores(criteria, 4, 4, 4)).status_code == 400


def test_no_active_criterion_is_a_state_conflict(client, ana, entry, criteria):
    RecipeRatingCriterion.objects.update(is_active=False)
    client.force_login(ana)
    assert _rate(client, 2, {}).status_code == 409


def test_rating_needs_only_the_reading_gate(client, shop, entry, criteria):
    outsider = User.objects.create_user("nota-fora", password="pw", is_staff=True)
    client.force_login(outsider)
    assert _rate(client, 2, _scores(criteria, 5, 5, 5)).status_code == 403


def test_missing_entry_or_version_is_404(client, ana, entry, criteria):
    client.force_login(ana)
    assert _rate(client, 9, _scores(criteria, 5, 5, 5)).status_code == 404
    assert _rate(client, 1, _scores(criteria, 5, 5, 5), ref="nao-existe").status_code == 404


def test_the_inventory_card_carries_the_current_version_average(client, ana, bia, entry, criteria):
    client.force_login(ana)
    _rate(client, 1, _scores(criteria, 0, 0, 0))  # versão antiga não conta no cartão
    _rate(client, 2, _scores(criteria, 5, 4, 3))
    client.force_login(bia)
    _rate(client, 2, _scores(criteria, 3, 3, 3))

    card = next(card for card in build_recipe_book().entries if card.ref == "baguete")
    assert (card.rating_display, card.rating_count) == ("3,5", 2)

    other = craftsman.create_entry(ref="sem-nota", name="Sem nota", kind="bread", output_sku="")
    card = next(card for card in build_recipe_book().entries if card.ref == other.ref)
    assert (card.rating_display, card.rating_count) == ("", 0)


def test_my_score_is_mine(client, ana, bia, entry, criteria):
    client.force_login(ana)
    _rate(client, 2, _scores(criteria, 5, 5, 5))

    projection = build_recipe_entry("baguete", operator_ref="nota-bia")
    rating = next(item for item in projection.ratings if item.version_number == 2)
    assert rating.ratings_count == 1
    assert rating.rated_by_me is False
    assert {c.my_score for c in rating.criteria} == {None}


def test_one_rating_per_operator_and_version_in_the_database(entry):
    RecipeVersionRating.objects.create(entry_ref="baguete", version_number=2, operator_ref="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        RecipeVersionRating.objects.create(entry_ref="baguete", version_number=2, operator_ref="x")


def test_score_out_of_range_is_refused_by_the_database(entry, criteria):
    rating = RecipeVersionRating.objects.create(entry_ref="baguete", version_number=2, operator_ref="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        RecipeVersionRatingScore.objects.create(rating=rating, criterion=criteria["Sabor"], score=6)
