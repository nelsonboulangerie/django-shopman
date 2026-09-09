"""Backfill the lot-owned quality grade from immutable production outputs.

Only blank lot grades are filled. Batches without an unambiguous
``WorkOrderItem.batch_ref`` remain blank and therefore fail closed in channels
whose policy accepts only explicit full-quality grades.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Batch = apps.get_model("stockman", "Batch")
    WorkOrderItem = apps.get_model("craftsman", "WorkOrderItem")

    outputs = (
        WorkOrderItem.objects.filter(kind="output")
        .exclude(batch_ref="")
        .exclude(quality_grade_ref="")
        .values_list("batch_ref", "quality_grade_ref")
    )
    grades_by_batch = {}
    for batch_ref, grade_ref in outputs.iterator():
        grades_by_batch.setdefault(batch_ref, set()).add(grade_ref)
    for batch_ref, grade_refs in grades_by_batch.items():
        if len(grade_refs) != 1:
            continue
        Batch.objects.filter(ref=batch_ref, quality_grade_ref="").update(
            quality_grade_ref=next(iter(grade_refs)),
        )


def backwards(apps, schema_editor):
    Batch = apps.get_model("stockman", "Batch")
    WorkOrderItem = apps.get_model("craftsman", "WorkOrderItem")

    outputs = (
        WorkOrderItem.objects.filter(kind="output")
        .exclude(batch_ref="")
        .exclude(quality_grade_ref="")
        .values_list("batch_ref", "quality_grade_ref")
    )
    grades_by_batch = {}
    for batch_ref, grade_ref in outputs.iterator():
        grades_by_batch.setdefault(batch_ref, set()).add(grade_ref)
    for batch_ref, grade_refs in grades_by_batch.items():
        if len(grade_refs) != 1:
            continue
        grade_ref = next(iter(grade_refs))
        Batch.objects.filter(
            ref=batch_ref,
            quality_grade_ref=grade_ref,
        ).update(quality_grade_ref="")


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0038_qualitygrade_is_active"),
        ("stockman", "0003_batch_quality_grade_ref"),
        ("craftsman", "0008_alter_workorderevent_kind"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
