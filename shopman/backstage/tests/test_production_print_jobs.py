"""Durable preparation-label jobs and their relay/browser truth boundary."""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from shopman.buyman.models import Material, MaterialConversion
from shopman.cashman.models import Terminal
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem

from shopman.backstage.models import PrintAgentCredential, PrintAttempt, PrintJob
from shopman.backstage.projections.production import build_production_weighing
from shopman.backstage.services import print_jobs

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def actor():
    return get_user_model().objects.create_superuser("print-manager", "print@example.com", "pw")


@pytest.fixture
def preparation():
    Material.objects.create(sku="FARINHA-FINA", name="Farinha Fina", unit="kg")
    recipe = Recipe.objects.create(
        ref="etiqueta-preparo",
        name="Creme de teste",
        output_sku="CREME-TESTE",
        batch_size=D("1"),
        meta={"shelf_life_days": 1},
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="FARINHA-FINA",
        quantity=D("0.101"),
        unit="kg",
        sort_order=1,
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="SAL",
        quantity=D("102"),
        unit="g",
        sort_order=2,
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="LEITE",
        quantity=D("0.250"),
        unit="L",
        sort_order=3,
    )
    craft.plan(recipe, D("1"), date=date.today())
    return recipe


@pytest.fixture
def weighing(preparation):
    return build_production_weighing(selected_date=date.today())


@pytest.fixture
def printer_terminal():
    return Terminal.objects.create(
        ref="prep-printer",
        label="Preparação",
        metadata={
            "hardware": {
                "printer": {
                    "enabled": True,
                    "adapter": "relay",
                    "role": "preparation",
                    "roll_width_mm": 80,
                    "columns": 48,
                    "cut_mode": "partial",
                }
            }
        },
    )


def _ticket(projection):
    return next(ticket for ticket in projection.tickets if ticket.recipe_ref == "etiqueta-preparo")


def _create(
    projection,
    actor,
    *,
    mode="blind",
    transport=PrintJob.Transport.BROWSER,
    station_ref="",
    key="create-1",
):
    return print_jobs.create_job(
        projection=projection,
        mode=mode,
        transport=transport,
        ticket_refs=[_ticket(projection).ticket_ref],
        actor=actor,
        station_ref=station_ref,
        source_revision="sha256:deadbeef:scope",
        idempotency_key=key,
    )


@override_settings(CRAFTSMAN={"SCALE_PRECISION_G": D("2")})
def test_weighing_projection_rounds_mass_up_and_preserves_typed_facts(weighing):
    projection = build_production_weighing(selected_date=date.today())
    ticket = _ticket(projection)
    farinha, sal, leite = ticket.ingredients

    assert projection.scale_precision_g == "2"
    assert projection.scale_precision_display == "2 g"
    assert projection.scale_rounding_note == "Alvos arredondados para cima · balança 2 g"
    assert (
        farinha.theoretical_g,
        farinha.target_g,
        farinha.rounding_delta_g,
        farinha.accepted_min_g,
        farinha.accepted_max_g,
        farinha.target_display,
    ) == ("101", "102", "1", "102", "104", "102 g")
    assert sal.target_g == "102"
    assert sal.rounding_delta_g == "0"
    assert leite.quantity_display == "0,25 L"
    assert leite.target_g is None
    assert ticket.theoretical_total_g == "203"
    assert ticket.target_total_g == "204"
    assert ticket.rounding_delta_total_g == "1"
    assert ticket.total_weight_display == "204 g"


@override_settings(CRAFTSMAN={"SCALE_PRECISION_G": D("0.5")})
def test_projection_honours_non_integer_canonical_precision(preparation):
    ticket = _ticket(build_production_weighing(selected_date=date.today()))
    farinha = ticket.ingredients[0]
    assert farinha.theoretical_g == "101"
    assert farinha.target_g == "101"
    assert D(farinha.target_g) >= D(farinha.theoretical_g)
    assert farinha.accepted_max_g == "101.5"


def test_ticket_ref_changes_when_same_recipe_quantity_changes(preparation):
    first = _ticket(build_production_weighing(selected_date=date.today())).ticket_ref
    craft.plan(preparation, D("1"), date=date.today())
    second = _ticket(build_production_weighing(selected_date=date.today())).ticket_ref
    assert first != second


