"""Clientes no Gestor — achar, comparar, unificar e desfazer (api/v1/backstage/customers/*).

O caso que motivou a seção: o cadastro do iFood (``IF-*``) nasce sem telefone e,
até 19/09/2026, nascia um por pedido. Nenhuma tela o achava para unificar. Estes
testes guardam que a lista o acha, que a prévia não grava nada, que unificar e
desfazer passam pelo ``MergeService`` e que quem não é gestor não chega perto.
"""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus
from shopman.guestman.models import ContactPoint, Customer, CustomerAddress, PriceTier
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


def _post(client, url: str, body: dict, *, key: str | None = None):
    return client.post(
        url,
        json.dumps(body),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def _patch(client, url: str, body: dict, *, key: str | None = None):
    return client.patch(
        url,
        json.dumps(body),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
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
        ("post", f"{LIST_URL}CLI-MARIA/duplicate/"),
        ("post", f"{LIST_URL}bulk/"),
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


def test_regular_list_limits_duplicate_scan_to_the_visible_page(client, manager, people, monkeypatch):
    from shopman.backstage.projections import customers

    calls = []
    original = customers._duplicate_sets

    def tracked(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(customers, "_duplicate_sets", tracked)
    client.force_login(manager)
    assert client.get(LIST_URL).status_code == 200

    assert len(calls) == 1
    assert calls[0]["names"] == {"maria souza", "maria s.", "joão lima"}
    assert calls[0]["documents"] == {"11122233344"}


def test_list_sorts_by_name_and_serves_form_options(client, manager, people):
    PriceTier.objects.create(ref="vizinho", name="Vizinho", priority=10)
    client.force_login(manager)

    listing = client.get(LIST_URL, {"sort": "name"}).json()["list"]

    assert [row["name"] for row in listing["items"]] == sorted(row["name"] for row in listing["items"])
    assert listing["sort"] == "name"
    assert listing["form"]["customer_types"] == [
        {"value": "individual", "label": "Pessoa Física"},
        {"value": "business", "label": "Pessoa Jurídica"},
    ]
    assert {tier["value"] for tier in listing["form"]["price_tiers"]} == {"vizinho"}


# ── Cadastro turbo ───────────────────────────────────────────────────


def test_create_customer_is_idempotent_and_returns_the_exact_record(client, manager, shop):
    tier = PriceTier.objects.create(ref="varejo", name="Varejo", is_default=True)
    client.force_login(manager)
    payload = {
        "firstName": "Ana",
        "lastName": "Silva",
        "customerType": "individual",
        "document": "529.982.247-25",
        "phone": "(43) 99999-1111",
        "email": "ANA@EXAMPLE.COM",
        "priceTierRef": tier.ref,
        "tags": ["vizinha", " Café "],
        "notes": "Prefere retirada.",
        "houseAccount": True,
        "houseAccountLimit": "250,50",
        "fiscalCpfNaNota": True,
        "fiscalEmailReceipt": True,
    }

    first = _post(client, LIST_URL, payload, key="create-ana")
    replay = _post(client, LIST_URL, payload, key="create-ana")

    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()
    body = first.json()
    assert body["outcome"] == "applied"
    assert body["resource"] == {"kind": "customer", "ref": body["customer"]["ref"]}
    customer = Customer.objects.get(ref=body["customer"]["ref"])
    assert Customer.objects.count() == 1
    assert customer.created_by == manager.username
    assert customer.source_system == "manual"
    assert customer.document == "52998224725"
    assert customer.email == "ana@example.com"
    assert set(customer.tags.names()) == {"vizinha", "Café"}
    assert customer.metadata == {
        "house_account": True,
        "house_account_limit_q": 25050,
        "fiscal_prefs": {"cpf_na_nota": True, "email_receipt": True},
    }
    assert ContactPoint.objects.filter(customer=customer, is_primary=True).count() == 2


def test_create_customer_refuses_invalid_fields_and_reused_intention(client, manager, shop):
    client.force_login(manager)
    invalid = _post(client, LIST_URL, {"firstName": "Ana", "document": "111"})
    assert invalid.status_code == 400
    assert invalid.json()["field"] == "document"

    assert _post(client, LIST_URL, {"firstName": "Ana"}, key="one-customer").status_code == 201
    conflict = _post(client, LIST_URL, {"firstName": "Bia"}, key="one-customer")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "intention_conflict"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"firstName": "Ana", "houseAccountLimit": "100,00"}, "houseAccountLimit"),
        ({"firstName": "Ana", "fiscalCpfNaNota": True}, "document"),
        ({"firstName": "Ana", "fiscalEmailReceipt": True}, "email"),
        ({"firstName": "Ana", "tags": ["vizinha", 7]}, "tags"),
    ],
)
def test_create_customer_refuses_inconsistent_commercial_data(client, manager, shop, payload, field):
    client.force_login(manager)

    response = _post(client, LIST_URL, payload)

    assert response.status_code == 400
    assert response.json()["field"] == field
    assert Customer.objects.count() == 0


