"""Ephemeral Django/WSGI observer: no Shopman apps, database or integrations."""
import os
from wsgiref.simple_server import WSGIRequestHandler, make_server

import django
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse
from django.urls import include, path
from django.views.decorators.http import require_GET

hosts = [host.strip() for host in os.environ.get("SHOPMAN_ADMIN_IP_PROBE_HOSTS", "").split(",") if host.strip()]
settings.configure(
    DEBUG=False, SECRET_KEY="unused-public-fixture-no-auth-no-sessions",
    ALLOWED_HOSTS=["127.0.0.1", "localhost", *hosts], ROOT_URLCONF=__name__,
    INSTALLED_APPS=[], DATABASES={},
    MIDDLEWARE=["observer_middleware.AdminIngressProbeMiddleware"],
    SHOPMAN_ENVIRONMENT=os.environ.get("SHOPMAN_ENVIRONMENT", ""),
    SHOPMAN_ADMIN_IP_PROBE_HOSTS=hosts,
    SHOPMAN_ADMIN_IP_PROBE_TOKEN=os.environ.get("SHOPMAN_ADMIN_IP_PROBE_TOKEN", ""),
    SHOPMAN_ADMIN_IP_PROBE_UNTIL=os.environ.get("SHOPMAN_ADMIN_IP_PROBE_UNTIL", "0"),
    LOGGING={"version": 1, "disable_existing_loggers": True,
        "handlers": {"probe": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
                     "null": {"class": "logging.NullHandler"}},
        "root": {"handlers": ["null"]},
        "loggers": {"observer_middleware": {"handlers": ["probe"], "level": "INFO", "propagate": False}}},
)
django.setup()


@require_GET
def health(request):
    return HttpResponse("ok", content_type="text/plain")


@require_GET
def login(request):
    return HttpResponse("isolated ingress observer", content_type="text/plain")


urlpatterns = [path("health/", health), path("admin/", include(([path("login/", login, name="login")], "admin")))]
application = get_wsgi_application()


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        # Deliberately no access log: do not copy query strings or headers.
        return


if __name__ == "__main__":
    with make_server("0.0.0.0", int(os.environ.get("PORT", "8080")), application, handler_class=QuietHandler) as server:
        server.serve_forever()
