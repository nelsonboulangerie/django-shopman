"""A quebra de caixa passa a ser apurada por GAVETA, não por operador.

Consequência da custódia virar do terminal (cashman 0005): várias pessoas
trabalham dentro do mesmo turno, e a nota que sumiu não deixa lançamento. Somar
a quebra "de fulano" quando três passaram pela gaveta seria inventar um culpado.
O nome volta a aparecer quando o livro prova que uma pessoa lançou sozinha.

A regra existente é MIGRADA, não recriada: quem já configurou régua e janela no
Admin não perde a configuração — só o eixo da apuração muda. Sem isto, a regra
ficaria com uma métrica que o dispatcher não conhece mais e pararia de ler em
silêncio, que é exatamente o modo de falha que esta mudança existe para evitar.
"""

from django.db import migrations, models

ANTIGA = "cash_variance_by_operator"
NOVA = "cash_variance_by_drawer"


def para_gaveta(apps, schema_editor):
    apps.get_model("backstage", "BIAlertRule").objects.filter(metric=ANTIGA).update(metric=NOVA)


def para_operador(apps, schema_editor):
    apps.get_model("backstage", "BIAlertRule").objects.filter(metric=NOVA).update(metric=ANTIGA)


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0033_alert_cash_sale_after_shift_close"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bialertrule",
            name="metric",
            field=models.CharField(
                choices=[
                    ("import_silence", "Importação esperada não chegou"),
                    ("daily_revenue_vs_baseline", "Faturamento do dia abaixo do esperado"),
                    ("native_overrides_history", "Pedido nativo apagou histórico"),
                    ("cash_variance_by_drawer", "Quebra de caixa acumulada por gaveta"),
                    ("curation_pending", "De-para de produto pendente"),
                ],
                max_length=32,
                verbose_name="métrica",
            ),
        ),
        migrations.RunPython(para_gaveta, para_operador),
    ]
