"""O widget oficial do iFood no Gestor (DEV-2026-018, issue #2321).

O servidor só diz qual widget e qual loja carregar; o widget vazio desliga tudo.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings

from shopman.backstage.projections.ifood_store import build_ifood_widget_projection
from shopman.shop.models import Shop

MERCHANT = "0c7b8e5f-de76-42e5-b5b3-d24a726b66f7"

pytestmark = pytest.mark.django_db


def _shop(widget_id: str = "") -> Shop:
    shop = Shop.load() or Shop.objects.create(name="Nelson")
    shop.ifood_widget_id = widget_id
    shop.save()
    return shop


@override_settings(SHOPMAN_IFOOD={"merchant_id": MERCHANT})
def test_sem_id_do_widget_nada_carrega():
    _shop("")
    projection = build_ifood_widget_projection()
    assert projection.widget_id == ""
    assert projection.merchant_ids == ()


@override_settings(SHOPMAN_IFOOD={"merchant_id": ""})
def test_sem_loja_no_ifood_nada_carrega_mesmo_com_widget():
    _shop("w-123")
    assert build_ifood_widget_projection().widget_id == ""


@override_settings(SHOPMAN_IFOOD={"merchant_id": MERCHANT})
def test_com_widget_e_loja_diz_os_dois():
    _shop(" w-123 ")
    projection = build_ifood_widget_projection()
    assert projection.widget_id == "w-123"
    assert projection.merchant_ids == (MERCHANT,)


@override_settings(SHOPMAN_IFOOD={"merchant_id": MERCHANT})
def test_endpoint_so_para_quem_gere_pedidos(client):
    _shop("w-123")
    user = get_user_model().objects.create_user("ana", password="x", is_staff=True)
    client.force_login(user)
    assert client.get("/api/v1/backstage/ifood/widget/").status_code == 403

    user.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="manage_orders"))
    user = get_user_model().objects.get(pk=user.pk)
    client.force_login(user)
    response = client.get("/api/v1/backstage/ifood/widget/")
    assert response.status_code == 200
    assert response.json() == {"widget_id": "w-123", "merchant_ids": [MERCHANT]}
