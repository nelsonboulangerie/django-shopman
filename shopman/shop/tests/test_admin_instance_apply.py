"""A trilha do apply do descritor aparece no Admin e não se edita por lá.

``InstanceApplyRecord`` é a base da comparação de três vias do próximo apply:
editar ou apagar uma linha mudaria o que o apply considera "mudado por fora".
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from shopman.shop.models import InstanceApplyRecord, Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def record():
    return InstanceApplyRecord.objects.create(
        instance_ref="nelson",
        schema_version=1,
        descriptor_sha256="a1b2c3d4e5f6" + "0" * 52,
        descriptor={"instance": {"ref": "nelson"}},
        changes=[{"kind": "channel", "ref": "web", "action": "updated"}],
        actor="deploy@release",
        on_drift="refuse",
    )


@pytest.fixture
def admin_client(client):
    Shop.objects.create(name="Loja")  # sem loja, o onboarding redireciona o Admin
    user = User.objects.create_superuser("auditor", "auditor@example.com", "x")
    client.force_login(user)
    return client


def test_changelist_shows_who_applied_what(admin_client, record):
    response = admin_client.get(reverse("admin:shop_instanceapplyrecord_changelist"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "deploy@release" in body
    assert "a1b2c3d4e5f6" in body


def test_detail_is_read_only(admin_client, record):
    url = reverse("admin:shop_instanceapplyrecord_change", args=[record.pk])
    response = admin_client.get(url)

    assert response.status_code == 200
    assert "updated" in response.content.decode()

    posted = admin_client.post(url, {"actor": "outra pessoa"})
    assert posted.status_code == 403
    record.refresh_from_db()
    assert record.actor == "deploy@release"


def test_trail_cannot_be_added_or_deleted(admin_client, record):
    assert admin_client.get(reverse("admin:shop_instanceapplyrecord_add")).status_code == 403
    delete_url = reverse("admin:shop_instanceapplyrecord_delete", args=[record.pk])
    assert admin_client.post(delete_url, {"post": "yes"}).status_code == 403
    assert InstanceApplyRecord.objects.filter(pk=record.pk).exists()
