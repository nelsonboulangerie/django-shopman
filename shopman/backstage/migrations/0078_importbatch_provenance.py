from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0077_baixa_do_ticket_por_porta"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="importbatch",
            name="backstage_importbatch_source_sha_done",
        ),
        migrations.AddField(
            model_name="importbatch",
            name="artifact_ref",
            field=models.CharField(
                blank=True,
                help_text="Referência segura na landing; nunca caminho pessoal, URL assinada ou segredo.",
                max_length=200,
                verbose_name="referência opaca do artefato",
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="counts",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Somente agregados sanitizados; PII e amostras de linha são proibidas.",
                verbose_name="contagens genéricas",
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="finished_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="finalizado em"),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="mode",
            field=models.CharField(
                choices=[("dry_run", "simulação"), ("apply", "aplicação")],
                default="apply",
                max_length=8,
                verbose_name="modo",
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="parser_version",
            field=models.CharField(blank=True, max_length=64, verbose_name="versão do parser"),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="purpose",
            field=models.CharField(
                blank=True,
                help_text="Destino permitido do lote (ex.: historical_sales); não é inferido pela origem.",
                max_length=64,
                verbose_name="finalidade",
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="report_ref",
            field=models.CharField(
                blank=True,
                help_text="Referência opaca do relatório sanitizado, sem caminho pessoal ou URL assinada.",
                max_length=200,
                verbose_name="referência do relatório",
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="schema_version",
            field=models.CharField(blank=True, max_length=64, verbose_name="versão do schema"),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="iniciado em"),
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "done"), models.Q(("file_sha256", ""), _negated=True)),
                fields=("source", "file_sha256", "purpose", "parser_version"),
                name="backstage_importbatch_identity_done",
            ),
        ),
    ]