def test_create_idempotency_reuses_same_intent_and_rejects_a_different_one(weighing, actor):
    first = _create(weighing, actor, key="same-create")
    second = _create(weighing, actor, key="same-create")
    assert second.pk == first.pk
    assert PrintJob.objects.count() == 1

    with pytest.raises(print_jobs.PrintJobError, match="outra impressão"):
        _create(weighing, actor, key="same-create", mode="explicit")


def test_blind_document_is_one_label_per_ingredient_and_never_leaks_recipe(weighing, actor):
    job = _create(weighing, actor)

    assert job.status == PrintJob.Status.PREPARED
    assert job.target_terminal is None
    assert job.label_count == 3
    assert len(job.document["tickets"]) == 3
    for label in job.document["tickets"]:
        assert len(label["ingredients"]) == 1
        assert "name" not in label
        assert "recipe_ref" not in label
        assert "output_sku" not in label
        ingredient = label["ingredients"][0]
        assert ingredient["name"]
        assert ingredient["sku"]
        assert "target_display" in ingredient
    paper = bytes(job.payload).decode("cp860", "replace")
    assert "Creme de teste" not in paper
    assert "CREME-TESTE" not in paper
    assert "Farinha Fina" in paper
    assert "FARINHA-FINA" in paper
    assert "PESAGEM INTERNA" in paper
    assert "NAO E ROTULO DE VENDA" in paper
    assert "Data" in paper
    assert "Validade" not in paper


def test_explicit_document_is_one_label_per_prep_with_name_sku_and_totals(weighing, actor):
    job = _create(weighing, actor, mode="explicit")

    assert job.label_count == 1
    label = job.document["tickets"][0]
    assert label["name"] == "Creme de teste"
    assert label["output_sku"] == "CREME-TESTE"
    assert label["theoretical_total_g"] == "203"
    assert label["target_total_g"] == "204"
    assert label["rounding_delta_total_g"] == "1"
    assert "ingredients" not in label
    assert job.document["purpose"] == "internal_preparation"
    assert job.document["legal_scope"] == "internal_only_not_for_sale"
    paper = bytes(job.payload).decode("cp860", "replace")
    assert "Creme de teste" in paper
    assert "CREME-TESTE" in paper
    assert "Alvo total: 204 g" in paper
    assert "PREPARO INTERNO" in paper
    assert "NAO E ROTULO DE VENDA" in paper
    assert "Preparo" in paper
    assert "Validade" in paper
    assert "Farinha Fina" not in paper


def test_explicit_document_fails_closed_without_validity(weighing):
    ticket = _ticket(weighing)
    projection = replace(
        weighing,
        tickets=(replace(ticket, expiry_display="", validity_configured=False),),
    )

    with pytest.raises(print_jobs.PrintJobError, match="não pode presumir validade") as error:
        print_jobs.compose_document(
            projection,
            mode="explicit",
            ticket_refs=[ticket.ticket_ref],
        )
    assert error.value.code == "preparation_validity_missing"


@override_settings(CRAFTSMAN={"SCALE_PRECISION_G": D("2")})
def test_counting_equivalence_is_frozen_and_printed_as_secondary_reference(
    preparation,
    actor,
):
    material = Material.objects.get(sku="FARINHA-FINA")
    MaterialConversion.objects.create(
        material=material,
        label="porções",
        to_base_factor=D("0.050"),
        kind=MaterialConversion.Kind.APPROXIMATE,
    )
    projection = build_production_weighing(selected_date=date.today())
    ticket = _ticket(projection)
    assert ticket.ingredients[0].target_display == "102 g"
    # 2,04 porções não existem na mão: a ajuda diz quantas unidades inteiras
    # separar, sempre para cima. O alvo autoritativo continua sendo 102 g.
    assert ticket.ingredients[0].annotation == "(≈ 3 un.)"

    job = _create(projection, actor)
    frozen = next(label for label in job.document["tickets"] if label["ingredients"][0]["sku"] == "FARINHA-FINA")
    assert frozen["ingredients"][0]["annotation"] == "(≈ 3 un.)"
    paper = bytes(job.payload).decode("cp860", "replace")
    assert "102 g" in paper
    assert "(≈ 3 un.)" in paper
    assert "Referencia:" not in paper


