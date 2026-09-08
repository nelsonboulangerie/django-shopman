"""A ficha de produto do seed fala por unidade, e isso não moveu um grama.

Lê o `seed.py` como dado, sem rodá-lo (mesmo gesto do
`test_seed_catalog_coerente`): rodar o seed custa minutos e monta 700 dias de
histórico, e o que está em jogo aqui é aritmética de tabela.

O que estes testes protegem é a promessa do WP-FICHA-DE-PRODUTO-E-PROMESSA §A:
a ficha da baguete passou a dizer "0,280 kg de Massa Tradição rendem 1 un" no
lugar de "7 kg rendem 25 un". É **reexpressão** — a razão não muda, então o
consumo por fornada tem de ser idêntico ao centésimo de grama. A tabela
`LOTE_ANTIGO` é o registro histórico de como cada ficha estava escrita antes;
sem ela a comparação seria circular (dividir o número novo pelo número novo).

⚠️ `LOTE_ANTIGO` e `FORMULA_EM_KG` são REGISTRO, não regra. Quando o dono mudar
uma receita de verdade — a baguete passar a levar 300 g de massa —, o teste vai
acusar, e o certo é **atualizar a linha daquela ficha** dizendo no commit que a
receita mudou. O que ele existe para pegar é o contrário: a receita mudando sem
ninguém ter decidido, por causa de uma conta.
"""

from __future__ import annotations

import ast
import pathlib
from decimal import Decimal

import pytest

SEED = pathlib.Path(__file__).resolve().parents[3] / "config/management/commands/seed.py"

