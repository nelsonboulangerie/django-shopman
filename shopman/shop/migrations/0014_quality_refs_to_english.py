# Rename dos graus pt→en nos DADOS (ADR-017 §Migração passo 3).
#
# regular→fair (o degrau MENOS punitivo, para não aprofundar desconto
# retroativo), bom→standard, excelente→excellent. Cobre WorkOrder.meta
# ["quality"] (craftsman) e Campaign.trigger_filter["quality_min"] (shop).
#
# A janela é agora: go-live-v1 não existe, então o rename é barato (ADR-015 só
# entra em vigor na tag). Depois do alpha, o mesmo rename exigiria
# expand-contract com janela de alias.

from django.db import migrations

FORWARD = {"regular": "fair", "bom": "standard", "excelente": "excellent"}
BACKWARD = {v: k for k, v in FORWARD.items()}


def _remap(apps, mapping):
    WorkOrder = apps.get_model("craftsman", "WorkOrder")
    Campaign = apps.get_model("shop", "Campaign")

    for wo in WorkOrder.objects.exclude(meta__quality__isnull=True).only("pk", "meta"):
        quality = (wo.meta or {}).get("quality")
        if quality in mapping:
            wo.meta = {**wo.meta, "quality": mapping[quality]}
            wo.save(update_fields=["meta"])

    for campaign in Campaign.objects.exclude(trigger_filter={}).only("pk", "trigger_filter"):
        quality_min = (campaign.trigger_filter or {}).get("quality_min")
        if quality_min in mapping:
            campaign.trigger_filter = {**campaign.trigger_filter, "quality_min": mapping[quality_min]}
            campaign.save(update_fields=["trigger_filter"])


def forwards(apps, schema_editor):
    _remap(apps, FORWARD)


def backwards(apps, schema_editor):
    _remap(apps, BACKWARD)


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0013_quality_catalog_seed"),
        ("craftsman", "0002_workorderitem_batch_ref_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
