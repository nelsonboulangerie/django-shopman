"""Toda leitura do B.I. diz quando o servidor a gerou (`generated_at`).

O `ReadFreshness` das telas mostra essa hora. Antes cada tela usava a hora em que a
resposta chegou ao dispositivo, e um relógio errado no dispositivo mudava a leitura.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.models import DayClosing

READINGS = [
    ("api-backstage-bi-production", {}),
    ("api-backstage-bi-over-short", {}),
    ("api-backstage-bi-sales", {}),
    ("api-backstage-bi-cash", {}),
    ("api-backstage-bi-customers", {}),
    ("api-backstage-bi-explore", {"metric": "revenue", "by": "time"}),
    ("api-backstage-bi-consumption-profiles", {}),
    ("api-backstage-bi-forecast", {}),
    ("api-backstage-bi-change", {}),
    ("api-backstage-bi-scenarios", {}),
]


@pytest.fixture
def viewer(db):
    user = User.objects.create_user("bi-frescor", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi"),
        # O Caixa é apuração: pede também a auditoria de turno.
        Permission.objects.get(content_type__app_label="cashman", codename="audit_shift"),
    )
    return user


@pytest.mark.django_db
@pytest.mark.parametrize(("name", "query"), READINGS)
def test_every_reading_carries_the_server_clock_in_the_project_timezone(client, viewer, name, query):
    client.force_login(viewer)
    before = timezone.now().replace(microsecond=0)
    response = client.get(reverse(name), query)
    after = timezone.now()

    assert response.status_code == 200, response.content
    body = response.json()
    assert "bi" in body
    stamped = datetime.fromisoformat(body["generated_at"])
    # ISO com fuso: o do projeto (America/Sao_Paulo), não UTC.
    assert stamped.utcoffset() == timezone.localtime(after).utcoffset()
    assert before <= stamped <= after + timedelta(seconds=1)
