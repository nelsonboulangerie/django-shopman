"""Textos da interface — página Admin canônica (navegação chave↔tela)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from shopman.backstage.projections.copy_catalog import build_copy_catalog


@pytest.fixture()
def staff_client(client, db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
    user = get_user_model().objects.create_superuser("copyadmin", "c@example.com", "pw")
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_projection_groups_keys_by_surface_and_screen():
    catalog = build_copy_catalog()

    # A fusão PAYMENT-TRACKING-MERGE apagou a máquina de copy da tela de pagamento
    # (~60 chaves); o registro segue com centenas de chaves mapeadas.
    assert catalog.total_keys >= 280
    assert catalog.mapped_keys >= 280
    labels = {(group.surface, group.screen) for group in catalog.groups}
    assert ("Loja", "Página do produto") in labels
    pdp = next(g for g in catalog.groups if g.screen == "Página do produto")
    assert "PRODUCT_CROSS_SELL_HEADING" in [row.key for row in pdp.rows]


@pytest.mark.django_db
def test_projection_search_finds_key_by_visible_text():
    # O operador procura pelo TEXTO que viu na tela, não pela chave.
    catalog = build_copy_catalog(q="Você também pode gostar")

    rows = [row.key for group in catalog.groups for row in group.rows]
    assert rows == ["PRODUCT_CROSS_SELL_HEADING"]


@pytest.mark.django_db
def test_projection_counts_active_overrides():
    from shopman.shop.models import OmotenashiCopy

    OmotenashiCopy.objects.create(
        key="PRODUCT_CROSS_SELL_HEADING", moment="*", audience="*",
        title="Combina com", active=True,
    )
    catalog = build_copy_catalog(q="PRODUCT_CROSS_SELL_HEADING")
    row = next(row for group in catalog.groups for row in group.rows)
    assert row.override_count == 1
    assert catalog.active_overrides == 1


@pytest.mark.django_db
def test_catalog_page_renders_grouped_by_screen(staff_client):
    resp = staff_client.get(reverse("admin_console_copy_catalog"))

    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Textos da interface" in content
    assert "Página do produto" in content
    assert "PRODUCT_CROSS_SELL_HEADING" in content
    # Link de personalizar já leva com a chave preenchida.
    assert "/admin/shop/omotenashicopy/add/?key=PRODUCT_CROSS_SELL_HEADING" in content


@pytest.mark.django_db
def test_catalog_page_filters_by_query(staff_client):
    resp = staff_client.get(
        reverse("admin_console_copy_catalog"), {"q": "Você também pode gostar"}
    )

    content = resp.content.decode()
    assert "PRODUCT_CROSS_SELL_HEADING" in content
    assert "TRACKING_STEP_RECEIVED" not in content


@pytest.mark.django_db
def test_catalog_requires_view_permission(client, db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
    user = get_user_model().objects.create_user("semperm", password="x", is_staff=True)
    client.force_login(user)

    resp = client.get(reverse("admin_console_copy_catalog"))

    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_configuration_opens_the_texts_page_not_the_raw_changelist():
    """A porta dos textos é a tela que navega por superfície → tela, não a tabela
    de chaves: quem quer mudar uma frase reconhece a tela onde ela aparece, não a
    constante que a nomeia.

    Desde o WP-ADM-R6 essa porta fica na Configuração, não no menu: a projection
    do hub é quem declara para onde o cartão aponta.
    """
    from shopman.backstage.projections.settings_hub import build_settings_hub

    cards = {
        card["label"]: card["url"]
        for group in build_settings_hub()["groups"]
        for card in group["cards"]
    }

    assert cards["Textos da interface"].endswith("/admin/configuracao/copy/")