def test_edit_customer_uses_revision_and_preserves_contact_history(client, manager, people):
    client.force_login(manager)
    url = f"{LIST_URL}CLI-MARIA/"
    detail = client.get(url).json()["customer"]

    payload = {
        "expectedRevision": detail["revision"],
        "firstName": "Maria Clara",
        "phone": "",
        "tags": ["cliente antiga"],
        "houseAccount": True,
        "houseAccountLimit": "1000.00",
        "fiscalCpfNaNota": True,
    }
    response = _patch(client, url, payload, key="edit-maria")
    replay = _patch(client, url, payload, key="edit-maria")

    assert response.status_code == replay.status_code == 200, response.content
    assert replay.json() == response.json()
    assert response.json()["outcome"] == "applied"
    edited = response.json()["customer"]
    assert edited["first_name"] == "Maria Clara"
    assert edited["phone"] == ""
    assert edited["tags"] == ["cliente antiga"]
    customer = Customer.objects.get(ref="CLI-MARIA")
    assert customer.metadata["house_account_limit_q"] == 100000
    assert ContactPoint.objects.filter(customer=customer, type=ContactPoint.Type.PHONE).exists()
    assert not ContactPoint.objects.filter(
        customer=customer, type__in=(ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP), is_primary=True,
    ).exists()

    turned_off = _patch(client, url, {
        "expectedRevision": edited["revision"],
        "houseAccount": False,
    })
    assert turned_off.status_code == 200
    customer.refresh_from_db()
    assert "house_account" not in customer.metadata
    assert "house_account_limit_q" not in customer.metadata


