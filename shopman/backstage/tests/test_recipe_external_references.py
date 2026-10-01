"""Fontes da receita (D6; "Fontes" na tela, D24): ``PATCH recipes/<ref>/`` com ``external_references``.

Moram em ``RecipeEntry.meta["external_references"]``, são da receita (não da
versão), a lista inteira se substitui, a forma é validada na porta (título
obrigatório, link só http/https, tamanhos máximos) e a leitura nunca entrega
um link que a porta recusaria, mesmo que o Admin tenha gravado um.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.craftsman.models import RecipeEntry, RecipeVersion
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.projections.recipe_book import build_recipe_entry
from shopman.backstage.services import recipe_external_references as references
from shopman.backstage.services.exceptions import RecipeBookServiceError
from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/recipes/massa-tradicao/"


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Referências")


@pytest.fixture
def viewer(shop):
    return grant_production_operator(User.objects.create_user("ref-viewer", password="pw", is_staff=True))


@pytest.fixture
def editor(shop):
    from shopman.shop.models import Shop

    user = grant_production_operator(User.objects.create_user("ref-editor", password="pw", is_staff=True))
    user.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shop), codename="manage_production")
    )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def entry(db):
    entry = craftsman.create_entry(ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="")
    entry.meta = {"other": "fica"}
    entry.save(update_fields=["meta"])
    return entry


def _patch(client, body):
    return client.patch(URL, json.dumps(body), content_type="application/json")


BOOK = {"title": "Tartine Bread, Chad Robertson", "note": "p. 48, a fórmula base"}
VIDEO = {"title": "Laminação da massa", "url": "https://www.youtube.com/watch?v=abc", "note": ""}


def test_editor_adds_and_removes_references_and_the_rest_of_meta_survives(client, editor, entry):
    client.force_login(editor)

    response = _patch(client, {"external_references": [BOOK, VIDEO]})
    assert response.status_code == 200, response.content
    body = response.json()["entry"]["external_references"]
    assert body == [
        {"title": "Tartine Bread, Chad Robertson", "url": "", "host_display": "", "note": "p. 48, a fórmula base"},
        {"title": "Laminação da massa", "url": "https://www.youtube.com/watch?v=abc", "host_display": "youtube.com",
         "note": ""},
    ]
    entry.refresh_from_db()
    # Chave vazia não se grava; o resto do meta fica.
    assert entry.meta == {
        "other": "fica",
        "external_references": [
            {"title": "Tartine Bread, Chad Robertson", "note": "p. 48, a fórmula base"},
            {"title": "Laminação da massa", "url": "https://www.youtube.com/watch?v=abc"},
        ],
    }

    response = _patch(client, {"external_references": [VIDEO]})
    assert [item["title"] for item in response.json()["entry"]["external_references"]] == ["Laminação da massa"]

    response = _patch(client, {"external_references": []})
    assert response.json()["entry"]["external_references"] == []
    entry.refresh_from_db()
    assert entry.meta == {"other": "fica"}


def test_references_belong_to_the_entry_not_to_the_published_version(client, editor, entry):
    """Acrescentar fonte depois de publicar não toca a versão: a fonte é da receita inteira."""
    version = craftsman.create_version(
        entry, formula={"anchor": {"kind": "total"}, "items": [], "parts": []}, yield_quantity=1, yield_unit="g",
    )
    RecipeVersion.objects.filter(pk=version.pk).update(status=RecipeVersion.Status.PUBLISHED)
    client.force_login(editor)

    assert _patch(client, {"external_references": [BOOK]}).status_code == 200
    version.refresh_from_db()
    assert "external_references" not in (version.meta or {})


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ("um livro", "external_references"),
        ([{"title": ""}], "external_references[0].title"),
        (["Tartine"], "external_references[0]"),
        ([BOOK, {"title": "x", "url": "javascript:alert(1)"}], "external_references[1].url"),
        ([{"title": "x", "url": "ftp://example.com/a"}], "external_references[0].url"),
        ([{"title": "x", "url": "https://"}], "external_references[0].url"),
        ([{"title": "x", "url": "https://exemplo.com/a b"}], "external_references[0].url"),
        ([{"title": "x" * 201}], "external_references[0].title"),
        ([{"title": "x", "note": "y" * 501}], "external_references[0].note"),
        ([{"title": "x", "page": 3}], "external_references[0].page"),
        ([{"title": 3}], "external_references[0].title"),
        ([{"title": f"t{i}"} for i in range(31)], "external_references"),
    ],
)
def test_the_shape_is_validated_and_points_at_the_item(client, editor, entry, payload, field):
    client.force_login(editor)
    response = _patch(client, {"external_references": payload})
    assert response.status_code == 400, response.content
    assert response.json()["field"] == field
    entry.refresh_from_db()
    assert "external_references" not in entry.meta


def test_editing_references_needs_the_edit_permission(client, viewer, entry):
    client.force_login(viewer)
    assert _patch(client, {"external_references": [BOOK]}).status_code == 403


def test_reading_drops_what_the_door_would_refuse(entry):
    """O Admin edita ``meta`` à mão: link inseguro não chega ao ``href`` da tela."""
    RecipeEntry.objects.filter(pk=entry.pk).update(meta={"external_references": [
        {"title": "Bom", "url": "http://exemplo.com.br/receita"},
        {"title": "Perigoso", "url": "javascript:alert(1)"},
        {"title": ""},
        "solto",
        {"title": "Sem link"},
    ]})
    projection = build_recipe_entry(entry.ref)
    assert [(item.title, item.url, item.host_display) for item in projection.external_references] == [
        ("Bom", "http://exemplo.com.br/receita", "exemplo.com.br"),
        ("Perigoso", "", ""),
        ("Sem link", "", ""),
    ]


def test_validate_trims_and_keeps_only_written_keys():
    assert references.validate([{"title": "  Livro  ", "url": " https://a.b/c ", "note": "  "}]) == [
        {"title": "Livro", "url": "https://a.b/c"},
    ]
    assert references.validate(None) == []
    with pytest.raises(RecipeBookServiceError):
        references.validate({"title": "x"})
