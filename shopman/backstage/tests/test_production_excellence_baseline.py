"""Versioned, anonymized baseline for the production excellence programme.

This is deliberately a measurement test, not the final performance budget.
It keeps the representative dataset and the seven read surfaces reproducible
while WP-P1.1 establishes constant-query limits from the captured baseline.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import perf_counter_ns

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.stockman.models import Position

from shopman.backstage.models import DayClosing, OperatorAlert


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs/plans/production-irrepressible-excellence-execution/fixtures-v1.json"
)


def _permission(app_label: str, model: str, codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label=app_label, model=model),
        codename=codename,
    )


@pytest.fixture
def excellence_operator(db):
    user = User.objects.create_user("production-baseline", password="fixture", is_staff=True)
    user.user_permissions.add(
        _permission("backstage", "dayclosing", "operate_production"),
        _permission("backstage", "dayclosing", "view_production_reports"),
        _permission("shop", "shop", "manage_production"),
    )
    return user


@pytest.fixture
def excellence_dataset(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Fixture Produção")
    Position.objects.create(ref="fixture-oven", name="Forno Fixture", kind="oven", is_default=True)
    recipe = Recipe.objects.create(
        ref="fixture-bread-v1",
        name="Pão Fixture",
        output_sku="FIX-BREAD",
        batch_size=Decimal("10"),
        steps=["Mistura", "Fermentação", "Forno"],
        meta={"max_started_minutes": 30, "capacity_per_day": 100},
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="FIX-FLOUR",
        quantity=Decimal("5"),
        unit="kg",
    )

    work_orders = [
        craft.plan(recipe, Decimal("10") + index, date=date.today(), position_ref="fixture-oven")
        for index in range(100)
    ]
    for work_order in work_orders[33:67]:
        craft.start(
            work_order,
            quantity=work_order.quantity,
            position_ref="fixture-oven",
            expected_rev=0,
        )
    for work_order in work_orders[67:]:
        craft.finish(order=work_order, finished=work_order.quantity, expected_rev=0)

    OperatorAlert.objects.create(
        type="production_late",
        severity="warning",
        message="Fornada fixture atrasada",
        order_ref=work_orders[33].ref,
    )
    return recipe


def test_anonymized_baseline_fixture_covers_required_risks():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_version"] == 1
    assert set(fixture["scenarios"]) == {
        "product_without_recipe",
        "single_work_order",
        "multiple_work_orders",
        "linked_order",
        "stock_states",
        "late_work_order",
        "partially_completed_steps",
        "mixed_quality",
        "total_loss",
        "tablet_race",
    }
    assert {row["state"] for row in fixture["scenarios"]["stock_states"]} == {
        "sufficient",
        "insufficient",
        "known_zero",
    }


@pytest.mark.django_db
def test_projection_baseline_is_measurable(
    client,
    excellence_operator,
    excellence_dataset,
    capsys,
):
    client.force_login(excellence_operator)
    endpoints = {
        "board": reverse("api-backstage-production"),
        "kds": reverse("api-backstage-production-kds"),
        "qc": reverse("api-backstage-production-qc"),
        "mise_en_place": reverse("api-backstage-production-mise-en-place"),
        "weighing": reverse("api-backstage-production-weighing"),
        "reports": reverse("api-backstage-production-reports"),
        "alerts": reverse("api-backstage-alerts"),
    }

    measurements = {}
    for name, url in endpoints.items():
        started = perf_counter_ns()
        with CaptureQueriesContext(connection) as captured:
            response = client.get(url)
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000
        assert response.status_code == 200, (name, response.content[:500])
        payload = response.json()
        measurements[name] = {
            "queries": len(captured),
            "elapsed_ms": round(elapsed_ms, 3),
            "payload_bytes": len(response.content),
            "top_level_keys": sorted(payload),
        }

    assert set(measurements) == set(endpoints)
    with capsys.disabled():
        print("PRODUCTION_BASELINE_METRICS=" + json.dumps(measurements, sort_keys=True))
