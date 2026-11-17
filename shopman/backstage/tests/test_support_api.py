"""Contrato do Suporte no backstage (helpdesk interno).

O ticket nasce determinístico; a classificação é sugestão; a aprovação é do
dono; o compromisso de dev é `DEV-` no ledger. A IA não aparece aqui.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from rest_framework.test import APIClient

from shopman.backstage.models import SupportTicket
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def _perm(codename: str) -> Permission:
    return Permission.objects.get(
        content_type__app_label="shop", codename=codename
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    user = User.objects.create_user("support-op", password="pw", is_staff=True)
    user.user_permissions.add(_perm("create_support_ticket"))
    return user


@pytest.fixture
def other_operator(db, shop):
    user = User.objects.create_user("support-op-2", password="pw", is_staff=True)
    user.user_permissions.add(_perm("create_support_ticket"))
    return user


@pytest.fixture
def manager(db, shop):
    user = User.objects.create_user("support-manager", password="pw", is_staff=True)
    user.user_permissions.add(
        _perm("create_support_ticket"),
        _perm("triage_support_tickets"),
        _perm("view_all_support_tickets"),
    )
    return user


@pytest.fixture
def owner(db, shop):
    return User.objects.create_superuser("support-owner", password="pw")


def _create(client, **overrides):
    payload = {
        "description": "A via do PDV não saiu",
        "type": SupportTicket.TYPE_QUESTION,
        "context": {"route": "/pos", "focus": {"kind": "order", "ref": "ORD-1"}},
    }
    payload.update(overrides)
    return client.post(reverse("api-backstage-support-tickets"), payload, format="json")


def test_operator_creates_ticket_with_context_and_ref(client, operator):
    client.force_login(operator)

    response = _create(client)

    assert response.status_code == 201
    body = response.json()
    assert body["ref"].startswith("HELP-")
    assert body["status"] == SupportTicket.STATUS_NEW
    assert body["requester"] == operator.username
    assert body["context"]["route"] == "/pos"
    assert body["sla_due"] is not None


def test_owner_explicit_request_is_implicitly_approved(client, owner):
    client.force_login(owner)

    response = _create(client, type=SupportTicket.TYPE_REQUEST)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == SupportTicket.STATUS_APPROVED
    assert body["approved_by"] == owner.username
    assert body["approval_basis"] == "solicitado pelo dono"


def test_owner_idea_goes_to_triage(client, owner):
    client.force_login(owner)

    response = _create(client, type=SupportTicket.TYPE_IDEA)

    assert response.status_code == 201
    assert response.json()["status"] == SupportTicket.STATUS_TRIAGE


def test_create_is_idempotent_by_client_uuid(client, operator):
    client.force_login(operator)
    client_uuid = str(uuid.uuid4())

    first = _create(client, client_uuid=client_uuid)
    second = _create(client, client_uuid=client_uuid)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["ref"] == second.json()["ref"]
    assert SupportTicket.objects.count() == 1


def test_list_scopes_operator_and_manager(client, operator, other_operator, manager):
    SupportTicket.objects.create(
        requester=operator, description="Meu chamado", subject="meu"
    )
    SupportTicket.objects.create(
        requester=other_operator, description="Chamado do outro", subject="outro"
    )

    client.force_login(operator)
    mine = client.get(reverse("api-backstage-support-tickets")).json()["tickets"]
    assert [ticket["requester"] for ticket in mine] == [operator.username]

    client.force_login(manager)
    every = client.get(reverse("api-backstage-support-tickets")).json()["tickets"]
    assert {ticket["requester"] for ticket in every} == {
        operator.username,
        other_operator.username,
    }


def test_detail_blocks_another_operator(client, operator, other_operator):
    ticket = SupportTicket.objects.create(
        requester=operator, description="Privado"
    )
    client.force_login(other_operator)

    response = client.get(
        reverse("api-backstage-support-ticket", kwargs={"ref": ticket.ref})
    )

    assert response.status_code == 403


def test_requester_replies_and_internal_note_is_team_only(
    client, operator, manager
):
    ticket = SupportTicket.objects.create(
        requester=operator, description="Preciso de ajuda"
    )
    url = reverse(
        "api-backstage-support-ticket-messages", kwargs={"ref": ticket.ref}
    )

    client.force_login(operator)
    assert client.post(url, {"body": "Ainda acontece"}, format="json").status_code == 201
    assert (
        client.post(
            url, {"body": "nota", "internal_note": True}, format="json"
        ).status_code
        == 403
    )

    client.force_login(manager)
    assert (
        client.post(
            url, {"body": "nota da equipe", "internal_note": True}, format="json"
        ).status_code
        == 201
    )


def test_manager_triage_sends_request_to_owner(client, operator, manager):
    ticket = SupportTicket.objects.create(
        requester=operator, description="Seria bom ter um botão"
    )
    client.force_login(manager)

    response = client.post(
        reverse("api-backstage-support-ticket-triage", kwargs={"ref": ticket.ref}),
        {"type": SupportTicket.TYPE_REQUEST, "priority": SupportTicket.PRIORITY_HIGH},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == SupportTicket.TYPE_REQUEST
    assert body["priority"] == SupportTicket.PRIORITY_HIGH
    assert body["status"] == SupportTicket.STATUS_WAITING_OWNER


def test_manager_cannot_decide(client, operator, manager):
    ticket = SupportTicket.objects.create(
        requester=operator, description="Pedido", type=SupportTicket.TYPE_REQUEST
    )
    client.force_login(manager)

    response = client.post(
        reverse("api-backstage-support-ticket-decision", kwargs={"ref": ticket.ref}),
        {"decision": "approve"},
        format="json",
    )

    assert response.status_code == 403


def test_owner_approves_rejects_and_defer_requires_date(client, operator, owner):
    approved = SupportTicket.objects.create(
        requester=operator,
        description="Pedido aprovado",
        type=SupportTicket.TYPE_REQUEST,
        status=SupportTicket.STATUS_WAITING_OWNER,
    )
    rejected = SupportTicket.objects.create(
        requester=operator,
        description="Pedido recusado",
        type=SupportTicket.TYPE_REQUEST,
        status=SupportTicket.STATUS_WAITING_OWNER,
    )
    deferred = SupportTicket.objects.create(
        requester=operator,
        description="Pedido adiado",
        type=SupportTicket.TYPE_REQUEST,
        status=SupportTicket.STATUS_WAITING_OWNER,
    )
    client.force_login(owner)

    approve_url = reverse(
        "api-backstage-support-ticket-decision", kwargs={"ref": approved.ref}
    )
    response = client.post(approve_url, {"decision": "approve"}, format="json")
    assert response.status_code == 200
    assert response.json()["status"] == SupportTicket.STATUS_APPROVED

    reject_url = reverse(
        "api-backstage-support-ticket-decision", kwargs={"ref": rejected.ref}
    )
    assert (
        client.post(reject_url, {"decision": "reject"}, format="json").status_code
        == 400
    )
    response = client.post(
        reject_url, {"decision": "reject", "reason": "Fora do escopo"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == SupportTicket.STATUS_REJECTED
    assert response.json()["resolution"] == "Fora do escopo"

    defer_url = reverse(
        "api-backstage-support-ticket-decision", kwargs={"ref": deferred.ref}
    )
    assert (
        client.post(defer_url, {"decision": "defer"}, format="json").status_code
        == 400
    )
    response = client.post(
        defer_url,
        {"decision": "defer", "reason": "Depois do go-live", "review_at": "2026-12-01"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == SupportTicket.STATUS_DEFERRED
    assert response.json()["review_at"] == "2026-12-01"


def test_link_dev_requires_approval_and_permission(client, operator, owner):
    ticket = SupportTicket.objects.create(
        requester=operator, description="Pedido", type=SupportTicket.TYPE_REQUEST
    )
    url = reverse(
        "api-backstage-support-ticket-link-dev", kwargs={"ref": ticket.ref}
    )

    client.force_login(operator)
    assert client.post(url, {"dev_ref": "DEV-2026-010"}, format="json").status_code == 403

    client.force_login(owner)
    assert client.post(url, {"dev_ref": "DEV-2026-010"}, format="json").status_code == 400

    ticket.status = SupportTicket.STATUS_APPROVED
    ticket.save(update_fields=["status", "updated_at"])
    assert (
        client.post(url, {"dev_ref": "C-2026-010"}, format="json").status_code == 400
    )
    response = client.post(url, {"dev_ref": "DEV-2026-010"}, format="json")
    assert response.status_code == 200
    assert response.json()["ledger_ref"] == "DEV-2026-010"
    assert response.json()["status"] == SupportTicket.STATUS_IN_DEV


def test_refs_are_sequential(client, operator):
    first = SupportTicket.objects.create(requester=operator, description="um")
    second = SupportTicket.objects.create(requester=operator, description="dois")

    assert first.ref == "HELP-0001"
    assert second.ref == "HELP-0002"


def test_capabilities_for_operator_manager_owner(client, operator, manager, owner):
    url = reverse("api-backstage-support-capabilities")

    client.force_login(operator)
    caps = client.get(url).json()
    assert caps["create"] is True
    assert caps["triage"] is False
    assert caps["approve"] is False

    client.force_login(manager)
    caps = client.get(url).json()
    assert caps["triage"] is True
    assert caps["view_all"] is True
    assert caps["approve"] is False

    client.force_login(owner)
    caps = client.get(url).json()
    assert caps["approve"] is True
    assert caps["link_dev"] is True
    assert caps["audit"] is True
