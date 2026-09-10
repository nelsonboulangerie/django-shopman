"""Margem de segurança do rendimento das massas (bloco E do WP-FICHA).

O que estes testes fixam, e por que cada um existe:

* o excesso esperado por peça é **meia divisão** da balança, não uma divisão —
  supor a divisão inteira joga fora 100 g por fornada de 100 pâtons;
* a margem escala com o **número de peças**, não com a massa;
* a perda da masseira é **fixa por fornada**, não por peça nem por work order;
* o colchão de variância **encolhe em proporção** quando a fornada cresce;
* e o mais importante: **o consumo lançado no ledger NÃO leva a margem**. A
  margem é do plano; o consumo é do fato.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrderItem
from shopman.craftsman.service import craft
from shopman.craftsman.services.yield_margin import compute_yield_margin

D = Decimal

# Divisão da balança da casa, em gramas.
SCALE_G = D("2")


@pytest.fixture
def tomorrow():
    return date(2026, 2, 25)


@pytest.fixture
def massa(db):
    """A fórmula: 7 kg de massa a partir de 4,2 kg de farinha e 2,8 kg de água.

    Sem perda de masseira declarada nesta ficha — cada teste declara a sua
    quando o número da masseira importa.
    """
    recipe = Recipe.objects.create(
        ref="massa-tradicao",
        name="Massa Tradição",
        output_sku="MASSA-TRADICAO",
        batch_size=D("7"),
        meta={"output_unit": "kg", "mixer_loss_g": "0"},
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity=D("4.2"), unit="kg")
    RecipeItem.objects.create(recipe=recipe, input_sku="AGUA", quantity=D("2.8"), unit="kg")
    return recipe


def _piece_recipe(*, ref, sku, pieces, dough_kg, dough_sku="MASSA-TRADICAO"):
    """Ficha de PEÇA: rende ``pieces`` unidades a partir de ``dough_kg`` de massa."""
    recipe = Recipe.objects.create(
        ref=ref,
        name=ref,
        output_sku=sku,
        batch_size=D(str(pieces)),
        meta={"output_unit": "un"},
    )
    RecipeItem.objects.create(recipe=recipe, input_sku=dough_sku, quantity=D(str(dough_kg)), unit="kg")
    return recipe


def _by_ref(needs):
    return {need.item_ref: need for need in needs}


# ══════════════════════════════════════════════════════════════
# A ARITMÉTICA — meia divisão, e não uma
# ══════════════════════════════════════════════════════════════


class TestMeiaDivisao:
    def test_excesso_esperado_e_meia_divisao_nao_a_divisao(self):
        """100 pâtons de 60 g em balança de 2 g: 100 g, não 200 g.

        Este é o número do dono. Com a régua "nunca abaixo do alvo", a peça cai
        em ``[W, W+d)`` e o excesso MÉDIO é ``d/2``. Orçar ``d`` por peça
        desperdiça exatamente meia divisão por peça — 100 g por fornada aqui, e
        essa massa vira sobra todo dia.
        """
        margin = compute_yield_margin(
            pieces=100, unit="g", scale_precision=SCALE_G, mixer_loss_g=0, sigmas=0,
        )

        assert margin.rounding == D("100")

        ingenuo = D("100") * SCALE_G  # supor a divisão INTEIRA por peça
        assert ingenuo - margin.rounding == D("100")

    def test_margem_escala_com_pecas_e_nao_com_a_massa(self, db, massa, tomorrow):
        """Mesmos 7 kg de massa: 25 peças pedem 25 g, 100 peças pedem 100 g.

        É por isso que uma porcentagem única não serve. A porcentagem olha a
        massa; o arredondamento olha quantas vezes a balança foi lida.
        """
        depois = date(2026, 2, 26)
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        mini = _piece_recipe(ref="mini", sku="MINI", pieces=100, dough_kg=7)
        craft.plan(baguete, 25, date=tomorrow)
        craft.plan(mini, 100, date=depois)

        pecas_grandes = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-TRADICAO"]
        pecas_pequenas = _by_ref(craft.needs(depois, yield_margin=True))["MASSA-TRADICAO"]

        # Massa igual nos dois dias (7 kg); o arredondamento quadruplica com N.
        assert pecas_grandes.quantity - pecas_grandes.margin.total == D("7.000")
        assert pecas_pequenas.quantity - pecas_pequenas.margin.total == D("7.000")
        assert pecas_grandes.margin.rounding == D("0.025")
        assert pecas_pequenas.margin.rounding == D("0.100")

    def test_colchao_de_variancia_encolhe_em_proporcao(self):
        """Quadruplicar a fornada dobra o colchão — logo, ele encolhe pela metade.

        A soma de N arredondamentos tem desvio ``d·√(N/12)``: cresce com √N
        enquanto o arredondamento cresce com N. A peça isolada é incerta; a
        fornada não é, e é por isso que a margem se orça na fornada.
        """
        pequena = compute_yield_margin(
            pieces=25, unit="g", scale_precision=SCALE_G, mixer_loss_g=0, sigmas=3,
        )
        grande = compute_yield_margin(
            pieces=100, unit="g", scale_precision=SCALE_G, mixer_loss_g=0, sigmas=3,
        )

        # 25 peças: 3 × 2 g × √(25/12) ≈ 8,66 g
        assert pequena.variance.quantize(D("0.01")) == D("8.66")
        assert grande.variance.quantize(D("0.01")) == D("17.32")

        # O colchão dobrou enquanto a fornada quadruplicou: por peça, metade.
        assert (grande.variance / grande.pieces) < (pequena.variance / pequena.pieces)
        assert (grande.variance / D("4")).quantize(D("0.001")) == (
            pequena.variance / D("2")
        ).quantize(D("0.001"))

    def test_margem_ignora_unidade_que_nao_e_massa(self):
        """Contagem e volume não recebem margem de rendimento — não há o que dividir."""
        assert compute_yield_margin(pieces=10, unit="un", scale_precision=SCALE_G) is None
        assert compute_yield_margin(pieces=0, unit="g", scale_precision=SCALE_G) is None


# ══════════════════════════════════════════════════════════════
# A PERDA DA MASSEIRA — fixa por fornada
# ══════════════════════════════════════════════════════════════


class TestPerdaDaMasseira:
    def test_perda_e_fixa_por_fornada_e_nao_por_peca(self):
        """Dobrar as peças não dobra o filme de massa que fica na bacia."""
        pequena = compute_yield_margin(pieces=25, unit="g", mixer_loss_g=150, sigmas=0)
        grande = compute_yield_margin(pieces=250, unit="g", mixer_loss_g=150, sigmas=0)

        assert pequena.mixer_loss == D("150")
        assert grande.mixer_loss == D("150")
        # O arredondamento, esse sim, decuplicou.
        assert grande.rounding == pequena.rounding * 10

    def test_duas_ordens_da_mesma_massa_pagam_uma_masseira_so(self, db, massa, tomorrow):
        """Baguete e bâtard da mesma Massa Tradição são UMA mistura.

        Se a margem fosse orçada por work order, a casa faria massa para duas
        bacias que não existem.
        """
        Recipe.objects.filter(ref="massa-tradicao").update(meta={"output_unit": "kg", "mixer_loss_g": "150"})
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        batard = _piece_recipe(ref="batard", sku="BATARD", pieces=20, dough_kg=6.4)
        craft.plan(baguete, 25, date=tomorrow)
        craft.plan(batard, 20, date=tomorrow)

        margin = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-TRADICAO"].margin

        assert margin.pieces == D("45")
        assert margin.mixer_loss == D("0.150")  # uma bacia, não duas
        assert margin.rounding == D("45") * D("0.002") / 2

    def test_perda_declarada_na_ficha_vence_o_padrao(self, db, massa, tomorrow):
        """``Recipe.meta["mixer_loss_g"]`` é a palavra da ficha; a setting é o resto."""
        Recipe.objects.filter(ref="massa-tradicao").update(meta={"output_unit": "kg", "mixer_loss_g": "80"})
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        craft.plan(baguete, 25, date=tomorrow)

        margin = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-TRADICAO"].margin
        assert margin.mixer_loss == D("0.080")

    @override_settings(CRAFTSMAN={"MIXER_LOSS_G": Decimal("200")})
    def test_ficha_sem_declaracao_cai_no_padrao_da_casa(self, db, tomorrow):
        recipe = Recipe.objects.create(
            ref="massa-sem-perda",
            name="Massa sem perda declarada",
            output_sku="MASSA-X",
            batch_size=D("7"),
            meta={"output_unit": "kg"},
        )
        RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity=D("7"), unit="kg")
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7, dough_sku="MASSA-X")
        craft.plan(baguete, 25, date=tomorrow)

        margin = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-X"].margin
        assert margin.mixer_loss == D("0.200")


# ══════════════════════════════════════════════════════════════
# A BALANÇA É CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════


class TestPrecisaoDaBalanca:
    def test_padrao_da_casa_e_dois_gramas(self, db, massa, tomorrow):
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        craft.plan(baguete, 25, date=tomorrow)

        margin = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-TRADICAO"].margin
        assert margin.scale_precision == D("0.002")  # 2 g, dito em kg

    @override_settings(CRAFTSMAN={"SCALE_PRECISION_G": Decimal("5")})
    def test_trocar_a_balanca_e_uma_linha_de_settings(self, db, massa, tomorrow):
        """A precisão é do EQUIPAMENTO, não da ficha — por isso mora no conf."""
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        craft.plan(baguete, 25, date=tomorrow)

        margin = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-TRADICAO"].margin
        assert margin.scale_precision == D("0.005")
        assert margin.rounding == D("25") * D("0.005") / 2


# ══════════════════════════════════════════════════════════════
# ONDE A MARGEM ENTRA — e onde ela NÃO entra
# ══════════════════════════════════════════════════════════════


class TestOndeAMargemEntra:
    def test_needs_sem_margem_e_o_padrao(self, db, massa, tomorrow):
        """Opt-in: nenhum consumidor antigo ganha gramas sem pedir."""
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        craft.plan(baguete, 25, date=tomorrow)

        need = _by_ref(craft.needs(tomorrow))["MASSA-TRADICAO"]
        assert need.quantity == D("7.000")
        assert need.margin is None

    def test_margem_soma_na_quantidade_e_diz_o_motivo(self, db, massa, tomorrow):
        Recipe.objects.filter(ref="massa-tradicao").update(meta={"output_unit": "kg", "mixer_loss_g": "150"})
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        craft.plan(baguete, 25, date=tomorrow)

        need = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-TRADICAO"]

        # 7 kg + 25 g de arredondamento + 150 g de masseira + ~8,66 g de folga
        assert need.quantity.quantize(D("0.001")) == D("7.184")
        assert need.quantity == D("7") + need.margin.total
        reason = need.margin.reason()
        assert "meia divisão da balança" in reason
        assert "perda da masseira" in reason
        assert "folga de variação" in reason

    def test_materia_prima_nao_recebe_margem(self, db, tomorrow):
        """Não se decide "quanto fazer" de sal.

        Inflar a linha de matéria-prima na lista de separação inflaria a
        sugestão de compra todo dia, por um excesso que não é consumo.
        """
        recipe = _piece_recipe(ref="focaccia", sku="FOCACCIA", pieces=10, dough_kg=3, dough_sku="FARINHA")
        craft.plan(recipe, 10, date=tomorrow)

        need = _by_ref(craft.needs(tomorrow, yield_margin=True))["FARINHA"]
        assert need.margin is None
        assert need.quantity == D("3.000")

    def test_ficha_que_rende_massa_nao_porciona_nada(self, db, massa, tomorrow):
        """Planejar a fórmula direto (7 kg de massa) não gera margem: não há peça."""
        craft.plan(massa, 7, date=tomorrow)

        needs = craft.needs(tomorrow, yield_margin=True)
        assert all(need.margin is None for need in needs)

    def test_margem_cascateia_para_a_materia_prima_no_modo_expandido(self, db, massa, tomorrow):
        """Fazer mais massa de fato pede mais farinha — a física não negocia.

        No expandido a linha do preparo some (foi explodida), então a margem
        aparece embutida na matéria-prima, e é a projection que carrega a
        explicação no cabeçalho.
        """
        Recipe.objects.filter(ref="massa-tradicao").update(meta={"output_unit": "kg", "mixer_loss_g": "150"})
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        craft.plan(baguete, 25, date=tomorrow)

        plano = _by_ref(craft.needs(tomorrow, expand=True, yield_margin=True))
        fato = _by_ref(craft.needs(tomorrow, expand=True))

        # A ficha da massa é 60% farinha (4,2 de 7 kg); a margem cascateia na
        # mesma proporção, sem ninguém redeclarar nada.
        assert "MASSA-TRADICAO" not in plano
        assert plano["FARINHA"].quantity > fato["FARINHA"].quantity
        proporcao = (plano["FARINHA"].quantity - fato["FARINHA"].quantity) / D("0.6")
        assert proporcao.quantize(D("0.001")) == D("0.184")


# ══════════════════════════════════════════════════════════════
# O LEDGER NÃO É CONTAMINADO — a margem é do plano, não do fato
# ══════════════════════════════════════════════════════════════


class TestLedgerNaoLevaAMargem:
    def test_consumo_congelado_no_finish_ignora_a_margem(self, db, massa, tomorrow):
        """O que baixa do estoque é a ficha, não o plano.

        ``CraftExecution.finish`` congela os ``WorkOrderItem`` de consumo a
        partir do snapshot da ficha, e é EXATAMENTE essa lista que
        ``contrib.stockman.handlers._consume_materials`` baixa do ledger.
        Nenhum dos dois passa por ``craft.needs()``.

        Se a margem escorresse para cá, o sistema debitaria 184 g de massa a
        mais por fornada, todo dia, e a sugestão de compra nasceria inflada na
        mesma proporção — o erro silencioso que só apareceria no inventário
        meses depois.
        """
        Recipe.objects.filter(ref="massa-tradicao").update(meta={"output_unit": "kg", "mixer_loss_g": "150"})
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        wo = craft.plan(baguete, 25, date=tomorrow)

        planejado = _by_ref(craft.needs(tomorrow, yield_margin=True))["MASSA-TRADICAO"]
        assert planejado.margin is not None
        assert planejado.quantity > D("7")

        craft.start(wo, quantity=25, expected_rev=wo.rev)
        wo.refresh_from_db()
        craft.finish(wo, finished=25, expected_rev=wo.rev)

        consumo = list(wo.items.filter(kind=WorkOrderItem.Kind.CONSUMPTION))
        assert [(item.item_ref, item.quantity) for item in consumo] == [
            ("MASSA-TRADICAO", D("7.000")),
        ]

    def test_requisito_registrado_tambem_e_o_da_ficha(self, db, massa, tomorrow):
        """O REQUIREMENT é a foto da ficha; margem ali seria a mesma mentira."""
        baguete = _piece_recipe(ref="baguete", sku="BAGUETE", pieces=25, dough_kg=7)
        wo = craft.plan(baguete, 25, date=tomorrow)
        craft.start(wo, quantity=25, expected_rev=wo.rev)
        wo.refresh_from_db()
        craft.finish(wo, finished=25, expected_rev=wo.rev)

        requisito = wo.items.get(kind=WorkOrderItem.Kind.REQUIREMENT)
        assert requisito.quantity == D("7.000")
