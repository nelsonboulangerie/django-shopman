"""Doce + bebida pede um SALGADO leve, não só o pão (dono, 24/09).

"Bebida quente <> doce, bebida gelada <> salgado são bidirecionais e não
excluem outras sugestões, desde que tenham outro fator preponderante." Com doce
e bebida na mesa, o fator preponderante é completá-la: 1º o salgado (o leve
ganha do prato quente; com bebida gelada, ganha mais), 2º o pão para levar.

⚠️ Mesma cautela das anteriores: a regra só muda se ainda for a da 0070. Se o
gestor mexeu, a regra é dele — aqui não há portão novo a acrescentar, só
pareamento, e pareamento é preferência da casa.
"""

import copy

from django.db import migrations

# Cópias congeladas — migração representa um momento do banco.
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

PARAMS_0071 = {
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
            "suggest": {"attr": "sabor", "value": "salgado"},
            "weight": 3,
        },
        {
            "when": [{"attr": "sabor", "value": "doce"}, {"attr": "natureza", "value": "bebida"}],
            "when_absent": [{"attr": "sabor", "value": "salgado"}],
            "suggest": [{"attr": "sabor", "value": "salgado"}, {"attr": "temperatura", "value": "ambiente"}],
            "weight": 1,
        },
        {
            "when": [{"attr": "sabor", "value": "doce"}, {"attr": "temperatura", "value": "gelado"}],
            "when_absent": [{"attr": "sabor", "value": "salgado"}],
            "suggest": {"attr": "sabor", "value": "salgado"},
            "weight": 2,
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


def forward(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(ref="suggestion.complement"):
        if rule.params == PARAMS_0070:
            rule.params = copy.deepcopy(PARAMS_0071)
            rule.save(update_fields=["params"])
    forget_rules_cache()


def backward(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(ref="suggestion.complement"):
        if rule.params == PARAMS_0071:
            rule.params = copy.deepcopy(PARAMS_0070)
            rule.save(update_fields=["params"])
    forget_rules_cache()


class Migration(migrations.Migration):
    dependencies = [("shop", "0070_sugestao_criterios_do_dono")]

    operations = [migrations.RunPython(forward, backward)]
