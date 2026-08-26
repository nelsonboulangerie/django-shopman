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
    skus += ["COMBO-PETIT-DEJ", "PHO4", "BBB2"]
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
    # Vale para as categorias, que são vínculo PRIMÁRIO. As coleções "do dia"
    # são agrupamento rotativo e entram como secundárias — "Chausson" é Finos e
    # também é "Folhado do dia", sem ambiguidade.
    dono = {}
    duplos = {}
    for ref, skus in colecoes.items():
        for sku in skus:
            if sku in dono:
                duplos[sku] = (dono[sku], ref)
            dono[sku] = ref
    assert not duplos, f"produto em duas coleções: {duplos}"


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


def test_produto_sem_foto_e_decisao_nao_esquecimento(arvore):
    """Foto vazia no seed é uma DECISÃO por produto, nunca item esquecido.

    Só o formato próprio da casa (bicho moldado, espiral, deli) fica sem foto,
    porque não existe placeholder honesto — foto errada é pior que sem foto — e
    o card de categoria (cor + ícone + SKU) cobre a vitrine. Todo o resto tem
    foto da casa (nb-catalog) ou Unsplash conferido a olho. Um produto novo que
    entrar sem foto tem que passar por aqui, de propósito.
    """
    decididos_sem_foto = {"PR", "ANU", "ANP", "JO", "DL"}
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

    esperadas = {
        "bebidas-quentes", "bebidas-geladas", "torneira", "rusticos", "finos",
        "salgados", "doces", "combos", "mercearia",
    }
    assert esperadas <= set(fixas), (
        f"categorias sem (cor, ícone): {sorted(esperadas - set(fixas))}"
    )
    for ref, (cor, icone) in fixas.items():
        assert hexa.match(cor), f"{ref}: cor `{cor}` não é hex #RRGGBB"
        assert icone.strip(), f"{ref}: ícone vazio"

    for ref, _nome, cor, icone, _skus in _atribuicao(arvore, "colecoes_do_dia"):
        assert hexa.match(cor), f"{ref}: cor `{cor}` não é hex #RRGGBB"
        assert icone.strip(), f"{ref}: ícone vazio"
