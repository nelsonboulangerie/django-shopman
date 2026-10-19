"""Envio sem backend nomeado não cai no console fora de DEBUG (fallbacks perigosos, item 14).

O console devolve sucesso para tudo. ``get_backend(None)`` resolvia para ele, em
qualquer ambiente: o desenho era "não especificado ⇒ o falso". Fora de DEBUG
agora não há backend padrão, e o envio falha alto (``logger.error``).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.test import override_settings

from shopman.shop import notifications


@pytest.fixture
def console_registered(monkeypatch):
    sent = []
    console = SimpleNamespace(send=lambda **kw: sent.append(kw) or True, is_available=lambda *a, **k: True)
    monkeypatch.setitem(notifications._adapters, "console", console)
    return console, sent


@pytest.fixture
def log_errors(monkeypatch):
    errors = []
    monkeypatch.setattr(notifications.logger, "error", lambda *a, **kw: errors.append(a))
    return errors


@override_settings(DEBUG=False)
def test_unnamed_backend_outside_debug_is_none_and_screams(console_registered, log_errors):
    assert notifications.get_backend(None) is None
    assert len(log_errors) == 1


@override_settings(DEBUG=False)
def test_notify_without_backend_outside_debug_fails_instead_of_faking_success(console_registered, log_errors):
    _, sent = console_registered
    result = notifications.notify(event="payment_requested", recipient="+5543999990000", context={})
    assert result.success is False
    assert result.error == "Backend not named"
    assert sent == []
    assert len(log_errors) == 1


@override_settings(DEBUG=True)
def test_unnamed_backend_in_debug_still_uses_the_console(console_registered, log_errors):
    console, _ = console_registered
    assert notifications.get_backend(None) is console
    assert log_errors == []


@override_settings(DEBUG=False)
def test_named_backend_is_untouched(console_registered, log_errors):
    console, _ = console_registered
    assert notifications.get_backend("console") is console
    assert log_errors == []


@override_settings(DEBUG=False)
def test_stock_arrived_without_consented_channel_does_not_reach_notify(monkeypatch):
    # O único chamador que podia mandar ``backend=None`` de propósito (cliente
    # sem canal com consentimento) agora para antes, em vez de gritar à toa.
    from shopman.shop.handlers import _stock_receivers

    customer = SimpleNamespace(pk=1, ref="C-1", phone="", email="", first_name="Ana")
    monkeypatch.setattr(_stock_receivers, "_resolve_session_customer", lambda session: customer)
    monkeypatch.setattr(_stock_receivers, "_notification_backend", lambda c: None)
    calls = []
    monkeypatch.setattr(notifications, "notify", lambda **kw: calls.append(kw))
    monkeypatch.setattr("shopman.offerman.models.Product.objects", SimpleNamespace(filter=lambda **kw: SimpleNamespace(first=lambda: None)))

    _stock_receivers._notify_stock_arrived(SimpleNamespace(session_key="s1", data={}), sku="PAO", target_date=None)
    assert calls == []
