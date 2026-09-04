"""Esquece o cache de regras que a 0031 deixou para trás.

A 0031 ligou `suggestion.substitute` com `.update()` — que não dispara
`post_save` e portanto não invalida o cache do motor de regras. Num deployment
com pod vivo (cache do Redis quente, TTL de 1 hora), o banco passou a ter a
regra ligada e `get_rule_params` continuou respondendo o estado anterior: a
fronteira de sabor do substituto ficou inerte, sem nada no log.

Foi observado no alpha em 04/09/2026 — Madeleine (doce) aceitando Croque
Monsieur (salgado) como substituto.

Esta migração só apaga a chave. É idempotente e não toca em dado nenhum.
"""

from django.db import migrations


def forget(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    forget_rules_cache()


class Migration(migrations.Migration):
    dependencies = [("shop", "0031_enable_substitute_rule")]

    operations = [migrations.RunPython(forget, migrations.RunPython.noop)]
