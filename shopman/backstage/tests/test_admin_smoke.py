"""Admin smoke tests (WP-C4).

Safety net for the whole Django Admin/Unfold surface: every registered
``ModelAdmin`` must render its changelist and add form without a server error,
and every read-only ``admin_console`` console page must return 200. This catches
broken ``list_display``/``fieldsets``, orphan actions, widget/form errors and bad
imports — the kind of breakage that unit tests of individual admins miss because
they never exercise the real request path.

It was this test that surfaced the offerman Product 500 (nutrition virtual fields
injected in ``__init__`` were invisible to ``modelform_factory``).
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import NoReverseMatch, reverse
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop

# Built at import time — pytest-django has already run ``django.setup()`` (which
# triggers admin autodiscover) before this module is collected.
_REGISTERED_MODELS = sorted(
    admin.site._registry.keys(),
    key=lambda m: (m._meta.app_label, m._meta.model_name),
)


# Core packages (packages/*). Every model whose admin lives in one of these is a
# Core model and MUST be registered with an Unfold ``ModelAdmin`` at deployment
# runtime — never a silent vanilla fallback (which happens if a contrib/admin_unfold
# app drops out of INSTALLED_APPS). See test_core_models_use_unfold_admin.
_CORE_MODULE_PREFIXES = (
    "shopman.refs.",
    "shopman.offerman.",
    "shopman.stockman.",
    "shopman.craftsman.",
    "shopman.orderman.",
    "shopman.guestman.",
    "shopman.doorman.",
    "shopman.payman.",
    "shopman.utils.",
)

_CORE_MODELS = [
    model for model in _REGISTERED_MODELS
    if model.__module__.startswith(_CORE_MODULE_PREFIXES)
]


def _model_id(model) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


def _admin_url(model, view: str, *args) -> str:
    return reverse(
        f"admin:{model._meta.app_label}_{model._meta.model_name}_{view}", args=args
    )


@pytest.fixture
def admin_client(client, db):
    Shop.objects.create(name="Loja")
    user = User.objects.create_superuser("smoke-admin", "smoke@test.com", "pw")
    client.force_login(user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("model", _REGISTERED_MODELS, ids=_model_id)
def test_changelist_renders(admin_client, model):
    """Every registered model's changelist must not 500."""
    response = admin_client.get(_admin_url(model, "changelist"), follow=True)
    assert response.status_code < 500, (
        f"{_model_id(model)} changelist returned {response.status_code}"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("model", _REGISTERED_MODELS, ids=_model_id)
def test_add_form_renders(admin_client, model):
    """Every registered model's add form must not 500 (403 = add disabled, OK)."""
    try:
        url = _admin_url(model, "add")
    except NoReverseMatch:
        pytest.skip("model has no add view")
    response = admin_client.get(url, follow=True)
    assert response.status_code < 500, (
        f"{_model_id(model)} add form returned {response.status_code}"
    )


@pytest.mark.django_db
def test_order_changelist_renders_with_an_active_order(admin_client):
    """A changelist precisa aguentar LINHAS, não só a lista vazia.

    ``test_changelist_renders`` roda com o banco limpo, então nenhuma coluna
    calculada por linha chega a ser exercitada. Foi essa fresta que deixou passar
    uma coluna que revertia ``admin_console_order_detail`` — URL removida junto
    com o console de pedidos: qualquer pedido ativo na lista derrubava a tela com
    NoReverseMatch, e só não aparecia porque a tela abria filtrada no dia de hoje.
    """
    Order.objects.create(
        ref="SMOKE-ACTIVE",
        channel_ref="web",
        session_key="smoke-active-session",
        status=Order.Status.PREPARING,
        total_q=2500,
        currency="BRL",
        data={"delivery_date": "2026-08-14", "is_preorder": True},
    )

    response = admin_client.get(_admin_url(Order, "changelist"))

    assert response.status_code == 200
    assert "SMOKE-ACTIVE" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_session_changelist_renders_with_a_session(admin_client):
    """Mesma fresta da lista de pedidos, outra trilha.

    O admin de sessões pedia ``prefetch_related("items")``, mas ``Session.items``
    é uma property que remonta as linhas em memória, não uma relação. O
    ValueError só é levantado depois que a query devolve alguma linha — com o
    banco vazio, o prefetch nem roda.
    """
    from shopman.orderman.models import Session

    Session.objects.create(
        session_key="smoke-session-list",
        channel_ref="pdv",
        handle_type="tab",
        handle_ref="M1",
    )

    response = admin_client.get(_admin_url(Session, "changelist"))

    assert response.status_code == 200
    assert "smoke-session-list" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_change_form_renders_for_seeded_order(admin_client):
    """The Order change form (rich display methods incl. cross-package payment
    info) must render against a real object."""
    order = Order.objects.create(
        ref="SMOKE-ORDER",
        channel_ref="web",
        session_key="smoke-session",
        status=Order.Status.ACCEPTED,
        total_q=3000,
        currency="BRL",
        data={"payment": {"method": "cash"}},
    )
    OrderItem.objects.create(
        order=order,
        line_id="1",
        sku="SMOKE-SKU",
        name="Smoke item",
        qty=2,
        unit_price_q=1500,
        line_total_q=3000,
    )
    response = admin_client.get(_admin_url(order.__class__, "change", order.pk))
    assert response.status_code == 200
    assert "Pagamentos" in response.content.decode("utf-8")


@pytest.mark.parametrize("model", _CORE_MODELS, ids=_model_id)
def test_core_models_use_unfold_admin(model):
    """Contract (WP-C3): every Core model is registered with an Unfold ModelAdmin.

    Each Core package ships a plain ``admin.py`` and (usually) a
    ``contrib/admin_unfold`` app that unregisters the plain admin and re-registers
    an Unfold one. If the contrib app silently drops out of INSTALLED_APPS, the
    admin degrades to vanilla Django with no warning. This guard fails loudly so
    that can never reach production unnoticed — no allowlist, no exceptions.
    """
    from unfold.admin import ModelAdmin as UnfoldModelAdmin

    registered = admin.site._registry[model]
    assert isinstance(registered, UnfoldModelAdmin), (
        f"{_model_id(model)} caiu em admin vanilla "
        f"({type(registered).__module__}.{type(registered).__name__}); "
        "registre-o com unfold.admin.ModelAdmin (ou via contrib/admin_unfold)."
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        # O console de produção saiu (WP-ADM-7d, → Produção) e o fechamento
        # também (WP-ADM-3, → antesala do PDV); resta o catálogo de copy.
        "admin_console_copy_catalog",
    ],
)
def test_admin_console_pages_render(admin_client, url_name):
    """Custom admin_console operational pages must render (200)."""
    response = admin_client.get(reverse(url_name), follow=True)
    assert response.status_code == 200, (
        f"{url_name} returned {response.status_code}"
    )
