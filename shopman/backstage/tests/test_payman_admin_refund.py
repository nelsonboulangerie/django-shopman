"""Estorno no Admin de cobranças: permissão dedicada e segunda confirmação no diálogo.

As duas ações (`refund` = total, `refund-amount` = um valor) são dialog actions
oficiais do Unfold. Quem estorna é quem tem `payman.refund_paymentintent`; ver a
cobrança (`view_paymentintent`) não basta. E o estorno só acontece com a
confirmação marcada: escolher a ação é o primeiro gesto, confirmar é o segundo.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from shopman.payman.models import PaymentIntent
from shopman.payman.service import PaymentService

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


def _captured_intent(amount_q=10000):
    intent = PaymentService.create_intent(
        f"ORD-ADMINREF{PaymentIntent.objects.count()}", amount_q, "pix"
    )
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    return PaymentService.get(intent.ref)


def _total_url(pk):
    return f"/admin/payman/paymentintent/{pk}/refund/"


def _amount_url(pk):
    return f"/admin/payman/paymentintent/{pk}/refund-amount/"


def _staff(username: str, *perms: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def refunder_client(client, shop):
    client.force_login(
        _staff("dono-estorno", "payman.view_paymentintent", "payman.refund_paymentintent")
    )
    return client


# ── quem estorna ────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [_total_url, _amount_url])
def test_view_only_staff_cannot_refund(client, shop, url):
    intent = _captured_intent(10000)
    client.force_login(_staff("so-ve", "payman.view_paymentintent"))

    resp = client.post(url(intent.pk), {"_form_submitted": "true", "confirm": "on"})

    assert resp.status_code == 403
    assert PaymentService.refunded_total(intent.ref) == 0


def test_permission_exists_on_the_model():
    assert Permission.objects.filter(
        content_type__app_label="payman", codename="refund_paymentintent"
    ).exists()


def test_refund_permission_goes_to_dono_not_gerente():
    """Estorno é dinheiro: mesma régua do `audit_shift`, do Dono e nunca do Gerente."""
    call_command("setup_groups")
    holders = set(
        Group.objects.filter(
            permissions__content_type__app_label="payman",
            permissions__codename="refund_paymentintent",
        ).values_list("name", flat=True)
    )
    assert holders == {"Dono"}


# ── segunda confirmação ─────────────────────────────────────────────


def test_amount_dialog_renders_with_available_and_confirmation(refunder_client):
    intent = _captured_intent(10000)
    resp = refunder_client.get(_amount_url(intent.pk))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'id="dialog"' in body
    assert "100,00" in body  # disponível no texto de ajuda
    assert 'name="confirm"' in body


@pytest.mark.parametrize("url", [_total_url, _amount_url])
def test_without_the_confirmation_nothing_is_refunded(refunder_client, url):
    intent = _captured_intent(10000)
    resp = refunder_client.post(url(intent.pk), {"_form_submitted": "true", "amount_reais": "30.00"})
    assert resp.status_code == 200  # diálogo volta com o erro
    assert "Marque a confirmação para estornar." in resp.content.decode()
    assert PaymentService.refunded_total(intent.ref) == 0


def test_partial_refund(refunder_client):
    intent = _captured_intent(10000)
    resp = refunder_client.post(
        _amount_url(intent.pk), {"_form_submitted": "true", "confirm": "on", "amount_reais": "30.00"}
    )
    assert resp.status_code == 302
    assert PaymentService.refunded_total(intent.ref) == 3000


def test_total_refund_when_blank(refunder_client):
    intent = _captured_intent(5000)
    resp = refunder_client.post(
        _amount_url(intent.pk), {"_form_submitted": "true", "confirm": "on", "amount_reais": ""}
    )
    assert resp.status_code == 302
    assert PaymentService.refunded_total(intent.ref) == 5000


def test_refund_above_available_is_rejected(refunder_client):
    intent = _captured_intent(4000)
    resp = refunder_client.post(
        _amount_url(intent.pk), {"_form_submitted": "true", "confirm": "on", "amount_reais": "99.00"}
    )
    assert resp.status_code == 200  # diálogo volta com o erro
    assert "Valor acima do disponível" in resp.content.decode()
    assert PaymentService.refunded_total(intent.ref) == 0


def test_total_row_action_refunds_with_confirmation(refunder_client):
    intent = _captured_intent(7000)
    resp = refunder_client.post(_total_url(intent.pk), {"_form_submitted": "true", "confirm": "on"})
    assert resp.status_code == 302
    assert PaymentService.refunded_total(intent.ref) == 7000


def test_bulk_refund_action_no_longer_exists():
    """Ação de lote do Django roda sem diálogo: estorno é um por vez."""
    from django.contrib import admin as django_admin

    model_admin = django_admin.site._registry[PaymentIntent]
    assert "refund_selected" not in (model_admin.actions or [])
