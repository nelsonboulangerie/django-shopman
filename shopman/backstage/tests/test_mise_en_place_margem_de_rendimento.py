"""A margem de rendimento na lista de separação — com o motivo à vista.

Bloco E do ``WP-FICHA-DE-PRODUTO-E-PROMESSA``. A aritmética (meia divisão da
balança, perda fixa da masseira, colchão que encolhe) mora no pacote e é
provada em ``packages/craftsman/.../tests/test_yield_margin.py``. Aqui se prova
o que a TELA promete:

* os gramas a mais aparecem, e aparecem com o motivo — nada de número que
  cresceu sozinho;
* o cabeçalho explica a margem mesmo no modo explodido, em que a linha do
  preparo já não existe;
* e o ledger continua limpo depois de a fornada fechar: a margem é do plano,
  não do fato.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrderItem

from shopman.backstage.projections.production import build_production_mise_en_place

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def massa(db):
    """A fórmula: 7 kg de massa, com 150 g de perda de masseira declarada."""
    recipe = Recipe.objects.create(
        ref="massa-tradicao",
        name="Massa Tradição",
        output_sku="MASSA-TRADICAO",
        batch_size=D("7"),
        meta={"output_unit": "kg", "mixer_loss_g": "150"},
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity="4.2", unit="kg")
    RecipeItem.objects.create(recipe=recipe, input_sku="AGUA", quantity="2.8", unit="kg")
    return recipe


@pytest.fixture
def baguete(massa):
    """A peça: 25 baguetes de 280 g a partir de 7 kg de massa."""
    recipe = Recipe.objects.create(
        ref="baguete", name="Baguete", output_sku="BAGUETE",
        batch_size=D("25"), meta={"output_unit": "un"},
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="MASSA-TRADICAO", quantity="7", unit="kg")
    return recipe


def _line(projection, sku):
    return next(line for line in projection.lines if line.sku == sku)


class TestAMargemApareceComOMotivo:
    def test_linha_da_massa_mostra_os_gramas_a_mais(self, baguete):
        craft.plan(baguete, 25, date=date.today())

        projection = build_production_mise_en_place(selected_date=date.today())
        massa_line = _line(projection, "MASSA-TRADICAO")

        # 7 kg + 25 g de arredondamento + 150 g de masseira + ~8,66 g de folga
        assert massa_line.quantity_display == "7,184 kg"
        assert massa_line.margin_display == "+ 0,184 kg de margem"

    def test_o_motivo_nomeia_as_tres_parcelas(self, baguete):
        """Três parcelas com formas diferentes; uma porcentagem só erraria as três."""
        craft.plan(baguete, 25, date=date.today())

        motivo = _line(
            build_production_mise_en_place(selected_date=date.today()), "MASSA-TRADICAO"
        ).margin_reason

        assert "25 peças × meia divisão da balança" in motivo
        assert "perda da masseira" in motivo
        assert "folga de variação" in motivo

    def test_cabecalho_explica_a_margem(self, baguete):
        craft.plan(baguete, 25, date=date.today())

        projection = build_production_mise_en_place(selected_date=date.today())
        assert projection.yield_margin_applied
        assert "meia divisão da balança" in projection.yield_margin_note
        assert "massa velha de amanhã" in projection.yield_margin_note

    def test_no_modo_explodido_o_cabecalho_e_o_unico_lugar(self, baguete):
        """A linha do preparo some, a margem continua na farinha — e é dita."""
        craft.plan(baguete, 25, date=date.today())

        expandido = build_production_mise_en_place(selected_date=date.today(), expand=True)

        assert [line.sku for line in expandido.lines] == ["AGUA", "FARINHA"]
        assert expandido.yield_margin_applied
        # 4,2/7 da massa é farinha; a margem cascateia na mesma proporção.
        assert _line(expandido, "FARINHA").quantity_display == "4,31 kg"
        assert _line(expandido, "FARINHA").margin_display == ""

    def test_materia_prima_direta_nao_ganha_margem(self, db):
        """Não se decide quanto FAZER de farinha — inflar aqui inflaria a compra."""
        recipe = Recipe.objects.create(
            ref="focaccia", name="Focaccia", output_sku="FOCACCIA",
            batch_size=D("10"), meta={"output_unit": "un"},
        )
        RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity="3", unit="kg")
        craft.plan(recipe, 10, date=date.today())

        projection = build_production_mise_en_place(selected_date=date.today())
        farinha = _line(projection, "FARINHA")
        assert farinha.quantity_display == "3 kg"
        assert farinha.margin_display == ""
        assert not projection.yield_margin_applied


class TestOLedgerNaoLevaAMargem:
    def test_a_fornada_fecha_consumindo_a_FICHA_e_nao_o_PLANO(self, baguete):
        """A lista de separação pede 7,184 kg; o ledger baixa 7,000 kg.

        É a prova de que a margem não escorreu para o fato. O consumo nasce em
        ``CraftExecution.finish`` (snapshot congelado da ficha) e é ele que a
        ponte ``craftsman/contrib/stockman`` baixa do ledger — nenhum dos dois
        passa pela projection nem por ``craft.needs()``. Se escorresse, o
        sistema debitaria 184 g a mais de massa por fornada, todo dia, e a
        sugestão de compra nasceria inflada na mesma proporção.
        """
        wo = craft.plan(baguete, 25, date=date.today())

        plano = _line(
            build_production_mise_en_place(selected_date=date.today()), "MASSA-TRADICAO"
        )
        assert plano.quantity_display == "7,184 kg"

        craft.start(wo, quantity=25)
        wo.refresh_from_db()
        craft.finish(wo, finished=25)

        consumo = list(wo.items.filter(kind=WorkOrderItem.Kind.CONSUMPTION))
        assert [(item.item_ref, item.quantity) for item in consumo] == [
            ("MASSA-TRADICAO", D("7.000")),
        ]
