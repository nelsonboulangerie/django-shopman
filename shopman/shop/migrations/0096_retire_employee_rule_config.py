"""Aposenta a RuleConfig da antiga regra de funcionário (EmployeeRule).

A EmployeeRule saiu do código (o benefício virou o grupo Equipe), mas num banco
EXISTENTE a linha employee_discount continua apontando para uma classe que não
existe mais. O _safe_load engole o ImportError como WARNING e a regra aparece
quebrada no rules.load do release-readiness e na coluna "carrega?" do Admin. O
seed só resolve banco novo; o dado velho morre aqui, como no rename da 0010.

O reverso é noop: a regra não existe mais no código, e recriar a configuração
apontaria de novo para uma classe inexistente.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    RuleConfig = apps.get_model("shop", "RuleConfig")
    RuleConfig.objects.filter(rule_path__endswith="EmployeeRule").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0095_pix_vencido_um_aviso_so"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
