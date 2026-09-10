from django.db import migrations

FORWARD_LABELS = {
    "excellent": "Ótimo",
    "minimal": "Mínimo",
}

REVERSE_LABELS = {
    "excellent": "Ótima",
    "minimal": "Mínima",
}


def update_labels(apps, schema_editor, labels):
    QualityGrade = apps.get_model("shop", "QualityGrade")
    for ref, label in labels.items():
        QualityGrade.objects.filter(ref=ref).update(label=label)


def forwards(apps, schema_editor):
    update_labels(apps, schema_editor, FORWARD_LABELS)


def backwards(apps, schema_editor):
    update_labels(apps, schema_editor, REVERSE_LABELS)


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0039_backfill_batch_quality_grade_ref"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
