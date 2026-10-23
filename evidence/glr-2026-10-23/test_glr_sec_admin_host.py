# ruff: noqa
# Prova do laudo docs/reports/2026-10-23-laudo-adversarial-go-live.md: PASSA enquanto o defeito existe.
import pytest
from django.test import override_settings

pytestmark = [pytest.mark.django_db]

@override_settings(
    ALLOWED_HOSTS=["api.boulangerie.com.br", "admin.boulangerie.com.br"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=".boulangerie.com.br",
    SHOPMAN_OPERATOR_API_HOST="api.boulangerie.com.br",
    SHOPMAN_ADMIN_HOST="admin.boulangerie.com.br",
)
def test_admin_on_api_host(client, django_user_model):
    django_user_model.objects.create_superuser("root", "r@x.com", "S3nha-forte-123")
    for host in ("admin.boulangerie.com.br", "api.boulangerie.com.br"):
        c = client.__class__()
        r = c.get("/admin/login/", HTTP_HOST=host, secure=True)
        print(host, "GET", r.status_code)
        csrftoken = r.cookies.get("csrftoken").value if r.cookies.get("csrftoken") else ""
        r = c.post("/admin/login/", {"username": "root", "password": "S3nha-forte-123", "csrfmiddlewaretoken": csrftoken, "next": "/admin/"}, HTTP_HOST=host, secure=True, HTTP_REFERER=f"https://{host}/admin/login/")
        sc = r.cookies.get("sessionid")
        print(host, "POST", r.status_code, r.get("Location"), "sessionid domain=", sc["domain"] if sc else None)