def test_browser_create_is_independent_of_a_relay_and_records_only_honest_outcomes(
    weighing,
    actor,
):
    job = _create(weighing, actor)
    assert print_jobs.job_data(job)["target_label"] == "Este dispositivo"

    opened = print_jobs.record_browser_result(
        job=job,
        actor=actor,
        result="dialog_opened",
        idempotency_key="browser-1",
    )
    assert opened.status == PrintJob.Status.AWAITING_CONFIRMATION
    assert opened.attempts.get().status == PrintAttempt.Status.BROWSER_OPENED

    confirmed = print_jobs.confirm_job(
        job=opened,
        actor=actor,
        result="confirmed",
        detail="",
        idempotency_key="confirm-1",
    )
    assert confirmed.status == PrintJob.Status.CONFIRMED
    assert confirmed.confirmed_by_ref == actor.get_username()


def test_incomplete_confirmation_requires_a_new_visible_copy(weighing, actor):
    job = _create(weighing, actor)
    job = print_jobs.record_browser_result(
        job=job,
        actor=actor,
        result="dialog_opened",
        idempotency_key="browser-incomplete",
    )
    job = print_jobs.confirm_job(
        job=job,
        actor=actor,
        result="incomplete",
        detail="Algumas etiquetas não saíram.",
        idempotency_key="confirm-incomplete",
    )

    state = print_jobs.job_data(job)
    assert job.status == PrintJob.Status.FAILED
    assert job.confirmation == PrintJob.Confirmation.INCOMPLETE
    assert not state["can_retry"]
    assert state["can_reprint"]
    with pytest.raises(print_jobs.PrintJobError, match="falha comprovada"):
        print_jobs.retry_job(job=job, actor=actor, idempotency_key="unsafe-retry")


def test_user_anonymization_keeps_print_audit_snapshots(weighing, actor):
    username = actor.get_username()
    job = _create(weighing, actor)
    job = print_jobs.record_browser_result(
        job=job,
        actor=actor,
        result="dialog_opened",
        idempotency_key="browser-before-delete",
    )
    job = print_jobs.confirm_job(
        job=job,
        actor=actor,
        result="confirmed",
        detail="",
        idempotency_key="confirm-before-delete",
    )

    actor.delete()
    job.refresh_from_db()
    assert job.requested_by is None
    assert job.confirmed_by is None
    assert job.requested_by_ref == username
    assert job.confirmed_by_ref == username


def test_credential_persists_only_digest_and_destination_health_is_honest(printer_terminal):
    credential, bearer = PrintAgentCredential.issue(terminal=printer_terminal, label="Bancada")
    secret = bearer.split(".", 1)[1]

    assert secret not in credential.token_digest
    assert secret not in credential.token_hint
    assert PrintAgentCredential.authenticate(bearer) == credential
    assert PrintAgentCredential.authenticate(f"{credential.ref}.incorreto") is None
    waiting = print_jobs.resolve_destination(station_ref=printer_terminal.ref)
    assert waiting.available
    assert waiting.status_label == "Aguardando estação"

    credential.last_seen_at = timezone.now()
    credential.save(update_fields=("last_seen_at",))
    assert print_jobs.resolve_destination(station_ref=printer_terminal.ref).status_label == "Pronta"