def test_edit_customer_refuses_missing_and_stale_revisions(client, manager, people):
    client.force_login(manager)
    url = f"{LIST_URL}CLI-MARIA/"
    revision = client.get(url).json()["customer"]["revision"]
    no_intention = client.patch(
        url,
        json.dumps({"expectedRevision": revision, "notes": "sem intenção"}),
        content_type="application/json",
    )
    assert no_intention.status_code == 400
    assert no_intention.json()["error"]["code"] == "intention_required"
    missing = _patch(client, url, {"notes": "sem revisão"})
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "revision_required"

    assert _patch(client, url, {"expectedRevision": revision, "notes": "primeira aba"}).status_code == 200
    stale = _patch(client, url, {"expectedRevision": revision, "notes": "segunda aba"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "customer_changed"
    assert Customer.objects.get(ref="CLI-MARIA").notes == "primeira aba"


def test_address_create_replays_and_first_address_becomes_default(client, manager, people):
    client.force_login(manager)
    url = f"{LIST_URL}CLI-MARIA/addresses/"
    payload = {
        "label": "home",
        "formattedAddress": "Rua das Flores, 10 - Centro, Londrina - PR",
        "route": "Rua das Flores",
        "streetNumber": "10",
        "neighborhood": "Centro",
        "city": "Londrina",
        "stateCode": "PR",
        "postalCode": "86000-000",
        "complement": "Fundos",
        # O formulário envia falso no estado inicial; o domínio ainda garante
        # que o primeiro endereço do cadastro seja o padrão.
        "isDefault": False,
    }

    first = _post(client, url, payload, key="address-1")
    replay = _post(client, url, payload, key="address-1")

    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()
    assert CustomerAddress.objects.count() == 1
    address = first.json()["customer"]["addresses"][0]
    assert address["label"] == "Casa"
    assert address["is_default"] is True
    assert address["is_verified"] is False


def test_address_other_requires_a_name(client, manager, people):
    client.force_login(manager)

    response = _post(client, f"{LIST_URL}CLI-MARIA/addresses/", {
        "label": "other",
        "formattedAddress": "Rua A, 1",
    })

    assert response.status_code == 400
    assert response.json()["field"] == "labelCustom"
    assert not CustomerAddress.objects.exists()


def test_address_edit_uses_its_own_revision(client, manager, people):
    address = CustomerAddress.objects.create(
        customer=people["balcao"], formatted_address="Rua A, 1", is_default=True,
    )
    client.force_login(manager)
    url = f"{LIST_URL}CLI-MARIA/addresses/{address.pk}/"
    revision = address.updated_at.isoformat()

    payload = {
        "expectedRevision": revision,
        "formattedAddress": "Rua A, 2",
        "streetNumber": "2",
    }
    edited = _patch(client, url, payload, key="edit-address-1")
    replay = _patch(client, url, payload, key="edit-address-1")
    stale = _patch(client, url, {
        "expectedRevision": revision,
        "formattedAddress": "Rua A, 3",
    })

    assert edited.status_code == replay.status_code == 200
    assert replay.json() == edited.json()
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "customer_changed"
    address.refresh_from_db()
    assert address.formatted_address == "Rua A, 2"


def test_address_non_location_edit_preserves_verification_but_location_edit_clears_it(client, manager, people):
    address = CustomerAddress.objects.create(
        customer=people["balcao"],
        formatted_address="Rua A, 1",
        place_id="google-place-1",
        latitude="-23.3100000",
        longitude="-51.1600000",
        is_verified=True,
        is_default=True,
    )
    client.force_login(manager)
    url = f"{LIST_URL}CLI-MARIA/addresses/{address.pk}/"

    instructions = _patch(client, url, {
        "expectedRevision": address.updated_at.isoformat(),
        "deliveryInstructions": "Chamar na portaria",
    })
    assert instructions.status_code == 200
    address.refresh_from_db()
    assert address.is_verified is True
    assert address.place_id == "google-place-1"

    moved = _patch(client, url, {
        "expectedRevision": address.updated_at.isoformat(),
        "formattedAddress": "Rua A, 2",
    })
    assert moved.status_code == 200
    address.refresh_from_db()
    assert address.is_verified is False
    assert address.place_id == ""
    assert address.latitude is None
    assert address.longitude is None


def test_address_cannot_leave_an_active_customer_without_a_default(client, manager, people):
    address = CustomerAddress.objects.create(
        customer=people["balcao"], formatted_address="Rua A, 1", is_default=True,
    )
    client.force_login(manager)

    response = _patch(client, f"{LIST_URL}CLI-MARIA/addresses/{address.pk}/", {
        "expectedRevision": address.updated_at.isoformat(),
        "isDefault": False,
    })

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "default_address_required"
    address.refresh_from_db()
    assert address.is_default is True


def test_address_delete_replays_and_promotes_a_replacement(client, manager, people):
    first = CustomerAddress.objects.create(
        customer=people["balcao"], formatted_address="Rua A, 1", is_default=True,
    )
    second = CustomerAddress.objects.create(
        customer=people["balcao"], formatted_address="Rua B, 2", is_default=False,
    )
    client.force_login(manager)
    url = f"{LIST_URL}CLI-MARIA/addresses/{first.pk}/"
    body = json.dumps({"expectedRevision": first.updated_at.isoformat()})

    removed = client.delete(
        url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="delete-address-1",
    )
    replay = client.delete(
        url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="delete-address-1",
    )

    assert removed.status_code == replay.status_code == 200
    assert replay.json() == removed.json()
    assert not CustomerAddress.objects.filter(pk=first.pk).exists()
    second.refresh_from_db()
    assert second.is_default is True


# ── Ficha e candidatos ────────────────────────────────────────────────


def test_detail_suggests_same_ifood_customer_and_same_name(client, manager, people):
    client.force_login(manager)
    customer = client.get(f"{LIST_URL}IF-AAAA0001/").json()["customer"]

    reasons = {candidate["ref"]: candidate["reason_label"] for candidate in customer["candidates"]}
    assert reasons == {"IF-BBBB0002": "Mesmo cliente no iFood", "CLI-MARIA": "Mesmo nome"}
    assert customer["identifiers"] == [{"type_label": "iFood", "value": "ifood-order-1"}]
    assert customer["orders_label"] == "1 pedido"
    assert customer["recent_orders"][0]["ref"] == "IF-ORD-1"


def test_detail_exposes_consent_as_read_only_evidence(client, manager, people):
    from shopman.guestman.contrib.consent.service import ConsentService

    ConsentService.grant_consent(
        "CLI-MARIA",
        "whatsapp",
        source="checkout",
        actor_ref="gerente",
    )
    client.force_login(manager)

    customer = client.get(f"{LIST_URL}CLI-MARIA/").json()["customer"]

    assert customer["consents"] == [
        {
            "channel_label": "WhatsApp",
            "purpose_label": "Marketing geral",
            "status_label": "Opt-in",
            "allowed": True,
            "proof_label": "Verificado",
            "source": "checkout",
            "updated_display": customer["consents"][0]["updated_display"],
        }
    ]
    assert customer["consents"][0]["updated_display"]


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


def test_channel_lookup_does_not_hide_database_failures(monkeypatch):
    from shopman.backstage.projections import customers
    from shopman.shop.models import Channel

    def unavailable(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Channel.objects, "filter", unavailable)

    with pytest.raises(RuntimeError, match="database unavailable"):
        customers._channel_names({"ifood"})


def test_order_evidence_does_not_hide_database_failures(monkeypatch):
    from shopman.backstage.projections import customers

    def unavailable(*args, **kwargs):
        raise RuntimeError("orders unavailable")

    monkeypatch.setattr(Order.objects, "filter", unavailable)

    with pytest.raises(RuntimeError, match="orders unavailable"):
        customers._order_stats(["CLI-MARIA"])
    with pytest.raises(RuntimeError, match="orders unavailable"):
        customers._ifood_customer_ids("CLI-MARIA")


def test_ifood_sibling_evidence_does_not_hide_database_failures(monkeypatch):
    from shopman.backstage.projections import customers

    monkeypatch.setattr(customers, "_ifood_customer_ids", lambda ref: {IFOOD_CUSTOMER_ID})

    def unavailable(*args, **kwargs):
        raise RuntimeError("orders unavailable")

    monkeypatch.setattr(Order.objects, "filter", unavailable)

    with pytest.raises(RuntimeError, match="orders unavailable"):
        customers._refs_sharing_ifood_customer("CLI-MARIA")


def test_history_does_not_hide_service_failures(people, monkeypatch):
    from shopman.orderman.services import CustomerOrderHistoryService

    from shopman.backstage.projections import customers

    def unavailable(*args, **kwargs):
        raise RuntimeError("history unavailable")

    monkeypatch.setattr(CustomerOrderHistoryService, "get_customer_stats", unavailable)

    with pytest.raises(RuntimeError, match="history unavailable"):
        customers.build_customer_detail(people["balcao"].ref)


def test_merged_destination_does_not_hide_database_failures(people, monkeypatch):
    from shopman.backstage.projections import customers

    Customer.objects.filter(pk=people["if_old"].pk).update(is_active=False)

    def unavailable(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(MergeAudit.objects, "filter", unavailable)

    with pytest.raises(RuntimeError, match="audit unavailable"):
        customers._merged_into(people["if_old"])


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


# ── Cópia e lote ──────────────────────────────────────────────────────

DUPLICATE_URL = f"{LIST_URL}CLI-MARIA/duplicate/"
BULK_URL = f"{LIST_URL}bulk/"


def test_duplicate_copies_relationship_and_addresses_but_not_identity(client, manager, people, shop):
    source = people["balcao"]
    tier = PriceTier.objects.create(ref="vizinho", name="Vizinho", priority=10)
    source.price_tiers.set([tier])
    source.metadata = {"house_account": True, "house_account_limit_q": 25000}
    source.save()
    source.tags.set(["vizinha", "café"])
    CustomerAddress.objects.create(
        customer=source, formatted_address="Rua das Flores, 10", is_default=True,
    )
    client.force_login(manager)
    revision = client.get(f"{LIST_URL}CLI-MARIA/").json()["customer"]["revision"]
    payload = {
        "expectedRevision": revision,
        "firstName": "Ana",
        "lastName": "Souza (cópia)",
    }

    first = _post(client, DUPLICATE_URL, payload, key="duplicate-maria")
    replay = _post(client, DUPLICATE_URL, payload, key="duplicate-maria")

    assert first.status_code == replay.status_code == 201, first.content
    assert replay.json() == first.json()
    body = first.json()
    assert body["outcome"] == "applied"
    assert body["resource"] == {"kind": "customer", "ref": body["customer"]["ref"]}
    copy = Customer.objects.get(ref=body["customer"]["ref"])
    assert copy.ref != source.ref
    assert copy.first_name == "Ana"
    assert copy.source_system == "manual"
    assert copy.created_by == manager.username
    # identidade e contato não se copiam: são únicos por cadastro
    assert copy.document == ""
    assert copy.phone == ""
    assert copy.email == ""
    # relacionamento comercial e endereços acompanham
    assert [t.pk for t in copy.price_tiers.all()] == [tier.pk]
    assert set(copy.tags.names()) == {"vizinha", "café"}
    assert copy.metadata == {"house_account": True, "house_account_limit_q": 25000}
    copied_address = copy.addresses.get()
    assert copied_address.formatted_address == "Rua das Flores, 10"
    assert copied_address.is_default is True


def test_duplicate_defaults_the_name_and_refuses_stale_or_absorbed_sources(client, manager, people):
    client.force_login(manager)
    revision = client.get(f"{LIST_URL}CLI-MARIA/").json()["customer"]["revision"]

    missing = _post(client, DUPLICATE_URL, {"firstName": "Ana"})
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "revision_required"

    stale = _post(client, DUPLICATE_URL, {"expectedRevision": "2000-01-01T00:00:00+00:00"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "customer_changed"

    absorbed = Customer.objects.create(ref="CLI-GONE", first_name="Some", is_active=False)
    absorbed_revision = absorbed.updated_at.isoformat()
    gone = _post(client, f"{LIST_URL}CLI-GONE/duplicate/", {"expectedRevision": absorbed_revision})
    assert gone.status_code == 409
    assert gone.json()["error"]["code"] == "inactive"

    unknown = _post(client, f"{LIST_URL}CLI-NAO-EXISTE/duplicate/", {"expectedRevision": revision})
    assert unknown.status_code == 404

    # sem sobrescrita, o nome nasce com o sufixo da cópia
    body = _post(client, DUPLICATE_URL, {"expectedRevision": revision}).json()
    assert body["customer"]["name"].endswith("(cópia)")


def test_bulk_customers_adds_and_removes_tags_in_one_trip(client, manager, people):
    client.force_login(manager)
    people["balcao"].tags.set(["vizinha"])
    people["other"].tags.set(["corredor"])

    added = _post(client, BULK_URL, {
        "refs": ["CLI-MARIA", "CLI-JOAO", "CLI-SUMIU"],
        "operation": "add_tags",
        "tags": ["campanha", "Vizinha"],
    })
    assert added.status_code == 200, added.content
    body = added.json()
    assert body["outcome"] == "applied"
    assert body["operation"] == "add_tags"
    assert set(body["applied"]) == {"CLI-MARIA", "CLI-JOAO"}
    assert body["skipped"] == [{"ref": "CLI-SUMIU", "reason": "not_found_or_inactive"}]
    assert set(Customer.objects.get(ref="CLI-MARIA").tags.names()) == {"vizinha", "campanha"}
    assert set(Customer.objects.get(ref="CLI-JOAO").tags.names()) == {"corredor", "campanha", "Vizinha"}

    removed = _post(client, BULK_URL, {
        "refs": ["CLI-MARIA", "CLI-JOAO"],
        "operation": "remove_tags",
        "tags": ["campanha"],
    })
    assert removed.status_code == 200
    assert set(Customer.objects.get(ref="CLI-MARIA").tags.names()) == {"vizinha"}
    assert set(Customer.objects.get(ref="CLI-JOAO").tags.names()) == {"corredor", "Vizinha"}


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"refs": [], "operation": "add_tags", "tags": ["x"]}, "refs"),
        ({"refs": ["CLI-MARIA"], "operation": "delete_all", "tags": ["x"]}, "operation"),
        ({"refs": ["CLI-MARIA"], "operation": "add_tags", "tags": []}, "tags"),
        ({"refs": [7], "operation": "add_tags", "tags": ["x"]}, "refs"),
    ],
)
def test_bulk_customers_refuses_invalid_requests(client, manager, people, payload, field):
    client.force_login(manager)

    response = _post(client, BULK_URL, payload)

    assert response.status_code == 400
    assert response.json()["field"] == field


def test_bulk_customers_replays_with_the_same_intention(client, manager, people):
    client.force_login(manager)
    payload = {"refs": ["CLI-MARIA"], "operation": "add_tags", "tags": ["campanha"]}

    first = _post(client, BULK_URL, payload, key="bulk-1")
    replay = _post(client, BULK_URL, payload, key="bulk-1")

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