#: As 42 fichas que rendem UNIDADE, como estavam escritas por lote antes do
#: WP-FICHA-DE-PRODUTO-E-PROMESSA: (rendimento, {insumo: quantidade}).
LOTE_ANTIGO: dict[str, tuple[str, dict[str, str]]] = {
    "baguete": ("25", {"MASSA-TRADICAO": "7.000"}),
    "campagne": ("10", {"MASSA-CAMPAGNE": "3.400"}),
    "ciabatta": ("20", {"MASSA-CIABATTA": "4.100"}),
    "focaccia-dia": ("8", {"MASSA-CIABATTA": "3.312", "ALECRIM": "0.032", "SAL-GROSSO": "0.016"}),
    "shokupan": ("12", {"MASSA-FORMA": "4.800"}),
    "kuro-pan": ("8", {"MASSA-KUROPAN": "2.240"}),
    "croissant": ("48", {"MASSA-CROISSANT": "3.840"}),
    "pain-chocolat": ("36", {"MASSA-CROISSANT": "2.880", "BATON-CHOCOLATE": "0.720"}),
    "animalzinho": ("16", {"MASSA-BRIOCHE": "0.960", "CREME-BAUNILHA": "0.640"}),
    "folhado-dia": ("12", {"MASSA-FOLHADO": "0.744", "RECHEIO-MACA": "0.240"}),
    "bichon": ("12", {"MASSA-FOLHADO": "0.960", "CREME-LIMAO": "0.240"}),
    "madeleine": ("24", {"MASSA-MADELEINE": "0.672"}),
    "baguete-lanche": ("12", {"MASSA-TRADICAO": "3.120"}),
    "batard": ("10", {"MASSA-TRADICAO": "3.200"}),
    "baguete-gergelim-pequena": ("12", {"MASSA-TRADICAO": "1.980", "GERGELIM": "0.060"}),
    "italiano-rustico": ("8", {"MASSA-TRADICAO": "3.840"}),
    "baguette-campagne": ("12", {"MASSA-CAMPAGNE": "3.600"}),
    "campagne-redondo": ("10", {"MASSA-CAMPAGNE": "3.400"}),
    "pita": ("24", {"MASSA-PITA": "0.720"}),
    "focaccia-cebola-bacon-tomilho": ("6", {"MASSA-CIABATTA": "3.600", "RECHEIO-CEBOLA-BACON-TOMILHO": "0.480"}),
    "focaccia-cebola-roxa": ("6", {"MASSA-CIABATTA": "2.970", "RECHEIO-CEBOLA-AZAPAS": "0.270"}),
    "mini-focaccia-alecrim": ("12", {"MASSA-CIABATTA": "1.260", "ALECRIM": "0.048", "SAL-GROSSO": "0.012"}),
    "mini-focaccia-cebola-bacon-tomilho": ("12", {"MASSA-CIABATTA": "1.896", "RECHEIO-CEBOLA-BACON-TOMILHO": "0.264"}),
    "mini-focaccia-cebola-roxa": ("12", {"MASSA-CIABATTA": "1.752", "RECHEIO-CEBOLA-AZAPAS": "0.168"}),
    "croissant-mini": ("24", {"MASSA-CROISSANT": "0.864"}),
    "pain-aux-raisins": ("12", {"MASSA-CROISSANT": "0.480", "CREME-BAUNILHA": "0.216", "PASSAS": "0.120"}),
    "maca": ("12", {"MASSA-FOLHADO": "0.960", "RECHEIO-MACA": "0.360"}),
    "croissant-presunto-queijo": ("12", {"MASSA-CROISSANT": "0.720", "PRESUNTO-DEFUMADO": "0.180", "QUEIJO-MINAS-PADRAO": "0.180"}),
    "folhado-frango": ("12", {"MASSA-FOLHADO": "1.140", "RECHEIO-FRANGO": "0.420"}),
    "mini-folhado-frango": ("12", {"MASSA-FOLHADO": "0.696", "RECHEIO-FRANGO": "0.264"}),
    "caranguejo": ("16", {"MASSA-FORMA": "0.608", "GERGELIM": "0.032"}),
    "kuro-pan-burger": ("12", {"MASSA-KUROPAN": "1.080"}),
    "brioche-nanterre": ("8", {"MASSA-BRIOCHE": "1.920"}),
    "brioche-chocolat": ("24", {"MASSA-BRIOCHE": "0.816", "GOTAS-CHOCOLATE": "0.192"}),
    "mini-brioche-bun-gergelim": ("24", {"MASSA-BRIOCHE": "0.720", "GERGELIM": "0.048"}),
    "ursinho": ("12", {"MASSA-BRIOCHE": "0.960", "CREME-BAUNILHA": "0.360"}),
    "porquinho": ("12", {"MASSA-BRIOCHE": "0.960", "CREME-BAUNILHA": "0.360"}),
    "challah": ("8", {"MASSA-BUTTER": "2.400"}),
    "hot-dog-vienna": ("12", {"MASSA-BUTTER": "0.720", "SALSICHA-VIENNA": "0.600"}),
    "mini-hot-dog-vienna": ("12", {"MASSA-BUTTER": "0.480", "SALSICHA-VIENNA": "0.300"}),
    "deli-milho-bacon": ("12", {"MASSA-BUTTER": "0.840", "MILHO-VERDE": "0.240", "BACON": "0.120", "SALSINHA-DESID": "0.012"}),
    "cornet-chocolate": ("12", {"MASSA-BUTTER": "0.576", "CREME-CHOCOLATE": "0.144"}),
}

#: As 25 fórmulas (saída em kg) que este WP NÃO toca: (rendimento, soma dos
#: insumos, número de linhas). Uma fórmula por unidade não quer dizer nada — 1 kg
#: de Massa Tradição não é "uma" de nada.
FORMULA_EM_KG: dict[str, tuple[str, str, int]] = {
    "creme-levain": ("5", "5.100", 3),
    "massa-pasta-autolizada": ("8.4", "8.500", 2),
    "massa-yudane": ("1.9", "2.000", 2),
    "massa-tradicao": ("10", "10.020", 4),
    "massa-campagne": ("10", "10.700", 6),
    "massa-ciabatta": ("10", "10.828", 5),
    "massa-forma": ("8.2", "8.554", 7),
    "massa-croissant": ("9", "9.456", 7),
    "massa-brioche": ("8", "8.040", 6),
    "massa-kuropan": ("8.2", "8.704", 8),
    "massa-folhado": ("9.5", "9.890", 4),
    "massa-madeleine": ("4.9", "5.000", 5),
    "recheio-maca": ("5", "5.080", 4),
    "creme-baunilha": ("5", "5.202", 5),
    "creme-limao": ("3", "3.050", 4),
    "massa-butter": ("8.5", "8.898", 7),
    "massa-pita": ("8.2", "8.387", 6),
    "recheio-frango": ("3.2", "4.077", 4),
    "recheio-cebola-bacon-tomilho": ("2.7", "2.997", 4),
    "recheio-cebola-azapas": ("2.8", "3.037", 3),
    "molho-bechamel": ("2.9", "3.098", 4),
    "creme-chocolate": ("2.9", "3.095", 4),
    "creme-leite-ovos": ("2", "2.076", 4),
    "salada-da-casa": ("1.8", "1.900", 4),
    "vinagrete-frances": ("0.9", "0.917", 5),
}

