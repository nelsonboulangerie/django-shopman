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
    skus.append("COMBO-PETIT-DEJ")
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


def test_um_produto_mora_em_uma_colecao_so(colecoes):
    # `is_primary=True` é gravado para todo vínculo; dois vínculos primários
    # para o mesmo produto é ambiguidade que só aparece na vitrine.
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
    permitidos = {"PAO-HOTDOG", "BRIOCHE-BURGER", "COMBO-PETIT-DEJ"}
    inventados = sorted({sku for sku in catalogo if "-" in sku} - permitidos)
    assert not inventados, (
        f"SKU inventado de volta no seed: {inventados}. "
        "Os códigos da casa são os do Yooga — ver docs/plans/sku-real-mapa.csv."
    )


def test_o_bundle_existe_de_verdade(arvore):
    # O catálogo o acrescenta à mão porque ele nasce fora do products_data;
    # se o seed parar de criá-lo, os outros testes passariam por engano.
    assert 'sku="COMBO-PETIT-DEJ"' in SEED.read_text()


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
