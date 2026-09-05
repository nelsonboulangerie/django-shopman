"""Os líquidos que a casa PESA contam em kg — e a troca não moveu a balança.

WP-BASE-UNIT-LIQUIDS-KG. Água, leite, azeite e creme de leite estavam cadastrados
em litro, mas a bancada os pesa; a R1 da ADR-024 diz que a unidade-base é a do
momento da verdade, então a base passou para `kg`.

O risco desta troca não é a unidade: é o rótulo. Manter `1.800` e escrever `kg`
onde estava `l` alteraria a fórmula do leite em 3% **em silêncio**, que é
exatamente o que a R3 proíbe. Por isso o teste central aqui não é "a unidade é
kg" — é **a massa de cada ficha continua a mesma**. Essa massa é a grandeza que o
`Recipe._validate_mass_balance` já calculava atravessando a densidade; escrever o
resultado dessa conta no cadastro não pode mudar o resultado da conta.

A tabela `QUANTIDADES_EM_LITRO` congela o cadastro ANTERIOR. É contra ela que o
teste multiplica pela densidade e confere o que o seed declara. Ela não duplica o
seed: é a única testemunha do que havia antes, e sem ela ninguém mais consegue
perguntar se a conversão aconteceu ou se só o rótulo mudou.

A aritmética é conferida no FONTE do seed (por AST, sem banco); o cadastro e o
invariante de massa são conferidos no banco, com um seed só.
"""

from __future__ import annotations

import ast
import inspect
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.buyman.models import Material, MaterialConversion
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.models.recipe import _item_mass_in_kg

# Densidade declarada em `INGREDIENT_PROFILES` (chega ao banco em
# `Material.metadata`). O teste não a inventa: confere que o perfil semeado diz o
# mesmo número.
DENSIDADES = {
    "AGUA-FILTRADA": Decimal("1.0"),
    "LEITE": Decimal("1.03"),
    "AZEITE": Decimal("0.91"),
    "CREME-DE-LEITE": Decimal("1.01"),
}

# A água vem da torneira e não tem fornecedor (`SUPPLIER_BY_MATERIAL`): nunca
# chega por nota, então não ganha conversão. Fator que ninguém usa é configuração
# morta, e se um dia a água vier numa nota a R4 trava e alguém declara ali.
COMPRADOS_EM_LITRO = ("LEITE", "AZEITE", "CREME-DE-LEITE")

# (ficha, insumo) → quantidade EM LITRO do cadastro anterior. 37 linhas: toda
# ocorrência dos quatro insumos no seed, receitas e pré-preparos.
QUANTIDADES_EM_LITRO = {
    ("creme-levain", "AGUA-FILTRADA"): Decimal("1.700"),
    ("massa-pasta-autolizada", "AGUA-FILTRADA"): Decimal("3.500"),
    ("massa-yudane", "AGUA-FILTRADA"): Decimal("1.000"),
    ("massa-campagne", "AGUA-FILTRADA"): Decimal("3.500"),
    ("massa-ciabatta", "AGUA-FILTRADA"): Decimal("4.000"),
    ("massa-ciabatta", "AZEITE"): Decimal("0.250"),
    ("massa-forma", "LEITE"): Decimal("1.800"),
    ("massa-croissant", "LEITE"): Decimal("1.200"),
    ("massa-kuropan", "LEITE"): Decimal("1.800"),
    ("massa-folhado", "AGUA-FILTRADA"): Decimal("1.800"),
    ("creme-baunilha", "LEITE"): Decimal("3.400"),
    ("massa-butter", "LEITE"): Decimal("1.600"),
    ("massa-pita", "AGUA-FILTRADA"): Decimal("3.000"),
    ("massa-pita", "AZEITE"): Decimal("0.150"),
    ("recheio-frango", "AZEITE"): Decimal("0.150"),
    ("recheio-cebola-bacon-tomilho", "AZEITE"): Decimal("0.150"),
    ("recheio-cebola-azapas", "AZEITE"): Decimal("0.150"),
    ("molho-bechamel", "LEITE"): Decimal("2.600"),
    ("creme-chocolate", "LEITE"): Decimal("1.500"),
    ("creme-leite-ovos", "CREME-DE-LEITE"): Decimal("0.800"),
    ("creme-leite-ovos", "LEITE"): Decimal("0.600"),
    ("vinagrete-frances", "AZEITE"): Decimal("0.700"),
    ("espresso-macchiato", "LEITE"): Decimal("0.020"),
    ("cafe-coado", "AGUA-FILTRADA"): Decimal("0.200"),
    ("cappuccino", "LEITE"): Decimal("0.150"),
    ("mochaccino", "LEITE"): Decimal("0.150"),
    ("mocha", "LEITE"): Decimal("0.180"),
    ("caffe-latte", "LEITE"): Decimal("0.220"),
    ("chocolate-quente", "LEITE"): Decimal("0.220"),
    ("cha-camille", "AGUA-FILTRADA"): Decimal("0.400"),
    ("cha-rouge", "AGUA-FILTRADA"): Decimal("0.400"),
    ("cha-sophie", "AGUA-FILTRADA"): Decimal("0.400"),
    ("cha-bleu", "AGUA-FILTRADA"): Decimal("0.400"),
    ("cha-hibisco", "AGUA-FILTRADA"): Decimal("0.300"),
    ("soft-chai-citrico", "AGUA-FILTRADA"): Decimal("0.250"),
    ("vienna-gelado", "LEITE"): Decimal("0.050"),
    ("vienna-gelado", "AGUA-FILTRADA"): Decimal("0.200"),
}