#: Montagem e bebida: ficha inativa (não é fornada), que já nascia por unidade.
MONTAGEM_E_BEBIDA = frozenset({
    "queijo-quente", "croque-monsieur", "croque-madame", "croque-complet", "jambon-beurre",
    "pain-grille", "pain-perdu", "espresso", "espresso-macchiato", "cafe-coado", "cappuccino",
    "mochaccino", "mocha", "caffe-latte", "chocolate-quente", "cha-camille", "cha-rouge",
    "cha-sophie", "cha-bleu", "cha-hibisco", "soft-chai-citrico", "vienna-gelado",
    "cha-tonica-frutas-vermelhas",
})

#: Uma quantidade planejada qualquer, para comparar o consumo por fornada. Não é
#: redonda de propósito: fornada de 37 peças pega erro de arredondamento que
#: fornada de 100 esconderia.
FORNADA = Decimal("37")

#: Resolução em que duas quantidades em quilo são a mesma quantidade.
MILIGRAMA = Decimal("0.000001")


@pytest.fixture(scope="module")
def arvore():
    return ast.parse(SEED.read_text())


def _no_da_atribuicao(arvore, nome):
    for node in ast.walk(arvore):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == nome:
            return node.value
    raise AssertionError(f"`{nome}` não encontrado no seed")


@pytest.fixture(scope="module")
def fichas(arvore):
    """As fichas do seed: {ref: (rendimento, {insumo: quantidade})}.

    `literal_eval` recusa `Decimal("...")`, então o valor é lido do argumento
    da chamada, que é sempre literal.
    """
    saida: dict[str, tuple[Decimal, dict[str, Decimal]]] = {}
    for elemento in _no_da_atribuicao(arvore, "recipes_data").elts:
        campos = {
            chave.value: valor
            for chave, valor in zip(elemento.keys, elemento.values, strict=True)
            if isinstance(chave, ast.Constant)
        }
        itens = {}
        for tupla in campos["items"].elts:
            itens[tupla.elts[0].value] = _decimal_literal(tupla.elts[1])
        saida[campos["ref"].value] = (_decimal_literal(campos["batch_size"]), itens)
    return saida


@pytest.fixture(scope="module")
def capacidade(arvore):
    return ast.literal_eval(_no_da_atribuicao(arvore, "PROVISIONAL_CAPACITY_PER_DAY"))


def _decimal_literal(node) -> Decimal:
    assert isinstance(node, ast.Call) and node.func.id == "Decimal", (
        f"quantidade que não é `Decimal(\"...\")` na linha {node.lineno}"
    )
    return Decimal(node.args[0].value)


