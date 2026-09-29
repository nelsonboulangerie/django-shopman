"""A revisão do insumo usa a ação de detalhe oficial e exige change_material."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from shopman.buyman.models import Material

from shopman.shop.models import Shop
from shopman.shop.services import material_enrichment as me
from shopman.shop.services import product_enrichment as pe


def _url(pk) -> str:
    return f"/admin/buyman/material/{pk}/gtin-suggestion/"


def _staff(username: str, *codenames: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="buyman", codename=codename)
        )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def material(db):
    Shop.objects.create(name="Loja")
    item = Material.objects.create(
        sku="FARINHA", name="Farinha cadastrada", unit="kg", metadata={}
    )
    suggestion = pe.EnrichmentSuggestion(gtin="7898708850309")
    suggestion.add("name", "FARINHA T55 1KG", pe.SOURCE_COSMOS)
    suggestion.add("ncm", "11010010", pe.SOURCE_NFE)
    suggestion.add("allergens", ["glúten"], pe.SOURCE_OFF)
    item.metadata = me.merge_into_metadata(item.metadata, suggestion)
    item.save()
    return item


@pytest.mark.django_db
def test_view_only_user_cannot_reach_action(client, material):
    client.force_login(_staff("so-ve-insumo", "view_material"))
    assert client.get(_url(material.pk)).status_code == 403


@pytest.mark.django_db
def test_get_renders_switches_without_applying(client, material):
    client.force_login(_staff("editor-insumo", "view_material", "change_material"))

    response = client.get(_url(material.pk))

    html = response.content.decode()
    assert response.status_code == 200
    for field in ("accept_name", "replace_name", "accept_ncm", "accept_allergens"):
        assert f'name="{field}"' in html
    material.refresh_from_db()
    assert material.name == "Farinha cadastrada"
    assert "ncm" not in material.metadata


@pytest.mark.django_db
def test_post_applies_only_selected_field(client, material):
    client.force_login(_staff("editor-insumo-2", "view_material", "change_material"))

    response = client.post(
        _url(material.pk), {"_form_submitted": "true", "accept_ncm": "on", "accept_name": "on"}
    )

    assert response.status_code in (204, 302)
    material.refresh_from_db()
    assert material.metadata["ncm"] == "11010010"
    assert material.name == "Farinha cadastrada"
    assert material.metadata["enrichment"]["accepted"]["ncm"]["accepted_by"] == "editor-insumo-2"
