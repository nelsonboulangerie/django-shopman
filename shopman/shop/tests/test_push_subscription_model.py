from __future__ import annotations

from io import StringIO

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop.admin.push_subscription import PushSubscriptionAdmin
from shopman.shop.models import PushSubscription

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def owner():
    return User.objects.create_user(username="push-model-owner", password="x")


def _subscription(owner, **changes):
    values = {
        "user": owner,
        "endpoint": "https://push.example.test/model",
        "p256dh": "public-key",
        "auth": "auth-key",
        "surface_ref": "orders",
        "device_label": "Telefone",
        "categories": ["order"],
    }
    values.update(changes)
    return PushSubscription(**values)


@pytest.mark.parametrize("categories", [["order", "order"], ["campaign"], "order"])
def test_model_rejects_invalid_categories_for_surface(owner, categories):
    with pytest.raises(ValidationError):
        _subscription(owner, categories=categories).full_clean()


def test_admin_is_read_only_and_hides_endpoint_keys(owner):
    model_admin = PushSubscriptionAdmin(PushSubscription, admin.site)
    assert model_admin.has_add_permission(None) is False
    assert model_admin.has_change_permission(None) is False
    assert model_admin.has_delete_permission(None) is False
    assert set(model_admin.exclude) == {"endpoint", "p256dh", "auth"}
    record = _subscription(owner)
    assert model_admin.endpoint_fingerprint(record) != record.endpoint


def test_rotation_command_requires_explicit_confirmation(owner):
    record = _subscription(owner)
    record.save()

    with pytest.raises(CommandError, match="confirm-vapid-rotation"):
        call_command("disable_push_subscriptions")

    output = StringIO()
    call_command("disable_push_subscriptions", confirm_vapid_rotation=True, stdout=output)
    record.refresh_from_db()
    assert record.disabled_at is not None
    assert "1 assinatura" in output.getvalue()
