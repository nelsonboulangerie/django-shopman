"""O caixa no Admin depois do cashman: turno do pacote, terminal da superfície.

- ``cashman.Shift`` é a tela de auditoria (readonly, linha do tempo inline).
- ``cashman.Terminal`` é registrado por cima pelo backstage, com o form da gaveta.
- Os models legados do caixa (``CashShift``/``CashMovement``/``POSTerminal``)
  saem do Admin; seguem no banco até o WP-5, sem tela.
- "Movimentações de caixa" some do menu: a movimentação é linha do turno.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import NoReverseMatch, reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift, Terminal

from shopman.backstage.admin.terminal import TerminalAdmin, TerminalForm

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _shop():
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")  # satisfaz o OnboardingMiddleware


@pytest.fixture
def closed_shift():
    terminal = Terminal.objects.create(ref="t1", label="Caixa 1", channel_ref="pdv")
    operator = User.objects.create_user("op-user", "op@test.com", "pw", is_staff=True)
    manager = User.objects.create_user("gerente", "g@test.com", "pw", is_staff=True)
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=10000)
    cash.record(Entry.Kind.CASH_OUT, shift=shift, operator=operator, approved_by=manager, amount_q=-250, reason="Cofre")
    cash.close_shift(shift, counted_q=9700, actor=operator)
    return shift


def _req():
    request = RequestFactory().get("/")
    request.user = User(is_superuser=True, is_staff=True)
    return request


def test_legacy_cash_models_are_not_in_the_admin():
    # Por rótulo, sem importar os models: eles morrem no WP-5 e este teste não
    # deve precisar mudar quando isso acontecer.
    registered = {model._meta.label_lower for model in admin.site._registry}
    for label in ("backstage.cashshift", "backstage.cashmovement", "backstage.posterminal"):
        assert label not in registered, f"{label} ainda registrado no Admin"


def test_terminal_admin_is_the_backstage_subclass_with_the_drawer_form():
    registered = admin.site._registry[Terminal]
    assert isinstance(registered, TerminalAdmin)
    assert registered.form is TerminalForm
    assert "drawer_adapter" in TerminalForm.base_fields


def test_shift_admin_is_a_readonly_trail():
    registered = admin.site._registry[Shift]
    assert registered.has_add_permission(_req()) is False
    assert registered.has_change_permission(_req()) is False
    assert registered.has_delete_permission(_req()) is False


def test_shift_changelist_shows_the_ledger_numbers(client, closed_shift):
    """Esperado, contado e diferença aparecem na RETAGUARDA (auditoria), somados do livro."""
    admin_user = User.objects.create_superuser("cash-admin", "c@test.com", "pw")
    client.force_login(admin_user)

    resp = client.get(reverse("admin:cashman_shift_changelist"))

    assert resp.status_code == 200
    body = resp.content.decode()
    assert "97,50" in body  # esperado: 100,00 − 2,50
    assert "97,00" in body  # contado
    assert "0,50" in body  # diferença


def test_shift_change_page_lists_the_timeline(client, closed_shift):
    admin_user = User.objects.create_superuser("cash-admin", "c@test.com", "pw")
    client.force_login(admin_user)

    resp = client.get(reverse("admin:cashman_shift_change", args=[closed_shift.pk]))

    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Cofre" in body
    assert "autorizado por gerente" in body


def test_movement_screen_is_gone_from_the_admin():
    with pytest.raises(NoReverseMatch):
        reverse("admin:backstage_cashmovement_changelist")
    with pytest.raises(NoReverseMatch):
        reverse("admin:backstage_cashshift_changelist")
    with pytest.raises(NoReverseMatch):
        reverse("admin:backstage_posterminal_changelist")


def test_navigation_points_to_cashman_and_drops_the_movement_item():
    from shopman.backstage.admin.navigation import get_sidebar_navigation

    request = RequestFactory().get("/admin/")
    request.user = User.objects.create_superuser("nav-admin", "n@test.com", "pw")
    groups = get_sidebar_navigation(request)
    audit = next(group for group in groups if group["title"] == "Auditoria")
    titles = [item["title"] for item in audit["items"]]

    assert "Turnos de caixa" in titles
    assert "Movimentações de caixa" not in titles
    turnos = next(item for item in audit["items"] if item["title"] == "Turnos de caixa")
    assert turnos["link"] == reverse("admin:cashman_shift_changelist")
