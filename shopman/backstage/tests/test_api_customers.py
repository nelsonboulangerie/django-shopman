"""Clientes no Gestor — achar, comparar, unificar e desfazer (api/v1/backstage/customers/*).

O caso que motivou a seção: o cadastro do iFood (``IF-*``) nasce sem telefone e,
até 19/09/2026, nascia um por pedido. Nenhuma tela o achava para unificar. Estes
testes guardam que a lista o acha, que a prévia não grava nada, que unificar e
desfazer passam pelo ``MergeService`` e que quem não é gestor não chega perto.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/backstage/customers/"
PREVIEW_URL = "/api/v1/backstage/customers/merge/preview/"
MERGE_URL = "/api/v1/backstage/customers/merge/"
MERGES_URL = "/api/v1/backstage/customers/merges/"

IFOOD_CUSTOMER_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def _perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_customers",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def manager(shop):
    user = User.objects.create_user("gerente", password="pw", is_staff=True)
    user.user_permissions.add(_perm())
    return user


@pytest.fixture
def plain_staff(shop):
    return User.objects.create_user("caixa", password="pw", is_staff=True)


def _order(ref: str, customer_ref: str, *, ifood_id: str = "", channel_ref: str = "ifood") -> Order:
    customer = {"name": "Maria"}
    if ifood_id:
        customer["ifood_customer_id"] = ifood_id
    return Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        session_key=f"s-{ref}",
        status="completed",
        total_q=2500,
        data={"customer_ref": customer_ref, "customer": customer},
    )


@pytest.fixture
def people(shop):
    """A mesma Maria três vezes: dois IF-* antigos e o cadastro do balcão."""
    balcao = Customer.objects.create(
        ref="CLI-MARIA", first_name="Maria", last_name="Souza",
        phone="+5543999990000", document="11122233344", source_system="pdv",
    )
    if_old = Customer.objects.create(
        ref="IF-AAAA0001", first_name="Maria", last_name="Souza", phone="", source_system="ifood",
    )
    if_new = Customer.objects.create(
        ref="IF-BBBB0002", first_name="Maria", last_name="S.", phone="", source_system="ifood",
    )
    CustomerIdentifier.objects.create(
        customer=if_old, identifier_type=IdentifierType.IFOOD, identifier_value="ifood-order-1", is_primary=True,
    )
    _order("IF-ORD-1", if_old.ref, ifood_id=IFOOD_CUSTOMER_ID)
    _order("IF-ORD-2", if_new.ref, ifood_id=IFOOD_CUSTOMER_ID)
    _order("BAL-1", balcao.ref, channel_ref="pdv")
    other = Customer.objects.create(
        ref="CLI-JOAO", first_name="João", last_name="Lima", phone="+5543988880000", source_system="pdv",
    )
    return {"balcao": balcao, "if_old": if_old, "if_new": if_new, "other": other}


# ── Permissão ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", LIST_URL),
        ("get", f"{LIST_URL}CLI-MARIA/"),
        ("get", f"{PREVIEW_URL}?source_ref=IF-AAAA0001&target_ref=CLI-MARIA"),
        ("post", MERGE_URL),
        ("get", MERGES_URL),
    ],
)
def test_every_route_requires_manage_customers(client, plain_staff, people, method, url):
    client.force_login(plain_staff)
    assert getattr(client, method)(url).status_code == 403


def test_anonymous_is_blocked(client, people):
    assert client.get(LIST_URL).status_code in (401, 403)


# ── Lista ─────────────────────────────────────────────────────────────


def test_list_shows_active_customers_with_order_counts(client, manager, people):
    client.force_login(manager)
    body = client.get(LIST_URL).json()["list"]

    refs = {row["ref"] for row in body["items"]}
    assert refs == {"CLI-MARIA", "IF-AAAA0001", "IF-BBBB0002", "CLI-JOAO"}
    maria = next(row for row in body["items"] if row["ref"] == "CLI-MARIA")
    assert maria["phone_display"] == "(43) 99999-0000"
    assert maria["document_display"] == "111.222.333-44"
    assert maria["orders_label"] == "1 pedido"
    assert maria["source_label"] == "Balcão"
    assert body["total_label"] == "4 clientes"


def test_filter_no_phone_finds_the_ifood_records(client, manager, people):
    client.force_login(manager)
    body = client.get(LIST_URL, {"filter": "no_phone"}).json()["list"]
    assert {row["ref"] for row in body["items"]} == {"IF-AAAA0001", "IF-BBBB0002"}
    assert all(row["is_ifood"] and row["source_label"] == "iFood" for row in body["items"])


def test_filter_ifood(client, manager, people):
    client.force_login(manager)
    body = client.get(LIST_URL, {"filter": "ifood"}).json()["list"]
    assert {row["ref"] for row in body["items"]} == {"IF-AAAA0001", "IF-BBBB0002"}


def test_filter_possible_duplicates_is_by_same_name_or_cpf(client, manager, people):
    client.force_login(manager)
    body = client.get(LIST_URL, {"filter": "possible_duplicates"}).json()["list"]
    assert {row["ref"] for row in body["items"]} == {"CLI-MARIA", "IF-AAAA0001"}
    assert all(row["duplicate_hint"] == "Mesmo nome de outro cadastro" for row in body["items"])


def test_search_by_formatted_phone_and_full_name(client, manager, people):
    client.force_login(manager)
    by_phone = client.get(LIST_URL, {"q": "(43) 99999-0000"}).json()["list"]["items"]
    assert [row["ref"] for row in by_phone] == ["CLI-MARIA"]
    by_name = client.get(LIST_URL, {"q": "maria souza"}).json()["list"]["items"]
    assert {row["ref"] for row in by_name} == {"CLI-MARIA", "IF-AAAA0001"}


def test_list_hides_absorbed_records(client, manager, people):
    Customer.objects.filter(ref="IF-AAAA0001").update(is_active=False)
    client.force_login(manager)
    refs = {row["ref"] for row in client.get(LIST_URL).json()["list"]["items"]}
    assert "IF-AAAA0001" not in refs


def test_list_paginates(client, manager, shop):
    for index in range(35):
        Customer.objects.create(ref=f"CLI-{index:03d}", first_name=f"Pessoa {index}", phone="")
    client.force_login(manager)
    first = client.get(LIST_URL).json()["list"]
    second = client.get(LIST_URL, {"page": 2}).json()["list"]
    assert len(first["items"]) == 30 and first["has_next"] is True
    assert len(second["items"]) == 5 and second["has_next"] is False


# ── Ficha e candidatos ────────────────────────────────────────────────


def test_detail_suggests_same_ifood_customer_and_same_name(client, manager, people):
    client.force_login(manager)
    customer = client.get(f"{LIST_URL}IF-AAAA0001/").json()["customer"]

    reasons = {candidate["ref"]: candidate["reason_label"] for candidate in customer["candidates"]}
    assert reasons == {"IF-BBBB0002": "Mesmo cliente no iFood", "CLI-MARIA": "Mesmo nome"}
    assert customer["identifiers"] == [{"type_label": "iFood", "value": "ifood-order-1"}]
    assert customer["orders_label"] == "1 pedido"
    assert customer["recent_orders"][0]["ref"] == "IF-ORD-1"


def test_detail_of_absorbed_record_says_where_it_went(client, manager, people):
    client.force_login(manager)
    client.post(MERGE_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"}, content_type="application/json")
    customer = client.get(f"{LIST_URL}IF-AAAA0001/").json()["customer"]
    assert customer["is_active"] is False
    assert customer["merged_into_ref"] == "CLI-MARIA"
    assert customer["candidates"] == []
    assert customer["actions"] == []


def test_detail_404(client, manager, shop):
    client.force_login(manager)
    assert client.get(f"{LIST_URL}NAO-EXISTE/").status_code == 404


# ── Prévia ────────────────────────────────────────────────────────────


def test_preview_describes_the_merge_and_writes_nothing(client, manager, people):
    client.force_login(manager)
    response = client.get(PREVIEW_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"})
    assert response.status_code == 200
    preview = response.json()["preview"]

    assert preview["source"]["ref"] == "IF-AAAA0001"
    assert preview["target"]["ref"] == "CLI-MARIA"
    moves = {move["ref"]: move["label"] for move in preview["moves"]}
    assert moves["orders"] == "1 pedido"
    assert moves["identifiers"] == "1 identificador"
    assert preview["actions"][0]["href"] == MERGE_URL
    # Sem conta de fidelidade, o aviso não fala de pontos.
    assert preview["loyalty_label"] == ""
    assert "fidelidade" not in preview["undo_notice"]

    assert Customer.objects.get(ref="IF-AAAA0001").is_active is True
    assert Order.objects.get(ref="IF-ORD-1").data["customer_ref"] == "IF-AAAA0001"
    assert not MergeAudit.objects.exists()


def test_preview_says_which_gap_the_donor_fills(client, manager, people):
    Customer.objects.filter(ref="IF-AAAA0001").update(document="99988877766")
    Customer.objects.filter(ref="CLI-JOAO").update(document="")
    client.force_login(manager)
    preview = client.get(PREVIEW_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-JOAO"}).json()["preview"]
    assert preview["fills"] == [{"field_label": "CPF", "value": "999.888.777-66"}]


@pytest.mark.parametrize(
    ("params", "status", "detail"),
    [
        ({"source_ref": "CLI-MARIA", "target_ref": "CLI-MARIA"}, 422, "mesmo cadastro"),
        ({"source_ref": "", "target_ref": "CLI-MARIA"}, 422, "Escolha os dois"),
        ({"source_ref": "NAO-EXISTE", "target_ref": "CLI-MARIA"}, 404, "não existe mais"),
    ],
)
def test_preview_refusals_speak_portuguese(client, manager, people, params, status, detail):
    client.force_login(manager)
    response = client.get(PREVIEW_URL, params)
    assert response.status_code == status
    assert detail in response.json()["detail"]


# ── Unificar e desfazer ───────────────────────────────────────────────


def test_merge_moves_orders_and_records_the_gestor(client, manager, people):
    client.force_login(manager)
    response = client.post(
        MERGE_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"}, content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    audit = MergeAudit.objects.get(pk=body["audit_id"])
    assert audit.actor == "gerente"
    assert audit.evidence["source_surface"] == "gestor"
    assert Customer.objects.get(ref="IF-AAAA0001").is_active is False
    assert Order.objects.get(ref="IF-ORD-1").data["customer_ref"] == "CLI-MARIA"


def test_merge_into_absorbed_record_is_refused(client, manager, people):
    Customer.objects.filter(ref="CLI-MARIA").update(is_active=False)
    client.force_login(manager)
    response = client.post(
        MERGE_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"}, content_type="application/json",
    )
    assert response.status_code == 422
    assert "Escolha o cadastro que ficou" in response.json()["detail"]


def test_history_lists_the_merge_and_undo_restores_it(client, manager, people):
    client.force_login(manager)
    audit_id = client.post(
        MERGE_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"}, content_type="application/json",
    ).json()["audit_id"]

    merges = client.get(MERGES_URL).json()["merges"]
    row = merges["items"][0]
    assert row["id"] == audit_id
    assert row["target_name"] == "Maria Souza"
    assert row["can_undo"] is True
    assert row["undo_label"].startswith("Dá para desfazer por mais")
    assert "1 pedido" in row["moved_label"]
    assert row["loyalty_merged"] is False
    assert merges["undo_window_hours"] == 24

    response = client.post(f"{MERGES_URL}{audit_id}/undo/")
    assert response.status_code == 200
    assert Customer.objects.get(ref="IF-AAAA0001").is_active is True
    assert Order.objects.get(ref="IF-ORD-1").data["customer_ref"] == "IF-AAAA0001"
    audit = MergeAudit.objects.get(pk=audit_id)
    assert audit.status == MergeStatus.REVERTED
    assert audit.reverted_by == "gerente"

    again = client.post(f"{MERGES_URL}{audit_id}/undo/")
    assert again.status_code == 422
    assert "já foi desfeita por gerente" in again.json()["detail"]


def test_undo_after_the_window_is_refused_with_the_manual_path(client, manager, people):
    client.force_login(manager)
    audit_id = client.post(
        MERGE_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"}, content_type="application/json",
    ).json()["audit_id"]
    MergeAudit.objects.filter(pk=audit_id).update(merged_at=timezone.now() - timedelta(hours=25))

    response = client.post(f"{MERGES_URL}{audit_id}/undo/")
    assert response.status_code == 422
    assert "cadastre IF-AAAA0001 de novo" in response.json()["detail"]
    row = client.get(MERGES_URL).json()["merges"]["items"][0]
    assert row["can_undo"] is False
    assert row["undo_label"].startswith("O prazo para desfazer terminou")


def test_undo_unknown_audit_is_404(client, manager, shop):
    client.force_login(manager)
    assert client.post(f"{MERGES_URL}nao-e-uuid/undo/").status_code == 404


def test_undo_requires_manage_customers(client, plain_staff, people):
    client.force_login(plain_staff)
    assert client.post(f"{MERGES_URL}00000000-0000-0000-0000-000000000000/undo/").status_code == 403


def test_preview_and_history_speak_of_loyalty_only_when_there_is_loyalty(client, manager, people):
    from shopman.guestman.contrib.loyalty.models import LoyaltyAccount

    LoyaltyAccount.objects.create(customer=people["if_old"], points_balance=120, lifetime_points=120)
    client.force_login(manager)
    preview = client.get(PREVIEW_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"}).json()["preview"]
    assert preview["loyalty_label"] == "120 pontos de fidelidade somam no cadastro que fica"
    assert "não voltam com o desfazer" in preview["undo_notice"]

    client.post(MERGE_URL, {"source_ref": "IF-AAAA0001", "target_ref": "CLI-MARIA"}, content_type="application/json")
    assert client.get(MERGES_URL).json()["merges"]["items"][0]["loyalty_merged"] is True


# ── A aba só para quem pode ───────────────────────────────────────────

SESSION_URL = "/api/v1/backstage/operator/session/"


def test_session_answers_whether_the_operator_can_manage_customers(client, manager, plain_staff):
    """A barra do Gestor pergunta à antessala se mostra a aba Clientes.

    Sem ``shop.manage_customers`` na allowlist a pergunta seria 400 e a aba
    sumiria para todos, inclusive o gerente.
    """
    client.force_login(manager)
    response = client.get(SESSION_URL, {"perm": "shop.manage_customers"})
    assert response.status_code == 200
    assert response.json()["authorized"] is True

    client.force_login(plain_staff)
    assert client.get(SESSION_URL, {"perm": "shop.manage_customers"}).json()["authorized"] is False
