from django.test import override_settings

from shopman.shop.services import notification


def test_active_notification_policy_recognizes_operational_templates_and_override():
    assert notification.requires_active_notification("order_ready") is True
    assert notification.requires_active_notification("marketing_digest") is False
    assert notification.requires_active_notification(
        "marketing_digest",
        payload={"requires_active_notification": True},
    ) is True


@override_settings(DEBUG=True)
def test_development_console_policy_requires_debug_and_the_console_backend():
    assert notification.dev_console_allowed(["manychat", "console"]) is True
    assert notification.dev_console_allowed(["manychat"]) is False


@override_settings(DEBUG=False)
def test_development_console_policy_stays_closed_outside_debug():
    assert notification.dev_console_allowed(["console"]) is False
