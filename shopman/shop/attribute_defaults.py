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
    # Os cereais que contêm glúten, NOMEADOS. A RDC 26/2015 os nomeia um a um, e
    # numa padaria é aqui que a declaração vive: "glúten" sozinho não distingue
    # um pão de centeio de um pão de trigo, e quem evita trigo não evita os dois.
    "glúten", "trigo", "centeio", "cevada", "aveia",
    "crustáceos", "ovos", "peixes", "amendoim", "soja", "leite",
    # As castanhas que a norma nomeia. `pinoli` estava faltando — não por
    # decisão, por descuido meu ao transcrever a lista.
    "castanhas", "amêndoa", "avelã", "castanha-de-caju", "castanha-do-brasil",
    "macadâmia", "nozes", "pecã", "pistache", "pinoli",
    "gergelim", "sulfitos", "látex natural",
    # Fora da RDC 26/2015 e declarada pela casa na mercearia (é alérgeno de
    # declaração obrigatória na UE). Lista que não cabe a realidade vira
    # alérgeno descartado em silêncio.
    "mostarda",
    # Fora de QUALQUER lista regulatória, e dentro por decisão do dono
    # (06/09/2026). A casa usa pimenta-do-reino e já viu reação a ela. O rótulo
    # existe para proteger quem come, não para cumprir a lista mínima da norma —
    # e o cliente que reage não pergunta o que a RDC nomeia.
    #
    # Escrita como a casa já escreve no aviso de cozinha compartilhada
    # (`Shop.defaults['food_safety_notice']`), que é o texto que o cliente lê.
    "pimenta-do-reino",
]

DIETA_CANONICA = [
    # ⚠️ A distinção que importa aqui é COMPOSIÇÃO × CONTAMINAÇÃO CRUZADA, e
    # confundir as duas custou uma correção no ar (08/09/2026).
    #
    # `sem lactose` e `vegetariano` afirmam o que a RECEITA tem ou não tem, e a
    # ficha sabe responder. Uma baguete de farinha, água, sal e levain não contém
    # lactose — dizer isso é verdade, é útil, e a RDC 135/2017 dá o limiar
    # objetivo (< 100 mg/100 g). Removê-los tirava informação correta do cliente.
    #
    # `sem glúten` é outra natureza: numa casa sem linha segregada a afirmação é
    # sobre o AMBIENTE, não sobre a fórmula — e é a única em que um celíaco pode
    # se machucar. Fica fora da derivação, e a casa declara o oposto em voz alta
    # (ver `food_safety_notice`).
    #
    # E as duas convivem sem contradição: intolerância à lactose é DOSE-dependente
    # e traço não a alcança; alergia à proteína do leite é outra coisa, e dela
    # cuida o aviso de cozinha compartilhada. Separar as duas é prática da
    # indústria, não invenção nossa.
    #
    # Parâmetros de norma citados aqui vivem em `shop/legal_parameters.py`, com
    # data de conferência e catraca — legislação muda, e parâmetro que ninguém
    # revisita faz o sistema ensinar o gestor a errar.
    "100% vegetal",
    "vegetariano",
    "sem lactose",
]


def _options(values):
    return [{"value": v, "label": v[:1].upper() + v[1:]} for v in values]


DEFAULT_DEFINITIONS = [
    {
        "ref": "alergenos", "label": "Alérgenos",
        "hint": "O que o produto CONTÉM. Sai no rótulo e no aviso de alergia da loja.",
        "type": "multi_choice", "options": _options(ALERGENOS_CANONICOS), "unit": "",
        "purposes": ["label", "facet"], "storage": "attributes",
        "required": False, "ordering": 10,
        # O vocabulário de alérgeno nasce da CADEIA DE INSUMOS, não da lei: a
        # lei é o piso. Insumo que declara algo que a lista não tem amplia a
        # lista, para revisão — nunca é barrado.
        "extends_from_source": True,
    },
    {
        "ref": "dieta", "label": "Dieta",
        "hint": "Marque quando o produto não leva NADA de origem animal — nem leite, ovo, mel ou banha.",
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