def test_relay_claim_ack_is_hash_bound_idempotent_and_never_claims_browser(
    weighing,
    actor,
    printer_terminal,
):
    credential, bearer = PrintAgentCredential.issue(terminal=printer_terminal)
    browser = _create(weighing, actor, key="browser", transport=PrintJob.Transport.BROWSER)
    relay = _create(
        weighing,
        actor,
        key="relay",
        transport=PrintJob.Transport.RELAY,
        station_ref=printer_terminal.ref,
    )

    claimed = print_jobs.claim_next_job(
        credential=credential,
        telemetry={"version": "1.2", "build": "abc", "queue": "EPSON", "health": "ready"},
    )
    assert claimed is not None
    job, attempt, lease_token = claimed
    payload = print_jobs.claimed_job_data(job, attempt, lease_token)
    assert job == relay
    assert browser.status == PrintJob.Status.PREPARED
    assert base64.b64decode(payload["payload_b64"]) == bytes(relay.payload)
    assert payload["payload_sha256"] == relay.payload_sha256
    assert payload["lease_token"] == lease_token
    assert lease_token not in attempt.lease_token_digest

    ack = {
        "credential": PrintAgentCredential.authenticate(bearer),
        "job_ref": job.ref,
        "status": "spooled",
        "spooler_job_id": "cups-42",
        "detail": "",
        "payload_sha256": job.payload_sha256,
        "lease_token": lease_token,
        "telemetry": {"build": "abc", "queue": "EPSON", "health": "ready"},
    }
    first = print_jobs.acknowledge_job(**ack)
    second = print_jobs.acknowledge_job(**ack)
    assert first.status == PrintJob.Status.SPOOLED
    assert second.status == PrintJob.Status.SPOOLED
    assert PrintAttempt.objects.get(pk=attempt.pk).spooler_job_id == "cups-42"

    with pytest.raises(print_jobs.PrintJobError, match="ACK diferente"):
        print_jobs.acknowledge_job(**{**ack, "detail": "divergente"})


def test_operator_poll_expires_dead_lease_and_late_identical_ack_reconciles(
    weighing,
    actor,
    printer_terminal,
):
    credential, _bearer = PrintAgentCredential.issue(terminal=printer_terminal)
    job = _create(
        weighing,
        actor,
        transport=PrintJob.Transport.RELAY,
        station_ref=printer_terminal.ref,
    )
    claimed_job, attempt, lease_token = print_jobs.claim_next_job(credential=credential, telemetry={})
    attempt.lease_expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=("lease_expires_at",))

    reconciled = print_jobs.reconcile_job_state(claimed_job)
    attempt.refresh_from_db()
    assert reconciled.status == PrintJob.Status.UNCERTAIN
    assert attempt.status == PrintAttempt.Status.EXPIRED

    late_ack = {
        "credential": credential,
        "job_ref": job.ref,
        "status": "spooled",
        "spooler_job_id": "cups-late",
        "detail": "journal reenviado",
        "payload_sha256": job.payload_sha256,
        "lease_token": lease_token,
        "telemetry": {},
    }
    late = print_jobs.acknowledge_job(**late_ack)
    assert late.status == PrintJob.Status.SPOOLED
    assert print_jobs.acknowledge_job(**late_ack).status == PrintJob.Status.SPOOLED


def test_reprint_uses_frozen_document_and_marks_the_copy(weighing, actor):
    original = _create(weighing, actor, mode="explicit")
    original.status = PrintJob.Status.CONFIRMED
    original.save(update_fields=("status",))

    reprint = print_jobs.reprint_job(
        job=original,
        actor=actor,
        station_ref="",
        transport=PrintJob.Transport.BROWSER,
        idempotency_key="reprint-1",
    )

    assert reprint.copy_number == 2
    assert reprint.series_ref == original.series_ref
    assert reprint.document == original.document
    assert reprint.document_sha256 == original.document_sha256
    assert reprint.payload_sha256 != original.payload_sha256
    assert "2ª VIA" in bytes(reprint.payload).decode("cp860", "replace")
    projected = print_jobs.job_data(reprint, include_document=True)
    assert projected["print_document"] == original.document
    assert projected["document_sha256"] == original.document_sha256


def test_ambiguous_blind_code_fails_closed(preparation):
    other = Recipe.objects.create(
        ref="segundo-preparo",
        name="Segundo preparo",
        output_sku="SEGUNDO-PREPARO",
        batch_size=D("1"),
    )
    RecipeItem.objects.create(recipe=other, input_sku="ACUCAR", quantity=D("100"), unit="g")
    craft.plan(other, D("1"), date=date.today())
    projection = build_production_weighing(selected_date=date.today())
    first, second = projection.tickets
    collision = replace(second, blind_code=first.blind_code)
    projection = replace(projection, tickets=(first, collision))

    with pytest.raises(print_jobs.PrintJobError, match="mesmo código cego"):
        print_jobs.compose_document(
            projection,
            mode="blind",
            ticket_refs=[first.ticket_ref],
        )


