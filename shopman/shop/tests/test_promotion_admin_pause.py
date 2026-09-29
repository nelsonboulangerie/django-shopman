"""Chave de desligar do go-live: pausar e reativar cupons e promoções em lote no Admin.

O que se prova aqui: a ação muda só o que precisa mudar, conta de verdade (pausar o
que já estava pausado não é pausa), deixa rastro no histórico de cada objeto, não
atravessa para o objeto vizinho (cupom ↔ promoção) e não roda para quem só vê.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from shopman.shop.models import Coupon, Promotion, Shop

pytestmark = pytest.mark.django_db

COUPON_CHANGELIST = "admin:shop_coupon_changelist"
PROMOTION_CHANGELIST = "admin:shop_promotion_changelist"


def _promotion(ref: str, *, active: bool = True) -> Promotion:
    now = timezone.now()
    return Promotion.objects.create(
        ref=ref,
        name=ref,
        type=Promotion.PERCENT,
        value=10,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        is_active=active,
    )


def _coupon(code: str, promotion: Promotion, *, active: bool = True) -> Coupon:
    return Coupon.objects.create(code=code, promotion=promotion, is_active=active)


@pytest.fixture(autouse=True)
def shop():
    # Sem `Shop`, o `OnboardingMiddleware` manda todo o Admin para o cadastro da loja.
    return Shop.objects.create(name="Test Shop")


@pytest.fixture
def admin_client(client):
    user = User.objects.create_superuser("admin", "admin@test.com", "pass")
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def viewer_client(client):
    user = User.objects.create_user("viewer", "viewer@test.com", "pass", is_staff=True)
    for model in (Coupon, Promotion):
        ct = ContentType.objects.get_for_model(model)
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=f"view_{model._meta.model_name}"))
    client.force_login(user)
    return client


def _run(client, changelist: str, action: str, objs):
    return client.post(
        reverse(changelist),
        {"action": action, "_selected_action": [obj.pk for obj in objs]},
        follow=True,
    )


def _messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


class TestCouponPause:
    def test_pause_changes_is_active_and_reports_count(self, admin_client):
        promo = _promotion("promo")
        coupons = [_coupon(f"C{i}", promo) for i in range(3)]

        response = _run(admin_client, COUPON_CHANGELIST, "pause_selected", coupons)

        assert response.status_code == 200
        assert Coupon.objects.filter(is_active=True).count() == 0
        assert _messages(response) == ["3 cupons pausados. Os códigos deles não dão desconto até reativar."]

    def test_already_paused_are_not_counted(self, admin_client):
        promo = _promotion("promo")
        active = _coupon("ATIVO", promo)
        paused = _coupon("PAUSADO", promo, active=False)

        response = _run(admin_client, COUPON_CHANGELIST, "pause_selected", [active, paused])

        assert _messages(response) == ["1 cupom pausado. O código dele não dá desconto até reativar."]
        assert LogEntry.objects.filter(object_id=str(paused.pk)).count() == 0

    def test_nothing_to_pause_says_so(self, admin_client):
        paused = _coupon("PAUSADO", _promotion("promo"), active=False)

        response = _run(admin_client, COUPON_CHANGELIST, "pause_selected", [paused])

        assert _messages(response) == ["Nenhum cupom mudou: os selecionados já estavam pausados."]

    def test_reactivate(self, admin_client):
        promo = _promotion("promo")
        coupons = [_coupon("A", promo, active=False), _coupon("B", promo, active=False), _coupon("C", promo)]

        response = _run(admin_client, COUPON_CHANGELIST, "reactivate_selected", coupons)

        assert Coupon.objects.filter(is_active=False).count() == 0
        assert _messages(response) == [
            "2 cupons reativados. Os códigos voltam a dar desconto se a promoção de cada um estiver ativa e no prazo."
        ]

    def test_pause_does_not_touch_the_promotion(self, admin_client):
        promo = _promotion("promo")
        coupon = _coupon("C", promo)

        _run(admin_client, COUPON_CHANGELIST, "pause_selected", [coupon])

        promo.refresh_from_db()
        assert promo.is_active is True

    def test_each_change_is_logged(self, admin_client):
        promo = _promotion("promo")
        coupons = [_coupon("A", promo), _coupon("B", promo)]

        _run(admin_client, COUPON_CHANGELIST, "pause_selected", coupons)
        _run(admin_client, COUPON_CHANGELIST, "reactivate_selected", coupons[:1])

        ct = ContentType.objects.get_for_model(Coupon)
        entries = LogEntry.objects.filter(content_type=ct, action_flag=CHANGE, user=admin_client.user)
        assert sorted((e.object_id, e.change_message) for e in entries) == sorted([
            (str(coupons[0].pk), "Pausa em lote."),
            (str(coupons[1].pk), "Pausa em lote."),
            (str(coupons[0].pk), "Reativação em lote."),
        ])


class TestPromotionPause:
    def test_pause_changes_is_active_and_reports_count(self, admin_client):
        promos = [_promotion("a"), _promotion("b")]

        response = _run(admin_client, PROMOTION_CHANGELIST, "pause_selected", promos)

        assert Promotion.objects.filter(is_active=True).count() == 0
        assert _messages(response) == [
            "2 promoções pausadas. Nenhum desconto delas vale até reativar, nem por cupom."
        ]

    def test_already_paused_are_not_counted(self, admin_client):
        active = _promotion("ativa")
        paused = _promotion("pausada", active=False)

        response = _run(admin_client, PROMOTION_CHANGELIST, "pause_selected", [active, paused])

        assert _messages(response) == ["1 promoção pausada. Nenhum desconto dela vale até reativar, nem por cupom."]

    def test_reactivate(self, admin_client):
        paused = _promotion("pausada", active=False)

        response = _run(admin_client, PROMOTION_CHANGELIST, "reactivate_selected", [paused])

        paused.refresh_from_db()
        assert paused.is_active is True
        assert _messages(response) == ["1 promoção reativada. Volta a valer dentro do prazo de validade."]

    def test_pause_does_not_touch_its_coupons(self, admin_client):
        promo = _promotion("promo")
        coupon = _coupon("C", promo)

        _run(admin_client, PROMOTION_CHANGELIST, "pause_selected", [promo])

        coupon.refresh_from_db()
        assert coupon.is_active is True

    def test_each_change_is_logged(self, admin_client):
        promos = [_promotion("a"), _promotion("b", active=False)]

        _run(admin_client, PROMOTION_CHANGELIST, "pause_selected", promos)

        ct = ContentType.objects.get_for_model(Promotion)
        entries = LogEntry.objects.filter(content_type=ct, action_flag=CHANGE)
        assert [(e.object_id, e.change_message) for e in entries] == [(str(promos[0].pk), "Pausa em lote.")]


def _offered_actions(response) -> list[str]:
    action_form = response.context.get("action_form")
    if action_form is None:
        return []
    return [name for name, _label in action_form.fields["action"].choices]


@pytest.mark.parametrize("changelist", [COUPON_CHANGELIST, PROMOTION_CHANGELIST])
def test_change_user_is_offered_the_actions(admin_client, changelist):
    response = admin_client.get(reverse(changelist))

    assert response.status_code == 200
    offered = _offered_actions(response)
    assert "pause_selected" in offered
    assert "reactivate_selected" in offered


@pytest.mark.parametrize("changelist", [COUPON_CHANGELIST, PROMOTION_CHANGELIST])
def test_view_only_user_is_not_offered_the_actions(viewer_client, changelist):
    response = viewer_client.get(reverse(changelist))

    assert response.status_code == 200
    offered = _offered_actions(response)
    assert "pause_selected" not in offered
    assert "reactivate_selected" not in offered


def test_view_only_user_cannot_pause_by_posting(viewer_client):
    promo = _promotion("promo")
    coupon = _coupon("C", promo)

    _run(viewer_client, COUPON_CHANGELIST, "pause_selected", [coupon])
    _run(viewer_client, PROMOTION_CHANGELIST, "pause_selected", [promo])

    coupon.refresh_from_db()
    promo.refresh_from_db()
    assert coupon.is_active is True
    assert promo.is_active is True
    assert LogEntry.objects.count() == 0
