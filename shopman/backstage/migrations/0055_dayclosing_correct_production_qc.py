from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("backstage", "0054_resolve_historical_production_low_yield")]

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
                    ("quick_finish_production", "Pode concluir produção sem ordem previamente iniciada"),
                    ("override_production_shortage", "Pode forçar produção apesar de falta ou compromisso"),
                    ("correct_production_qc", "Pode corrigir a qualidade de uma fornada concluída"),
                    ("void_production", "Pode estornar uma ordem de produção"),
                    ("reveal_production_blind_map", "Pode revelar o mapa cego da pesagem"),
                    ("operate_purchase", "Pode operar compras e recebimento de insumos no app dedicado"),
                    ("audit_stock", "Pode auditar e ajustar o estoque de insumos (contagem no Compras)"),
                    ("view_bi", "Pode ver o B.I. (leitura analítica cross-suite)"),
                    ("export_backup", "Pode baixar o backup de dados curados"),
                ],
                "verbose_name": "fechamento do dia",
                "verbose_name_plural": "fechamentos do dia",
            },
        ),
    ]
