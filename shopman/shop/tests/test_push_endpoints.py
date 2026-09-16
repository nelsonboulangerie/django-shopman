from __future__ import annotations

import pytest

from shopman.shop.services.push_endpoints import normalize_push_endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/device",
        "https://updates.push.services.mozilla.com/wpush/v2/device",
        "https://web.push.apple.com/Q-device",
        "https://db3.notify.windows.com/w/?token=device",
    ],
)
def test_browser_provider_endpoint_is_allowed(endpoint):
    assert normalize_push_endpoint(endpoint) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/device",
        "https://fcm.googleapis.com.evil.test/device",
        "https://push.apple.com/device",
        "https://notify.windows.com/device",
        "https://user@fcm.googleapis.com/device",
        "https://fcm.googleapis.com:444/device",
        "https://127.0.0.1/device",
        "https://[::1]/device",
        "https://internal.example.test/device",
        "https://fcm.googleapis.com/device#redirect",
    ],
)
def test_non_provider_or_ambiguous_endpoint_is_rejected(endpoint):
    assert normalize_push_endpoint(endpoint) is None
