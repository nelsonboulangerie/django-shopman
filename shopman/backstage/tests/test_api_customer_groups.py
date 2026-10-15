"""Grupos comerciais no Gestor: contrato, concorrência e promoção derivada."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.guestman.models import Customer, PriceTier
from shopman.offerman.models import Listing

from shopman.backstage.projections.customer_groups import build_customer_group_list
from shopman.shop.models import Channel, Promotion, Shop
from shopman.shop.services import customer_groups as customer_group_service
from shopman.shop.services.promotions import group_discount_ref

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/customers/groups/"


@pytest.fixture
def shop():
    return Shop.objects.create(name="Loja")


@pytest.fixture
def manager(shop):
    user = User.objects.create_user("gerente-grupos", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_customers",
    )
    user.user_permissions.add(permission)
    return user


@pytest.fixture
def plain_staff(shop):
    return User.objects.create_user("caixa-grupos", password="pw", is_staff=True)


def _payload(**overrides):
    payload = {
        "ref": "alianca-francesa",
        "name": "Aliança Francesa",
        "description": "Parceiros da escola",
        "listingRef": "",
        "priority": 20,
        "isDefault": False,
        "discountType": "percent",
        "discountValue": "15",
        "channelRefs": [],
        "pickupOnly": False,
        "discountKind": "parceiro",
        "rounding": True,
        "savingsMessage": "Hoje você economizou {amount} por ser {group}",
    }
    payload.update(overrides)
    return payload


def _post(client, payload, *, key=None):
    return client.post(
        URL, json.dumps(payload), content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def _patch(client, ref, payload, *, key=None):
    return client.patch(
        f"{URL}{ref}/", json.dumps(payload), content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def test_routes_require_manage_customers(client, plain_staff):
    client.force_login(plain_staff)
    assert client.get(URL).status_code == 403
    assert _post(client, _payload()).status_code == 403


def test_create_group_and_derived_promotion(client, manager):
    client.force_login(manager)
    response = _post(client, _payload())

    assert response.status_code == 201
    group = response.json()["group"]
    assert group["discount_label"] == "15% em cada item"
    assert group["channels_label"] == "Todos os canais"
    assert group["rounding"] is True
    tier = PriceTier.objects.get(ref="alianca-francesa")
    assert tier.metadata == {
        "discount_kind": "parceiro",
        "rounding": 50,
        "savings_message": "Hoje você economizou {amount} por ser {group}",
    }
    promo = Promotion.objects.get(ref=group_discount_ref(tier.ref))
    assert promo.value == 15
    assert promo.customer_segments == [tier.ref]
    assert promo.is_active is True


def test_create_is_idempotent_and_rejects_key_reuse(client, manager):
    client.force_login(manager)
    key = str(uuid4())
    first = _post(client, _payload(), key=key)
    replay = _post(client, _payload(), key=key)
    conflict = _post(client, _payload(name="Outro"), key=key)

    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert conflict.status_code == 409
    assert PriceTier.objects.count() == 1


def test_update_uses_revision_and_keeps_ref_immutable(client, manager):
    client.force_login(manager)
    created = _post(client, _payload()).json()["group"]
    changed = _patch(
        client,
        created["ref"],
        _payload(expectedRevision=created["revision"], discountValue="18", pickupOnly=True),
    )
    assert changed.status_code == 200
    assert changed.json()["group"]["pickup_only"] is True

    stale = _patch(
        client,
        created["ref"],
        _payload(expectedRevision=created["revision"], discountValue="19"),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "group_changed"

    current = changed.json()["group"]
    immutable = _patch(
        client,
        created["ref"],
        _payload(ref="novo-codigo", expectedRevision=current["revision"]),
    )
    assert immutable.status_code == 400
    assert immutable.json()["field"] == "ref"


def test_no_discount_pauses_promotion_without_deleting_history(client, manager):
    client.force_login(manager)
    created = _post(client, _payload()).json()["group"]
    response = _patch(
        client,
        created["ref"],
        _payload(
            expectedRevision=created["revision"], discountType="", discountValue="", discountKind="",
        ),
    )
    assert response.status_code == 200
    assert response.json()["group"]["discount_label"] == "Sem desconto automático"
    assert Promotion.objects.get(ref=group_discount_ref(created["ref"])).is_active is False


def test_channels_listing_and_fixed_money_are_validated_and_projected(client, manager, shop):
    client.force_login(manager)
    Channel.objects.create(ref="pdv", name="Balcão", shop=shop)
    Listing.objects.create(ref="parceiros", name="Tabela parceiros")

    response = _post(client, _payload(
        listingRef="parceiros", discountType="fixed", discountValue="2,50", channelRefs=["pdv"],
    ))
    assert response.status_code == 201
    group = response.json()["group"]
    assert group["listing_name"] == "Tabela parceiros"
    assert group["discount_value"] == "2.50"
    assert group["channels_label"] == "Balcão"
    assert Promotion.objects.get(ref=group_discount_ref(group["ref"])).value == 250

    invalid = _post(client, _payload(ref="invalido", channelRefs=["sumiu"]))
    assert invalid.status_code == 400
    assert invalid.json()["field"] == "channelRefs"


def test_default_is_unique_and_group_with_customers_is_counted(client, manager):
    client.force_login(manager)
    first = _post(client, _payload(ref="varejo", name="Varejo", isDefault=True)).json()["group"]
    second = _post(client, _payload(ref="vip", name="VIP", isDefault=True)).json()["group"]
    assert PriceTier.objects.get(ref=first["ref"]).is_default is False
    tier = PriceTier.objects.get(ref=second["ref"])
    Customer.objects.create(ref="CLI-VIP", first_name="Ana", price_tier=tier)

    groups = client.get(URL).json()["groups"]
    vip = next(item for item in groups["items"] if item["ref"] == "vip")
    assert vip["customer_count_label"] == "1 cliente"
    assert vip["is_default"] is True


def test_list_query_count_does_not_grow_with_groups(django_assert_num_queries):
    for index in range(6):
        tier = PriceTier.objects.create(ref=f"g-{index}", name=f"Grupo {index}")
        customer_group_service.sync_group_discount(
            tier, discount_type=Promotion.PERCENT, discount_value_q=10 + index,
        )
    with django_assert_num_queries(5):
        result = build_customer_group_list()
        assert result.total == 6


def test_groups_are_not_hard_deleted(client, manager):
    client.force_login(manager)
    created = _post(client, _payload()).json()["group"]
    assert client.delete(f"{URL}{created['ref']}/").status_code == 405
    assert PriceTier.objects.filter(ref=created["ref"]).exists()
