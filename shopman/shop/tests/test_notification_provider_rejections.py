"""Known refusals can fall back; a lost response must never duplicate delivery."""
import smtplib
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from shopman.shop.adapters import notification_email, notification_manychat, notification_sms

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("code,unknown", [(400, False), (401, False), (403, False), (422, False),
                                         (429, False), (408, True), (500, True), (502, True), (504, True)])
def test_http_rejection_differs_from_unknown_acceptance(settings, monkeypatch, code, unknown):
    settings.SHOPMAN_SMS = {"api_key": "test", "route": "17"}
    error = HTTPError("https://provider.invalid", code, "private provider message", {}, None)
    monkeypatch.setattr(notification_manychat, "urlopen", Mock(side_effect=error))
    result = notification_manychat._api_call("/sending/sendFlow", {}, {"api_token": "test"})
    assert bool(result.get("outcome_unknown")) is unknown
    assert not result["success"]
    monkeypatch.setattr(notification_sms, "urlopen", Mock(side_effect=error))
    if unknown:
        with pytest.raises(RuntimeError, match="acceptance_unconfirmed"):
            notification_sms.send("+5543999990001", "order_received", {})
    else:
        assert notification_sms.send("+5543999990001", "order_received", {}) is False


@pytest.mark.parametrize("error", [smtplib.SMTPAuthenticationError(535, b"private"),
    smtplib.SMTPDataError(550, b"private"), smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"private")})])
def test_explicit_smtp_refusal_allows_fallback(monkeypatch, error):
    monkeypatch.setattr(notification_email, "send_mail", Mock(side_effect=error))
    assert notification_email.send("a@example.com", "order_received", {}) is False


@pytest.mark.parametrize("error", [TimeoutError(), smtplib.SMTPServerDisconnected(), URLError("lost")])
def test_uncertain_email_acceptance_still_blocks_fallback(monkeypatch, error):
    monkeypatch.setattr(notification_email, "send_mail", Mock(side_effect=error))
    with pytest.raises(RuntimeError, match="acceptance_unconfirmed"):
        notification_email.send("a@example.com", "order_received", {})
