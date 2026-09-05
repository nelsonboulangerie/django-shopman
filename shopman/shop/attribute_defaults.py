"""As definições de atributo com que esta casa nasce.

Vivem aqui, e não só nas migrações, porque **dado criado por migração não
sobrevive a um teste transacional** (o `TransactionTestCase` trunca as tabelas
no fim e não repõe o que a migração escreveu) nem a um `seed --flush`. A
migração cobre quem já está no ar; o seed cobre quem reconstrói do zero.

É a mesma razão pela qual `DEFAULT_COMPLEMENT_PARAMS` mora em
`shop/rules/suggestion.py` e não só na 0030 — e o teste de drift compara as
duas, para mudar uma sem a outra ficar vermelho.
"""

from __future__ import annotations

ALERGENOS_CANONICOS = [
    "glúten", "crustáceos", "ovos", "peixes", "amendoim", "soja", "leite",
    "castanhas", "amêndoa", "avelã", "castanha-de-caju", "castanha-do-brasil",
    "macadâmia", "nozes", "pecã", "pistache", "gergelim", "mostarda",
    "sulfitos", "látex natural",
]

DIETA_CANONICA = ["100% vegetal", "vegetariano", "sem glúten", "sem lactose"]


def _options(values):
    return [{"value": v, "label": v[:1].upper() + v[1:]} for v in values]


DEFAULT_DEFINITIONS = [
    {
        "ref": "alergenos", "label": "Alérgenos",
        "hint": "O que o produto CONTÉM. Sai no rótulo e no aviso de alergia da loja.",
        "type": "multi_choice", "options": _options(ALERGENOS_CANONICOS), "unit": "",
        "purposes": ["label", "facet"], "storage": "attributes",
        "required": False, "ordering": 10,
    },
    {
        "ref": "dieta", "label": "Dieta",
        "hint": "100% vegetal, vegetariano, sem glúten, sem lactose.",
        "type": "multi_choice", "options": _options(DIETA_CANONICA), "unit": "",
        "purposes": ["label", "facet"], "storage": "attributes",
        "required": False, "ordering": 20,
    },
    {
        "ref": "porcoes", "label": "Porções",
        "hint": "Como a porção é apresentada: “2 pessoas”, “6 fatias grossas”, “pote 170 g”.",
        "type": "text", "options": [], "unit": "",
        "purposes": ["label"], "storage": "attributes",
        "required": False, "ordering": 30,
    },
    {
        "ref": "peso_unidade_g", "label": "Peso por unidade",
        "hint": "Peso aproximado de uma unidade. É o que aproxima um substituto do outro.",
        "type": "number", "options": [], "unit": "g",
        "purposes": ["rule", "label"], "storage": "column:unit_weight_g",
        "required": False, "ordering": 40,
    },
    {
        "ref": "natureza", "label": "Natureza",
        "hint": "O que é o item na mesa. É o que deixa 'comida pede bebida' ser regra.",
        "type": "choice",
        "options": [
            {"value": "comida", "label": "Comida"},
            {"value": "bebida", "label": "Bebida"},
            {"value": "acompanhamento", "label": "Acompanhamento"},
            {"value": "outro", "label": "Outro"},
        ],
        "unit": "", "purposes": ["rule"], "storage": "attributes",
        "required": False, "ordering": 50,
    },
    {
        "ref": "sabor", "label": "Sabor",
        "hint": "Doce, salgado ou neutro. É a fronteira do substituto e a regra doce → café.",
        "type": "choice",
        "options": [
            {"value": "doce", "label": "Doce"},
            {"value": "salgado", "label": "Salgado"},
            {"value": "neutro", "label": "Neutro"},
        ],
        "unit": "", "purposes": ["rule"], "storage": "attributes",
        "required": False, "ordering": 60,
    },
    {
        "ref": "temperatura", "label": "Temperatura",
        "hint": "Como o item é servido. É o que sustenta o par quente → gelado.",
        "type": "choice",
        "options": [
            {"value": "quente", "label": "Quente"},
            {"value": "gelado", "label": "Gelado"},
            {"value": "ambiente", "label": "Ambiente"},
        ],
        "unit": "", "purposes": ["rule"], "storage": "attributes",
        "required": False, "ordering": 70,
    },
]


def ensure_definitions() -> int:
    """Cria o que faltar no registro. Idempotente; não desfaz ajuste do gestor."""
    from shopman.shop.models import AttributeDefinition
    from shopman.shop.services.attributes import invalidate_cache

    criadas = 0
    for spec in DEFAULT_DEFINITIONS:
        _, novo = AttributeDefinition.objects.get_or_create(
            ref=spec["ref"],
            defaults={**{k: v for k, v in spec.items() if k != "ref"}, "is_active": True},
        )
        criadas += int(novo)

    # Invalida SEMPRE, não só quando criou. Um cache que guardou "(registro
    # vazio)" antes das linhas existirem sobreviveria a este ponto e o seed
    # morreria em `Atributo 'alergenos' não existe no registro` com as sete
    # definições no banco, olhando para ele. Um delete de chave custa nada;
    # descobrir isso custou uma rodada de CI.
    invalidate_cache()
    return criadas