# O cadastro guarda três casas. Arredondar ali desloca a massa em no máximo meio
# grama por linha, e é este o único desvio que o teste tolera.
TOLERANCIA_KG_POR_LINHA = Decimal("0.0005")


def _literal(node: ast.AST):
    """Valor de `Decimal("1.800")` ou de uma string literal; senão, ``None``."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Decimal":
        return node.args[0].value
    return None


def _liquidos_declarados_no_seed() -> dict[tuple[str, str], Decimal]:
    """(ficha, insumo) → quantidade, lidos do FONTE do `recipes_data`.

    Por AST, e não pelo banco, porque é o literal escrito no fonte que esta
    frente tinha de mudar: o número precisa nascer arredondado no cadastro, não
    de uma multiplicação em tempo de execução.
    """
    from config.management.commands import seed as seed_module

    tree = ast.parse(inspect.getsource(seed_module))
    declaradas: dict[tuple[str, str], Decimal] = {}
    for node in ast.walk(tree):
        alvos = getattr(node, "targets", [])
        if not (
            isinstance(node, ast.Assign)
            and any(getattr(alvo, "id", None) == "recipes_data" for alvo in alvos)
        ):
            continue
        for entrada in node.value.elts:
            campos = {
                chave.value: valor
                for chave, valor in zip(entrada.keys, entrada.values, strict=True)
            }
            ref = _literal(campos["ref"])
            for item in campos["items"].elts:
                sku = _literal(item.elts[0])
                if sku in DENSIDADES:
                    declaradas[(ref, sku)] = Decimal(_literal(item.elts[1]))
    assert declaradas, "recipes_data não foi encontrado no fonte do seed"
    return declaradas


def test_cada_quantidade_e_a_do_litro_multiplicada_pela_densidade():
    """O invariante que separa CONVERTER de trocar o rótulo.

    Se alguém tivesse mantido `1.800` e escrito `kg` no lugar de `l`, a fórmula
    do leite teria encolhido 3% sem uma linha de aviso. Aqui a conta é refeita a
    partir do cadastro anterior, insumo a insumo.
    """
    declaradas = _liquidos_declarados_no_seed()
    assert set(declaradas) == set(QUANTIDADES_EM_LITRO), (
        "linha de líquido que apareceu ou sumiu do seed sem passar por aqui: "
        f"{sorted(set(declaradas) ^ set(QUANTIDADES_EM_LITRO))}"
    )
    for (ref, sku), litros in sorted(QUANTIDADES_EM_LITRO.items()):
        esperado = (litros * DENSIDADES[sku]).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
        assert declaradas[(ref, sku)] == esperado, f"{ref}/{sku}"


def test_a_massa_de_liquido_de_cada_ficha_nao_se_moveu():
    """A prova de que a troca foi de unidade, não de fórmula.

    A massa de antes é a que o `_item_mass_in_kg` calculava atravessando a
    densidade (litro × densidade); a de depois é o próprio número em kg. As duas
    batem a menos do arredondamento de três casas do cadastro.
    """
    declaradas = _liquidos_declarados_no_seed()
    fichas = {ref for ref, _sku in QUANTIDADES_EM_LITRO}
    for ref in sorted(fichas):
        linhas = [chave for chave in QUANTIDADES_EM_LITRO if chave[0] == ref]
        antes = sum(
            (QUANTIDADES_EM_LITRO[chave] * DENSIDADES[chave[1]] for chave in linhas),
            Decimal("0"),
        )
        depois = sum((declaradas[chave] for chave in linhas), Decimal("0"))
        limite = TOLERANCIA_KG_POR_LINHA * len(linhas)
        assert abs(depois - antes) <= limite, f"{ref}: {antes} kg → {depois} kg"


@pytest.mark.django_db
def test_o_cadastro_semeado_conta_os_liquidos_em_quilo(monkeypatch):
    """Um seed só, e todas as perguntas de cadastro de uma vez — ele leva minutos."""
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-liquids-password")
    call_command("seed", "--flush", stdout=StringIO())

    # A densidade que este arquivo usa é a que o perfil declara.
    for sku, densidade in DENSIDADES.items():
        material = Material.objects.get(sku=sku)
        assert Decimal(str(material.metadata["density_g_per_ml"])) == densidade, sku
        assert material.unit == "kg", sku

    # A base é a unidade do momento da verdade, e a casa pesa tudo (R1).
    assert sorted(Material.objects.filter(unit="l").values_list("sku", flat=True)) == []

    # `RecipeItem.clean` já obrigaria; o teste diz por quê. Item em `L` para
    # insumo em `kg` seria número mudo: a separação pesaria uma coisa e o ledger
    # baixaria outra.
    itens = RecipeItem.objects.filter(input_sku__in=DENSIDADES)
    assert itens.count() == len(QUANTIDADES_EM_LITRO)
    for item in itens.select_related("recipe"):
        assert item.unit == "kg", f"{item.recipe.ref}/{item.input_sku}: {item.unit}"
        item.full_clean()

    # Misturar não cria matéria: `Recipe.clean` recusa quem rende mais do que
    # pesa. Se alguma conversão tivesse encolhido um insumo, a ficha reprovaria.
    fichas = list(Recipe.objects.all())
    assert fichas
    for recipe in fichas:
        recipe.full_clean()

    # Sem fator declarado a nota em litro TRAVA — e travar é o desenho (R4). A
    # ponte é APPROXIMATE porque densidade é equivalência física com incerteza, e
    # é isso que faz o número chegar carimbado à tela (R3).
    # O rótulo é plural porque sai tal como escrito na anotação da separação,
    # ao lado de "≈ 17 ovos" e "≈ 1,5 limões".
    for sku in COMPRADOS_EM_LITRO:
        conversao = MaterialConversion.objects.get(material__sku=sku, label="litros")
        assert conversao.to_base_factor == DENSIDADES[sku], sku
        assert conversao.is_approximate is True, sku
        assert conversao.supplier_id is None, sku
        assert conversao.is_active is True, sku
    assert not MaterialConversion.objects.filter(material__sku="AGUA-FILTRADA").exists()

    # O ganho concreto: a massa do item sai direto do cadastro. Antes, item sem
    # `density_g_per_ml` devolvia `None` e calava o invariante da ficha inteira.
    leite = RecipeItem.objects.filter(input_sku="LEITE").first()
    leite.meta = {}
    assert _item_mass_in_kg(leite) == leite.quantity
