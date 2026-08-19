"""As telas de curadoria dos de-paras aguentam linhas e assinam a confirmação.

Confirmar — pelo formulário ou pela ação — carimba quem e quando; a ação
recusa vocabulário sem significado em vez de confirmar um vazio; rejeitar
apaga a assinatura. Com linhas de verdade, porque lista vazia esconde bug.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from shopman.offerman.models import Product

from shopman.backstage.models import (
    AliasStatus,
    CategoryAlias,
    PaymentMethodAlias,
    ProductAlias,
)
from shopman.shop.models import Shop


@pytest.fixture
def admin_user(db):
    Shop.objects.create(name="Loja")
    return User.objects.create_superuser("alias-admin", "alias@test.com", "pw")


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def rows(db):
    croissant = Product.objects.create(sku="CT", name="Croissant Tradicional")
    product = ProductAlias.objects.create(
        source="yooga", external_sku="CT", external_name="Croissant", product=croissant, score=100,
        note="SKU igual ao do catálogo",
    )
    category = CategoryAlias.objects.create(pattern="pães finos", reading="hybrid", position=10)
    payment = PaymentMethodAlias.objects.create(pattern="fiado", position=10)  # sem forma: não confirma
    return product, category, payment


def test_lists_and_forms_render_with_rows(admin_client, rows):
    product, category, payment = rows
    for name, obj in (
        ("backstage_productalias", product),
        ("backstage_categoryalias", category),
        ("backstage_paymentmethodalias", payment),
    ):
        listing = admin_client.get(reverse(f"admin:{name}_changelist"))
        assert listing.status_code == 200
        assert "proposto" in listing.content.decode()
        assert admin_client.get(reverse(f"admin:{name}_change", args=[obj.pk])).status_code == 200


def test_confirm_action_signs_and_refuses_meaningless_rows(admin_client, admin_user, rows):
    product, category, payment = rows
    response = admin_client.post(
        reverse("admin:backstage_paymentmethodalias_changelist"),
        {"action": "confirm_selected", "_selected_action": [payment.pk]},
        follow=True,
    )
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == AliasStatus.PROPOSED  # sem method_key não confirma
    assert "recusado" in response.content.decode()

    admin_client.post(
        reverse("admin:backstage_categoryalias_changelist"),
        {"action": "confirm_selected", "_selected_action": [category.pk]},
        follow=True,
    )
    category.refresh_from_db()
    assert category.status == AliasStatus.CONFIRMED
    assert category.confirmed_by == admin_user and category.confirmed_at is not None


def test_reject_action_clears_the_signature(admin_client, admin_user, rows):
    product, _category, _payment = rows
    product.mark_confirmed(admin_user)
    product.save()
    admin_client.post(
        reverse("admin:backstage_productalias_changelist"),
        {"action": "reject_selected", "_selected_action": [product.pk]},
        follow=True,
    )
    product.refresh_from_db()
    assert product.status == AliasStatus.REJECTED
    assert product.confirmed_by is None and product.confirmed_at is None
