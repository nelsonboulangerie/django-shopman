from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder

from shopman.backstage.projections.production import build_production_kds, resolve_production_access
from shopman.backstage.services import production as production_service
from shopman.backstage.services.exceptions import ProductionConflict, ProductionError


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("steps-admin", "steps@test.com", "pw")


def _recipe(ref: str, *, meta=None, steps=None):
    return Recipe.objects.create(
        ref=ref,
        name=ref,
        output_sku=ref.upper(),
        batch_size=Decimal("10"),
        meta=meta or {},
        steps=steps or [],
    )


def _started(recipe, *, minutes_ago: int, meta=None):
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    WorkOrder.objects.filter(pk=wo.pk).update(
        started_at=timezone.now() - timedelta(minutes=minutes_ago),
        meta=meta or {},
    )
    return WorkOrder.objects.get(pk=wo.pk)


def _advance(wo, key: str):
    return production_service.apply_advance_step(
        work_order_id=wo.pk,
        actor="op:test",
        expected_rev=wo.rev,
        idempotency_key=key,
    )


@pytest.mark.django_db
def test_work_order_without_steps_keeps_fallback(superuser):
    recipe = _recipe("plain")
    _started(recipe, minutes_ago=1)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step == "Produção"
    assert card.current_step_index is None
    assert card.total_steps == 0


@pytest.mark.django_db
def test_meta_steps_calculate_current_step_progress(superuser):
    recipe = _recipe(
        "with-steps",
        meta={
            "steps": [
                {"name": "Misturar", "target_seconds": 600},
                {"name": "Assar", "target_seconds": 300},
                {"name": "Resfriar", "target_seconds": 180},
            ]
        },
    )
    _started(recipe, minutes_ago=5)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_index == 1
    assert card.current_step_name == "Misturar"
    assert 45 <= card.step_progress_pct <= 55
    assert card.next_step_name == "Assar"


@pytest.mark.django_db
def test_elapsed_time_advances_to_next_step(superuser):
    recipe = _recipe(
        "advanced",
        meta={
            "steps": [
                {"name": "Misturar", "target_seconds": 600},
                {"name": "Assar", "target_seconds": 300},
            ]
        },
    )
    _started(recipe, minutes_ago=12)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_index == 2
    assert card.current_step_name == "Assar"


@pytest.mark.django_db
def test_steps_progress_manual_override(superuser):
    recipe = _recipe(
        "manual",
        meta={
            "steps": [
                {"name": "Misturar", "target_seconds": 600},
                {"name": "Assar", "target_seconds": 300},
            ]
        },
    )
    _started(recipe, minutes_ago=1, meta={"steps_progress": 2})

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_index == 2
    assert card.current_step_name == "Assar"


@pytest.mark.django_db
def test_legacy_recipe_steps_are_supported(superuser):
    recipe = _recipe("legacy", steps=["Modelar", "Forno"], meta={"max_started_minutes": 20})
    _started(recipe, minutes_ago=1)

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]

    assert card.current_step_name == "Modelar"
    assert card.total_steps == 2


@pytest.mark.django_db
def test_apply_advance_step_increments_pointer(superuser):
    recipe = _recipe(
        "advance",
        meta={
            "steps": [
                {"name": "Misturar", "target_seconds": 600},
                {"name": "Assar", "target_seconds": 300},
                {"name": "Resfriar", "target_seconds": 180},
            ]
        },
    )
    wo = _started(recipe, minutes_ago=1)

    new_index = _advance(wo, "advance-1")
    assert new_index == 1
    wo.refresh_from_db()
    assert wo.meta["steps_progress"] == 1

    _advance(wo, "advance-2")
    wo.refresh_from_db()
    assert wo.meta["steps_progress"] == 2


@pytest.mark.django_db
def test_apply_advance_step_rejects_when_all_steps_are_complete(superuser):
    recipe = _recipe(
        "cap",
        meta={
            "steps": [
                {"name": "A", "target_seconds": 60},
                {"name": "B", "target_seconds": 60},
            ]
        },
    )
    wo = _started(recipe, minutes_ago=1, meta={"steps_progress": 5})

    original_rev = wo.rev
    original_events = wo.events.count()

    with pytest.raises(ProductionConflict):
        _advance(wo, "advance-complete")

    wo.refresh_from_db()
    assert wo.rev == original_rev
    assert wo.events.count() == original_events


@pytest.mark.django_db
def test_completed_steps_have_no_enabled_or_signed_advance_action(
    client,
    superuser,
):
    recipe = _recipe(
        "completed-action",
        meta={"steps": [{"name": "A"}, {"name": "B"}]},
    )
    work_order = _started(recipe, minutes_ago=1, meta={"steps_progress": 2})
    client.force_login(superuser)

    kds = client.get(reverse("api-backstage-production-kds")).json()["kds"]
    card = next(item for item in kds["cards"] if item["pk"] == work_order.pk)
    action = next(item for item in kds["actions"] if item["ref"] == f"advance_step:{work_order.pk}")

    assert card["can_advance_step"] is False
    assert action["enabled"] is False
    assert action["proof"] == ""
    assert action["reason"] == "Todos os passos desta fornada já foram concluídos."


@pytest.mark.django_db
def test_apply_advance_step_rejects_recipe_without_steps(superuser):
    recipe = _recipe("no-steps")
    wo = _started(recipe, minutes_ago=1)

    with pytest.raises(ProductionError):
        _advance(wo, "advance-no-steps")


@pytest.mark.django_db
def test_apply_advance_step_rejects_missing_attempt_metadata_without_mutation(superuser):
    recipe = _recipe("attempt-required", steps=["Misturar"])
    work_order = _started(recipe, minutes_ago=1)
    original_rev = work_order.rev
    original_events = work_order.events.count()

    with pytest.raises(ProductionConflict) as caught:
        production_service.apply_advance_step(work_order_id=work_order.pk, actor="op:test")

    assert caught.value.data["cause"] == "missing_mutation_attempt"
    work_order.refresh_from_db()
    assert work_order.rev == original_rev
    assert work_order.events.count() == original_events


@pytest.mark.django_db
def test_empty_frozen_steps_do_not_inherit_later_recipe_edits(superuser):
    recipe = _recipe("frozen-empty")
    wo = craft.plan(recipe, 10, date=date.today())
    recipe.meta = {"steps": [{"name": "Passo tardio", "target_seconds": 60}]}
    recipe.save(update_fields=["meta", "updated_at"])
    craft.start(wo, quantity=10, expected_rev=wo.rev)

    with pytest.raises(ProductionError, match="Receita sem passos"):
        _advance(wo, "advance-frozen-empty")

    card = build_production_kds(access=resolve_production_access(superuser)).cards[0]
    assert card.total_steps == 0


# The advance-step HTTP path moved to the headless API
# (POST /api/v1/backstage/production/<pk>/advance-step/) consumed by the prod.
# Nuxt app; that contract is covered by test_api_production_surface and the
# repointed test_backstage_e2e. The pure-service behaviour stays tested above
# (test_apply_advance_step_*).
