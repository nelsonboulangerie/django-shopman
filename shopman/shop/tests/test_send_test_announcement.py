"""O CLI usa a mesma lane sandbox, receipt e autoridade da API."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop import notifications
from shopman.shop.services.marketing_security import activate_freeze

pytestmark = pytest.mark.django_db

RECIPIENT = "4605528796186498"
TARGET_REF = "owner-sandbox"
KEY = "cli-test-send-0123456789"


class _Adapter:
    def __init__(self, *, available: bool = True, ok: bool = True):
        self._available = available
        self._ok = ok
        self.calls: list[dict] = []

    def is_available(self, *_args, **_kwargs) -> bool:
        return self._available

    def send(self, *, recipient, template, context=None, **_kwargs) -> bool:
        self.calls.append({"recipient": recipient, "template": template, "context": context})
        return self._ok


@pytest.fixture
def adapter(settings, monkeypatch):
    fake = _Adapter()
    settings.SHOPMAN_MARKETING_TEST_TARGETS = {
        TARGET_REF: {
            "label": "Aparelho verificado",
            "recipient": RECIPIENT,
            "backend": "manychat",
            "sandbox": True,
            "ownership_verified": True,
        },
    }
    monkeypatch.setattr(notifications, "_adapters", {"manychat": fake})
    return fake


@pytest.fixture
def actor():
    user = get_user_model().objects.create_user(
        username="marketing-test", password="x", is_staff=True
    )
    user.user_permissions.add(Permission.objects.get(codename="send_marketing_test"))
    return user


def _run(*args) -> str:
    out = StringIO()
    call_command("send_test_announcement", *args, stdout=out, stderr=out)
    return out.getvalue()


def _send_args():
    return (
        "--target-ref", TARGET_REF,
        "--actor", "marketing-test",
        "--idempotency-key", KEY,
        "--send",
    )


def test_dry_run_is_default_and_never_prints_recipient(adapter):
    output = _run("--target-ref", TARGET_REF)

    assert adapter.calls == []
    assert "Nada foi enviado" in output
    assert "exatamente 1" in output
    assert RECIPIENT not in output


def test_send_calls_sandbox_once_and_returns_receipt(adapter, actor):
    output = _run(*_send_args())

    assert len(adapter.calls) == 1
    assert adapter.calls[0]["recipient"] == RECIPIENT
    assert adapter.calls[0]["template"] == "announcement_published"
    assert "accepted_unconfirmed" in output
    assert "Aceitou" not in output  # a copy não afirma entrega confirmada
    assert "Sandbox aceitou" in output
    assert RECIPIENT not in output


def test_repeating_command_key_does_not_send_again(adapter, actor):
    _run(*_send_args())
    output = _run(*_send_args())

    assert len(adapter.calls) == 1
    assert "nenhum segundo envio" in output


def test_emergency_freeze_blocks_sandbox_at_the_last_boundary(adapter, actor):
    security = get_user_model().objects.create_user(
        username="marketing-security", password="x", is_staff=True
    )
    security.user_permissions.add(Permission.objects.get(codename="freeze_marketing"))
    activate_freeze(actor=security, reason="Exercício local do kill switch")

    with pytest.raises(CommandError, match="congelado"):
        _run(*_send_args())

    assert adapter.calls == []


def test_unconfigured_target_is_fail_closed(adapter):
    with pytest.raises(CommandError, match="não autorizado"):
        _run("--target-ref", "telefone-livre")
    assert adapter.calls == []


def test_send_requires_named_authorized_actor(adapter):
    get_user_model().objects.create_user(
        username="sem-capacidade", password="x", is_staff=True
    )

    with pytest.raises(CommandError, match="capacidade"):
        _run(
            "--target-ref", TARGET_REF,
            "--actor", "sem-capacidade",
            "--idempotency-key", KEY,
            "--send",
        )
    assert adapter.calls == []


def test_refused_sandbox_is_not_reported_as_accepted(settings, monkeypatch, actor):
    fake = _Adapter(ok=False)
    settings.SHOPMAN_MARKETING_TEST_TARGETS = {
        TARGET_REF: {
            "label": "Sintético",
            "recipient": RECIPIENT,
            "backend": "manychat",
            "sandbox": True,
            "synthetic": True,
        },
    }
    monkeypatch.setattr(notifications, "_adapters", {"manychat": fake})

    output = _run(*_send_args())

    assert "failed_final" in output
    assert "Sandbox aceitou" not in output
