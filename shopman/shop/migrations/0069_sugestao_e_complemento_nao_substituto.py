"""`suggestion.complement` aprende que adicional é complemento, não substituto.

A sacola com Croque Madame recebeu Croque Monsieur (dono, 23/09). A regra passa
a declarar ``distinct_from_cart`` (natureza + sabor iguais = mesmo papel na
mesa) e ganha o espelho de "doce pede café": quem leva a bebida ganha o doce.

⚠️ Mesma cautela da 0031: se o gestor não mexeu na regra (params idênticos aos
da 0030), ela vira os defaults novos inteiros. Se mexeu, os pareamentos são
decisão dele e o deploy não os toca — só acrescenta ``distinct_from_cart``
quando a chave falta, porque ela é portão (a definição de complemento), não
preferência de pareamento.
"""

import copy

from django.db import migrations

# Cópias congeladas — migração representa um momento do banco.
PARAMS_0030 = {
    "pairings": [
        {
            "when": {"attr": "natureza", "value": "comida"},
            "suggest": {"attr": "natureza", "in": ["acompanhamento", "bebida"]},
            "weight": 3,
        },
        {
            "when": {"attr": "sabor", "value": "doce"},
            "suggest": {"tag": "café"},
            "weight": 2,
        },
        {
            "when": {"attr": "temperatura", "value": "quente"},
            "suggest": {"attr": "temperatura", "value": "gelado"},
            "weight": 2,
        },
    ],
    "affinity_weight": 3,
    "price": "below_cart_average",
    "per_surface": {"web": 1, "concierge": 1},
}

DRINK_PAIRING = {
    "when": {"attr": "natureza", "value": "bebida"},
    "suggest": {"attr": "sabor", "value": "doce"},
    "weight": 2,
}

DISTINCT_FROM_CART = ["natureza", "sabor"]

PARAMS_0069 = {
    "pairings": [*copy.deepcopy(PARAMS_0030["pairings"]), DRINK_PAIRING],
    "affinity_weight": 3,
    "distinct_from_cart": DISTINCT_FROM_CART,
    "price": "below_cart_average",
    "per_surface": {"web": 1, "concierge": 1},
}


def forward(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(ref="suggestion.complement"):
        params = rule.params or {}
        if params == PARAMS_0030:
            rule.params = copy.deepcopy(PARAMS_0069)
        elif "distinct_from_cart" not in params:
            rule.params = {**params, "distinct_from_cart": list(DISTINCT_FROM_CART)}
        else:
            continue
        rule.save(update_fields=["params"])
    forget_rules_cache()


def backward(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    RuleConfig.objects.filter(
        ref="suggestion.complement", params=PARAMS_0069,
    ).update(params=PARAMS_0030)
    forget_rules_cache()


class Migration(migrations.Migration):
    dependencies = [("shop", "0068_lapides_de_23_09")]

    operations = [migrations.RunPython(forward, backward)]
