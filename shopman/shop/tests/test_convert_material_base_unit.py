"""Trocar a unidade-base de um insumo converte todo o rastro dele, ou não converte nada.

O que estes testes protegem não é o comando: é a física. Depois da troca, a
mesma quantidade de leite tem de continuar sendo a mesma quantidade de leite —
dita em quilo. Se um único número escapar, o sistema passa a ler litro como se
fosse quilo, e o erro é mudo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderItem
from shopman.stockman.models import Hold, Move, Quant, StockAlert

pytestmark = pytest.mark.django_db

#: 1 L de leite = 1,03 kg. É a densidade que o cadastro declara, e é a única
#: fonte do fator — o comando não tem tabela de densidade.
DENSIDADE = Decimal("1.03")


@pytest.fixture
def leite(db):
    return Material.objects.create(
        sku="LEITE",
        name="Leite integral",
        unit="l",
        metadata={"density_g_per_ml": 1.03},
    )


@pytest.fixture
def cenario(leite):
    """Um insumo em litro com saldo, ledger, reserva, alerta, ficha, fornada e custo."""
    quant = Quant.objects.create(sku="LEITE", _quantity=Decimal("0"))
    Move.objects.create(quant=quant, delta=Decimal("10.000"), reason="Compra inicial")
    Move.objects.create(quant=quant, delta=Decimal("-2.000"), reason="Consumo da fornada")

    Hold.objects.create(sku="LEITE", quant=quant, quantity=Decimal("2.000"), target_date="2026-09-10")
    StockAlert.objects.create(sku="LEITE", min_quantity=Decimal("20.000"))

    recipe = Recipe.objects.create(
        ref="brioche", name="Brioche", output_sku="BRIOCHE", batch_size=Decimal("10"),
    )
    item = RecipeItem.objects.create(
        recipe=recipe, input_sku="LEITE", quantity=Decimal("0.500"), unit="L",
    )

    aberta = WorkOrder.objects.create(
        recipe=recipe, output_sku="BRIOCHE", quantity=Decimal("10"),
        status=WorkOrder.Status.PLANNED, target_date="2026-09-10",
        meta={"_recipe_snapshot": {
            "batch_size": "10",
            "version_ref": "",
            "items": [{"input_sku": "LEITE", "quantity": "0.500", "unit": "L"}],
        }},
    )
    WorkOrderItem.objects.create(
        work_order=aberta, kind=WorkOrderItem.Kind.REQUIREMENT, item_ref="LEITE",
        quantity=Decimal("0.500"), unit="L", recorded_at="2026-09-03T08:00:00Z",
    )

    concluida = WorkOrder.objects.create(
        recipe=recipe, output_sku="BRIOCHE", quantity=Decimal("10"),
        status=WorkOrder.Status.PLANNED, target_date="2026-09-01",
        meta={"_recipe_snapshot": {
            "batch_size": "10",
            "version_ref": "",
            "items": [{"input_sku": "LEITE", "quantity": "0.500", "unit": "L"}],
        }},
    )
    # O status vira 'finished' por update para não passar de novo pelo save().
    WorkOrder.objects.filter(pk=concluida.pk).update(status=WorkOrder.Status.FINISHED)
    concluida.refresh_from_db()

    fornecedor = Supplier.objects.create(ref="laticinio", name="Laticínio Bom Leite")
    custo = SupplierMaterialCost.objects.create(
        supplier=fornecedor, material=leite, cost_q=500, is_preferred=True,
    )
    return {
        "quant": quant, "recipe": recipe, "item": item,
        "aberta": aberta, "concluida": concluida, "custo": custo,
    }


# ────────────────────────────────────────────────────────────────────────
# 1. O cenário completo
# ────────────────────────────────────────────────────────────────────────
def test_cada_numero_sai_convertido_e_a_unidade_vira_kg(leite, cenario):
    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    leite.refresh_from_db()
    assert leite.unit == "kg"

    quant = cenario["quant"]
    quant.refresh_from_db()
    # 8 L viram 8,24 kg — a mesma quantidade de leite, dita em quilo.
    assert quant.quantity == Decimal("8.240")

    deltas = sorted(Move.objects.filter(quant=quant).values_list("delta", flat=True))
    assert deltas == [Decimal("-2.060"), Decimal("10.300")]
    # O cache continua sendo Σ(moves.delta): o ledger é que manda.
    assert quant.quantity == sum(deltas, Decimal("0"))

    assert Hold.objects.get(sku="LEITE").quantity == Decimal("2.060")
    assert StockAlert.objects.get(sku="LEITE").min_quantity == Decimal("20.600")

    item = cenario["item"]
    item.refresh_from_db()
    assert item.quantity == Decimal("0.515")
    assert item.unit == "kg"

    aberta = cenario["aberta"]
    aberta.refresh_from_db()
    linha = aberta.meta["_recipe_snapshot"]["items"][0]
    assert linha["quantity"] == "0.515"
    assert linha["unit"] == "kg"

    item_da_fornada = WorkOrderItem.objects.get(work_order=aberta)
    assert item_da_fornada.quantity == Decimal("0.515")
    assert item_da_fornada.unit == "kg"

    custo = cenario["custo"]
    custo.refresh_from_db()
    # R$ 5,00 por litro ÷ 1,03 = R$ 4,854… → 485 centavos por quilo.
    assert custo.cost_q == 485


# ────────────────────────────────────────────────────────────────────────
# 2. Ensaio
# ────────────────────────────────────────────────────────────────────────
def test_ensaio_nao_grava_nada(leite, cenario):
    call_command("convert_material_base_unit", "LEITE", "--to", "kg")

    leite.refresh_from_db()
    assert leite.unit == "l"
    cenario["quant"].refresh_from_db()
    assert cenario["quant"].quantity == Decimal("8.000")
    cenario["item"].refresh_from_db()
    assert cenario["item"].quantity == Decimal("0.500")
    cenario["custo"].refresh_from_db()
    assert cenario["custo"].cost_q == 500
    assert not MaterialConversion.objects.exists()


# ────────────────────────────────────────────────────────────────────────
# 3. Idempotência
# ────────────────────────────────────────────────────────────────────────
def test_segunda_passada_nao_move_mais_nada(leite, cenario):
    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")
    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    cenario["quant"].refresh_from_db()
    assert cenario["quant"].quantity == Decimal("8.240")
    cenario["item"].refresh_from_db()
    assert cenario["item"].quantity == Decimal("0.515")
    cenario["custo"].refresh_from_db()
    assert cenario["custo"].cost_q == 485
    assert MaterialConversion.objects.filter(material=leite).count() == 1


# ────────────────────────────────────────────────────────────────────────
# 4. Sem densidade, recusa — e a transação inteira volta
# ────────────────────────────────────────────────────────────────────────
def test_sem_densidade_recusa_nomeando_o_que_cadastrar(db):
    azeite = Material.objects.create(sku="AZEITE", name="Azeite extra virgem", unit="l")
    quant = Quant.objects.create(sku="AZEITE", _quantity=Decimal("0"))
    Move.objects.create(quant=quant, delta=Decimal("5.000"), reason="Compra")

    with pytest.raises(CommandError) as erro:
        call_command("convert_material_base_unit", "AZEITE", "--to", "kg", "--apply")

    mensagem = str(erro.value)
    assert "AZEITE" in mensagem
    assert "density_g_per_ml" in mensagem

    azeite.refresh_from_db()
    assert azeite.unit == "l"
    quant.refresh_from_db()
    assert quant.quantity == Decimal("5.000")


def test_recusa_de_um_sku_desfaz_a_conversao_do_outro(leite, cenario):
    """Uma transação só: o insumo bom não fica convertido pela metade."""
    Material.objects.create(sku="AZEITE", name="Azeite extra virgem", unit="l")

    with pytest.raises(CommandError):
        call_command("convert_material_base_unit", "LEITE", "AZEITE", "--to", "kg", "--apply")

    leite.refresh_from_db()
    assert leite.unit == "l"
    cenario["quant"].refresh_from_db()
    assert cenario["quant"].quantity == Decimal("8.000")


def test_contagem_nao_atravessa(db):
    Material.objects.create(sku="OVOS", name="Ovos", unit="un")

    with pytest.raises(CommandError) as erro:
        call_command("convert_material_base_unit", "OVOS", "--to", "kg", "--apply")

    assert "contagem" in str(erro.value)


# ────────────────────────────────────────────────────────────────────────
# 5. História não se reescreve
# ────────────────────────────────────────────────────────────────────────
def test_fornada_concluida_mantem_o_snapshot(leite, cenario):
    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    concluida = cenario["concluida"]
    concluida.refresh_from_db()
    linha = concluida.meta["_recipe_snapshot"]["items"][0]
    assert linha["quantity"] == "0.500"
    assert linha["unit"] == "L"

    aberta = cenario["aberta"]
    aberta.refresh_from_db()
    assert aberta.meta["_recipe_snapshot"]["items"][0]["quantity"] == "0.515"


def test_item_de_fornada_concluida_nao_e_convertido(leite, cenario):
    velho = WorkOrderItem.objects.create(
        work_order=cenario["concluida"], kind=WorkOrderItem.Kind.CONSUMPTION,
        item_ref="LEITE", quantity=Decimal("0.500"), unit="L",
        recorded_at="2026-09-01T08:00:00Z",
    )

    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    velho.refresh_from_db()
    assert velho.quantity == Decimal("0.500")
    assert velho.unit == "L"


# ────────────────────────────────────────────────────────────────────────
# O mínimo do Compras é política, e política não muda de valor
# ────────────────────────────────────────────────────────────────────────
def test_o_minimo_declarado_no_compras_acompanha_a_troca(leite, cenario):
    leite.metadata = {**leite.metadata, "purchase": {"min_stock": "20"}}
    leite.save(update_fields=["metadata"])

    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    leite.refresh_from_db()
    assert leite.metadata["purchase"]["min_stock"] == "20.600"


# ────────────────────────────────────────────────────────────────────────
# 6 e 7. A conversão da unidade antiga
# ────────────────────────────────────────────────────────────────────────
def test_a_conversao_litro_nasce_com_o_fator_e_o_carimbo(leite, cenario):
    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    conversao = MaterialConversion.objects.get(material=leite, label="litros")
    assert conversao.to_base_factor == Decimal("1.030000")
    assert conversao.kind == MaterialConversion.Kind.APPROXIMATE
    assert conversao.supplier_id is None


def test_mesma_dimensao_converte_pela_fisica_e_nao_cria_conversao(db):
    canela = Material.objects.create(sku="CANELA", name="Canela", unit="g")
    quant = Quant.objects.create(sku="CANELA", _quantity=Decimal("0"))
    Move.objects.create(quant=quant, delta=Decimal("2500.000"), reason="Compra")

    call_command("convert_material_base_unit", "CANELA", "--to", "kg", "--apply")

    canela.refresh_from_db()
    assert canela.unit == "kg"
    quant.refresh_from_db()
    assert quant.quantity == Decimal("2.500")
    assert not MaterialConversion.objects.filter(material=canela).exists()


def test_embalagem_ja_cadastrada_e_reescalada(leite, cenario):
    """'Galão' valia 5 litros; depois da troca ele vale 5,15 quilos."""
    MaterialConversion.objects.create(
        material=leite, label="Galão", to_base_factor=Decimal("5"),
        kind=MaterialConversion.Kind.CONVENTIONAL,
    )

    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    galao = MaterialConversion.objects.get(material=leite, label="Galão")
    assert galao.to_base_factor == Decimal("5.150000")
    # O preço da embalagem é o número da nota e não muda: quem mudou foi o fator.
    assert galao.kind == MaterialConversion.Kind.CONVENTIONAL


def test_custo_de_embalagem_nao_e_redividido(leite, cenario):
    galao = MaterialConversion.objects.create(
        material=leite, label="Galão", to_base_factor=Decimal("5"),
    )
    outro = Supplier.objects.create(ref="distribuidora", name="Distribuidora")
    custo = SupplierMaterialCost.objects.create(
        supplier=outro, material=leite, conversion=galao, cost_q=2500,
    )

    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    custo.refresh_from_db()
    assert custo.cost_q == 2500


# ────────────────────────────────────────────────────────────────────────
# 8. A ficha continua válida
# ────────────────────────────────────────────────────────────────────────
def test_a_ficha_continua_validando_depois_da_troca(leite, cenario):
    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply")

    recipe = cenario["recipe"]
    recipe.refresh_from_db()
    recipe.full_clean()
    # É o clean do ITEM que exige a unidade do cadastro: ficha não convertida
    # deixa de validar aqui, e é isso que torna a troca segura.
    for item in recipe.items.all():
        item.full_clean()


def test_no_bridge_converte_sem_deixar_a_conversao_para_tras(leite, cenario):
    """Insumo fora da nota (água de torneira) não ganha ponte: seria anotação sem informação.

    A tela de separação anota a linha pela conversão declarada de menor fator, e
    para um insumo cuja densidade é 1 a anotação repetiria o mesmo número com um
    ``≈`` na frente, mentindo sobre a precisão.
    """
    call_command("convert_material_base_unit", "LEITE", "--to", "kg", "--apply", "--no-bridge")

    leite.refresh_from_db()
    assert leite.unit == "kg"
    assert not MaterialConversion.objects.filter(material=leite, label="litros").exists()
    # A conversão do saldo acontece do mesmo jeito: a ponte é só o cadastro da compra.
    quant = Quant.objects.get(sku="LEITE")
    assert quant.quantity == Decimal("8.240")
