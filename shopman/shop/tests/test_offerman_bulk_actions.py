"""Bulk actions do admin de Product disparam product_updated (re-projeção externa).

Regressão: publish/unpublish/pause/resume usavam queryset.update() → pulavam
Product.save() → product_updated nunca disparava → o iFood (e outros canais
projetados) NÃO retraía o produto despublicado em massa. Roda no framework porque
o admin de Product depende de django.contrib.admin/import_export.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from shopman.offerman.contrib.admin_unfold.admin import ProductAdmin, ProductArchiveFilter
from shopman.offerman.models import Product
from shopman.offerman.signals import product_updated

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


class _Req:
    pass


@pytest.fixture
def product_admin():
    a = ProductAdmin(Product, AdminSite())
    a.message_user = lambda *args, **kwargs: None
    return a


def _capture():
    seen = []

    def receiver(sender, sku, **kwargs):
        seen.append(sku)

    product_updated.connect(receiver, weak=False)
    return seen, receiver


def test_unpublish_bulk_fires_product_updated(product_admin):
    p1 = Product.objects.create(sku="BULKAA", name="A", unit="un", base_price_q=100, is_published=True)
    p2 = Product.objects.create(sku="BULKBB", name="B", unit="un", base_price_q=100, is_published=True)
    seen, receiver = _capture()
    try:
        product_admin.unpublish_products(_Req(), Product.objects.filter(pk__in=[p1.pk, p2.pk]))
    finally:
        product_updated.disconnect(receiver)

    p1.refresh_from_db()
    assert p1.is_published is False
    assert set(seen) == {"BULKAA", "BULKBB"}


def test_pause_bulk_skips_noop(product_admin):
    p1 = Product.objects.create(sku="BULKCC", name="C", unit="un", base_price_q=100, is_sellable=True)
    p2 = Product.objects.create(sku="BULKDD", name="D", unit="un", base_price_q=100, is_sellable=False)
    seen, receiver = _capture()
    try:
        product_admin.pause_products(_Req(), Product.objects.filter(pk__in=[p1.pk, p2.pk]))
    finally:
        product_updated.disconnect(receiver)

    assert seen == ["BULKCC"]  # p2 já era não-vendável → sem re-projeção


def test_archive_filter_hides_archived_by_default_and_can_show_only_archived(product_admin):
    active = Product.objects.create(sku="FILTER-A", name="Ativo")
    archived = Product.objects.create(sku="FILTER-B", name="Arquivado", is_active=False)

    default_filter = ProductArchiveFilter(_Req(), {}, Product, product_admin)
    archived_filter = ProductArchiveFilter(
        _Req(), {"arquivados": ["sim"]}, Product, product_admin
    )

    assert list(default_filter.queryset(_Req(), Product.objects.all())) == [active]
    assert list(archived_filter.queryset(_Req(), Product.objects.all())) == [archived]


def test_archive_and_unarchive_actions_preserve_toggles_and_fire_reconcile(
    product_admin, monkeypatch
):
    product = Product.objects.create(
        sku="ACTION-ARCHIVE",
        name="Produto",
        is_published=False,
        is_sellable=True,
    )
    product_admin.log_change = lambda *args, **kwargs: None
    monkeypatch.setattr(
        "shopman.offerman.contrib.admin_unfold.admin.messages.success",
        lambda *args, **kwargs: None,
    )
    seen, receiver = _capture()
    try:
        ProductAdmin.archive_product.__wrapped__(product_admin, _Req(), None, product.pk)
        ProductAdmin.unarchive_product.__wrapped__(product_admin, _Req(), None, product.pk)
    finally:
        product_updated.disconnect(receiver)

    product.refresh_from_db()
    assert product.is_active is True
    assert product.is_published is False
    assert product.is_sellable is True
    assert seen == ["ACTION-ARCHIVE", "ACTION-ARCHIVE"]


def test_admin_changelist_hides_archived_until_filter_is_requested(admin_client):
    Shop.objects.create(name="Loja")
    Product.objects.create(sku="ADMIN-ACTIVE", name="Produto visível")
    Product.objects.create(sku="ADMIN-ARCHIVED", name="Produto guardado", is_active=False)
    url = reverse("admin:offerman_product_changelist")

    default_html = admin_client.get(url).content.decode()
    archived_html = admin_client.get(url, {"arquivados": "sim"}).content.decode()

    assert "ADMIN-ACTIVE" in default_html
    assert "ADMIN-ARCHIVED" not in default_html
    assert "ADMIN-ACTIVE" not in archived_html
    assert "ADMIN-ARCHIVED" in archived_html


def test_admin_detail_actions_require_dialog_post_and_preserve_toggles(admin_client):
    Shop.objects.create(name="Loja")
    product = Product.objects.create(
        sku="ADMIN-DIALOG",
        name="Produto",
        is_published=False,
        is_sellable=True,
    )
    archive_url = f"/admin/offerman/product/{product.pk}/archive/"
    unarchive_url = f"/admin/offerman/product/{product.pk}/unarchive/"

    confirmation = admin_client.get(archive_url)
    product.refresh_from_db()
    assert confirmation.status_code == 200
    assert "Arquivar este produto?" in confirmation.content.decode()
    assert product.is_active is True

    assert admin_client.post(archive_url, {"_form_submitted": "true"}).status_code == 302
    product.refresh_from_db()
    assert product.is_active is False
    assert product.is_published is False
    assert product.is_sellable is True
    assert admin_client.post(unarchive_url, {"_form_submitted": "true"}).status_code == 302
    product.refresh_from_db()
    assert product.is_active is True
    assert product.is_published is False
    assert product.is_sellable is True
