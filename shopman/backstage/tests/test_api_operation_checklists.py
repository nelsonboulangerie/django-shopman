"""Operational checklists are executable from the Gestor surface."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from shopman.backstage.api.operations import _validated_unlock_perm
from shopman.backstage.models import (
    OperationArea,
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationChecklistTemplateTask,
    OperationEvidence,
    OperationMoment,
    OperationRunStatus,
    OperationTaskTemplate,
)

pytestmark = pytest.mark.django_db

BASE = "/api/v1/backstage/operation-checklists/"


def test_perform_permission_is_an_allowed_session_capability():
    assert _validated_unlock_perm("backstage.perform_operation_task") == (
        "backstage.perform_operation_task",
        True,
    )


def _permission(codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="backstage", model="operationtasktemplate"),
        codename=codename,
    )


@pytest.fixture
def performer(db):
    user = User.objects.create_user("performer", password="pw", is_staff=True)
    user.user_permissions.add(_permission("perform_operation_task"))
    return user


@pytest.fixture
def supervisor(db):
    user = User.objects.create_user("supervisor", password="pw", is_staff=True)
    user.user_permissions.add(
        _permission("perform_operation_task"),
        _permission("supervise_operation_task"),
    )
    return user


@pytest.fixture
def checklist(db):
    template = OperationChecklistTemplate.objects.create(
        ref="opening-surface",
        title="Abertura da loja",
        description="Preparar a casa antes do atendimento.",
        moment=OperationMoment.OPENING,
    )
    count = OperationTaskTemplate.objects.create(
        ref="opening-count-surface",
        title="Conferir fundo de caixa",
        moment=OperationMoment.OPENING,
        area=OperationArea.CASH,
        evidence_required=OperationEvidence.NUMBER,
        sort_order=10,
    )
    keys = OperationTaskTemplate.objects.create(
        ref="opening-keys-surface",
        title="Conferir chaves",
        moment=OperationMoment.OPENING,
        area=OperationArea.MANAGEMENT,
        evidence_required=OperationEvidence.DOUBLE_CHECK,
        sort_order=20,
    )
    note = OperationTaskTemplate.objects.create(
        ref="opening-note-surface",
        title="Registrar observação do turno",
        moment=OperationMoment.OPENING,
        area=OperationArea.MANAGEMENT,
        evidence_required=OperationEvidence.TEXT,
        is_required=False,
        sort_order=30,
    )
    photo = OperationTaskTemplate.objects.create(
        ref="opening-photo-surface",
        title="Registrar foto da vitrine",
        moment=OperationMoment.OPENING,
        area=OperationArea.ROOM,
        evidence_required=OperationEvidence.PHOTO,
        is_required=False,
        sort_order=40,
    )
    OperationChecklistTemplateTask.objects.create(checklist_template=template, task_template=count, sort_order=10)
    OperationChecklistTemplateTask.objects.create(checklist_template=template, task_template=keys, sort_order=20)
    OperationChecklistTemplateTask.objects.create(checklist_template=template, task_template=note, sort_order=30)
    OperationChecklistTemplateTask.objects.create(checklist_template=template, task_template=photo, sort_order=40)
    return template


def _login(client, user):
    client.force_login(user)


def _start(client):
    return client.post(
        f"{BASE}start/",
        {"template_ref": "opening-surface", "shift_ref": "manha"},
        content_type="application/json",
    )


def test_board_requires_perform_permission(client, checklist, performer):
    plain = User.objects.create_user("plain", password="pw", is_staff=True)
    _login(client, plain)
    assert client.get(BASE).status_code == 403

    _login(client, performer)
    response = client.get(BASE)
    assert response.status_code == 200
    board = response.json()["checklists"]
    assert board["business_date"] == timezone.localdate().isoformat()
    assert board["can_supervise"] is False
    assert board["templates"][0]["ref"] == "opening-surface"
    assert board["templates"][0]["runs"] == []


def test_start_and_complete_number_task_from_surface(client, checklist, performer):
    _login(client, performer)
    started = _start(client)
    assert started.status_code == 201
    run = started.json()["checklists"]["templates"][0]["runs"][0]
    assert [task["ref"] for task in run["tasks"]] == [
        "opening-count-surface",
        "opening-keys-surface",
        "opening-note-surface",
        "opening-photo-surface",
    ]

    number_task = run["tasks"][0]
    missing = client.post(
        f"{BASE}{run['id']}/tasks/{number_task['id']}/complete/",
        {},
        content_type="application/json",
    )
    assert missing.status_code == 400
    assert "evidência numérica" in missing.json()["detail"]

    completed = client.post(
        f"{BASE}{run['id']}/tasks/{number_task['id']}/complete/",
        {"evidence_number": "200.00", "notes": "Contado no início do turno."},
        content_type="application/json",
    )
    assert completed.status_code == 200
    projected = completed.json()["checklists"]["templates"][0]["runs"][0]["tasks"][0]
    assert projected["status"] == "done"
    assert projected["evidence_number"] == "200"
    assert projected["executed_by"] == "performer"

    text_task = run["tasks"][2]
    text_completed = client.post(
        f"{BASE}{run['id']}/tasks/{text_task['id']}/complete/",
        {"evidence_text": "Equipe avisada sobre a entrega."},
        content_type="application/json",
    )
    projected_text = text_completed.json()["checklists"]["templates"][0]["runs"][0]["tasks"][2]
    assert projected_text["evidence_text"] == "Equipe avisada sobre a entrega."

    photo_task = run["tasks"][3]
    photo_completed = client.post(
        f"{BASE}{run['id']}/tasks/{photo_task['id']}/complete/",
        {"evidence_data": {"photo_ref": "drive://abertura/vitrine-01"}},
        content_type="application/json",
    )
    projected_photo = photo_completed.json()["checklists"]["templates"][0]["runs"][0]["tasks"][3]
    assert projected_photo["evidence_data"] == {"photo_ref": "drive://abertura/vitrine-01"}


def test_supervision_has_its_own_permission_and_closes_run(client, checklist, performer, supervisor):
    _login(client, performer)
    run = _start(client).json()["checklists"]["templates"][0]["runs"][0]
    number_task, double_task, _text_task, _photo_task = run["tasks"]
    client.post(
        f"{BASE}{run['id']}/tasks/{number_task['id']}/complete/",
        {"evidence_number": "200"},
        content_type="application/json",
    )
    client.post(
        f"{BASE}{run['id']}/tasks/{double_task['id']}/complete/",
        {},
        content_type="application/json",
    )

    denied = client.post(
        f"{BASE}{run['id']}/tasks/{double_task['id']}/supervise/",
        {},
        content_type="application/json",
    )
    assert denied.status_code == 403

    blocked = client.post(f"{BASE}{run['id']}/complete/", {}, content_type="application/json")
    assert blocked.status_code == 400
    assert "dupla conferência" in blocked.json()["detail"]

    _login(client, supervisor)
    supervised = client.post(
        f"{BASE}{run['id']}/tasks/{double_task['id']}/supervise/",
        {"notes": "Conferido presencialmente."},
        content_type="application/json",
    )
    task = supervised.json()["checklists"]["templates"][0]["runs"][0]["tasks"][1]
    assert task["supervised"] is True
    assert task["supervised_by"] == "supervisor"

    closed = client.post(f"{BASE}{run['id']}/complete/", {}, content_type="application/json")
    projected_run = closed.json()["checklists"]["templates"][0]["runs"][0]
    assert projected_run["status"] == "completed"
    assert projected_run["completed_by"] == "supervisor"


def test_task_url_cannot_cross_run_boundary(client, checklist, performer):
    _login(client, performer)
    first = _start(client).json()["checklists"]["templates"][0]["runs"][0]
    response = client.post(
        f"{BASE}{first['id'] + 999}/tasks/{first['tasks'][0]['id']}/complete/",
        {"evidence_number": "10"},
        content_type="application/json",
    )
    assert response.status_code == 404


def test_completed_run_rejects_every_further_transition(client, checklist, supervisor):
    _login(client, supervisor)
    projected = _start(client).json()["checklists"]["templates"][0]["runs"][0]
    OperationChecklistRun.objects.filter(pk=projected["id"]).update(
        status=OperationRunStatus.COMPLETED
    )

    urls_and_bodies = [
        (
            f"{BASE}{projected['id']}/tasks/{projected['tasks'][0]['id']}/complete/",
            {"evidence_number": "10"},
        ),
        (
            f"{BASE}{projected['id']}/tasks/{projected['tasks'][1]['id']}/supervise/",
            {},
        ),
        (f"{BASE}{projected['id']}/complete/", {}),
    ]
    for url, body in urls_and_bodies:
        response = client.post(url, body, content_type="application/json")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "checklist_run_closed"
