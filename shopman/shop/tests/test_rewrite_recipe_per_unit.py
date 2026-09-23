"""Reexpressar a ficha por unidade não pode mover um grama de insumo.

O comando divide `batch_size` e as quantidades pelo mesmo número. O que estes
testes protegem é a razão: 40 baguetes consumiam 11,2 kg de Massa Tradição
antes, e têm de consumir 11,2 kg depois. Se um dos dois lados escapar, o sistema
passa a debitar 25 vezes mais (ou menos) insumo por fornada, e o erro é mudo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


def _consumo(ficha: Recipe, fornada: Decimal) -> dict[str, Decimal]:
    """O que uma fornada de ``fornada`` peças consome — a conta do `finish`."""
    coeficiente = fornada / ficha.batch_size
    return {
        item.input_sku: (item.quantity * coeficiente).quantize(Decimal("0.000001"))
        for item in ficha.items.filter(is_optional=False)
    }


@pytest.fixture
def baguete(db):
    """A ficha como o alpha a tem: 7 kg de massa rendendo 25 baguetes."""
    Product.objects.create(sku="BF", name="Baguette de Tradition", unit="un", base_price_q=1000)
    ficha = Recipe.objects.create(
        ref="baguete", name="Baguette de Tradition", output_sku="BF", batch_size=Decimal("25"),
    )
    RecipeItem.objects.create(recipe=ficha, input_sku="MASSA-TRADICAO", quantity=Decimal("7.000"), unit="kg")
    return ficha


@pytest.fixture
def massa(db):
    """Fórmula: rende massa, e por unidade não quer dizer nada."""
    ficha = Recipe.objects.create(
        ref="massa-tradicao", name="Massa Tradição", output_sku="MASSA-TRADICAO",
        batch_size=Decimal("10"), meta={"output_unit": "kg"},
    )
    RecipeItem.objects.create(recipe=ficha, input_sku="FARINHA-T65", quantity=Decimal("6.000"), unit="kg")
    RecipeItem.objects.create(recipe=ficha, input_sku="AGUA-FILTRADA", quantity=Decimal("4.100"), unit="kg")
    return ficha


class TestReexpressao:
    def test_o_ensaio_nao_grava(self, baguete):
        call_command("rewrite_recipe_per_unit")
        baguete.refresh_from_db()
        assert baguete.batch_size == Decimal("25")
        assert baguete.items.get(input_sku="MASSA-TRADICAO").quantity == Decimal("7.000")

    def test_o_consumo_por_fornada_nao_se_move(self, baguete):
        fornada = Decimal("40")
        antes = _consumo(baguete, fornada)
        assert antes == {"MASSA-TRADICAO": Decimal("11.200000")}

        call_command("rewrite_recipe_per_unit", "--apply")

        baguete.refresh_from_db()
        assert baguete.batch_size == Decimal("1.000")
        assert baguete.items.get(input_sku="MASSA-TRADICAO").quantity == Decimal("0.280")
        assert _consumo(baguete, fornada) == antes

    def test_e_idempotente(self, baguete):
        call_command("rewrite_recipe_per_unit", "--apply")
        baguete.refresh_from_db()
        depois_da_primeira = _consumo(baguete, Decimal("40"))

        saida = _rodar(["--apply"])
        assert "1 já por unidade" in saida

        baguete.refresh_from_db()
        assert baguete.batch_size == Decimal("1.000")
        assert baguete.items.get(input_sku="MASSA-TRADICAO").quantity == Decimal("0.280")
        assert _consumo(baguete, Decimal("40")) == depois_da_primeira

    def test_a_formula_em_kg_nao_e_tocada(self, baguete, massa):
        call_command("rewrite_recipe_per_unit", "--apply")
        massa.refresh_from_db()
        assert massa.batch_size == Decimal("10.000")
        assert massa.items.get(input_sku="FARINHA-T65").quantity == Decimal("6.000")
        assert massa.items.get(input_sku="AGUA-FILTRADA").quantity == Decimal("4.100")

    def test_recorta_por_ref(self, baguete):
        outra = Recipe.objects.create(
            ref="batard", name="Bâtard", output_sku="TB", batch_size=Decimal("10"),
            meta={"output_unit": "un"},
        )
        RecipeItem.objects.create(recipe=outra, input_sku="MASSA-TRADICAO", quantity=Decimal("3.200"), unit="kg")

        call_command("rewrite_recipe_per_unit", "batard", "--apply")

        outra.refresh_from_db()
        baguete.refresh_from_db()
        assert outra.batch_size == Decimal("1.000")
        assert baguete.batch_size == Decimal("25.000")

    def test_recusa_a_ficha_cuja_linha_arredondaria_a_zero(self, baguete):
        """Uma linha da ficha não pode virar nada — e a recusa leva a rodada junto."""
        RecipeItem.objects.create(recipe=baguete, input_sku="CORANTE", quantity=Decimal("0.010"), unit="kg")
        with pytest.raises(Exception) as erro:
            call_command("rewrite_recipe_per_unit", "--apply")
        assert "Nada foi gravado" in str(erro.value)

        baguete.refresh_from_db()
        assert baguete.batch_size == Decimal("25.000")
        assert baguete.items.get(input_sku="MASSA-TRADICAO").quantity == Decimal("7.000")


class TestFornadas:
    def test_a_fornada_aberta_com_snapshot_inteiro_nao_e_tocada(self, baguete):
        """O snapshot congela rendimento e itens juntos: a razão dele já é coerente."""
        aberta = WorkOrder.objects.create(
            recipe=baguete, output_sku="BF", quantity=Decimal("40"),
            status=WorkOrder.Status.PLANNED, target_date="2026-09-10",
            meta={"_recipe_snapshot": {
                "batch_size": "25",
                "version_ref": "",
                "items": [{"input_sku": "MASSA-TRADICAO", "quantity": "7.000", "unit": "kg"}],
            }},
        )
        call_command("rewrite_recipe_per_unit", "--apply")

        aberta.refresh_from_db()
        snapshot = aberta.meta["_recipe_snapshot"]
        assert snapshot["batch_size"] == "25"
        assert snapshot["items"] == [{"input_sku": "MASSA-TRADICAO", "quantity": "7.000", "unit": "kg"}]
        # A conta que o `finish` faria: 40 ÷ 25 × 7 kg, igual antes e depois.
        coeficiente = Decimal("40") / Decimal(snapshot["batch_size"])
        assert Decimal(snapshot["items"][0]["quantity"]) * coeficiente == Decimal("11.200")

    def test_a_fornada_aberta_com_snapshot_pela_metade_recebe_o_rendimento_de_agora(self, baguete):
        """Snapshot com itens e sem rendimento cai na ficha VIVA — e cortaria os pesos."""
        aberta = WorkOrder.objects.create(
            recipe=baguete, output_sku="BF", quantity=Decimal("40"),
            status=WorkOrder.Status.PLANNED, target_date="2026-09-10",
            meta={"_recipe_snapshot": {
                "items": [{"input_sku": "MASSA-TRADICAO", "quantity": "7.000", "unit": "kg"}],
            }},
        )
        call_command("rewrite_recipe_per_unit", "--apply")

        aberta.refresh_from_db()
        snapshot = aberta.meta["_recipe_snapshot"]
        assert Decimal(snapshot["batch_size"]) == Decimal("25")
        # A pesagem faria 40 ÷ 25 × 7 kg — o mesmo de antes da reexpressão.
        coeficiente = Decimal("40") / Decimal(snapshot["batch_size"])
        assert Decimal(snapshot["items"][0]["quantity"]) * coeficiente == Decimal("11.200")

    def test_a_fornada_concluida_nao_e_tocada(self, baguete):
        concluida = WorkOrder.objects.create(
            recipe=baguete, output_sku="BF", quantity=Decimal("40"),
            status=WorkOrder.Status.PLANNED, target_date="2026-09-01",
            meta={"_recipe_snapshot": {
                "items": [{"input_sku": "MASSA-TRADICAO", "quantity": "7.000", "unit": "kg"}],
            }},
        )
        WorkOrder.objects.filter(pk=concluida.pk).update(status=WorkOrder.Status.FINISHED)

        call_command("rewrite_recipe_per_unit", "--apply")

        concluida.refresh_from_db()
        assert "batch_size" not in concluida.meta["_recipe_snapshot"]


class TestLivroDeReceitas:
    def test_relata_a_versao_publicada_que_ainda_fala_o_rendimento_antigo(self, baguete):
        """Publicar de volta desfaria a reexpressão; o comando diz o nome antes."""
        from shopman.craftsman.services import recipe_book

        recipe_book.bootstrap_entry_from_recipe(baguete)
        saida = _rodar(["--apply"])
        assert "baguete@1" in saida
        assert "rende 25" in saida


def _rodar(args: list[str]) -> str:
    from io import StringIO

    out = StringIO()
    call_command("rewrite_recipe_per_unit", *args, stdout=out)
    return out.getvalue()