def test_physical_label_limit_is_enforced_after_blind_expansion(weighing):
    ticket = _ticket(weighing)
    oversized = replace(ticket, ingredients=(ticket.ingredients[0],) * 51)
    projection = replace(weighing, tickets=(oversized,))

    with pytest.raises(print_jobs.PrintJobError, match="51 etiquetas"):
        print_jobs.compose_document(
            projection,
            mode="blind",
            ticket_refs=[oversized.ticket_ref],
        )


def test_browser_api_create_uses_projected_proof_and_uniform_job_contract(
    preparation,
    actor,
    printer_terminal,
):
    client = APIClient()
    client.force_authenticate(actor)
    response = client.get(reverse("api-backstage-production-weighing"))
    assert response.status_code == 200
    projection = response.json()["weighing"]
    action = next(item for item in projection["actions"] if item["kind"] == "print_labels")
    ticket = next(item for item in projection["tickets"] if item["recipe_ref"] == preparation.ref)
    # Relay health is a volatile preflight, not production input. A pairing
    # between projection and click must not invalidate the signed intent.
    PrintAgentCredential.issue(terminal=printer_terminal)
    body = {
        "selected_date": projection["selected_date"],
        "position": projection["selected_position_ref"],
        "base_recipe": projection["selected_base_recipe"],
        "mode": "blind",
        "transport": "browser",
        "ticket_refs": [ticket["ticket_ref"]],
        "idempotency_key": "api-create-1",
        "projection_generated_at": projection["generated_at"],
        "source_revision": projection["source_revision"],
        "fresh_until": projection["fresh_until"],
        "contract_version": projection["contract_version"],
        "action_ref": action["ref"],
        "action_proof": action["proof"],
    }

    created = client.post(action["href"], body, format="json")
    assert created.status_code == 201
    assert set(created.json()["print_job"]) == {
        "ref",
        "status",
        "status_label",
        "message",
        "target_label",
        "label_count",
        "copy_number",
        "can_retry",
        "can_reprint",
        "can_confirm",
        "poll_after_ms",
        "print_document",
        "document_sha256",
    }
    assert created.json()["print_job"]["status"] == "prepared"
    assert created.json()["print_job"]["target_label"] == "Este dispositivo"


def test_operator_job_is_visible_only_to_requester_same_station_or_manager(weighing, actor):
    print_permission = Permission.objects.get(
        content_type__app_label="shop",
        codename="edit_production_started",
    )
    requester = get_user_model().objects.create_user("requester", password="pw", is_staff=True)
    outsider = get_user_model().objects.create_user("outsider", password="pw", is_staff=True)
    requester.user_permissions.add(print_permission)
    outsider.user_permissions.add(print_permission)
    job = _create(weighing, requester)
    url = reverse("api-backstage-production-print-job", args=[job.ref])

    client = APIClient()
    client.force_authenticate(requester)
    assert client.get(url).status_code == 200

    client.force_authenticate(outsider)
    assert client.get(url).status_code == 403

    client.force_authenticate(actor)
    assert client.get(url).status_code == 200


def test_agent_http_contract_requires_bearer_and_hash(
    weighing,
    actor,
    printer_terminal,
):
    _credential, bearer = PrintAgentCredential.issue(terminal=printer_terminal)
    job = _create(
        weighing,
        actor,
        transport=PrintJob.Transport.RELAY,
        station_ref=printer_terminal.ref,
    )
    client = APIClient()
    assert client.post(reverse("api-backstage-print-agent-claim"), {}, format="json").status_code == 401

    claimed = client.post(
        reverse("api-backstage-print-agent-claim"),
        {"version": "1", "build": "build", "queue": "EPSON", "health": "ready"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {bearer}",
    )
    assert claimed.status_code == 200
    wire = claimed.json()["job"]
    assert wire["job_ref"] == str(job.ref)
    assert "payload_b64" in wire
    assert "payload_sha256" in wire
    assert "lease_token" in wire

    bad = client.post(
        reverse("api-backstage-print-agent-ack", args=[job.ref]),
        {
            "status": "spooled",
            "spooler_job_id": "cups-1",
            "detail": "",
            "payload_sha256": "0" * 64,
            "lease_token": wire["lease_token"],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {bearer}",
    )
    assert bad.status_code == 409
    job.refresh_from_db()
    assert job.status == PrintJob.Status.LEASED
