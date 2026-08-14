"""OvenRun — o fato temporal do forno (ADR-021 §4, BI-PLAN §4).

O timer do kiosk declara; o servidor carimba. Cobre o gate coarse
``backstage.operate_production``, o carimbo server-side no arm/conclude, o
supersede de run aberto (re-armar = nova enfornada), o conclude sem run
(sem medição, sem erro — o cliente é best-effort) e o sweep de runs vencidos.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.stockman.models import Position

from shopman.backstage.models import DayClosing, OvenRun
from shopman.backstage.services.production import (
    ProductionError,
    apply_oven_arm,
    apply_oven_conclude,
    apply_void,
)


def _operate_production_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_production",
    )


@pytest.fixture
def production_operator(db):
    user = User.objects.create_user("oven-api", password="pw", is_staff=True)
    user.user_permissions.add(_operate_production_perm())
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
    return craft.plan(recipe, 10, date=date.today(), position_ref="forno")


def _arm_url(wo) -> str:
    return reverse("api-backstage-wo-oven-arm", kwargs={"wo_id": wo.pk})


def _conclude_url(wo) -> str:
    return reverse("api-backstage-wo-oven-conclude", kwargs={"wo_id": wo.pk})


# ── Gate ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_arm_requires_operate_production(client, work_order):
    bare = User.objects.create_user("bare-oven", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.post(_arm_url(work_order), {"planned_seconds": 600}).status_code == 403
    assert client.post(_conclude_url(work_order)).status_code == 403


# ── Arm (enfornou) ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_arm_creates_open_run_with_server_stamp(client, work_order, production_operator):
    client.force_login(production_operator)
    before = timezone.now()
    response = client.post(_arm_url(work_order), {"planned_seconds": 900})
    assert response.status_code == 200
    run = OvenRun.objects.get(pk=response.json()["run_id"])
    assert run.status == "open"
    assert run.work_order_ref == work_order.ref
    assert run.oven_ref == "forno"
    assert run.planned_seconds == 900
    assert before <= run.armed_at <= timezone.now()
    assert run.concluded_at is None
    assert run.elapsed_seconds is None


@pytest.mark.django_db
def test_arm_supersedes_open_run(client, work_order, production_operator):
    client.force_login(production_operator)
    first = client.post(_arm_url(work_order), {"planned_seconds": 600}).json()["run_id"]
    second = client.post(_arm_url(work_order), {"planned_seconds": 1200}).json()["run_id"]
    assert first != second
    assert OvenRun.objects.get(pk=first).status == "abandoned"
    new_run = OvenRun.objects.get(pk=second)
    assert new_run.status == "open"
    assert new_run.metadata == {"superseded_open_runs": 1}
    assert OvenRun.objects.filter(work_order_ref=work_order.ref, status="open").count() == 1


@pytest.mark.django_db
def test_arm_rejects_invalid_duration(client, work_order, production_operator):
    client.force_login(production_operator)
    for bad in (0, -5, "abc", "", 86_401):
        assert client.post(_arm_url(work_order), {"planned_seconds": bad}).status_code == 400
    assert not OvenRun.objects.exists()


@pytest.mark.django_db
def test_arm_rejects_closed_work_order(client, work_order, production_operator):
    apply_void(work_order.pk, actor="test")
    client.force_login(production_operator)
    response = client.post(_arm_url(work_order), {"planned_seconds": 600})
    assert response.status_code == 400
    assert not OvenRun.objects.exists()


# ── Conclude (retirou) ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_conclude_measures_open_run(client, work_order, production_operator):
    client.force_login(production_operator)
    client.post(_arm_url(work_order), {"planned_seconds": 600})
    response = client.post(_conclude_url(work_order))
    assert response.status_code == 200
    assert response.json()["measured"] is True
    run = OvenRun.objects.get(work_order_ref=work_order.ref)
    assert run.status == "concluded"
    assert run.concluded_at is not None
    assert run.elapsed_seconds is not None and run.elapsed_seconds >= 0


@pytest.mark.django_db
def test_conclude_without_open_run_measures_nothing(client, work_order, production_operator):
    client.force_login(production_operator)
    response = client.post(_conclude_url(work_order))
    assert response.status_code == 200
    assert response.json()["measured"] is False
    assert not OvenRun.objects.exists()


@pytest.mark.django_db
def test_conclude_ignores_already_closed_runs(work_order, production_operator):
    apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    assert apply_oven_conclude(work_order_id=work_order.pk, actor="test") is not None
    # Segundo Concluir: o run já fechou; não há o que medir de novo.
    assert apply_oven_conclude(work_order_id=work_order.pk, actor="test") is None
    assert OvenRun.objects.filter(status="concluded").count() == 1


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
    run2 = apply_oven_arm(
        work_order_id=work_order.pk, planned_seconds=600,
        operator_ref="marina", actor="production:ana",
    )
    assert run2.operator_ref == "marina"


# ── Sweep ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sweep_abandons_only_stale_open_runs(work_order):
    stale = apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    OvenRun.objects.filter(pk=stale.pk).update(
        status="abandoned"
    )  # libera o partial unique p/ abrir o run fresco
    fresh = apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    OvenRun.objects.filter(pk=stale.pk).update(
        status="open", armed_at=timezone.now() - timedelta(minutes=600), work_order_ref="wo-stale"
    )
    call_command("sweep_stale_oven_runs")
    assert OvenRun.objects.get(pk=stale.pk).status == "abandoned"
    assert OvenRun.objects.get(pk=fresh.pk).status == "open"


@pytest.mark.django_db
def test_sweep_max_minutes_override(work_order):
    run = apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    OvenRun.objects.filter(pk=run.pk).update(armed_at=timezone.now() - timedelta(minutes=10))
    call_command("sweep_stale_oven_runs", "--max-minutes", "5")
    assert OvenRun.objects.get(pk=run.pk).status == "abandoned"


@pytest.mark.django_db
def test_concluded_run_survives_sweep(work_order):
    apply_oven_arm(work_order_id=work_order.pk, planned_seconds=600, actor="test")
    run = apply_oven_conclude(work_order_id=work_order.pk, actor="test")
    OvenRun.objects.filter(pk=run.pk).update(armed_at=timezone.now() - timedelta(minutes=600))
    call_command("sweep_stale_oven_runs")
    assert OvenRun.objects.get(pk=run.pk).status == "concluded"
