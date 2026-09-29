"""Pão para levar pede mercearia, e em refeição o doce vem antes (dono, 24/09).

"Pão <> Antepasto/Queijo/Manteiga, Croissant/Brioche <> Geleia ... Deve haver
outros tipos de combinações válidas e criativas!" e "adicione kuropan com
manteiga e/ou geleia, combinação clássica também." Os pares entram como
pareamentos de peso 2 (bônus, nos dois sentidos quando faz sentido); a sacola
só de pão ganha o pote como complemento principal; em refeição (comida +
bebida) o doce pesa 3 e passa na frente.

⚠️ Mesma cautela das anteriores: a regra só muda se ainda for a da 0071. Se o
gestor mexeu, a regra é dele — aqui só há pareamento, que é preferência.
"""

import copy

from django.db import migrations

# Cópias congeladas — migração representa um momento do banco.
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

PARAMS_0072 = {
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
            "weight": 3,
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
            "when_absent": [
                {"attr": "natureza", "value": "bebida"},
                {"attr": "sabor", "value": "doce"},
                {"attr": "sabor", "value": "salgado"},
            ],
            "suggest": {"attr": "natureza", "value": "acompanhamento"},
            "weight": 3,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"collection": "rusticos"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "queijo"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"collection": "rusticos"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "pate"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"collection": "rusticos"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "tapenade"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"collection": "rusticos"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "picles"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"collection": "rusticos"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "manteiga"}],
            "weight": 2,
        },
        {
            "when": {"tag": "focaccia"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "tapenade"}],
            "weight": 2,
        },
        {
            "when": {"tag": "focaccia"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "azeite"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "italiano"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "tapenade"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "italiano"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "azeite"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "campagne"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "camembert"}],
            "weight": 2,
        },
        {
            "when": {"tag": "croissant"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}],
            "weight": 2,
        },
        {
            "when": {"tag": "croissant"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "mel"}],
            "weight": 2,
        },
        {
            "when": {"tag": "croissant"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "manteiga"}],
            "weight": 2,
        },
        {
            "when": {"tag": "brioche"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}],
            "weight": 2,
        },
        {
            "when": {"tag": "brioche"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "doce-de-leite"}],
            "weight": 2,
        },
        {
            "when": {"tag": "brioche"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "mel"}],
            "weight": 2,
        },
        {
            "when": {"tag": "rabanada"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "mel"}],
            "weight": 2,
        },
        {
            "when": {"tag": "rabanada"},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "doce-de-leite"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "shokupan"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "manteiga"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "shokupan"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "kuropan"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "manteiga"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "kuropan"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "hotdog"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "mostarda"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "hamburger"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "mostarda"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "hamburger"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "picles"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "hamburger"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "queijo"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "sabor", "value": "neutro"}, {"tag": "hamburger"}]},
            "when_absent": [{"attr": "natureza", "value": "bebida"}],
            "suggest": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "bacon"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "queijo"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"collection": "rusticos"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "pate"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"collection": "rusticos"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "tapenade"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "focaccia"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "tapenade"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "italiano"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "croissant"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "brioche"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "shokupan"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "geleia"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "kuropan"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "manteiga"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "shokupan"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "manteiga"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "kuropan"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "manteiga"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"collection": "rusticos"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "mostarda"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "hotdog"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "mostarda"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "hamburger"}],
            "weight": 2,
        },
        {
            "when": {"all": [{"attr": "natureza", "value": "acompanhamento"}, {"tag": "picles"}]},
            "suggest": [{"attr": "natureza", "value": "comida"}, {"tag": "hamburger"}],
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
        if rule.params == PARAMS_0071:
            rule.params = copy.deepcopy(PARAMS_0072)
            rule.save(update_fields=["params"])
    forget_rules_cache()


def backward(apps, schema_editor):
    from shopman.shop.rules.engine import forget_rules_cache

    RuleConfig = apps.get_model("shop", "RuleConfig")
    for rule in RuleConfig.objects.filter(ref="suggestion.complement"):
        if rule.params == PARAMS_0072:
            rule.params = copy.deepcopy(PARAMS_0071)
            rule.save(update_fields=["params"])
    forget_rules_cache()


class Migration(migrations.Migration):
    dependencies = [("shop", "0071_doce_e_bebida_pede_salgado")]

    operations = [migrations.RunPython(forward, backward)]
