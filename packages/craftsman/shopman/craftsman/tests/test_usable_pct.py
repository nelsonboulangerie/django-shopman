"""Aproveitamento do insumo: a líquida entra no produto, a bruta sai do estoque.

A ficha da casa («Ficha Técnica - Maysa») declara três números por ingrediente —
líquida, aproveitamento e bruta. Aqui se cobra que o terceiro seja sempre
DERIVADO, que o default não mude nada do que já existe, e que a fornada requeira
e consuma a bruta enquanto o rótulo continua lendo a líquida.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrderItem

pytestmark = pytest.mark.django_db


def _ficha(ref="recheio-cebola", rende="2.700", **meta) -> Recipe:
    return Recipe.objects.create(
        ref=ref, name=ref, output_sku=ref.upper(), batch_size=Decimal(rende),
        meta={"output_unit": "kg", **meta},
    )


# ------------------------------------------------------------------ a derivada


def test_sem_declarar_nada_a_bruta_e_a_liquida():
    """Default 100% é o comportamento de antes deste campo — migração no-op."""
    ficha = _ficha()
    item = RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("1.800"), unit="kg",
    )
    assert item.usable_pct == Decimal("100.00")
    assert item.gross_quantity == item.quantity


def test_a_bruta_e_a_liquida_dividida_pelo_aproveitamento():
    """Os números da ficha dela: 0,200 kg de cebola limpa a 84% = 0,238 brutos."""
    ficha = _ficha()
    item = RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_pct=Decimal("84.00"),
    )
    assert item.gross_quantity == Decimal("0.238")


@pytest.mark.parametrize(
    "pct,liquida,bruta",
    [
        ("60.00", "0.002", "0.003"),   # tomilho, só folhas
        ("40.00", "0.056", "0.140"),   # suco de limão
        ("100.00", "0.035", "0.035"),  # bacon, nada se perde
    ],
)
def test_os_fatores_da_ficha_da_casa(pct, liquida, bruta):
    ficha = _ficha()
    item = RecipeItem.objects.create(
        recipe=ficha, input_sku=f"X{pct}", quantity=Decimal(liquida), unit="kg",
        usable_pct=Decimal(pct),
    )
    assert item.gross_quantity == Decimal(bruta)


def test_a_bruta_nunca_e_gravada():
    """Campo derivado que vira coluna envelhece sozinho; este é property."""
    assert "gross_quantity" not in {f.name for f in RecipeItem._meta.get_fields()}


# ----------------------------------------------------------------- as recusas


@pytest.mark.parametrize("pct", ["0.00", "-1.00", "100.01", "150.00"])
def test_aproveitamento_fora_da_faixa_e_recusado_pelo_BANCO(pct):
    """A trava é do banco, não só do form: quem escreve por shell também erra.

    Zero divide por zero; acima de 100 faria a bruta ser MENOR que a líquida —
    limpar criando matéria.
    """
    ficha = _ficha()
    with pytest.raises(IntegrityError), transaction.atomic():
        RecipeItem.objects.create(
            recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("1"), unit="kg",
            usable_pct=Decimal(pct),
        )


# ------------------------------------------------- o que NÃO muda (o rótulo)


def test_o_rendimento_continua_comparando_com_a_LIQUIDA():
    """Misturar não cria matéria — e a bacia recebe o que já foi limpo.

    Se o invariante passasse a somar a bruta, uma ficha com muita perda passaria
    a "caber" sem que nada nela mudasse, e o defeito que ele pega — debitar menos
    insumo do que o padeiro usa — voltaria pela porta dos fundos.
    """
    ficha = _ficha(rende="1.000")
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.900"), unit="kg",
        usable_pct=Decimal("50.00"),  # bruta = 1,800 kg; líquida = 0,900
    )
    with pytest.raises(ValidationError, match="Misturar não cria matéria"):
        ficha.full_clean()


# ------------------------------------------------------------- a travessia


def _fornada(ficha, quantidade="2.700"):
    return craft.plan(ficha, Decimal(quantidade))


def test_o_snapshot_congela_os_dois_numeros():
    ficha = _ficha()
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_pct=Decimal("84.00"),
    )
    wo = _fornada(ficha)
    item = wo.meta["_recipe_snapshot"]["items"][0]
    assert item["quantity"] == "0.200"
    assert item["gross_quantity"] == "0.238"
    assert item["usable_pct"] == "84.00"


def test_a_fornada_consome_a_BRUTA_e_guarda_a_liquida_no_meta():
    ficha = _ficha(rende="1.000")
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_pct=Decimal("84.00"),
    )
    wo = _fornada(ficha, "1.000")
    craft.finish(wo, Decimal("1.000"))

    consumo = wo.items.get(kind=WorkOrderItem.Kind.CONSUMPTION, item_ref="CEBOLA-ROXA")
    assert consumo.quantity == Decimal("0.238"), "o estoque desce o que sai da caixa"
    assert consumo.meta["net_quantity"] == "0.200", "e a líquida fica, para a tela e a auditoria"
    assert consumo.meta["approximate"] is True, "ADR-024 R3: o ≈ não se dissolve"


def test_snapshot_ANTIGO_sem_a_bruta_cai_na_liquida():
    """Fornada planejada antes deste campo não pode mudar de número no meio.

    O `_recipe_snapshot` existe justamente para o `finish` usar a ficha como ela
    era; uma fornada em voo tem de terminar com os números com que começou.
    """
    ficha = _ficha(rende="1.000")
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_pct=Decimal("84.00"),
    )
    wo = _fornada(ficha, "1.000")
    # Reescreve o snapshot na forma antiga, sem a bruta nem o aproveitamento.
    wo.meta["_recipe_snapshot"]["items"] = [
        {"input_sku": "CEBOLA-ROXA", "quantity": "0.200", "unit": "kg"}
    ]
    wo.save(update_fields=["meta"])

    craft.finish(wo, Decimal("1.000"))
    consumo = wo.items.get(kind=WorkOrderItem.Kind.CONSUMPTION, item_ref="CEBOLA-ROXA")
    assert consumo.quantity == Decimal("0.200")
    assert consumo.meta == {}, "sem aproveitamento declarado, nenhum rastro a deixar"


def test_aproveitamento_de_100_nao_deixa_rastro_no_meta():
    """`meta` que repete o óbvio em toda linha de toda fornada é ruído com custo."""
    ficha = _ficha(rende="1.000")
    RecipeItem.objects.create(
        recipe=ficha, input_sku="BACON", quantity=Decimal("0.035"), unit="kg",
    )
    wo = _fornada(ficha, "1.000")
    craft.finish(wo, Decimal("1.000"))
    assert wo.items.get(kind=WorkOrderItem.Kind.CONSUMPTION).meta == {}
