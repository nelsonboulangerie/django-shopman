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
    """1 é o valor VERDADEIRO de quase todo insumo: farinha e sal não têm casca.

    O default não está aqui para preservar o que já existe — é o que a ficha diz
    quando nada se perde no preparo.
    """
    ficha = _ficha()
    item = RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("1.800"), unit="kg",
    )
    assert item.usable_factor == Decimal("1")
    assert item.gross_quantity == item.quantity


def test_a_bruta_e_a_liquida_dividida_pelo_aproveitamento():
    """Os números da ficha dela: 0,200 kg de cebola limpa a 84% = 0,238 brutos."""
    ficha = _ficha()
    item = RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_factor=Decimal("0.84"),
    )
    assert item.gross_quantity == Decimal("0.238")


@pytest.mark.parametrize(
    "fator,liquida,bruta",
    [
        ("0.60", "0.002", "0.003"),   # tomilho, só folhas
        ("0.40", "0.056", "0.140"),   # suco de limão
        ("1", "0.035", "0.035"),      # bacon, nada se perde
    ],
)
def test_os_fatores_da_ficha_da_casa(fator, liquida, bruta):
    ficha = _ficha()
    item = RecipeItem.objects.create(
        recipe=ficha, input_sku=f"X{fator}", quantity=Decimal(liquida), unit="kg",
        usable_factor=Decimal(fator),
    )
    assert item.gross_quantity == Decimal(bruta)


def test_a_bruta_nunca_e_gravada():
    """Campo derivado que vira coluna envelhece sozinho; este é property."""
    assert "gross_quantity" not in {f.name for f in RecipeItem._meta.get_fields()}


# ----------------------------------------------------------------- as recusas


@pytest.mark.parametrize(
    "fator",
    [
        "0",        # divide por zero
        "-0.01",
        "1.0001",
        "1.5",
        # ⚠️ O caso do mundo real: o "fator de correção" da cozinha é o INVERSO
        # deste campo. Quem vem da ficha de chef digita 1,19 onde o sistema
        # espera 0,84, e os dois números são plausíveis — só a faixa fechada
        # distingue. Se guardássemos o FC, a faixa seria [1, ∞) e este engano
        # passaria calado, fazendo o estoque descer 41% a menos.
        "1.19",
    ],
)
def test_aproveitamento_fora_da_faixa_e_recusado_pelo_BANCO(fator):
    """A trava é do banco, não só do form: quem escreve por shell também erra.

    Zero divide por zero; acima de 1 faria a bruta ser MENOR que a líquida —
    limpar criando matéria.
    """
    ficha = _ficha()
    with pytest.raises(IntegrityError), transaction.atomic():
        RecipeItem.objects.create(
            recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("1"), unit="kg",
            usable_factor=Decimal(fator),
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
        usable_factor=Decimal("0.50"),  # bruta = 1,800 kg; líquida = 0,900
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
        usable_factor=Decimal("0.84"),
    )
    wo = _fornada(ficha)
    item = wo.meta["_recipe_snapshot"]["items"][0]
    assert item["quantity"] == "0.200"
    assert item["gross_quantity"] == "0.238"
    assert item["usable_factor"] == "0.8400"  # 4 casas: o Decimal do banco


def test_a_fornada_consome_a_BRUTA_e_guarda_a_liquida_no_meta():
    ficha = _ficha(rende="1.000")
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_factor=Decimal("0.84"),
    )
    wo = _fornada(ficha, "1.000")
    craft.finish(wo, Decimal("1.000"))

    consumo = wo.items.get(kind=WorkOrderItem.Kind.CONSUMPTION, item_ref="CEBOLA-ROXA")
    assert consumo.quantity == Decimal("0.238"), "o estoque desce o que sai da caixa"
    assert consumo.meta["net_quantity"] == "0.200", "e a líquida fica, para a tela e a auditoria"
    assert consumo.meta["approximate"] is True, "ADR-024 R3: o ≈ não se dissolve"


def test_snapshot_SEM_a_bruta_faz_o_finish_PARAR():
    """Antes do go-live não há BOM congelado a preservar — ausência é defeito.

    A tentação seria cair na líquida "para não quebrar fornada antiga". Isso
    debitaria menos insumo do que o padeiro usa, que é exatamente o defeito que
    `_validate_mass_balance` existe para pegar — e calado, que é o pior tipo.
    """
    from shopman.craftsman import CraftError

    ficha = _ficha(rende="1.000")
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_factor=Decimal("0.84"),
    )
    wo = _fornada(ficha, "1.000")
    wo.meta["_recipe_snapshot"]["items"] = [
        {"input_sku": "CEBOLA-ROXA", "quantity": "0.200", "unit": "kg"}
    ]
    wo.save(update_fields=["meta"])

    with pytest.raises(CraftError) as erro:
        craft.finish(wo, Decimal("1.000"))
    assert "gross_quantity" in str(erro.value.data)


def test_aproveitamento_de_100_nao_deixa_rastro_no_meta():
    """`meta` que repete o óbvio em toda linha de toda fornada é ruído com custo."""
    ficha = _ficha(rende="1.000")
    RecipeItem.objects.create(
        recipe=ficha, input_sku="BACON", quantity=Decimal("0.035"), unit="kg",
    )
    wo = _fornada(ficha, "1.000")
    craft.finish(wo, Decimal("1.000"))
    assert wo.items.get(kind=WorkOrderItem.Kind.CONSUMPTION).meta == {}


# -------------------------------------------- o congelado tem uma fonte só


def test_o_snapshot_do_seed_e_o_do_plano_sao_o_MESMO():
    """Duas montagens do mesmo congelado divergem sempre — é só questão de tempo.

    O `seed` tinha a própria cópia: nasceu sem a seção `production` e, quando o
    aproveitamento entrou, nasceu sem `gross_quantity`. Quem descobriu foi a
    recusa do `finish`, depois de a CI ficar verde escondendo o buraco — porque
    o fallback que eu tinha escrito caía na líquida em silêncio.

    Este teste cobra a forma, não o chamador: qualquer campo novo que entre pelo
    plano e não pelo seed reprova aqui.
    """
    from shopman.craftsman.services.scheduling import build_recipe_snapshot

    ficha = _ficha()
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
        usable_factor=Decimal("0.84"),
    )
    do_plano = _fornada(ficha).meta["_recipe_snapshot"]
    assert build_recipe_snapshot(ficha) == do_plano


def test_o_congelado_declara_todas_as_chaves_que_o_finish_exige():
    """A recusa do `finish` cobra `gross_quantity`; a prova nasce aqui."""
    from shopman.craftsman.services.scheduling import build_recipe_snapshot

    ficha = _ficha()
    RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-ROXA", quantity=Decimal("0.200"), unit="kg",
    )
    item = build_recipe_snapshot(ficha)["items"][0]
    assert set(item) == {"input_sku", "quantity", "gross_quantity", "usable_factor", "unit"}


def test_o_fator_de_correcao_da_cozinha_e_o_inverso_e_so_de_LEITURA():
    """A tela pode falar a língua do chef sem que ninguém inverta de cabeça."""
    ficha = _ficha()
    item = RecipeItem.objects.create(
        recipe=ficha, input_sku="CEBOLA-BRANCA", quantity=Decimal("0.200"), unit="kg",
        usable_factor=Decimal("0.84"),
    )
    assert item.correction_factor == Decimal("1.1905")
    assert "correction_factor" not in {f.name for f in RecipeItem._meta.get_fields()}
