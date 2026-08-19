# A camada de ingestão do B.I. ganha memória de lote (BI-DATA-FOUNDATION-PLAN, P0).
#
# Três passos, na ordem, porque a FK nasce obrigatória:
#   1. cria `ImportBatch` e pendura `HistoricalSale.batch` NULA;
#   2. para cada `source` que já tem vendas sem lote, cria UM lote "legado"
#      (sem arquivo, sem hash — a proveniência anterior ao controle não é
#      inventada, é declarada como desconhecida) e aponta as vendas para ele;
#   3. torna a FK obrigatória.
# Em banco zerado o passo 2 não faz nada e os três passam em sequência.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

LEGACY_NOTE = "anterior ao controle de lote: arquivo e hash desconhecidos"


def _legacy_batches(apps, schema_editor):
    HistoricalSale = apps.get_model("backstage", "HistoricalSale")
    ImportBatch = apps.get_model("backstage", "ImportBatch")
    # ⚠️ `.order_by()` limpando o ordering do Meta é OBRIGATÓRIO antes do
    # `.distinct()`: o Django acrescenta as colunas do ORDER BY ao SELECT e, com
    # `ordering = ["-occurred_at"]`, o DISTINCT passaria a ser sobre (source,
    # occurred_at) — 81 mil "fontes" em vez de duas, e o laço abaixo faria 81 mil
    # INSERTs e UPDATEs da tabela inteira (foi o que prendeu o staging por uma
    # hora em 19/08/2026). Materializado em lista: duas fontes, um laço.
    orphan_sources = list(
        HistoricalSale.objects.filter(batch__isnull=True)
        .order_by()
        .values_list("source", flat=True)
        .distinct()
    )
    for source in orphan_sources:
        rows = HistoricalSale.objects.filter(batch__isnull=True, source=source)
        batch = ImportBatch.objects.create(
            source=source,
            status="done",
            sales_created=rows.count(),
            notes=LEGACY_NOTE,
        )
        rows.update(batch=batch)


def _unlink_legacy_batches(apps, schema_editor):
    HistoricalSale = apps.get_model("backstage", "HistoricalSale")
    ImportBatch = apps.get_model("backstage", "ImportBatch")
    legacy = ImportBatch.objects.filter(notes=LEGACY_NOTE)
    HistoricalSale.objects.filter(batch__in=legacy).update(batch=None)
    legacy.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('backstage', '0023_consumption_eat_in_weight'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalsale',
            name='metadata',
            field=models.JSONField(blank=True, default=dict, help_text='O que o export traz e nenhuma coluna guarda. Chaves em docs/reference/data-schemas.md.', verbose_name='metadados'),
        ),
        migrations.CreateModel(
            name='ImportBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(db_index=True, help_text='Mesmo valor carimbado nas linhas importadas (ex.: yooga).', max_length=16, verbose_name='origem')),
                ('file_name', models.CharField(blank=True, max_length=200, verbose_name='arquivo')),
                ('file_sha256', models.CharField(blank=True, help_text='Identidade do arquivo. O mesmo hash não entra duas vezes na mesma origem.', max_length=64, verbose_name='hash do arquivo (sha256)')),
                ('imported_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='importado em')),
                ('status', models.CharField(choices=[('done', 'concluído'), ('failed', 'falhou')], default='done', max_length=8, verbose_name='estado')),
                ('rows_read', models.PositiveIntegerField(default=0, verbose_name='linhas lidas')),
                ('sales_created', models.PositiveIntegerField(default=0, verbose_name='vendas novas')),
                ('sales_skipped', models.PositiveIntegerField(default=0, help_text='Chave natural já conhecida: a linha foi lida e não duplicou.', verbose_name='vendas já existentes')),
                ('sales_completed', models.PositiveIntegerField(default=0, help_text='Vendas que já existiam e ganharam dado que faltava (metadados).', verbose_name='vendas completadas')),
                ('items_created', models.PositiveIntegerField(default=0, verbose_name='itens novos')),
                ('error', models.TextField(blank=True, verbose_name='erro')),
                ('notes', models.CharField(blank=True, max_length=200, verbose_name='observação')),
                ('imported_by', models.ForeignKey(blank=True, help_text='Vazio quando veio de comando no console (sem sessão de usuário).', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='import_batches', to=settings.AUTH_USER_MODEL, verbose_name='importado por')),
            ],
            options={
                'verbose_name': 'lote de importação',
                'verbose_name_plural': 'lotes de importação',
                'ordering': ['-imported_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='importbatch',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'done'), models.Q(('file_sha256', ''), _negated=True)), fields=('source', 'file_sha256'), name='backstage_importbatch_source_sha_done'),
        ),
        migrations.AddField(
            model_name='historicalsale',
            name='batch',
            field=models.ForeignKey(help_text='A importação que trouxe esta venda.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='backstage.importbatch', verbose_name='lote'),
        ),
        migrations.RunPython(_legacy_batches, _unlink_legacy_batches),
        migrations.AlterField(
            model_name='historicalsale',
            name='batch',
            field=models.ForeignKey(help_text='A importação que trouxe esta venda.', on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='backstage.importbatch', verbose_name='lote'),
        ),
    ]
