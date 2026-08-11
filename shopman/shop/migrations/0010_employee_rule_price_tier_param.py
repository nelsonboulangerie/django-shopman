"""O parâmetro `group` da regra de funcionário virou `price_tier`.

⚠️ Sem esta migração o rename ficaria pela metade num banco EXISTENTE, e do pior jeito
possível: em silêncio. A `RuleConfig` guarda os parâmetros em JSON, o engine instancia a
regra com `cls(**rule_config.params)` (`rules/engine.py:143`), e um parâmetro que a classe
não conhece mais levanta `TypeError`. Aí o `_safe_load` (`engine.py:227`) engole a exceção
como WARNING e **a regra simplesmente não carrega** — o desconto de funcionário para de
existir, ninguém é avisado, e a única pista fica num log que ninguém lê.

Descoberto rodando o `seed` num banco local que já tinha a linha antiga:

    WARNING rules.engine: Failed to load rule employee_discount
    TypeError: EmployeeRule.__init__() got an unexpected keyword argument 'group'

Renomear a chave nos dados é o que faz o rename ser completo. O reverso existe porque
migração de dados que não volta transforma rollback em perda.
"""

from django.db import migrations


def _rename_key(apps, schema_editor, *, old: str, new: str) -> None:
    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(rule_path__endswith="EmployeeRule"):
        params = rule.params or {}
        if old not in params:
            continue
        params[new] = params.pop(old)
        rule.params = params
        rule.save(update_fields=["params"])


def forwards(apps, schema_editor):
    _rename_key(apps, schema_editor, old="group", new="price_tier")


def backwards(apps, schema_editor):
    _rename_key(apps, schema_editor, old="price_tier", new="group")


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0009_campaign_audience_match"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
