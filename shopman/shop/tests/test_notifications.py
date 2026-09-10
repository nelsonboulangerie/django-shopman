"""Contract of the canonical notification backend registry."""

from types import SimpleNamespace
from unittest.mock import patch

from shopman.shop.notifications import notify
from shopman.shop.protocols import NotificationResult


def _notify_with(raw_result):
    adapter = SimpleNamespace(send=lambda **_kwargs: raw_result)
    with patch("shopman.shop.notifications.get_backend", return_value=adapter):
        return notify(
            event="order_ready",
            recipient="+5543999999999",
            context={"order_ref": "ORD-1"},
            backend="provider",
        )


def test_bool_acceptance_never_fabricates_a_message_id_from_recipient():
    result = _notify_with(True)

    assert result == NotificationResult(success=True)
    assert "+5543999999999" not in repr(result)


def test_dict_acceptance_preserves_provider_message_id():
    result = _notify_with({"success": True, "message_id": "provider-msg-123"})

    assert result == NotificationResult(success=True, message_id="provider-msg-123")


def test_notification_result_is_preserved_without_reinterpretation():
    provider_result = NotificationResult(success=True, message_id="native-456")

    assert _notify_with(provider_result) is provider_result


def test_unsuccessful_dict_is_not_treated_as_truthy_success():
    result = _notify_with({"success": False, "error": "provider rejected"})

    assert result == NotificationResult(success=False, error="provider rejected")


def test_unknown_truthy_result_is_rejected_instead_of_marked_accepted():
    result = _notify_with("accepted")

    assert result.success is False
    assert result.error == "Adapter provider returned an invalid result"
