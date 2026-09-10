"""As sete definições com que o registro nasce.

Vai em migração, não no ``seed``: o alpha já está no ar e reseedar é decisão do
dono, não efeito colateral de um deploy. Aqui o registro chega junto com a
tabela, em qualquer deployment, sem apagar nada.

As três primeiras são **ponteiros** para chaves que já existem no
``Product.metadata`` — nenhum dado se move, nenhum leitor muda. O peso por
unidade aponta para a coluna. As três últimas (natureza, sabor, temperatura)
nascem vazias e são preenchidas pelo ``propose_product_attributes``, que deriva
das coleções e marca tudo como proposta a revisar.
"""

from django.db import migrations

DEFINITIONS = [
    {
        "ref": "alergenos",
        "label": "Alérgenos",
        "hint": "O que o produto CONTÉM. Sai no rótulo e no aviso de alergia da loja.",
        "type": "multi_text",
        "options": [],
        "unit": "",
        "purposes": ["label", "facet"],
        # Escrito hoje pelo formulário de rótulo do Offerman (texto separado por
        # vírgula) e pelo `dietary_from_recipe`. Por isso é lista de termos e não
        # escolha múltipla: o registro não controla a escrita, e prometer uma
        # lista fechada seria prometer o que não dá para cumprir.
        "storage": "metadata:allergens",
        "required": False,
        "ordering": 10,
    },
    {
        "ref": "dieta",
        "label": "Dieta",
        "hint": "100% vegetal, vegetariano, sem glúten, sem lactose.",
        "type": "multi_text",
        "options": [],
        "unit": "",
        "purposes": ["label", "facet"],
        "storage": "metadata:dietary_info",
        "required": False,
        "ordering": 20,
    },
    {
        "ref": "porcoes",
        "label": "Porções",
        "hint": "Quantas pessoas o produto serve.",
        "type": "number",
        "options": [],
        "unit": "porções",
        "purposes": ["label"],
        "storage": "metadata:serves",
        "required": False,
        "ordering": 30,
    },
    {
        "ref": "peso_unidade_g",
        "label": "Peso por unidade",
        "hint": "Peso aproximado de uma unidade. É o que aproxima um substituto do outro.",
        "type": "number",
        "options": [],
        "unit": "g",
        "purposes": ["rule", "label"],
        # Fato físico com integridade no banco: continua coluna. O registro só o
        # torna citável por uma regra de sugestão.
        "storage": "column:unit_weight_g",
        "required": False,
        "ordering": 40,
    },
    {
        "ref": "natureza",
        "label": "Natureza",
        "hint": "O que é o item na mesa. É o que deixa 'comida pede bebida' ser regra.",
        "type": "choice",
        "options": [
            {"value": "comida", "label": "Comida"},
            {"value": "bebida", "label": "Bebida"},
            {"value": "acompanhamento", "label": "Acompanhamento"},
            {"value": "outro", "label": "Outro"},
        ],
        "unit": "",
        "purposes": ["rule"],
        "storage": "attributes",
        "required": False,
        "ordering": 50,
    },
    {
        "ref": "sabor",
        "label": "Sabor",
        "hint": "Doce, salgado ou neutro. É a fronteira do substituto e a regra doce → café.",
        "type": "choice",
        "options": [
            {"value": "doce", "label": "Doce"},
            {"value": "salgado", "label": "Salgado"},
            {"value": "neutro", "label": "Neutro"},
        ],
        "unit": "",
        "purposes": ["rule"],
        "storage": "attributes",
        "required": False,
        "ordering": 60,
    },
    {
        "ref": "temperatura",
        "label": "Temperatura",
        "hint": "Como o item é servido. É o que sustenta o par quente → gelado.",
        "type": "choice",
        "options": [
            {"value": "quente", "label": "Quente"},
            {"value": "gelado", "label": "Gelado"},
            {"value": "ambiente", "label": "Ambiente"},
        ],
        "unit": "",
        "purposes": ["rule"],
        "storage": "attributes",
        "required": False,
        "ordering": 70,
    },
]


def create_definitions(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    for spec in DEFINITIONS:
        # ``get_or_create``, não ``update_or_create``: se o gestor já ajustou o
        # rótulo ou as opções de um atributo, o deploy seguinte não desfaz.
        AttributeDefinition.objects.get_or_create(
            ref=spec["ref"],
            defaults={**{k: v for k, v in spec.items() if k != "ref"}, "is_active": True},
        )


def drop_definitions(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    AttributeDefinition.objects.filter(ref__in=[s["ref"] for s in DEFINITIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0027_attribute_definition")]

    operations = [migrations.RunPython(create_definitions, drop_definitions)]