class TestFichaPorUnidade:
    def test_toda_ficha_de_peca_rende_uma_unidade(self, fichas):
        for ref in LOTE_ANTIGO:
            rendimento, _itens = fichas[ref]
            assert rendimento == Decimal("1"), f"{ref} ainda rende lote"

    def test_o_consumo_por_fornada_e_identico_ao_de_antes(self, fichas):
        """A prova do WP: reexpressar não move insumo.

        Antes: `fornada ÷ rendimento_antigo × quantidade_antiga`.
        Depois: `fornada ÷ 1 × quantidade_nova`.
        Para toda ficha, toda linha, os dois números têm de ser o MESMO.

        A igualdade das razões é conferida por multiplicação cruzada, que é
        exata; a conta da fornada aparece do lado para a mensagem de falha dizer
        quantos quilos estariam em jogo. A divisão de `Decimal` deixa cauda em
        rendimento não exato (37 ÷ 36), então ela é comparada no miligrama, que
        é fino demais para a bancada e grosso demais para a cauda.
        """
        for ref, (rendimento_antigo, itens_antigos) in LOTE_ANTIGO.items():
            rendimento_novo, itens_novos = fichas[ref]
            assert set(itens_novos) == set(itens_antigos), f"{ref} ganhou ou perdeu insumo"
            for sku, quantidade_antiga in itens_antigos.items():
                antes = FORNADA / Decimal(rendimento_antigo) * Decimal(quantidade_antiga)
                depois = FORNADA / rendimento_novo * itens_novos[sku]
                assert Decimal(quantidade_antiga) * rendimento_novo == itens_novos[sku] * Decimal(rendimento_antigo), (
                    f"{ref}/{sku}: a razão mudou — fornada de {FORNADA} consumia {antes} "
                    f"e passou a consumir {depois}"
                )
                assert antes.quantize(MILIGRAMA) == depois.quantize(MILIGRAMA), (
                    f"{ref}/{sku}: fornada de {FORNADA} consumia {antes} e passou a consumir {depois}"
                )

    def test_a_peca_por_unidade_sai_em_grama_redonda(self, fichas):
        """Nada de 0,2799 kg: a reexpressão dividiu exato, sem resto escondido."""
        for ref in LOTE_ANTIGO:
            _rendimento, itens = fichas[ref]
            for sku, quantidade in itens.items():
                gramas = quantidade * 1000
                assert gramas == gramas.to_integral_value(), f"{ref}/{sku} não fecha em grama inteira"
                assert gramas > 0, f"{ref}/{sku} zerou"

    def test_as_formulas_em_kg_nao_mudaram(self, fichas):
        for ref, (rendimento, soma, linhas) in FORMULA_EM_KG.items():
            rendimento_atual, itens = fichas[ref]
            assert rendimento_atual == Decimal(rendimento), f"{ref} mudou de rendimento"
            assert len(itens) == linhas, f"{ref} mudou de número de insumos"
            assert sum(itens.values(), Decimal("0")) == Decimal(soma), f"{ref} mudou de soma"

    def test_a_ficha_de_montagem_e_bebida_ja_era_por_unidade(self, fichas):
        for ref in MONTAGEM_E_BEBIDA:
            rendimento, _itens = fichas[ref]
            assert rendimento == Decimal("1")

    def test_as_tres_familias_cobrem_o_seed_inteiro(self, fichas):
        conhecidas = set(LOTE_ANTIGO) | set(FORMULA_EM_KG) | set(MONTAGEM_E_BEBIDA)
        assert set(fichas) == conhecidas, (
            "ficha nova ou removida no seed sem passar por este teste: "
            f"{sorted(set(fichas) ^ conhecidas)}"
        )


class TestCapacidadeProvisoria:
    """A capacidade parou de ser `3 × rendimento`, mas o NÚMERO não mudou."""

    def test_cada_ficha_tem_capacidade_declarada(self, fichas, capacidade):
        assert set(capacidade) == set(fichas), (
            "a tabela de capacidade e as fichas divergiram: "
            f"{sorted(set(capacidade) ^ set(fichas))}"
        )

    def test_a_capacidade_da_peca_e_a_mesma_de_antes(self, capacidade):
        for ref, (rendimento_antigo, _itens) in LOTE_ANTIGO.items():
            assert capacidade[ref] == int(Decimal(rendimento_antigo) * 3), (
                f"{ref}: a capacidade absoluta mudou, e a decisão dela é do dono"
            )

    def test_a_capacidade_da_formula_e_da_montagem_e_a_mesma_de_antes(self, fichas, capacidade):
        """Nessas o rendimento não mudou, então a conta antiga ainda serve de régua."""
        for ref in set(FORMULA_EM_KG) | MONTAGEM_E_BEBIDA:
            rendimento, _itens = fichas[ref]
            assert capacidade[ref] == int(rendimento * 3), f"{ref}: a capacidade absoluta mudou"

    def test_a_capacidade_nao_e_mais_derivada_do_rendimento(self, arvore):
        """Baguete a 75/dia com rendimento 1: a conta velha daria 3."""
        fonte = SEED.read_text()
        assert 'int(rd["batch_size"] * Decimal("3"))' not in fonte
        assert 'PROVISIONAL_CAPACITY_PER_DAY[rd["ref"]]' in fonte
