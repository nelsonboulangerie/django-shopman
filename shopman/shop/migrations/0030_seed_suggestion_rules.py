"""As duas regras de sugestão, com os defaults que o dono ditou em 04/09.

Vai em migração pelo mesmo motivo das definições de atributo (0028): o alpha
está no ar, reseedar é decisão do dono, e o deploy não pode depender disso.

⚠️ Sem estas linhas o motor roda **só** com co-ocorrência — que é o contrato
("regra em branco não quebra nada") e não um defeito, mas numa base sem
histórico de cestas ainda ele não sugere nada. Os pareamentos são o que faz um
produto novo, sem uma única venda, poder ser oferecido.

O que NÃO é seedado, de propósito:

- ``context`` (ex.: não sugerir gelado numa entrega). O plano trazia isso como
  *exemplo* de esquema, não como política da casa — e recusar sorvete na entrega
  é decisão de negócio do dono, não default de deploy.
- ``suggestion.substitute`` fica ``enabled=False``: o motor de substituto é da
  F2. Cadastrada e desligada, o gestor já vê a política e a validação já recusa
  erro de digitação, sem que nada leia a regra ainda.
"""

from django.db import migrations

COMPLEMENT_PARAMS = {
    "pairings": [
        # "comida → acompanhamento" genérico, em vez de manteiga/geleia por SKU
        # (resposta do dono, 04/09).
        {
            "when": {"attr": "natureza", "value": "comida"},
            "suggest": {"attr": "natureza", "in": ["acompanhamento", "bebida"]},
            "weight": 3,
        },
        # Doce pede café. A palavra-chave já existe no catálogo e é mais precisa
        # que "bebida quente": chá quente não é o que se oferece com madeleine.
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

SUBSTITUTE_PARAMS = {
    "must_match": ["sabor"],          # doce → doce, salgado → salgado é fronteira
    "prefer": ["collection"],          # dentro da coleção primeiro
    "approximate": ["peso_unidade_g"],  # o mais próximo ganha, sem faixa
    "price_band": 0.30,
    "cross_collection_when_empty": True,
}

RULES = [
    {
        "ref": "suggestion.complement",
        "label": "Sugestão de adicional",
        "rule_path": "shopman.shop.rules.suggestion.ComplementRule",
        "params": COMPLEMENT_PARAMS,
        "enabled": True,
        "priority": 100,
    },
    {
        "ref": "suggestion.substitute",
        "label": "Sugestão de substituto",
        "rule_path": "shopman.shop.rules.suggestion.SubstituteRule",
        "params": SUBSTITUTE_PARAMS,
        "enabled": False,
        "priority": 101,
    },
]


def create_rules(apps, schema_editor):
    RuleConfig = apps.get_model("shop", "RuleConfig")
    for spec in RULES:
        # `get_or_create`: se o gestor já ajustou os pesos, o deploy seguinte
        # não desfaz o ajuste dele.
        RuleConfig.objects.get_or_create(
            ref=spec["ref"],
            defaults={k: v for k, v in spec.items() if k != "ref"},
        )


def drop_rules(apps, schema_editor):
    RuleConfig = apps.get_model("shop", "RuleConfig")
    RuleConfig.objects.filter(ref__in=[s["ref"] for s in RULES]).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0029_product_affinity")]

    operations = [migrations.RunPython(create_rules, drop_rules)]
