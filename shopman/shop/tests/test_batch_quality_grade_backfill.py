from __future__ import annotations

from importlib import import_module

import pytest
from django.apps import apps
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderItem
from shopman.stockman.models import Batch

pytestmark = pytest.mark.django_db


def test_backfill_only_accepts_unambiguous_batch_grade():
    recipe = Recipe.objects.create(
        ref="grade-backfill",
        name="Grade backfill",
        output_sku="GRADE-BACKFILL",
        batch_size=1,
    )
    work_order = WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=3,
    )
    Batch.objects.create(ref="UNIQUE-GRADE", sku=recipe.output_sku)
    Batch.objects.create(ref="AMBIGUOUS-GRADE", sku=recipe.output_sku)
    recorded_at = timezone.now()
    WorkOrderItem.objects.create(
        work_order=work_order,
        kind=WorkOrderItem.Kind.OUTPUT,
        item_ref=recipe.output_sku,
        quantity=1,
        recorded_at=recorded_at,
        batch_ref="UNIQUE-GRADE",
        quality_grade_ref="standard",
    )
    WorkOrderItem.objects.create(
        work_order=work_order,
        kind=WorkOrderItem.Kind.OUTPUT,
        item_ref=recipe.output_sku,
        quantity=1,
        recorded_at=recorded_at,
        batch_ref="AMBIGUOUS-GRADE",
        quality_grade_ref="standard",
    )
    WorkOrderItem.objects.create(
        work_order=work_order,
        kind=WorkOrderItem.Kind.OUTPUT,
        item_ref=recipe.output_sku,
        quantity=1,
        recorded_at=recorded_at,
        batch_ref="AMBIGUOUS-GRADE",
        quality_grade_ref="minimal",
    )

    migration = import_module("shopman.shop.migrations.0039_backfill_batch_quality_grade_ref")
    migration.forwards(apps, None)

    assert Batch.objects.get(ref="UNIQUE-GRADE").quality_grade_ref == "standard"
    assert Batch.objects.get(ref="AMBIGUOUS-GRADE").quality_grade_ref == ""
