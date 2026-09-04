"""Liga `suggestion.substitute`: a F2 chegou, e agora alguém lê a regra.

A 0030 cadastrou a regra DESLIGADA de propósito — o gestor já via a política e a
validação já recusava erro de digitação, mas nada a consumia ainda. Com o
`shop/services/substitutes.find` passando a aplicar `must_match`, deixá-la
desligada seria cadastrar uma fronteira que a casa declarou e o sistema ignora.

⚠️ Liga **só se ninguém tiver mexido**. Se o gestor já ligou, não há o que
fazer; se ele mexeu nos params, a decisão passou a ser dele e um deploy não a
desfaz — o `filter(params=...)` é o que garante isso.
"""

from django.db import migrations

# Cópia congelada dos params da 0030 — migração representa um momento do banco,
# e não pode mudar de sentido quando as constantes vivas mudarem.
SEEDED_PARAMS = {
    "must_match": ["sabor"],
    "prefer": ["collection"],
    "approximate": ["peso_unidade_g"],
    "price_band": 0.30,
    "cross_collection_when_empty": True,
}


def enable(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    RuleConfig.objects.filter(
        ref="suggestion.substitute", enabled=False, params=SEEDED_PARAMS,
    ).update(enabled=True)
    # `.update()` não dispara post_save, então o cache do motor de regras não se
    # invalida sozinho — e o banco e o Redis divergem por uma hora, em silêncio.
    forget_rules_cache()


def disable(apps, schema_editor):
    RuleConfig = apps.get_model("shop", "RuleConfig")
    RuleConfig.objects.filter(
        ref="suggestion.substitute", enabled=True, params=SEEDED_PARAMS,
    ).update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [("shop", "0030_seed_suggestion_rules")]

    operations = [migrations.RunPython(enable, disable)]
