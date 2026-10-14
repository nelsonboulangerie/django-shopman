"""AccessLogMiddleware: uma linha por request, sem dado de quem pediu.

O daphne fica com `--access-log=/dev/null` porque grava o caminho cru (com o
`?token=` do webhook da Efí) e o IP do cliente. Esta linha é a substituta, e as
travas aqui são as de privacidade: padrão da rota, nunca o caminho pedido.
"""

from __future__ import annotations

import logging

import pytest
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory
from django.urls import resolve

from shopman.shop.middleware import AccessLogMiddleware


def _middleware(response, settings, *, resolve_path: str | None = None):
    settings.SHOPMAN_ACCESS_LOG = True

    def get_response(request):
        if resolve_path is not None:
            request.resolver_match = resolve(resolve_path)
        return response

    return AccessLogMiddleware(get_response)


@pytest.fixture(autouse=True)
def _capture_access_logger(caplog):
    # `shopman` não propaga para a raiz (config/settings.py), onde o caplog escuta.
    # Quando outra suíte do mesmo processo religa a propagação, o registro chega
    # pelos dois caminhos: `_records` conta cada registro uma vez só.
    logger = logging.getLogger("shopman.access")
    logger.addHandler(caplog.handler)
    yield
    logger.removeHandler(caplog.handler)


def _records(caplog):
    seen: set[int] = set()
    out = []
    for record in caplog.records:
        if record.name == "shopman.access" and id(record) not in seen:
            seen.add(id(record))
            out.append(record)
    return out


def test_off_by_default_leaves_the_chain(settings):
    settings.SHOPMAN_ACCESS_LOG = False
    with pytest.raises(MiddlewareNotUsed):
        AccessLogMiddleware(lambda request: HttpResponse())


def test_never_logs_query_string_nor_client_ip(settings, caplog):
    caplog.set_level(logging.INFO, logger="shopman.access")
    middleware = _middleware(HttpResponse(status=200), settings, resolve_path="/health/ready/")
    request = RequestFactory().get("/webhook/?token=segredo-da-efi-123", REMOTE_ADDR="203.0.113.7")

    middleware(request)

    (record,) = _records(caplog)
    assert record.getMessage().startswith("access GET /health/ready/ 200 ")
    assert record.http_route == "/health/ready/"
    assert record.http_status == 200
    assert record.levelno == logging.INFO
    for value in (record.getMessage(), *record.__dict__.values()):
        assert "segredo-da-efi-123" not in str(value)
        assert "203.0.113.7" not in str(value)


def test_resolved_route_keeps_the_placeholder_not_the_value(settings, caplog):
    caplog.set_level(logging.INFO, logger="shopman.access")
    path = "/admin/auth/user/987654/change/"
    middleware = _middleware(HttpResponse(status=302), settings, resolve_path=path)

    middleware(RequestFactory().get(path))

    (record,) = _records(caplog)
    assert record.http_route.startswith("/admin/")
    assert "987654" not in record.http_route
    assert "987654" not in record.getMessage()


def test_unresolved_request_logs_a_dash(settings, caplog):
    caplog.set_level(logging.INFO, logger="shopman.access")
    middleware = _middleware(HttpResponse(status=404), settings)

    middleware(RequestFactory().get("/auth/access/abc123token/"))

    (record,) = _records(caplog)
    assert record.http_route == "-"
    assert "abc123token" not in record.getMessage()


def test_server_error_is_a_warning(settings, caplog):
    caplog.set_level(logging.INFO, logger="shopman.access")
    middleware = _middleware(HttpResponse(status=503), settings)

    middleware(RequestFactory().post("/x/"))

    (record,) = _records(caplog)
    assert record.levelno == logging.WARNING
    assert record.http_status == 503
    assert record.http_method == "POST"


def test_healthy_platform_probe_is_silent_and_failing_probe_is_logged(settings, caplog):
    caplog.set_level(logging.INFO, logger="shopman.access")
    _middleware(HttpResponse(status=200), settings)(RequestFactory().get("/health/database/"))
    assert _records(caplog) == []

    _middleware(HttpResponse(status=503), settings)(RequestFactory().get("/health/database/"))
    (record,) = _records(caplog)
    assert record.http_status == 503


def test_unknown_method_is_not_echoed(settings, caplog):
    caplog.set_level(logging.INFO, logger="shopman.access")
    request = RequestFactory().generic("PROPFIND", "/x/")

    _middleware(HttpResponse(status=405), settings)(request)

    (record,) = _records(caplog)
    assert record.http_method == "OTHER"
    assert "PROPFIND" not in record.getMessage()


def test_streaming_response_is_marked(settings, caplog):
    caplog.set_level(logging.INFO, logger="shopman.access")
    response = StreamingHttpResponse(iter([b"data: 1\n\n"]))

    _middleware(response, settings)(RequestFactory().get("/events/x/"))

    (record,) = _records(caplog)
    assert record.streaming is True
    assert record.getMessage().endswith(" stream")


def test_middleware_is_first_in_the_chain():
    from django.conf import settings as django_settings

    assert django_settings.MIDDLEWARE[0] == "shopman.shop.middleware.AccessLogMiddleware"
