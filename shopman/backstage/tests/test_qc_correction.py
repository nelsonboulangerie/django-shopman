"""Post-close QC correction: immutable audit + versioned stock facts."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrderEvent, WorkOrderItem
from shopman.stockman import Position
from shopman.stockman.models import Batch, Hold, HoldStatus, Move, Quant

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.production import build_qc_kiosk
from shopman.backstage.services import production
from shopman.backstage.services.exceptions import ProductionConflict, ProductionError
from shopman.backstage.tests.production_grants import grant_production_operator
from shopman.backstage.tests.support import production_mutation_post


@pytest.fixture
def qc_recipe(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Correção QC")
    Position.objects.create(ref="forno-qc", name="Forno QC", is_default=True)
    Position.objects.create(ref="vitrine-qc", name="Vitrine QC", is_saleable=True)
    return Recipe.objects.create(
        ref="qc-correction-bread",
        name="Pão Correção",
        output_sku="QC-CORRECTION",
        batch_size=Decimal("10"),
        meta={"shelf_life_days": 3},
    )


def _finished(qc_recipe, monkeypatch, *, partition=None):
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    wo = craft.plan(qc_recipe, 10, date=date.today(), position_ref="forno-qc")
    craft.start(wo, quantity=10, position_ref="forno-qc", expected_rev=0)
    wo.refresh_from_db()
    production.apply_finish(
        work_order_id=wo.pk,
        quantity="10",
        actor="production:forneiro",
        expected_rev=wo.rev,
        idempotency_key=f"finish-{wo.pk}",
        partition=partition or [{"quantity": "10", "quality_grade_ref": "standard"}],
    )
    wo.refresh_from_db()
    return wo


def _quality_announcement(work_order, *, status):
    from shopman.shop.models import Announcement, AnnouncementTemplate, Campaign

    template = AnnouncementTemplate.objects.create(
        name=f"Fornada {work_order.pk}",
        body="A fornada saiu.",
    )
    rule = Campaign.objects.create(
        name=f"Qualidade normal {work_order.pk}",
        trigger="production_finished",
        trigger_filter={"quality_min": "standard"},
        template=template,
        platforms=["instagram"],
    )
    return Announcement.objects.create(
        rule=rule,
        template=template,
        status=status,
        content={"body": "A fornada saiu."},
        platforms=["instagram"],
        trigger_context={
            "trigger": "production_finished",
            "work_order_ref": work_order.ref,
            "quality": "standard",
            "output_partition": [{"grade_ref": "standard", "quantity": "10"}],
            "planned_qty": "10",
        },
    )


@pytest.mark.django_db
def test_correction_versions_lots_moves_stock_and_effective_projection(qc_recipe, monkeypatch):
    from shopman.craftsman.signals import production_changed

    from shopman.shop.services import quality as quality_service

    wo = _finished(qc_recipe, monkeypatch)
    original_items = list(
        WorkOrderItem.objects.filter(work_order=wo).values_list(
            "pk", "quality_grade_ref", "quality_defect_ref", "batch_ref"
        )
    )
    original_batch_ref = next(row[3] for row in original_items if row[3])
    original_batch = Batch.objects.get(ref=original_batch_ref)
    original_rev = wo.rev
    seen = []

    def receiver(**kwargs):
        seen.append(kwargs.get("action"))

    production_changed.connect(receiver, dispatch_uid="test-qc-correction-no-refinish", weak=False)
    try:
        corrected = production.apply_quality_correction(
            work_order_id=wo.pk,
            partition=[
                {"quantity": "6", "quality_grade_ref": "standard"},
                {
                    "quantity": "4",
                    "quality_grade_ref": "fair",
                    "quality_defect_ref": "misshapen",
                },
            ],
            reason="Quatro unidades ficaram menores após a conferência.",
            actor="production:gerente",
            expected_rev=original_rev,
            idempotency_key="correct-qc-1",
        )
    finally:
        production_changed.disconnect(dispatch_uid="test-qc-correction-no-refinish")

    assert corrected.finished == Decimal("10")
    assert corrected.rev == original_rev + 1
    assert seen == [], "correction must never replay the finished signal"
    assert (
        list(
            WorkOrderItem.objects.filter(work_order=wo).values_list(
                "pk", "quality_grade_ref", "quality_defect_ref", "batch_ref"
            )
        )
        == original_items
    )
    original_batch.refresh_from_db()
    assert original_batch.quality_grade_ref == "standard"
    assert Quant.objects.get(batch=original_batch_ref).quantity == 0

    event = WorkOrderEvent.objects.get(work_order=wo, kind=WorkOrderEvent.Kind.QUALITY_CORRECTED)
    assert event.actor == "production:gerente"
    assert event.payload["reason"].startswith("Quatro unidades")
    assert event.payload["impact"]["stock_reclassified"] is True
    new_refs = event.payload["impact"]["to_batch_refs"]
    assert sum(
        Quant.objects.filter(batch__in=new_refs).values_list("_quantity", flat=True),
        Decimal("0"),
    ) == Decimal("10")
    assert (
        sum(
            Move.objects.filter(
                metadata__operation="production_qc_correction",
                metadata__work_order_ref=wo.ref,
            ).values_list("delta", flat=True),
            Decimal("0"),
        )
        == 0
    )
    assert quality_service.output_partition(wo) == [
        {"grade_ref": "standard", "quantity": "6"},
        {"grade_ref": "fair", "quantity": "4"},
    ]

    kiosk = build_qc_kiosk(selected_date=date.today())
    card = next(item for item in kiosk.orders if item.pk == wo.pk)
    assert card.correction_count == 1
    assert card.can_correct is True
    assert [(group.quality_grade_ref, group.quantity) for group in card.partition] == [
        ("standard", "6"),
        ("fair", "4"),
    ]
    action = next(item for item in kiosk.actions if item.ref == f"correct_qc:{wo.pk}")
    assert action.href.endswith(f"/{wo.pk}/quality-correction/")


@pytest.mark.django_db
def test_correction_replay_is_exact_and_does_not_duplicate_moves(qc_recipe, monkeypatch):
    wo = _finished(qc_recipe, monkeypatch)
    expected_rev = wo.rev
    kwargs = {
        "work_order_id": wo.pk,
        "partition": [
            {
                "quantity": "10",
                "quality_grade_ref": "fair",
                "quality_defect_ref": "misshapen",
            }
        ],
        "reason": "Formato revisto.",
        "actor": "production:gerente",
        "expected_rev": expected_rev,
        "idempotency_key": "correct-qc-replay",
    }
    first = production.apply_quality_correction(**kwargs)
    move_count = Move.objects.filter(metadata__operation="production_qc_correction").count()
    second = production.apply_quality_correction(**kwargs)

    assert second.pk == first.pk
    assert Move.objects.filter(metadata__operation="production_qc_correction").count() == move_count
    assert WorkOrderEvent.objects.filter(kind=WorkOrderEvent.Kind.QUALITY_CORRECTED).count() == 1

    with pytest.raises(ProductionConflict):
        production.apply_quality_correction(
            **{
                **kwargs,
                "partition": [{"quantity": "10", "quality_grade_ref": "excellent"}],
            }
        )


@pytest.mark.django_db
def test_correction_recovers_loss_and_updates_the_effective_saleable_aggregate(qc_recipe, monkeypatch):
    wo = _finished(
        qc_recipe,
        monkeypatch,
        partition=[
            {"quantity": "8", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "underproofed", "loss": True},
        ],
    )
    production.apply_quality_correction(
        work_order_id=wo.pk,
        partition=[
            {"quantity": "9", "quality_grade_ref": "standard"},
            {"quantity": "1", "quality_defect_ref": "underproofed", "loss": True},
        ],
        reason="Uma unidade foi localizada e conferida fisicamente.",
        actor="production:gerente",
        expected_rev=wo.rev,
        idempotency_key="correct-qc-loss-change",
    )

    wo.refresh_from_db()
    assert wo.finished == Decimal("9")
    assert wo.loss == Decimal("1")
    moves = Move.objects.filter(metadata__operation="production_qc_correction")
    assert sum(moves.filter(kind=Move.Kind.TRANSFER).values_list("delta", flat=True), Decimal("0")) == 0
    assert sum(moves.filter(kind=Move.Kind.WASTE).values_list("delta", flat=True), Decimal("0")) == 1
    event = WorkOrderEvent.objects.get(kind=WorkOrderEvent.Kind.QUALITY_CORRECTED)
    assert event.payload["schema_version"] == 2
    assert event.payload["saleable_before"] == "8"
    assert event.payload["saleable_after"] == "9"
    assert event.payload["loss_before"] == "2"
    assert event.payload["loss_after"] == "1"


@pytest.mark.django_db
def test_correction_increases_loss_with_a_balanced_transfer_and_explicit_waste(qc_recipe, monkeypatch):
    wo = _finished(qc_recipe, monkeypatch)

    production.apply_quality_correction(
        work_order_id=wo.pk,
        partition=[
            {"quantity": "8", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "overbaked", "loss": True},
        ],
        reason="Duas unidades foram descartadas após conferência.",
        actor="production:gerente",
        expected_rev=wo.rev,
        idempotency_key="correct-qc-loss-increase",
    )

    wo.refresh_from_db()
    assert wo.finished == Decimal("8")
    assert wo.loss == Decimal("2")
    moves = Move.objects.filter(metadata__operation="production_qc_correction")
    assert sum(moves.filter(kind=Move.Kind.TRANSFER).values_list("delta", flat=True), Decimal("0")) == 0
    assert sum(moves.filter(kind=Move.Kind.WASTE).values_list("delta", flat=True), Decimal("0")) == -2
    current_refs = WorkOrderEvent.objects.get(kind=WorkOrderEvent.Kind.QUALITY_CORRECTED).payload["impact"][
        "to_batch_refs"
    ]
    assert sum(Quant.objects.filter(batch__in=current_refs).values_list("_quantity", flat=True), Decimal("0")) == 8


@pytest.mark.django_db
def test_correction_recovers_a_total_loss_into_a_dated_saleable_lot(qc_recipe, monkeypatch):
    wo = _finished(
        qc_recipe,
        monkeypatch,
        partition=[{"quantity": "10", "quality_defect_ref": "overbaked", "loss": True}],
    )

    production.apply_quality_correction(
        work_order_id=wo.pk,
        partition=[{"quantity": "10", "quality_grade_ref": "standard"}],
        reason="As unidades estavam separadas e foram conferidas pelo gerente.",
        actor="production:gerente",
        expected_rev=wo.rev,
        idempotency_key="correct-qc-total-loss-recovery",
    )

    wo.refresh_from_db()
    assert wo.finished == Decimal("10")
    quant = Quant.objects.get(metadata__production_qc_correction=wo.ref, _quantity=10)
    assert quant.position.is_saleable is True
    batch = Batch.objects.get(ref=quant.batch)
    assert batch.production_date == wo.target_date
    assert batch.expiry_date == wo.target_date + timedelta(days=3)
    recovery = Move.objects.get(
        quant=quant,
        kind=Move.Kind.WASTE,
        metadata__direction="loss_recovery",
    )
    assert recovery.delta == Decimal("10")


@pytest.mark.django_db
def test_incompatible_remote_hold_blocks_atomically(qc_recipe, monkeypatch):
    from shopman.stockman.services.holds import (
        QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
        QUALITY_GRADE_POLICY_VERSION,
        QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    )

    wo = _finished(qc_recipe, monkeypatch)
    source = Quant.objects.get(batch__gt="", _quantity=10)
    hold = Hold.objects.create(
        sku=wo.output_sku,
        quant=source,
        quantity=4,
        target_date=date.today(),
        status=HoldStatus.PENDING,
        metadata={
            "order_ref": "ORD-REMOTE-1",
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            QUALITY_GRADE_ALLOWLIST_METADATA_KEY: ["excellent", "standard"],
        },
    )

    with pytest.raises(ProductionConflict, match="ORD-REMOTE-1"):
        production.apply_quality_correction(
            work_order_id=wo.pk,
            partition=[
                {
                    "quantity": "10",
                    "quality_grade_ref": "minimal",
                    "quality_defect_ref": "overbaked",
                }
            ],
            reason="Lote abaixo do padrão remoto.",
            actor="production:gerente",
            expected_rev=wo.rev,
            idempotency_key="correct-qc-held",
        )

    source.refresh_from_db()
    hold.refresh_from_db()
    wo.refresh_from_db()
    assert source.quantity == Decimal("10")
    assert hold.quant_id == source.pk
    assert not WorkOrderEvent.objects.filter(kind=WorkOrderEvent.Kind.QUALITY_CORRECTED).exists()


@pytest.mark.django_db
def test_loss_correction_never_consumes_units_promised_to_a_customer(qc_recipe, monkeypatch):
    from shopman.stockman.services.holds import (
        QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
        QUALITY_GRADE_POLICY_VERSION,
        QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    )

    wo = _finished(qc_recipe, monkeypatch)
    source = Quant.objects.get(batch__gt="", _quantity=10)
    hold = Hold.objects.create(
        sku=wo.output_sku,
        quant=source,
        quantity=9,
        target_date=date.today(),
        status=HoldStatus.CONFIRMED,
        metadata={
            "order_ref": "PED-CLIENTE-9",
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            QUALITY_GRADE_ALLOWLIST_METADATA_KEY: ["excellent", "standard"],
        },
    )

    with pytest.raises(ProductionConflict, match="PED-CLIENTE-9|Gestor"):
        production.apply_quality_correction(
            work_order_id=wo.pk,
            partition=[
                {"quantity": "8", "quality_grade_ref": "standard"},
                {"quantity": "2", "quality_defect_ref": "overbaked", "loss": True},
            ],
            reason="Duas unidades foram descartadas após conferência.",
            actor="production:gerente",
            expected_rev=wo.rev,
            idempotency_key="correct-qc-held-loss",
        )

    source.refresh_from_db()
    hold.refresh_from_db()
    wo.refresh_from_db()
    assert source.quantity == Decimal("10")
    assert hold.quant_id == source.pk
    assert wo.finished == Decimal("10")
    assert not Move.objects.filter(metadata__operation="production_qc_correction").exists()
    assert not WorkOrderEvent.objects.filter(kind=WorkOrderEvent.Kind.QUALITY_CORRECTED).exists()
    production_alert = OperatorAlert.objects.get(
        type="production_quality_hold_risk",
        order_ref=wo.ref,
    )
    order_alert = OperatorAlert.objects.get(
        type="order_production_quality_risk",
        order_ref="PED-CLIENTE-9",
    )
    assert production_alert.audience == "production"
    assert order_alert.audience == "orders"
    assert "substituição, próxima fornada ou reembolso" in order_alert.message


@pytest.mark.django_db
def test_permissive_hold_keeps_the_best_compatible_corrected_grade(qc_recipe, monkeypatch):
    from shopman.stockman.services.holds import (
        QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
        QUALITY_GRADE_POLICY_VERSION,
        QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    )

    wo = _finished(qc_recipe, monkeypatch)
    source = Quant.objects.get(batch__gt="", _quantity=10)
    hold = Hold.objects.create(
        sku=wo.output_sku,
        quant=source,
        quantity=4,
        target_date=date.today(),
        status=HoldStatus.PENDING,
        metadata={
            "order_ref": "ORD-LOCAL-1",
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            QUALITY_GRADE_ALLOWLIST_METADATA_KEY: ["excellent", "standard", "fair", "minimal"],
        },
    )

    production.apply_quality_correction(
        work_order_id=wo.pk,
        partition=[
            {"quantity": "4", "quality_grade_ref": "excellent"},
            {"quantity": "2", "quality_grade_ref": "standard"},
            {
                "quantity": "4",
                "quality_grade_ref": "fair",
                "quality_defect_ref": "misshapen",
            },
        ],
        reason="Partição conferida pela gestão.",
        actor="production:gerente",
        expected_rev=wo.rev,
        idempotency_key="correct-qc-local-hold",
    )

    hold.refresh_from_db()
    assert Batch.objects.get(ref=hold.quant.batch).quality_grade_ref == "excellent"


@pytest.mark.django_db
def test_recovered_units_materialize_waiting_demand_without_a_false_batch_alert(qc_recipe, monkeypatch):
    from shopman.stockman.services.holds import (
        QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
        QUALITY_GRADE_POLICY_VERSION,
        QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    )

    wo = _finished(
        qc_recipe,
        monkeypatch,
        partition=[
            {"quantity": "8", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "underproofed", "loss": True},
        ],
    )
    waiting = Hold.objects.create(
        sku=wo.output_sku,
        quant=None,
        quantity=2,
        target_date=wo.target_date,
        status=HoldStatus.PENDING,
        metadata={
            "reference": "waiting-session",
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            QUALITY_GRADE_ALLOWLIST_METADATA_KEY: ["excellent", "standard"],
        },
    )

    production.apply_quality_correction(
        work_order_id=wo.pk,
        partition=[{"quantity": "10", "quality_grade_ref": "standard"}],
        reason="Duas unidades separadas foram localizadas e conferidas.",
        actor="production:gerente",
        expected_rev=wo.rev,
        idempotency_key="correct-qc-materialize-recovery",
    )

    waiting.refresh_from_db()
    assert waiting.quant_id is not None
    assert "-qc" in waiting.quant.batch
    event = WorkOrderEvent.objects.get(kind=WorkOrderEvent.Kind.QUALITY_CORRECTED)
    assert event.payload["impact"]["holds_materialized"] == 1


@pytest.mark.django_db
def test_partition_collapses_every_loss_cause_into_one_operator_bucket(qc_recipe, monkeypatch):
    wo = _finished(qc_recipe, monkeypatch)

    with pytest.raises(ProductionError, match="perda deve ser informada em um único grupo"):
        production.resolve_partition(
            wo,
            quantity="10",
            partition=[
                {
                    "quantity": "5",
                    "quality_defect_ref": "overbaked",
                    "loss": True,
                },
                {
                    "quantity": "5",
                    "quality_grade_ref": "standard",
                    "quality_defect_ref": "contaminated",
                },
            ],
        )


@pytest.mark.django_db
def test_correction_supersedes_unsent_quality_campaign_atomically(qc_recipe, monkeypatch):
    from shopman.shop.models import AnnouncementStatus

    wo = _finished(qc_recipe, monkeypatch)
    announcement = _quality_announcement(wo, status=AnnouncementStatus.PENDING_REVIEW)

    production.apply_quality_correction(
        work_order_id=wo.pk,
        partition=[
            {
                "quantity": "10",
                "quality_grade_ref": "fair",
                "quality_defect_ref": "misshapen",
            }
        ],
        reason="A qualidade foi reavaliada antes da campanha.",
        actor="production:gerente",
        expected_rev=wo.rev,
        idempotency_key="correct-qc-supersede-campaign",
    )

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.SUPERSEDED
    event = WorkOrderEvent.objects.get(
        work_order=wo,
        kind=WorkOrderEvent.Kind.QUALITY_CORRECTED,
    )
    assert event.payload["impact"]["communications"] == {
        "superseded_announcement_ids": [announcement.pk],
        "irreversible_announcements": [],
        "closed_review_notification_ids": [],
    }
    assert not OperatorAlert.objects.filter(
        type="production_quality_communication",
        order_ref=wo.ref,
    ).exists()


@pytest.mark.django_db
def test_correction_preserves_sent_campaign_and_raises_operator_alert(qc_recipe, monkeypatch):
    from django.utils import timezone

    from shopman.shop.models import AnnouncementStatus

    wo = _finished(qc_recipe, monkeypatch)
    announcement = _quality_announcement(wo, status=AnnouncementStatus.PUBLISHED)
    announcement.published_at = timezone.now()
    announcement.save(update_fields=["published_at"])

    production.apply_quality_correction(
        work_order_id=wo.pk,
        partition=[
            {
                "quantity": "10",
                "quality_grade_ref": "minimal",
                "quality_defect_ref": "overbaked",
            }
        ],
        reason="A comunicação já havia saído antes da reavaliação.",
        actor="production:gerente",
        expected_rev=wo.rev,
        idempotency_key="correct-qc-sent-campaign",
    )

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PUBLISHED
    alert = OperatorAlert.objects.get(
        type="production_quality_communication",
        order_ref=wo.ref,
    )
    assert alert.audience == "production"
    assert "Marketing" in alert.message
    event = WorkOrderEvent.objects.get(
        work_order=wo,
        kind=WorkOrderEvent.Kind.QUALITY_CORRECTED,
    )
    assert (
        event.payload["impact"]["communications"]["irreversible_announcements"][0]["announcement_id"] == announcement.pk
    )


@pytest.mark.django_db
def test_quality_correction_api_requires_manager_capability(client, qc_recipe, monkeypatch):
    wo = _finished(qc_recipe, monkeypatch)
    floor = grant_production_operator(User.objects.create_user("qc-floor-only", password="pw", is_staff=True))
    url = reverse("api-backstage-wo-quality-correction", args=[wo.pk])
    body = {
        "partition": [
            {
                "quantity": "10",
                "quality_grade_ref": "fair",
                "quality_defect_ref": "misshapen",
            }
        ],
        "reason": "Conferência da gestão.",
        "expected_rev": wo.rev,
        "idempotency_key": "correct-qc-api",
    }
    client.force_login(floor)
    denied = production_mutation_post(client, url, body, content_type="application/json")
    assert denied.status_code == 403

    floor.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename="correct_production_qc")
    )
    floor = User.objects.get(pk=floor.pk)
    client.force_login(floor)
    accepted = production_mutation_post(client, url, body, content_type="application/json")
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["current"]["rev"] == wo.rev + 1
