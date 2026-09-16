from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@pytest.mark.django_db
def test_bootstrap_admin_creates_named_superuser(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "strong-staging-owner-password")

    call_command(
        "bootstrap_admin",
        username="pablo",
        email="pablo@example.com",
        stdout=StringIO(),
    )

    user = get_user_model().objects.get(username="pablo")
    assert user.email == "pablo@example.com"
    assert user.is_active is True
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("strong-staging-owner-password")


@pytest.mark.django_db
def test_bootstrap_admin_is_idempotent(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "strong-staging-owner-password")

    for email in ["old@example.com", "new@example.com"]:
        call_command(
            "bootstrap_admin",
            username="pablo",
            email=email,
            stdout=StringIO(),
        )

    users = get_user_model().objects.filter(username="pablo")
    assert users.count() == 1
    assert users.get().email == "new@example.com"


@pytest.mark.django_db
def test_bootstrap_admin_can_deactivate_seed_admin(monkeypatch):
    User = get_user_model()
    User.objects.create_superuser("admin", "admin@example.com", "seed-pass")
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "strong-staging-owner-password")

    call_command(
        "bootstrap_admin",
        username="pablo",
        email="pablo@example.com",
        deactivate_seed_admin=True,
        stdout=StringIO(),
    )

    assert User.objects.get(username="admin").is_active is False
    assert User.objects.get(username="pablo").is_active is True


@pytest.mark.django_db
def test_bootstrap_admin_rejects_weak_password_when_not_debug(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", "admin")

    with override_settings(DEBUG=False):
        with pytest.raises(CommandError):
            call_command(
                "bootstrap_admin",
                username="pablo",
                email="pablo@example.com",
                stdout=StringIO(),
            )


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["bootstrap_admin", "ensure_dev_superuser"])
def test_repeated_bootstrap_preserves_sessions_but_password_rotation_revokes_them(command, monkeypatch):
    """Um deploy não troca a identidade; senha nova continua revogando acesso."""
    from django.contrib.auth import SESSION_KEY
    from django.test import Client

    password = "strong-staging-owner-password"

    def bootstrap(secret):
        monkeypatch.setenv("SHOPMAN_ADMIN_PASSWORD", secret)
        if command == "bootstrap_admin":
            call_command(command, username="owner", email="owner@example.com", stdout=StringIO())
        else:
            call_command(command, "owner", password=secret, stdout=StringIO())

    bootstrap(password)
    user = get_user_model().objects.get(username="owner")
    original_hash = user.password
    # Sessões independentes: o Admin e o balcão continuam autenticados após bootstrap.
    admin, operator = Client(), Client()
    for client in (admin, operator):
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
    bootstrap(password)
    user.refresh_from_db()
    assert user.password == original_hash
    assert admin.get("/admin/").wsgi_request.user.pk == user.pk
    assert operator.get("/api/v1/backstage/operator/session/").json()["operator"]["id"] == user.pk
    for client in (admin, operator):
        assert client.session[SESSION_KEY] == str(user.pk)

    bootstrap("a-different-strong-password")
    user.refresh_from_db()
    assert user.check_password("a-different-strong-password")
    assert admin.get("/admin/").status_code == 302
    assert operator.get("/api/v1/backstage/operator/session/").status_code in (401, 403)
    for client in (admin, operator):
        assert SESSION_KEY not in client.session
