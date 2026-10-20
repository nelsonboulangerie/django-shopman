"""Pôr e tirar vários clientes de um grupo comercial, numa ida (Gestor).

O vínculo cliente ↔ grupo é N:N (``Customer.price_tiers``). Pôr nunca apaga os
outros grupos do cliente; tirar devolve ao grupo padrão quem ficaria sem nenhum.
O número de consultas não cresce com a seleção.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.guestman.models import Customer, PriceTier

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/customers/groups/{ref}/members/"
LIST_URL = "/api/v1/backstage/customers/"


@pytest.fixture
def shop():
    return Shop.objects.create(name="Loja")


@pytest.fixture
def manager(shop):
    user = User.objects.create_user("gerente-membros", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_customers",
    )
    user.user_permissions.add(permission)
    return user


@pytest.fixture
def tiers(shop):
    varejo = PriceTier.objects.create(ref="varejo", name="Varejo", is_default=True, priority=0)
    equipe = PriceTier.objects.create(ref="equipe", name="Equipe", priority=30)
    alianca = PriceTier.objects.create(ref="alianca", name="Aliança Francesa", priority=20)
    return {"varejo": varejo, "equipe": equipe, "alianca": alianca}


def _customers(count: int, *, prefix: str = "CLI") -> list[Customer]:
    return [
        Customer.objects.create(ref=f"{prefix}-{index:03d}", first_name=f"Cliente {index}")
        for index in range(count)
    ]


def _post(client, ref, payload, *, key=None):
    return client.post(
        URL.format(ref=ref), json.dumps(payload), content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def _groups(customer: Customer) -> set[str]:
    return set(customer.price_tiers.values_list("ref", flat=True))


def test_exige_manage_customers(client, shop, tiers):
    plain = User.objects.create_user("caixa-membros", password="pw", is_staff=True)
    client.force_login(plain)
    response = _post(client, "equipe", {"operation": "add", "refs": ["X"]})
    assert response.status_code == 403


def test_por_no_grupo_preserva_os_outros_grupos(client, manager, tiers):
    first, second = _customers(2)
    first.price_tiers.add(tiers["alianca"])
    client.force_login(manager)

    response = _post(client, "equipe", {"operation": "add", "refs": [first.ref, second.ref]})

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["outcome"] == "applied"
    assert body["applied"] == [first.ref, second.ref]
    assert body["group"] == {"ref": "equipe", "name": "Equipe"}
    # Nada some: o padrão e a Aliança continuam, a Equipe entra.
    assert _groups(first) == {"varejo", "alianca", "equipe"}
    assert _groups(second) == {"varejo", "equipe"}


def test_repetir_o_gesto_nao_muda_nada(client, manager, tiers):
    (customer,) = _customers(1)
    client.force_login(manager)
    _post(client, "equipe", {"operation": "add", "refs": [customer.ref]})

    again = _post(client, "equipe", {"operation": "add", "refs": [customer.ref]}).json()

    assert again["applied"] == []
    assert again["unchanged"] == [customer.ref]
    assert customer.price_tiers.filter(ref="equipe").count() == 1


def test_mesma_intencao_reaproveita_a_resposta(client, manager, tiers):
    (customer,) = _customers(1)
    client.force_login(manager)
    key = str(uuid4())
    first = _post(client, "equipe", {"operation": "add", "refs": [customer.ref]}, key=key)
    replay = _post(client, "equipe", {"operation": "add", "refs": [customer.ref]}, key=key)
    assert first.json()["applied"] == replay.json()["applied"] == [customer.ref]


def test_tirar_do_grupo_tira_so_dele(client, manager, tiers):
    (customer,) = _customers(1)
    customer.price_tiers.add(tiers["equipe"], tiers["alianca"])
    client.force_login(manager)

    body = _post(client, "equipe", {"operation": "remove", "refs": [customer.ref]}).json()

    assert body["applied"] == [customer.ref]
    assert body["moved_to_default"] == []
    assert _groups(customer) == {"varejo", "alianca"}


def test_quem_ficaria_sem_grupo_volta_para_o_padrao(client, manager, tiers):
    (customer,) = _customers(1)
    customer.price_tiers.set([tiers["equipe"]])
    client.force_login(manager)

    body = _post(client, "equipe", {"operation": "remove", "refs": [customer.ref]}).json()

    assert body["applied"] == [customer.ref]
    assert body["moved_to_default"] == [customer.ref]
    assert body["default_group"] == {"ref": "varejo", "name": "Varejo"}
    assert _groups(customer) == {"varejo"}


def test_quem_so_esta_no_padrao_continua_nele(client, manager, tiers):
    only_default, with_other = _customers(2)
    with_other.price_tiers.add(tiers["alianca"])
    client.force_login(manager)

    body = _post(
        client, "varejo", {"operation": "remove", "refs": [only_default.ref, with_other.ref]},
    ).json()

    assert body["applied"] == [with_other.ref]
    assert body["skipped"] == [{"ref": only_default.ref, "reason": "only_group"}]
    assert _groups(only_default) == {"varejo"}
    assert _groups(with_other) == {"alianca"}


def test_inativo_e_inexistente_ficam_de_fora(client, manager, tiers):
    active, inactive = _customers(2)
    Customer.objects.filter(pk=inactive.pk).update(is_active=False)
    client.force_login(manager)

    body = _post(
        client, "equipe", {"operation": "add", "refs": [active.ref, inactive.ref, "SUMIU"]},
    ).json()

    assert body["applied"] == [active.ref]
    assert body["skipped"] == [
        {"ref": inactive.ref, "reason": "not_found_or_inactive"},
        {"ref": "SUMIU", "reason": "not_found_or_inactive"},
    ]
    assert not inactive.price_tiers.filter(ref="equipe").exists()


@pytest.mark.parametrize(
    ("ref", "payload", "status", "field"),
    [
        ("nao-existe", {"operation": "add", "refs": ["X"]}, 404, None),
        ("equipe", {"operation": "trocar", "refs": ["X"]}, 400, "operation"),
        ("equipe", {"operation": "add", "refs": []}, 400, "refs"),
        ("equipe", {"operation": "add", "refs": [""]}, 400, "refs"),
        ("equipe", {"operation": "add", "refs": ["X"], "tags": ["a"]}, 400, "tags"),
        ("equipe", {"operation": "add", "refs": [f"C{n}" for n in range(201)]}, 400, "refs"),
    ],
)
def test_recusa_no_dialeto_canonico(client, manager, tiers, ref, payload, status, field):
    client.force_login(manager)
    response = _post(client, ref, payload)
    assert response.status_code == status
    body = response.json()
    assert body["detail"]
    assert body["outcome"] == "not_applied"
    if field:
        assert body["field"] == field
        assert body["errors"] == {field: [body["detail"]]}


def _post_queries(client, ref, payload) -> tuple[int, object]:
    with CaptureQueriesContext(connection) as captured:
        response = _post(client, ref, payload)
    assert response.status_code == 200, response.json()
    return len(captured.captured_queries), response


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_consultas_nao_crescem_com_a_selecao(client, manager, tiers, operation):
    small = _customers(3, prefix="P")
    large = _customers(60, prefix="G")
    if operation == "remove":
        for customer in small + large:
            customer.price_tiers.set([tiers["equipe"]])
    client.force_login(manager)

    small_count, _ = _post_queries(client, "equipe", {"operation": operation, "refs": [c.ref for c in small]})
    large_count, response = _post_queries(client, "equipe", {"operation": operation, "refs": [c.ref for c in large]})

    assert large_count == small_count
    assert len(response.json()["applied"]) == 60
    assert "projection;dur=" in response.headers["Server-Timing"]


def test_lista_recorta_por_grupo_e_mostra_os_grupos(client, manager, tiers):
    first, second = _customers(2)
    first.price_tiers.add(tiers["equipe"])
    client.force_login(manager)

    response = client.get(LIST_URL, {"group": "equipe"})

    assert response.status_code == 200
    listing = response.json()["list"]
    assert listing["group"] == "equipe"
    assert [row["ref"] for row in listing["items"]] == [first.ref]
    assert [group["ref"] for group in listing["items"][0]["groups"]] == ["equipe", "varejo"]
    assert listing["items"][0]["groups"][0]["is_primary"] is True


def test_lista_carrega_os_grupos_sem_consulta_por_linha(client, manager, tiers):
    _customers(3, prefix="P")
    client.force_login(manager)
    with CaptureQueriesContext(connection) as small:
        client.get(LIST_URL)
    _customers(20, prefix="G")
    with CaptureQueriesContext(connection) as large:
        client.get(LIST_URL)
    assert len(large.captured_queries) == len(small.captured_queries)
