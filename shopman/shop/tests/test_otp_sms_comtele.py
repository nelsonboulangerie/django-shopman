from __future__ import annotations

import json
import logging
from unittest import mock

import pytest
from django.test import override_settings

from shopman.shop.adapters import otp_sms_comtele as comtele

_CFG = {
    "api_key": "chave-ficticia-de-teste-comtele",
    "route": "17",
    "tag": "shopman-otp",
    "code_message": "",
    "timeout": 5,
}


class _Resp:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


@override_settings(SHOPMAN_SMS=dict(_CFG, api_key=""))
def test_returns_false_without_api_key():
    assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False


@override_settings(SHOPMAN_SMS=dict(_CFG, route=""))
def test_returns_false_without_route():
    assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False


@override_settings(SHOPMAN_SMS=_CFG)
def test_sends_with_x_api_key_header_and_json_body():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["key"] = request.headers.get("X-api-key")  # urllib title-cases header keys
        captured["ctype"] = request.headers.get("Content-type")
        captured["body"] = json.loads(request.data.decode())
        return _Resp({"hasError": False, "message": None, "totalRecords": 1, "errors": None})

    with mock.patch.object(comtele, "urlopen", fake_urlopen):
        ok = comtele.ComteleSMSSender().send_code("+55 43 99999-0000", "482913", "sms")

    assert ok is True
    assert captured["url"] == "https://api.comtele.com.br/messages/sms/send"
    assert captured["key"] == "chave-ficticia-de-teste-comtele"
    assert captured["ctype"] == "application/json"
    body = captured["body"]
    assert body["receivers"] == ["5543999990000"]  # array, digits only
    assert body["route"] == "17"
    assert body["tag"] == "shopman-otp"
    assert "482913" in body["message"]


@override_settings(SHOPMAN_SMS=_CFG)
def test_returns_false_when_api_reports_error():
    def fake_urlopen(request, timeout=None):
        return _Resp({"hasError": True, "message": "saldo insuficiente", "errors": []})

    with mock.patch.object(comtele, "urlopen", fake_urlopen):
        assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False


@override_settings(SHOPMAN_SMS=_CFG)
def test_returns_false_on_http_error():
    from urllib.error import HTTPError

    def boom(request, timeout=None):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    with mock.patch.object(comtele, "urlopen", boom):
        assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False


# ── Falhar gritando: a falha do provedor chega a alguém que não é o cliente ──
#
# Antes, qualquer recusa da Comtele morria num `logger.warning` (que nem vira
# evento no Sentry) e o cliente lia "verifique o número". Agora vira evento
# ERROR estruturado + OperatorAlert `integration_failed` com debounce + aviso no
# sino do gestor, pelo mesmo `record_integration_failure` do Google/NFC-e.


def _alerts():
    from shopman.backstage.models import OperatorAlert

    return list(OperatorAlert.objects.filter(type="integration_failed"))


@pytest.mark.django_db
@override_settings(SHOPMAN_SMS=_CFG)
def test_http_error_raises_operator_alert_without_phone_or_code():
    from urllib.error import HTTPError

    def boom(request, timeout=None):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    with mock.patch.object(comtele, "urlopen", boom):
        assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False

    alerts = _alerts()
    assert len(alerts) == 1
    assert "SMS de login (Comtele)" in alerts[0].message
    assert "HTTP 401" in alerts[0].message
    # A mensagem é a CAUSA (dedupe entre clientes), nunca o caso.
    assert "99990000" not in alerts[0].message
    assert "482913" not in alerts[0].message


@pytest.mark.django_db
@override_settings(SHOPMAN_SMS=_CFG)
def test_rejection_by_provider_raises_alert_and_debounces_across_customers():
    def fake_urlopen(request, timeout=None):
        return _Resp({"hasError": True, "message": "saldo insuficiente", "errors": []})

    with mock.patch.object(comtele, "urlopen", fake_urlopen):
        comtele.ComteleSMSSender().send_code("+5543999990000", "111111", "sms")
        comtele.ComteleSMSSender().send_code("+5543988880000", "222222", "sms")

    alerts = _alerts()
    assert len(alerts) == 1, "mesma causa para dois clientes é UM alerta, não dois"
    assert "saldo insuficiente" in alerts[0].message


@pytest.mark.django_db
@override_settings(SHOPMAN_SMS=_CFG)
def test_timeout_raises_alert():
    from urllib.error import URLError

    def slow(request, timeout=None):
        raise URLError(TimeoutError("timed out"))

    with mock.patch.object(comtele, "urlopen", slow):
        assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False

    assert "sem resposta" in _alerts()[0].message


@override_settings(SHOPMAN_SMS=dict(_CFG, api_key=""))
def test_missing_config_does_not_alert_per_request():
    # Configuração ausente é da prontidão (integration_readiness), não um alerta
    # por cliente que tenta entrar.
    with mock.patch("shopman.shop.services.observability.record_integration_failure") as rec:
        assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False
    rec.assert_not_called()


@override_settings(SHOPMAN_SMS=_CFG)
def test_accept_emits_latency_event(caplog):
    def fake_urlopen(request, timeout=None):
        return _Resp({"hasError": False})

    with caplog.at_level(logging.INFO, logger="shopman.operational"):
        with mock.patch.object(comtele, "urlopen", fake_urlopen):
            assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is True

    events = [r for r in caplog.records if getattr(r, "event", "") == "otp.sms.accepted"]
    assert len(events) == 1
    record = events[0]
    assert isinstance(record.duration_ms, int)
    assert record.slow is False
    assert record.levelno == logging.INFO
    assert record.target == "***0000"


@override_settings(SHOPMAN_SMS=_CFG)
def test_slow_accept_is_a_warning(caplog):
    def fake_urlopen(request, timeout=None):
        return _Resp({"hasError": False})

    ticks = iter([100.0, 100.0 + comtele.SLOW_ACCEPT_MS / 1000 + 1])
    with caplog.at_level(logging.INFO, logger="shopman.operational"):
        with mock.patch.object(comtele, "urlopen", fake_urlopen), \
                mock.patch.object(comtele.time, "monotonic", lambda: next(ticks)):
            assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is True

    record = next(r for r in caplog.records if getattr(r, "event", "") == "otp.sms.accepted")
    assert record.slow is True
    assert record.levelno == logging.WARNING
