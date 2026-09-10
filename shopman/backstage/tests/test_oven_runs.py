"""OvenRun — o fato temporal do forno (ADR-021 §4, BI-PLAN §4).

O timer do kiosk declara; o servidor carimba. Cobre a capacidade efetiva de
registrar fato de forno, o carimbo server-side no arm/conclude, o veto de
re-arm sem ação projetada, o conflito tipado ao concluir sem run conciliável
e o sweep de runs vencidos.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
from shopman.stockman.models import Position

from shopman.backstage.models import DayClosing, OvenRun
from shopman.backstage.services.production import (
    ProductionConflict,
    ProductionError,
)
from shopman.backstage.services.production import (
    apply_finish as _raw_apply_finish,
)
from shopman.backstage.services.production import (
    apply_oven_arm as _raw_apply_oven_arm,
)
from shopman.backstage.services.production import (
    apply_oven_conclude as _raw_apply_oven_conclude,
)
from shopman.backstage.services.production import (
    apply_void as _raw_apply_void,
)
from shopman.backstage.tests.support import production_mutation_post

_attempts = count(1)


def _service_attempt(work_order_id, kwargs, action: str):
    enriched = dict(kwargs)
    if "expected_rev" not in enriched:
        enriched["expected_rev"] = WorkOrder.objects.filter(pk=work_order_id).values_list("rev", flat=True).first() or 0
    enriched.setdefault("idempotency_key", f"test-{action}-{next(_attempts)}")
    return enriched


def apply_oven_arm(*, work_order_id, **kwargs):
    return _raw_apply_oven_arm(
        work_order_id=work_order_id,
        **_service_attempt(work_order_id, kwargs, "oven-arm"),
    )


def apply_oven_conclude(*, work_order_id, **kwargs):
    return _raw_apply_oven_conclude(
        work_order_id=work_order_id,
        **_service_attempt(work_order_id, kwargs, "oven-conclude"),
    )


def apply_finish(*, work_order_id, **kwargs):
    return _raw_apply_finish(
        work_order_id=work_order_id,
        **_service_attempt(work_order_id, kwargs, "finish"),
    )


def apply_void(work_order_id, **kwargs):
    return _raw_apply_void(
        work_order_id,
        **_service_attempt(work_order_id, kwargs, "void"),
    )


def _operate_production_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_production",
    )


@pytest.fixture
def production_operator(db):
    user = User.objects.create_user("oven-api", password="pw", is_staff=True)
    user.user_permissions.add(
        _operate_production_perm(),
        Permission.objects.get(
            content_type__app_label="shop",
            codename="edit_production_started",
        ),
    )
    return user


@pytest.fixture
def position(db):
    return Position.objects.create(ref="forno", name="Forno", kind="oven", is_default=True)


@pytest.fixture
def recipe(db, position):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Forno")
    return Recipe.objects.create(
        ref="oven-run-v1",
        name="Pão do Forno",
        output_sku="OVEN-RUN",
        batch_size=Decimal("10"),
    )


@pytest.fixture
def work_order(recipe):
    order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    return craft.start(order, quantity=10, position_ref="forno")


def _arm_url(wo) -> str:
    return reverse("api-backstage-wo-oven-arm", kwargs={"wo_id": wo.pk})


def _conclude_url(wo) -> str:
    return reverse("api-backstage-wo-oven-conclude", kwargs={"wo_id": wo.pk})


def _mutation(wo, key: str, **values) -> dict:
    wo.refresh_from_db()
    return {
        "expected_rev": wo.rev,
        "idempotency_key": key,
        **values,
    }


# ── Gate ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_arm_requires_operate_production(client, work_order):
    bare = User.objects.create_user("bare-oven", password="pw", is_staff=True)
    client.force_login(bare)
    assert production_mutation_post(client, _arm_url(work_order), {"planned_seconds": 600}).status_code == 403
    assert production_mutation_post(client, _conclude_url(work_order)).status_code == 403


# ── Arm (enfornou) ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_arm_creates_open_run_with_server_stamp(client, work_order, production_operator):
    client.force_login(production_operator)
    before = timezone.now()
    response = production_mutation_post(
        client,
        _arm_url(work_order),
        _mutation(work_order, "arm-server-stamp", planned_seconds=900),
    )
    assert response.status_code == 200
    assert response.json()["run_status"] == "open"
    run = OvenRun.objects.get(pk=response.json()["run_id"])
    assert run.status == "open"
    assert run.work_order_ref == work_order.ref
    assert run.oven_ref == "forno"
    assert run.planned_seconds == 900
    assert before <= run.armed_at <= timezone.now()
    assert run.concluded_at is None
    assert run.elapsed_seconds is None


@pytest.mark.django_db
def test_arm_rejects_a_second_attempt_while_a_run_is_open(
    client,
    work_order,
    production_operator,
):
    client.force_login(production_operator)
    first = production_mutation_post(
        client,
        _arm_url(work_order),
        _mutation(work_order, "arm-first", planned_seconds=600),
    ).json()["run_id"]
    second = production_mutation_post(
        client,
        _arm_url(work_order),
        _mutation(work_order, "arm-second", planned_seconds=1200),
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"
    assert OvenRun.objects.get(pk=first).status == "open"
    assert OvenRun.objects.filter(work_order_ref=work_order.ref, status="open").count() == 1
    assert not WorkOrderEvent.objects.filter(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.OVEN_ABANDONED,
    ).exists()


@pytest.mark.django_db
def test_retrying_arm_after_lifecycle_abandonment_returns_the_original_outcome(
    client,
    work_order,
    production_operator,
    position,
):
    client.force_login(production_operator)
    first_payload = _mutation(work_order, "arm-old", planned_seconds=600)
    first = production_mutation_post(client, _arm_url(work_order), first_payload)
    assert first.status_code == 200
    position.is_saleable = True
    position.save(update_fields=["is_saleable", "updated_at"])
    work_order.refresh_from_db()
    apply_finish(
        work_order_id=work_order.pk,
        quantity=10,
        actor="finish-after-arm",
        expected_rev=work_order.rev,
        idempotency_key="finish-after-arm",
    )

    replay = production_mutation_post(client, _arm_url(work_order), first_payload)

    assert replay.status_code == 200
    assert replay.json()["run_id"] == first.json()["run_id"]
    assert OvenRun.objects.get(arm_idempotency_key__endswith="arm-old").status == "abandoned"


@pytest.mark.django_db
def test_arm_retry_with_same_attempt_does_not_create_or_abandon_another_run(
    client,
    work_order,
    production_operator,
):
    client.force_login(production_operator)
    payload = _mutation(work_order, "arm-retry", planned_seconds=600)

    first = production_mutation_post(client, _arm_url(work_order), payload)
    second = production_mutation_post(client, _arm_url(work_order), payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    assert OvenRun.objects.filter(work_order_ref=work_order.ref).count() == 1
    work_order.refresh_from_db()
    assert work_order.rev == 2
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.OVEN_ARMED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_second_arm_with_another_attempt_and_stale_revision_conflicts(
    client,
    work_order,
    production_operator,
):
    client.force_login(production_operator)
    original_rev = work_order.rev
    first = production_mutation_post(
        client,
        _arm_url(work_order),
        {
            "planned_seconds": 600,
            "expected_rev": original_rev,
            "idempotency_key": "arm-tablet-one",
        },
    )
    second = production_mutation_post(
        client,
        _arm_url(work_order),
        {
            "planned_seconds": 900,
            "expected_rev": original_rev,
            "idempotency_key": "arm-tablet-two",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "stale_projection"
    assert OvenRun.objects.filter(work_order_ref=work_order.ref).count() == 1


@pytest.mark.django_db
def test_arm_rejects_invalid_duration(client, work_order, production_operator):
    client.force_login(production_operator)
    for index, bad in enumerate((0, -5, "abc", "", 86_401)):
        assert (
            production_mutation_post(
                client,
                _arm_url(work_order),
                _mutation(work_order, f"arm-invalid-{index}", planned_seconds=bad),
            ).status_code
            == 400
        )
    assert not OvenRun.objects.exists()


@pytest.mark.django_db
def test_arm_rejects_operator_ref_longer_than_storage(
    client,
    work_order,
    production_operator,
):
    client.force_login(production_operator)

    response = production_mutation_post(
        client,
        _arm_url(work_order),
        _mutation(
            work_order,
            "arm-long-operator",
            planned_seconds=600,
            operator_ref="o" * 101,
        ),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert not OvenRun.objects.exists()


@pytest.mark.django_db
def test_arm_rejects_closed_work_order(client, work_order, production_operator):
    apply_void(work_order.pk, actor="test")
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        _arm_url(work_order),
        _mutation(work_order, "arm-closed", planned_seconds=600),
    )
    assert response.status_code == 403
    assert response.json()["error"]["capability"] == "can_manage_all"
    assert not OvenRun.objects.exists()


@pytest.mark.django_db
def test_arm_rejects_planned_work_order(client, recipe, production_operator):
    planned = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)

    response = production_mutation_post(
        client,
        _arm_url(planned),
        _mutation(planned, "arm-before-start", planned_seconds=600),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert response.json()["error"]["current"]["status"] == "planned"
    assert not OvenRun.objects.exists()


# ── Conclude (retirou) ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_conclude_measures_open_run(client, work_order, production_operator):
    client.force_login(production_operator)
    production_mutation_post(
        client,
        _arm_url(work_order),
        _mutation(work_order, "arm-for-conclude", planned_seconds=600),
    )
    response = production_mutation_post(
        client,
        _conclude_url(work_order),
        _mutation(work_order, "conclude-open"),
    )
    assert response.status_code == 200
    assert response.json()["measured"] is True
    assert response.json()["run_status"] == "concluded"
    run = OvenRun.objects.get(work_order_ref=work_order.ref)
    assert run.status == "concluded"
    assert run.concluded_at is not None
    assert run.elapsed_seconds is not None and run.elapsed_seconds >= 0


@pytest.mark.django_db
def test_conclude_retry_with_same_attempt_is_exactly_once(
    client,
    work_order,
    production_operator,
):
    client.force_login(production_operator)
    production_mutation_post(
        client,
        _arm_url(work_order),
        _mutation(work_order, "arm-before-retry", planned_seconds=600),
    )
    payload = _mutation(work_order, "conclude-retry")

    first = production_mutation_post(client, _conclude_url(work_order), payload)
    second = production_mutation_post(client, _conclude_url(work_order), payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["measured"] is second.json()["measured"] is True
    assert (
        OvenRun.objects.filter(
            work_order_ref=work_order.ref,
            status="concluded",
        ).count()
        == 1
    )
    work_order.refresh_from_db()
    assert work_order.rev == 3
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.OVEN_CONCLUDED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_retrying_old_conclude_replays_without_clearing_a_new_open_run(
    client,
    work_order,
    production_operator,
):
    client.force_login(production_operator)
    assert (
        production_mutation_post(
            client,
            _arm_url(work_order),
            _mutation(work_order, "arm-a", planned_seconds=600),
        ).status_code
        == 200
    )
    conclude_payload = _mutation(work_order, "conclude-a")
    assert production_mutation_post(client, _conclude_url(work_order), conclude_payload).status_code == 200
    assert (
        production_mutation_post(
            client,
            _arm_url(work_order),
            _mutation(work_order, "arm-b", planned_seconds=900),
        ).status_code
        == 200
    )
    work_order.refresh_from_db()
    rev_before_replay = work_order.rev

    replay = production_mutation_post(client, _conclude_url(work_order), conclude_payload)

    assert replay.status_code == 200
    assert replay.json()["run_status"] == "concluded"
    assert OvenRun.objects.filter(work_order_ref=work_order.ref, status="open").count() == 1
    work_order.refresh_from_db()
    assert work_order.rev == rev_before_replay
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.OVEN_CONCLUDED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_conclude_without_open_run_is_reconciliable_conflict(
    client,
    work_order,
    production_operator,
):
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        _conclude_url(work_order),
        _mutation(work_order, "conclude-none"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "oven_run_missing"
    assert response.json()["error"]["current"]["pk"] == work_order.pk
    assert not OvenRun.objects.exists()


@pytest.mark.django_db
def test_conclude_ignores_already_closed_runs(work_order, production_operator):
    apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    assert apply_oven_conclude(work_order_id=work_order.pk, actor="test") is not None
    # Segundo Concluir não pode fingir um fato que não existe.
    with pytest.raises(ProductionConflict) as exc:
        apply_oven_conclude(work_order_id=work_order.pk, actor="test")
    assert exc.value.code == "oven_run_missing"
    assert OvenRun.objects.filter(status="concluded").count() == 1


@pytest.mark.django_db
def test_void_abandons_open_run_and_terminal_conclude_cannot_mutate(work_order):
    run = apply_oven_arm(
        work_order_id=work_order.pk,
        planned_seconds=600,
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="arm-before-void",
    )
    work_order.refresh_from_db()
    apply_void(
        work_order.pk,
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="void-open-oven",
        reason="fornada cancelada",
    )
    work_order.refresh_from_db()
    rev_before_conclude = work_order.rev

    run.refresh_from_db()
    assert run.status == "abandoned"
    assert run.concluded_at is None
    assert run.metadata["terminal_transition"] == "void"
    abandonment = WorkOrderEvent.objects.get(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.OVEN_ABANDONED,
    )
    assert abandonment.payload["run_id"] == run.pk
    assert abandonment.payload["reason"] == "work_order_voided"

    with pytest.raises(ProductionConflict) as exc_info:
        apply_oven_conclude(
            work_order_id=work_order.pk,
            actor="production:test",
            expected_rev=work_order.rev,
            idempotency_key="conclude-after-void",
        )

    assert exc_info.value.data["cause"] == "invalid_status"
    work_order.refresh_from_db()
    assert work_order.rev == rev_before_conclude
    assert not WorkOrderEvent.objects.filter(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.OVEN_CONCLUDED,
    ).exists()


@pytest.mark.django_db
def test_finish_abandons_open_run_and_terminal_conclude_cannot_mutate(
    work_order,
    position,
):
    position.is_saleable = True
    position.save(update_fields=["is_saleable", "updated_at"])
    run = apply_oven_arm(
        work_order_id=work_order.pk,
        planned_seconds=600,
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="arm-before-finish",
    )
    work_order.refresh_from_db()
    apply_finish(
        work_order_id=work_order.pk,
        quantity="10",
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="finish-open-oven",
    )
    work_order.refresh_from_db()
    rev_before_conclude = work_order.rev

    run.refresh_from_db()
    assert run.status == "abandoned"
    assert run.concluded_at is None
    assert run.metadata["terminal_transition"] == "finish"
    assert WorkOrderEvent.objects.filter(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.OVEN_ABANDONED,
        payload__run_id=run.pk,
    ).exists()

    with pytest.raises(ProductionConflict) as exc_info:
        apply_oven_conclude(
            work_order_id=work_order.pk,
            actor="production:test",
            expected_rev=work_order.rev,
            idempotency_key="conclude-after-finish",
        )

    assert exc_info.value.data["cause"] == "invalid_status"
    work_order.refresh_from_db()
    assert work_order.rev == rev_before_conclude
    assert not WorkOrderEvent.objects.filter(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.OVEN_CONCLUDED,
    ).exists()


# ── Service edges ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_service_rejects_unknown_work_order(db):
    with pytest.raises(ProductionError):
        apply_oven_arm(work_order_id=999_999, planned_seconds=600, actor="test")
    with pytest.raises(ProductionError):
        apply_oven_conclude(work_order_id=999_999, actor="test")


@pytest.mark.django_db
def test_service_operator_ref_falls_back_to_actor(work_order):
    run = apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="production:ana")
    assert run.operator_ref == "production:ana"
    apply_oven_conclude(work_order_id=work_order.pk, actor="production:ana")
    run2 = apply_oven_arm(
        work_order_id=work_order.pk,
        planned_seconds=600,
        operator_ref="marina",
        actor="production:ana",
    )
    assert run2.operator_ref == "marina"


@pytest.mark.django_db
def test_oven_run_accepts_full_width_actor_and_position(recipe):
    position_ref = "p" * 100
    Position.objects.create(ref=position_ref, name="Forno longo")
    planned = craft.plan(recipe, 10, date=date.today(), position_ref=position_ref)
    started = craft.start(planned, quantity=10, position_ref=position_ref)

    run = apply_oven_arm(
        work_order_id=started.pk,
        planned_seconds=600,
        actor="a" * 100,
    )

    assert run.oven_ref == position_ref
    assert run.operator_ref == "a" * 100


# ── Sweep ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sweep_abandons_only_stale_open_runs(work_order):
    stale = apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    OvenRun.objects.filter(pk=stale.pk).update(status="abandoned")  # libera o partial unique p/ abrir o run fresco
    fresh = apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    OvenRun.objects.filter(pk=stale.pk).update(
        status="open", armed_at=timezone.now() - timedelta(minutes=600), work_order_ref="wo-stale"
    )
    call_command("sweep_stale_oven_runs")
    stale.refresh_from_db()
    assert stale.status == "abandoned"
    assert stale.metadata["abandoned_reason"] == "stale_timeout_orphan"
    assert OvenRun.objects.get(pk=fresh.pk).status == "open"


@pytest.mark.django_db
def test_sweep_max_minutes_override(work_order):
    run = apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    OvenRun.objects.filter(pk=run.pk).update(armed_at=timezone.now() - timedelta(minutes=10))
    call_command("sweep_stale_oven_runs", "--max-minutes", "5")
    run.refresh_from_db()
    assert run.status == "abandoned"
    assert run.metadata["abandoned_reason"] == "stale_timeout"
    abandoned = WorkOrderEvent.objects.get(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.OVEN_ABANDONED,
    )
    assert abandoned.actor == "system:oven-sweep"
    assert abandoned.payload["transition"] == "sweep"


@pytest.mark.django_db
def test_concluded_run_survives_sweep(work_order):
    apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    run = apply_oven_conclude(work_order_id=work_order.pk, actor="test")
    OvenRun.objects.filter(pk=run.pk).update(armed_at=timezone.now() - timedelta(minutes=600))
    call_command("sweep_stale_oven_runs")
    assert OvenRun.objects.get(pk=run.pk).status == "concluded"
