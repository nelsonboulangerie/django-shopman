"""O schema OpenAPI é mapa da API inteira: só staff lê (laudo S5, 23/10)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

PATHS = ("/api/schema/", "/api/docs/")


@pytest.mark.parametrize("path", PATHS)
def test_anonymous_cannot_read_the_schema(client, path):
    assert client.get(path).status_code in (401, 403)


@pytest.mark.parametrize("path", PATHS)
def test_logged_customer_cannot_read_the_schema(client, django_user_model, path):
    client.force_login(django_user_model.objects.create_user("cliente", password="x"))
    assert client.get(path).status_code == 403


def test_staff_reads_the_schema(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("gestor", password="x", is_staff=True))
    response = client.get("/api/schema/")
    assert response.status_code == 200
    assert b"openapi" in response.content
