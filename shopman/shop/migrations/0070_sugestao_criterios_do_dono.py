"""`suggestion.complement` passa a seguir os critérios do dono (23/09).

Em palavras dele: "a primeira frente de sugestão de complemento deve ser bebida
com comida e comida com bebida"; bebida quente + doce e bebida gelada + salgado
"são preferenciais, mas não devem excluir cruzamentos diferentes"; "bebida com
bebida acho que não"; "se já tem salgado e já tem bebida, oferece um doce".

⚠️ Mesma cautela da 0031 e da 0069: a regra só vira a nova inteira se ainda for
uma das que o deploy escreveu (0030 ou 0069). Se o gestor mexeu, os pareamentos
são decisão dele e ficam; o deploy só acrescenta o portão ``one_per_cart``
("bebida com bebida, não") quando a chave falta — portão é definição, não
preferência.
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
        {"when": {"attr": "sabor", "value": "doce"}, "suggest": {"tag": "café"}, "weight": 2},
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

PARAMS_0069 = {
    "pairings": [*copy.deepcopy(PARAMS_0030["pairings"]), DRINK_PAIRING],
    "affinity_weight": 3,
    "distinct_from_cart": ["natureza", "sabor"],
    "price": "below_cart_average",
    "per_surface": {"web": 1, "concierge": 1},
}

PARAMS_0070 = {
    "pairings": [
        {
            "when": {"attr": "natureza", "value": "comida"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": {"attr": "natureza", "value": "bebida"},
            "weight": 3,
        },
        {
            "when": {"attr": "sabor", "value": "salgado"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "bebida"}, {"attr": "temperatura", "value": "gelado"}],
            "weight": 2,
        },
        {
            "when": {"attr": "sabor", "value": "doce"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "bebida"}, {"attr": "temperatura", "value": "quente"}],
            "weight": 2,
        },
        {
            "when": {"attr": "temperatura", "value": "ambiente"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "bebida"}, {"attr": "temperatura", "value": "quente"}],
            "weight": 1,
        },
        {
            "when": {"attr": "natureza", "value": "bebida"},
            "when_absent": [{"attr": "natureza", "value": "comida"}],
            "suggest": {"attr": "natureza", "value": "comida"},
            "weight": 3,
        },
        {
            "when": {"attr": "temperatura", "value": "quente"},
            "when_absent": [{"attr": "natureza", "value": "comida"}],
            "suggest": {"attr": "sabor", "value": "doce"},
            "weight": 2,
        },
        {
            "when": {"attr": "temperatura", "value": "gelado"},
            "when_absent": [{"attr": "natureza", "value": "comida"}],
            "suggest": {"attr": "sabor", "value": "salgado"},
            "weight": 2,
        },
        {
            "when": [{"attr": "sabor", "value": "salgado"}, {"attr": "natureza", "value": "bebida"}],
            "suggest": {"attr": "sabor", "value": "doce"},
            "weight": 3,
        },
        {
            "when": [{"attr": "natureza", "value": "comida"}, {"attr": "natureza", "value": "bebida"}],
            "suggest": {"attr": "sabor", "value": "doce"},
            "weight": 1,
        },
        {
            "when": [{"attr": "sabor", "value": "doce"}, {"attr": "natureza", "value": "bebida"}],
            "when_absent": [{"attr": "sabor", "value": "salgado"}],
            "suggest": [{"attr": "sabor", "value": "neutro"}, {"tag": "pao"}],
            "weight": 1,
        },
        {
            "when": {"attr": "sabor", "value": "neutro"},
            "suggest": {"attr": "natureza", "value": "acompanhamento"},
            "weight": 2,
        },
        {"when": {"attr": "sabor", "value": "salgado"}, "suggest": {"attr": "sabor", "value": "doce"}, "weight": 1},
    ],
    "affinity_weight": 3,
    "distinct_from_cart": ["natureza", "sabor"],
    "one_per_cart": [{"attr": "natureza", "value": "bebida"}],
    "price": "below_cart_average",
    "per_surface": {"web": 1, "concierge": 1},
}

ONE_PER_CART = [{"attr": "natureza", "value": "bebida"}]


def forward(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(ref="suggestion.complement"):
        params = rule.params or {}
        if params in (PARAMS_0030, PARAMS_0069):
            rule.params = copy.deepcopy(PARAMS_0070)
        elif "one_per_cart" not in params:
            rule.params = {**params, "one_per_cart": copy.deepcopy(ONE_PER_CART)}
        else:
            continue
        rule.save(update_fields=["params"])
    forget_rules_cache()


def backward(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(ref="suggestion.complement"):
        if rule.params == PARAMS_0070:
            rule.params = copy.deepcopy(PARAMS_0069)
            rule.save(update_fields=["params"])
    forget_rules_cache()


class Migration(migrations.Migration):
    dependencies = [("shop", "0069_sugestao_e_complemento_nao_substituto")]

    operations = [migrations.RunPython(forward, backward)]
