"""O catálogo do seed tem de fechar consigo mesmo (SKU-REAL-PLAN F4).

Lê o `seed.py` como dado, sem rodá-lo: rodar custa minutos e monta 700 dias de
histórico. O que estes testes protegem são erros de edição que o `ast.parse`
aceita calado — e um deles quase passou: ao acrescentar produtos numa lista de
uma linha, a vírgula que faltou fez `"TJ"` e `"BH"` virarem `"TJBH"`, porque
literais adjacentes concatenam em Python.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

SEED = pathlib.Path(__file__).resolve().parents[3] / "config/management/commands/seed.py"


@pytest.fixture(scope="module")
def arvore():
    return ast.parse(SEED.read_text())


def _no_da_atribuicao(arvore, nome):
    for node in ast.walk(arvore):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == nome:
            return node.value
    raise AssertionError(f"`{nome}` não encontrado no seed")


def _atribuicao(arvore, nome):
    return ast.literal_eval(_no_da_atribuicao(arvore, nome))


@pytest.fixture(scope="module")
def catalogo(arvore):
    """Só os SKUs: as tuplas de produto trazem `unsplash(...)` e f-strings, que
    o `literal_eval` recusa — e o SKU é o primeiro elemento, sempre literal."""
    skus = []
    for elemento in _no_da_atribuicao(arvore, "products_data").elts:
        primeiro = elemento.elts[0]
        assert isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str), (
            f"produto cujo SKU não é literal, em products_data linha {elemento.lineno}"
        )
        skus.append(primeiro.value)
    # O bundle nasce fora da lista, num update_or_create próprio: ele não tem
    # preço nem ficha de produto, tem componentes.
    # Nascem fora do products_data, num update_or_create próprio: bundle não
    # tem ficha de produto, tem componentes.
    skus += ["COMBO-PETIT-DEJ", "PHO4", "BBB2", "PI4"]
    return skus


@pytest.fixture(scope="module")
def colecoes(arvore):
    return _atribuicao(arvore, "collection_skus")


def test_toda_colecao_aponta_para_produto_existente(catalogo, colecoes):
    orfaos = sorted(
        {sku for skus in colecoes.values() for sku in skus} - set(catalogo)
    )
    assert not orfaos, (
        f"SKUs em collection_skus sem produto em products_data: {orfaos}. "
        "Vírgula faltando entre dois literais os concatena silenciosamente."
    )


def test_todo_produto_esta_em_alguma_colecao(catalogo, colecoes):
    em_colecao = {sku for skus in colecoes.values() for sku in skus}
    fora = sorted(set(catalogo) - em_colecao)
    assert not fora, f"produtos sem coleção: {fora}"


def test_nenhum_sku_repetido(catalogo):
    skus = catalogo
    repetidos = sorted({s for s in skus if skus.count(s) > 1})
    assert not repetidos, f"SKU repetido em products_data: {repetidos}"


def test_nenhum_vinculo_de_colecao_repetido(colecoes):
    repetidos = {}
    for ref, skus in colecoes.items():
        dup = sorted({s for s in skus if skus.count(s) > 1})
        if dup:
            repetidos[ref] = dup
    assert not repetidos, f"produto listado duas vezes na mesma coleção: {repetidos}"


def test_um_produto_mora_em_uma_categoria_so(colecoes):
    """Uma categoria PRINCIPAL por produto — as outras são só as outras.

    O produto pode aparecer em mais de uma lista: o Pain au Chocolat é Folhados
    (a massa) e também é Doces (o sabor). A regra que vale é que ele MORA num
    lugar só, e esse lugar é a primeira lista em que aparece — é o que o seed
    grava como `is_primary`. Sem estrutura paralela: a ordem das listas decide.
    """
    principal = {}
    for ref, skus in colecoes.items():
        for sku in skus:
            principal.setdefault(sku, ref)

    sem_casa = [sku for skus in colecoes.values() for sku in skus if sku not in principal]
    assert not sem_casa, f"produto sem categoria principal: {sem_casa}"

    # O que a regra proíbe é a MESMA lista repetir o produto — isso é erro de
    # edição, não taxonomia, e criaria dois vínculos idênticos.
    for ref, skus in colecoes.items():
        assert len(skus) == len(set(skus)), f"'{ref}' repete SKU: {sorted({s for s in skus if skus.count(s) > 1})}"


def test_o_catalogo_usa_os_codigos_reais(catalogo):
    """Os SKUs inventados pela geração automática não voltam pelo seed.

    Sobrevivem três, e cada um por um motivo escrito: dois pacotes cujo código
    do Yooga media UNIDADE (decisão pendente do dono) e o combo, que é bundle
    sem contrapartida no histórico.
    """
    # Sobra um: o combo, que é bundle sem contrapartida no histórico. Os pacotes
    # de pão saíram desta lista ao virarem bundle sobre PHO e BBB.
    permitidos = {"COMBO-PETIT-DEJ"}
    inventados = sorted({sku for sku in catalogo if "-" in sku} - permitidos)
    assert not inventados, (
        f"SKU inventado de volta no seed: {inventados}. "
        "Os códigos da casa são os do Yooga — ver docs/plans/sku-real-mapa.csv."
    )


def test_o_bundle_existe_de_verdade(arvore):
    # O catálogo o acrescenta à mão porque ele nasce fora do products_data;
    # se o seed parar de criá-lo, os outros testes passariam por engano.
    fonte = SEED.read_text()
    for sku in ('"COMBO-PETIT-DEJ"', '"PHO4"', '"BBB2"'):
        assert f"sku={sku}" in fonte or f"({sku}," in fonte, f"{sku} sumiu do seed"


def test_quem_esta_sem_ficha_nasce_despublicado(arvore, catalogo):
    """Produto sem alergênico e tabela nutricional não vai para a vitrine.

    O portão de completude do próprio seed cobra isso. A lista existe para o
    portão continuar cobrando: quem completar a ficha tira o SKU daqui, e aí o
    produto passa a ser validado como todos os outros.
    """
    sem_ficha = None
    for node in ast.walk(arvore):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "sem_ficha":
            sem_ficha = ast.literal_eval(node.value)
    assert sem_ficha, "`sem_ficha` sumiu do seed"

    fantasmas = sorted(sem_ficha - set(catalogo))
    assert not fantasmas, f"`sem_ficha` cita produto que não existe: {fantasmas}"


def _curadoria(nome_da_funcao, marca_de_fim):
    """SKU → papel, lendo o corpo de uma das funções de curadoria do seed."""
    import re

    linhas = SEED.read_text().splitlines()
    i = next(k for k, linha in enumerate(linhas) if nome_da_funcao in linha)
    j = next(k for k in range(i + 1, len(linhas)) if marca_de_fim in linhas[k])
    corpo = "\n".join(linhas[i:j])
    fora = {}
    for bloco in re.finditer(r'"([a-z][a-z-]+)": (?:\(|\[)(.*?)(?:\]\)|\])', corpo, re.S):
        papel = bloco.group(1)
        for sku in re.findall(r'"((?:nome:)?[A-Z][A-Za-z0-9_ +&-]*)"', bloco.group(2)):
            fora[sku] = papel
    return fora


def test_as_duas_curadorias_de_consumo_nao_se_contradizem():
    """Onde cardápio e histórico se encontram, a leitura tem de ser a mesma.

    Elas se encontram desde que o catálogo passou a usar os códigos do Yooga:
    "CT" no cardápio e "CT" no histórico são o mesmo produto. As duas gravam na
    mesma linha (`sku` é único), então a segunda a rodar vence — em silêncio.
    Divergência aqui não daria erro nenhum: daria um número de B.I. diferente
    dependendo da ordem das funções.
    """
    cardapio = _curadoria("def _seed_consumption_tags", "_seed_historical_consumption_tags")
    historico = _curadoria("def _seed_historical_consumption_tags", "def _seed_seating")

    conflitos = {
        sku: (cardapio[sku], historico[sku])
        for sku in set(cardapio) & set(historico)
        if cardapio[sku] != historico[sku]
    }
    assert not conflitos, (
        f"cardápio e histórico discordam sobre {len(conflitos)} SKU(s): {conflitos}. "
        "Quem roda por último venceria, sem erro nenhum."
    )


def test_a_promessa_ao_cliente_nao_e_a_politica_de_estoque(arvore):
    """⚠️ Duas perguntas, duas listas — e a água é quem prova que são duas.

    ``sells_without_stock_skus`` responde "a venda pode passar sem saldo?".
    ``made_to_order_skus`` responde "a casa promete finalizar isto na hora?".

    Elas quase coincidem, e a quase-coincidência é a armadilha: enquanto havia
    uma lista só, a Água saía da sacola anunciada como "Preparado na hora". Ela
    é ``demand_ok`` porque sempre há outra garrafa na geladeira — não porque
    alguém a prepare. Era a mesma confusão entre política e promessa que já
    tinha sido tirada do código, reaparecendo na camada do dado.

    Este teste existe para que ninguém volte a fundir as listas "porque são
    quase iguais".
    """
    politica = _atribuicao(arvore, "sells_without_stock_skus")
    promessa = _atribuicao(arvore, "made_to_order_skus")

    assert "AG" in politica, "água vende sem saldo: sempre há outra na geladeira"
    assert "AG" not in promessa, (
        "ninguém prepara uma água na hora — o selo é sobre o acabamento, e "
        "garrafa não tem acabamento"
    )
    assert set(promessa) != set(politica), (
        "as duas listas viraram a mesma: é o sinal de que alguém tornou a "
        "tratar política de estoque e promessa ao cliente como uma coisa só"
    )


def test_produto_sem_foto_e_decisao_nao_esquecimento(arvore):
    """Foto vazia no seed é uma DECISÃO por produto, nunca item esquecido.

    Só o Porquinho fica sem foto — o acervo da casa (nb-catalog, loja/ e
    img/products/) não tem registro dele, e foto errada é pior que sem foto;
    o card de categoria (cor + ícone + SKU) cobre a vitrine. Todo o resto tem
    foto da casa ou Unsplash conferido a olho. Um produto novo que entrar sem
    foto tem que passar por aqui, de propósito.
    """
    decididos_sem_foto = {"ANP"}
    vazios = set()
    for elemento in _no_da_atribuicao(arvore, "products_data").elts:
        imagem = elemento.elts[7]
        if isinstance(imagem, ast.Constant) and imagem.value == "":
            vazios.add(elemento.elts[0].value)
    assert vazios == decididos_sem_foto, (
        f"sem foto no seed: {sorted(vazios)}; decididos: {sorted(decididos_sem_foto)}. "
        "Foto nova resolve; sem foto de propósito, registre aqui e no comentário do seed."
    )


def test_toda_categoria_tem_cor_e_icone(arvore):
    """Cor (paleta NB) e ícone (Lucide) são parte do contrato da categoria.

    É o que veste o card-fallback de produto sem foto e os chips de categoria
    nas superfícies. Categoria sem os dois quebra o fallback em silêncio.
    """
    import re

    hexa = re.compile(r"^#[0-9A-Fa-f]{6}$")

    fixas = {}
    for node in ast.walk(arvore):
        if (
            isinstance(node, ast.Tuple)
            and len(node.elts) == 4
            and all(isinstance(e, ast.Constant) for e in node.elts)
            and isinstance(node.elts[2].value, str)
            and node.elts[2].value.startswith("#")
        ):
            ref, _nome, cor, icone = (e.value for e in node.elts)
            fixas[ref] = (cor, icone)

    # Taxonomia do dono (01/09): finos→macios, torneira absorvida, folhados
    # nasce, e as rotativas "*-do-dia" morreram — rotativo é vitrine, não
    # taxonomia. A lista espelha as categorias ESTÁVEIS do seed.
    esperadas = {
        "rusticos", "macios", "folhados", "salgados", "doces",
        "bebidas-quentes", "bebidas-geladas", "mercearia", "combos",
    }
    assert esperadas <= set(fixas), (
        f"categorias sem (cor, ícone): {sorted(esperadas - set(fixas))}"
    )
    for ref, (cor, icone) in fixas.items():
        assert hexa.match(cor), f"{ref}: cor `{cor}` não é hex #RRGGBB"
        assert icone.strip(), f"{ref}: ícone vazio"


# ── Folhados: a MASSA manda, não o sabor (decisão do dono, 02/09) ────────────
#
# Antes disso a taxonomia seguia o paladar: Folhado de Frango em Salgados,
# Bichon au Citron em Doces, Croissant Mini em Macios. Três massas laminadas em
# três categorias diferentes, e nenhuma delas em Folhados. O cliente que abre
# "Folhados" quer ver folhado.
#
# O contraexemplo é o Pain aux Raisins: o nome é francês e o vizinho de vitrine
# é folhado, mas o NOSSO é feito de brioche. Ele mora em Macios, e é por isso
# que a regra é sobre a massa e não sobre o nome.

FAMILIA_LAMINADA = {
    "CT": "Croissant",
    "PC": "Pain au Chocolat",
    "CM": "Croissant Mini",
    "CN": "Chausson",
    "FF": "Folhado de Frango",
    "BH": "Bichon au Citron",
}


@pytest.mark.parametrize("sku,nome", sorted(FAMILIA_LAMINADA.items()))
def test_massa_laminada_mora_em_folhados(sku, nome, colecoes):
    assert sku in colecoes["folhados"], (
        f"{nome} ({sku}) é massa laminada e tem de estar em Folhados — "
        "a categoria segue a massa, não o recheio."
    )


def test_pain_aux_raisins_e_brioche_e_fica_em_macios(colecoes):
    assert "PR" in colecoes["macios"]
    assert "PR" not in colecoes["folhados"], (
        "o nosso Pain aux Raisins é de brioche; o nome francês não decide a categoria"
    )



def test_a_categoria_principal_do_laminado_e_folhados(colecoes):
    """A massa decide onde o produto MORA; o sabor é a categoria adicional."""
    principal = {}
    for ref, skus in colecoes.items():
        for sku in skus:
            principal.setdefault(sku, ref)

    for sku in ("CT", "PC", "CM", "CN", "FF", "BH", "CPQ"):
        assert principal[sku] == "folhados", (
            f"{sku} mora em '{principal[sku]}' — massa laminada mora em Folhados"
        )
    assert principal["PR"] == "macios", "o nosso Pain aux Raisins é de brioche"


def test_o_sabor_entra_como_categoria_adicional(colecoes):
    for sku in ("PC", "CM", "CN", "BH", "PR"):
        assert sku in colecoes["doces"], f"{sku} é recheado doce e também é Doces"
    for sku in ("FF", "CPQ"):
        assert sku in colecoes["salgados"], f"{sku} é salgado e também é Salgados"
    assert "CT" not in colecoes["doces"], "o croissant puro não é doce"
