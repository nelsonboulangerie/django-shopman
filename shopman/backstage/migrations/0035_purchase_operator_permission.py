from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0034_cash_variance_by_drawer"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="dayclosing",
            options={
                "ordering": ["-date"],
                "permissions": [
                    ("perform_closing", "Pode executar fechamento do dia"),
                    ("view_production_reports", "Pode ver relatórios de produção"),
                    ("view_dayclosing_management", "Pode ver agregados gerenciais do fechamento"),
                    ("operate_production", "Pode operar a produção (chão + planejamento) no app dedicado"),
                    ("operate_purchase", "Pode operar compras e recebimento de insumos no app dedicado"),
                    ("view_bi", "Pode ver o B.I. (leitura analítica cross-suite)"),
                ],
                "verbose_name": "fechamento do dia",
                "verbose_name_plural": "fechamentos do dia",
            },
        ),
    ]
