"""Access messages use native WhatsApp buttons without exposing credentials."""

from __future__ import annotations

import io
import json
from importlib import import_module
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from django.test import override_settings

CONFIG = {"api_token": "token", "timeout": 5, "flow_map": {}}


def _send(event: str, context: dict, *, provider_results=None):
    from shopman.shop.adapters import notification_manychat as adapter

    results = provider_results or [{"success": True}]
    with patch.object(adapter, "_get_config", return_value=CONFIG):
        with patch.object(adapter, "_resolve_subscriber", return_value=123):
            with patch.object(adapter, "_load_db_flow_ns", return_value=None):
                with patch.object(adapter, "_api_call", side_effect=results) as api:
                    sent = adapter.send("123", event, context)
    return sent, api


def test_login_copy_does_not_use_dashes():
    from shopman.shop.notification_copy import CUSTOMER_COPY
    from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS

    texts = [
        CUSTOMER_COPY["access_link"]["body"],
        CUSTOMER_COPY["access_link_site"]["body"],
    ]
    for key in ("LOGIN_PHONE_HEADING", "LOGIN_WA_WHY", "LOGIN_WA_STEPS", "LOGIN_WA_WAITING"):
        entry = OMOTENASHI_DEFAULTS[key]["*"]["*"]
        texts.extend([entry.title, entry.message])

    assert all("—" not in text and "–" not in text for text in texts if text)


@pytest.mark.django_db
def test_copy_migration_updates_known_defaults_and_preserves_operator_edits():
    from django.apps import apps

    from shopman.shop.models import NotificationTemplate, OmotenashiCopy

    migration = import_module("shopman.shop.migrations.0082_access_link_button_copy")
    NotificationTemplate.objects.update_or_create(
        event=migration.ACCESS_EVENT,
        defaults={
            "subject": migration.ACCESS_SUBJECT,
            "body": migration.ACCESS_OLD_BODY,
            "is_active": True,
        },
    )
    NotificationTemplate.objects.update_or_create(
        event=migration.SITE_EVENT,
        defaults={
            "subject": "Texto da casa",
            "body": "A loja escreveu esta mensagem.",
            "is_active": True,
        },
    )
    OmotenashiCopy.objects.update_or_create(
        key="LOGIN_PHONE_HEADING",
        moment="*",
        audience="*",
        defaults={"title": "Entre com seu WhatsApp", "message": "", "active": True},
    )

    migration.forwards(apps, None)

    assert NotificationTemplate.objects.get(event=migration.ACCESS_EVENT).body == migration.ACCESS_BODY
    assert NotificationTemplate.objects.get(event=migration.SITE_EVENT).body == "A loja escreveu esta mensagem."
    assert OmotenashiCopy.objects.get(key="LOGIN_PHONE_HEADING").title == "Entre pelo WhatsApp"


@pytest.mark.django_db
@override_settings(SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG=True)
def test_site_login_uses_two_bubbles_with_one_url_button_each():
    access_url = "https://loja.test/a?t=secret"
    revoke_url = "https://loja.test/encerrar-acesso#ref"

    sent, api = _send(
        "access_link_site",
        {
            "customer_name": "Joyce",
            "access_url": access_url,
            "revoke_url": revoke_url,
            "cart_note": "Sua sacola está guardada. ",
            "has_cart_context": True,
        },
    )

    assert sent is True
    _endpoint, payload, _config = api.call_args.args
    messages = payload["data"]["content"]["messages"]
    assert messages == [
        {
            "type": "text",
            "text": "Não reconhece este acesso?",
            "buttons": [
                {"type": "url", "caption": "Encerrar acesso", "url": revoke_url},
            ],
        },
        {
            "type": "text",
            "text": "Pronto, Joyce! Seu acesso foi liberado.\nSua sacola está guardada. Volte à loja para continuar.",
            "buttons": [
                {"type": "url", "caption": "Continuar pedido", "url": access_url},
            ],
        },
    ]
    assert all(len(message["buttons"]) == 1 for message in messages)
    assert all(button["url"] not in message["text"] for message in messages for button in message["buttons"])


@pytest.mark.django_db
@override_settings(SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG=True)
def test_organic_login_uses_one_primary_button():
    access_url = "https://loja.test/a?t=secret"

    _sent, api = _send(
        "access_link",
        {"access_url": access_url, "cart_note": ""},
    )

    message = api.call_args.args[1]["data"]["content"]["messages"][0]
    assert message["buttons"] == [
        {"type": "url", "caption": "Entrar na loja", "url": access_url},
    ]


@pytest.mark.django_db
@override_settings(SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG=True)
def test_explicit_button_rejection_retries_once_as_plain_text():
    from shopman.shop.adapters import notification_manychat as adapter

    access_url = "https://loja.test/a?t=secret"
    revoke_url = "https://loja.test/encerrar-acesso#ref"

    with patch.object(adapter.logger, "warning") as warning:
        sent, api = _send(
            "access_link_site",
            {"access_url": access_url, "revoke_url": revoke_url, "cart_note": ""},
            provider_results=[
                {
                    "success": False,
                    "error": "provider_rejected",
                    "provider_code": "invalid_button_contract",
                    "provider_http_status": 400,
                },
                {"success": True},
            ],
        )

    assert sent is True
    assert api.call_count == 2
    fallback = api.call_args_list[1].args[1]["data"]["content"]["messages"][0]
    assert "buttons" not in fallback
    assert f"Entrar na loja: {access_url}" in fallback["text"]
    assert f"Encerrar acesso: {revoke_url}" in fallback["text"]
    warning.assert_called_once_with(
        "manychat.buttons_rejected template=%s provider_code=%s http_status=%s fallback=plain_text",
        "access_link_site",
        "invalid_button_contract",
        400,
    )


@pytest.mark.django_db
def test_http_rejection_keeps_only_sanitized_provider_metadata():
    from shopman.shop.adapters import notification_manychat as adapter

    error = HTTPError(
        "https://api.manychat.test/sendContent",
        400,
        "bad request",
        {},
        io.BytesIO(
            json.dumps(
                {
                    "status": "error",
                    "details": {
                        "code": "button_limit",
                        "customer_phone": "+5511999999999",
                    },
                }
            ).encode()
        ),
    )
    with patch.object(adapter, "urlopen", side_effect=error):
        result = adapter._api_call(
            "/sending/sendContent",
            {"subscriber_id": 123, "data": {}},
            CONFIG,
        )

    assert result == {
        "success": False,
        "error": "provider_rejected",
        "provider_code": "button_limit",
        "provider_http_status": 400,
    }


@pytest.mark.django_db
@override_settings(SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG=True)
def test_other_notifications_keep_plain_text_payload():
    _sent, api = _send("order_accepted", {"order_ref": "NB-1"})

    message = api.call_args.args[1]["data"]["content"]["messages"][0]
    assert "buttons" not in message
