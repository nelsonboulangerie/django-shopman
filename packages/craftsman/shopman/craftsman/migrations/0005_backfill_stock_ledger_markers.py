"""Carimba as fornadas JÁ concluídas como tendo fechado o ledger.

Os marcadores ``stock_consumed_at``/``stock_realized_at`` nascem agora; toda
WorkOrder ``finished`` anterior a esta migração está sem eles. Sem este
backfill, o primeiro ciclo do ``sweep_unrealized_production`` leria o histórico
inteiro como "não realizado" e re-executaria as duas pernas de cada fornada: o
insumo baixaria de novo e a vitrine seria creditada EM DOBRO — o handler não é
idempotente, o marcador é que é o guarda.

Assumir "realizado" é a escolha segura e é honesta sobre o que se sabe: uma
fornada antiga que de fato tenha ficado com drift não é recuperável por
re-execução cega (não dá para distinguir dela mesma bem realizada), e o
prejuízo de creditar duas vezes é maior que o de não corrigir uma divergência
histórica. Daqui pra frente o marcador é escrito na hora, e o sweeper só
enxerga o que nasceu com ele.

O carimbo usa o ``finished_at`` da própria ordem, para não fingir que o ledger
fechou no dia da migração.
"""

from django.db import migrations

STOCK_CONSUMED_KEY = "stock_consumed_at"
STOCK_REALIZED_KEY = "stock_realized_at"
BATCH_SIZE = 500


def stamp_finished_work_orders(apps, schema_editor):
    WorkOrder = apps.get_model("craftsman", "WorkOrder")

    pending = []
    queryset = WorkOrder.objects.filter(status="finished").only(
        "pk", "meta", "finished_at", "updated_at"
    )
    for work_order in queryset.iterator(chunk_size=BATCH_SIZE):
        meta = dict(work_order.meta or {})
        if meta.get(STOCK_CONSUMED_KEY) and meta.get(STOCK_REALIZED_KEY):
            continue
        stamp = work_order.finished_at or work_order.updated_at
        stamp_value = stamp.isoformat() if stamp else ""
        meta.setdefault(STOCK_CONSUMED_KEY, stamp_value)
        meta.setdefault(STOCK_REALIZED_KEY, stamp_value)
        work_order.meta = meta
        pending.append(work_order)
        if len(pending) >= BATCH_SIZE:
            WorkOrder.objects.bulk_update(pending, ["meta"])
            pending = []
    if pending:
        WorkOrder.objects.bulk_update(pending, ["meta"])


def drop_markers(apps, schema_editor):
    WorkOrder = apps.get_model("craftsman", "WorkOrder")

    pending = []
    queryset = WorkOrder.objects.filter(status="finished").only("pk", "meta")
    for work_order in queryset.iterator(chunk_size=BATCH_SIZE):
        meta = dict(work_order.meta or {})
        if not (meta.pop(STOCK_CONSUMED_KEY, None) or meta.pop(STOCK_REALIZED_KEY, None)):
            continue
        work_order.meta = meta
        pending.append(work_order)
        if len(pending) >= BATCH_SIZE:
            WorkOrder.objects.bulk_update(pending, ["meta"])
            pending = []
    if pending:
        WorkOrder.objects.bulk_update(pending, ["meta"])


class Migration(migrations.Migration):

    dependencies = [
        ("craftsman", "0004_alter_recipe_ref_alter_recipeitem_input_sku_and_more"),
    ]

    operations = [
        migrations.RunPython(stamp_finished_work_orders, drop_markers),
    ]
