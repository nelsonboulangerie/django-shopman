"""`apply_material_skus`: a curadoria da lista de insumos, com a ficha junto.

O que este teste cobra não é o cascade — esse é do
`test_sku_cascade_coverage`. É o que o comando acrescenta: a tabela ser coerente
consigo mesma, a recusa ser fechada quando o alvo já é produto vendável, e o
impedimento ser NOMINAL quando o mundo trava uma frente sozinha — o ledger
imutável do Stockman, que foi o que o ensaio contra a cópia do alpha descobriu.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product
from shopman.stockman.models import Position
from shopman.stockman.services import StockMovements

from config.management.commands.apply_material_skus import (
    CRIACOES,
    EXCLUSOES,
    FORA_DA_TABELA,
    REAPONTAMENTOS,
    RENOMEACOES,
    TABELAS_DE_CODIGO,
)

pytestmark = pytest.mark.django_db


def _insumo(sku: str, nome: str = "", unidade: str = "kg") -> Material:
    return Material.objects.create(sku=sku, name=nome or sku, unit=unidade)


def _rodar(**kwargs) -> str:
    saida = StringIO()
    call_command("apply_material_skus", stdout=saida, stderr=saida, **kwargs)
    return saida.getvalue()


# --------------------------------------------------------------- a tabela


def test_a_tabela_nao_disputa_endereco_consigo_mesma():
    """Dois insumos não dividem SKU, nem na origem nem no destino."""
    antigos = [a for a, _n, _q in RENOMEACOES]
    novos = [n for _a, n, _q in RENOMEACOES]
    assert len(set(antigos)) == len(antigos), "SKU de hoje repetido"
    assert len(set(novos)) == len(novos), "SKU curado repetido"
    # Uma exceção nomeada: `AGUA-FILTRADA → AGUA` mira o SKU de um insumo que a
    # mesma travessia apaga. É o único cruzamento, e ele é declarado.
    cruzados = set(novos) & set(antigos)
    assert cruzados <= set(EXCLUSOES), (
        f"{cruzados - set(EXCLUSOES)} é alvo de uma linha e origem de outra, sem estar "
        "na lista de exclusões: o rename teria de ser encadeado, e encadeamento é chute"
    )


def test_quem_decidiu_cada_linha_esta_escrito():
    """A procedência não é decorativa: é o que o relatório mostra antes do --apply."""
    for antigo, novo, quem in RENOMEACOES:
        assert quem in {"dele", "proposta"}, f"{antigo} → {novo}: procedência '{quem}'"


def test_o_que_fica_de_fora_tem_motivo_escrito():
    for sku, motivo in FORA_DA_TABELA.items():
        assert motivo.strip(), f"{sku} está fora da tabela sem motivo"
        assert sku not in [a for a, _n, _q in RENOMEACOES]


def test_as_tabelas_de_codigo_existem():
    """Caminho que envelhece vira relatório mudo — e o relatório é a cobrança."""
    from pathlib import Path

    from django.conf import settings

    for rel in TABELAS_DE_CODIGO:
        assert (Path(settings.BASE_DIR) / rel).is_file(), f"{rel} não existe mais"


# ------------------------------------------------------------- a travessia


def test_o_ensaio_nao_grava():
    _insumo("MANTEIGA-FR", "Manteiga francesa")
    saida = _rodar()
    assert "ensaio" in saida
    assert Material.objects.filter(sku="MANTEIGA-FR").exists()
    assert not Material.objects.filter(sku="MANTEIGA-PRESIDENT-SEM-SAL").exists()


def test_o_apply_troca_o_sku_e_arrasta_a_ficha():
    _insumo("MANTEIGA-FR", "Manteiga francesa")
    receita = Recipe.objects.create(
        ref="massa-brioche", name="Massa Brioche", output_sku="MASSA-BRIOCHE",
        batch_size=Decimal("10"),
    )
    RecipeItem.objects.create(
        recipe=receita, input_sku="MANTEIGA-FR", quantity=Decimal("2.4"), unit="kg",
    )

    _rodar(apply=True, sku="MANTEIGA-FR")

    assert Material.objects.filter(sku="MANTEIGA-PRESIDENT-SEM-SAL").exists()
    assert not Material.objects.filter(sku="MANTEIGA-FR").exists()
    assert RecipeItem.objects.get(recipe=receita).input_sku == "MANTEIGA-PRESIDENT-SEM-SAL"


def test_rodar_de_novo_nao_faz_nada():
    _insumo("MANTEIGA-FR", "Manteiga francesa")
    _rodar(apply=True, sku="MANTEIGA-FR")
    saida = _rodar(apply=True, sku="MANTEIGA-FR")
    assert "sem insumo no cadastro" in saida
    assert Material.objects.filter(sku="MANTEIGA-PRESIDENT-SEM-SAL").count() == 1


def test_o_insumo_que_falta_nasce_e_a_ficha_deixa_de_apontar_para_o_produto():
    """`MT` é SKU de PRODUTO, e a ficha do Vinagrete o citava como insumo.

    O conserto é a linha da ficha, não um rename: renomear `MT` levaria o
    produto Mostarda da Casa junto.
    """
    ficha, antigo, novo = REAPONTAMENTOS[0]
    produto = Product.objects.create(
        sku=antigo, name="Mostarda da Casa", unit="un", base_price_q=1800,
    )
    receita = Recipe.objects.create(
        ref=ficha, name="Vinagrete à Francesa", output_sku="VINAGRETE-FRANCES",
        batch_size=Decimal("0.9"),
    )
    RecipeItem.objects.create(
        recipe=receita, input_sku=antigo, quantity=Decimal("0.1"), unit="kg",
    )

    _rodar(apply=True)

    assert RecipeItem.objects.get(recipe=receita).input_sku == novo
    produto.refresh_from_db()
    assert produto.sku == antigo, "o produto Mostarda da Casa não podia ser tocado"
    assert Material.objects.filter(sku=novo).exists()


# ---------------------------------------------------------------- recusas


def test_recusa_fechada_quando_o_alvo_ja_e_produto_vendavel():
    """Insumo e produto dividem um namespace só — o ledger indexa por SKU."""
    _insumo("MANTEIGA-FR", "Manteiga francesa")
    Product.objects.create(
        sku="MANTEIGA-PRESIDENT-SEM-SAL", name="Manteiga Francesa", unit="un", base_price_q=3000,
    )

    with pytest.raises(CommandError, match="Nada foi gravado"):
        _rodar(apply=True)

    assert Material.objects.filter(sku="MANTEIGA-FR").exists(), (
        "recusa fechada: nenhuma outra linha pode ter sido gravada"
    )


def test_recusa_quando_a_ficha_alvo_ja_tem_o_insumo_certo():
    """(ficha, insumo) é único: fundir somaria quantidade, e isso é curadoria."""
    ficha, antigo, novo = REAPONTAMENTOS[0]
    receita = Recipe.objects.create(
        ref=ficha, name="Vinagrete à Francesa", output_sku="VINAGRETE-FRANCES",
        batch_size=Decimal("0.9"),
    )
    RecipeItem.objects.create(recipe=receita, input_sku=antigo, quantity=Decimal("0.1"), unit="kg")
    RecipeItem.objects.create(recipe=receita, input_sku=novo, quantity=Decimal("0.2"), unit="kg")

    with pytest.raises(CommandError, match="Nada foi gravado"):
        _rodar(apply=True)


# ------------------------------------------------------------ impedimentos


def _agua_com_historia():
    """O estado do alpha: o órfão `AGUA` com saldo semeado, e a água do filtro."""
    orfao = next(iter(EXCLUSOES))
    _insumo(orfao, "Água", "l")
    _insumo("AGUA-FILTRADA", "Água filtrada", "l")
    deposito = Position.objects.create(ref="deposito", name="Depósito")
    StockMovements.receive(
        sku=orfao, position=deposito, quantity=Decimal("5"),
        reason="Saldo de abertura de insumo (seed)",
    )
    StockMovements.receive(
        sku="AGUA-FILTRADA", position=deposito, quantity=Decimal("211.6"),
        reason="Saldo de abertura de insumo (seed)",
    )
    return orfao


def test_o_ledger_imutavel_impede_a_exclusao_e_a_frente_para_sozinha():
    """`Move` recusa delete/update e a FK para o quant é PROTECT.

    O quant de um insumo que teve qualquer movimento não sai do banco — nem o
    saldo de abertura do seed. Logo `AGUA` não é apagável, e `AGUA-FILTRADA →
    AGUA` não cabe. As duas param **nomeadas**, e o resto da tabela segue.
    """
    orfao = _agua_com_historia()
    _insumo("MANTEIGA-FR", "Manteiga francesa")

    saida = _rodar(apply=True)

    assert Material.objects.filter(sku=orfao).exists(), "o órfão não podia sair"
    assert Material.objects.filter(sku="AGUA-FILTRADA").exists(), "o rename não podia passar"
    assert "imutável" in saida and "seed --flush" in saida
    assert Material.objects.filter(sku="MANTEIGA-PRESIDENT-SEM-SAL").exists(), (
        "impedimento para UMA frente, não recusa para a tabela inteira"
    )


def test_a_exclusao_passa_quando_o_saldo_nao_tem_historia():
    """Sem movimento, o quant sai e o SKU fica livre — que é o estado do seed."""
    orfao = next(iter(EXCLUSOES))
    _insumo(orfao, "Água", "l")
    _insumo("AGUA-FILTRADA", "Água filtrada", "l")

    _rodar(apply=True, sku=orfao)

    assert not Material.objects.filter(sku=orfao).exists()


def test_a_exclusao_para_se_alguma_ficha_ainda_usa_o_insumo():
    """Apagar deixaria a ficha apontando para o vazio — o defeito do `MT`."""
    orfao = next(iter(EXCLUSOES))
    _insumo(orfao, "Água", "l")
    receita = Recipe.objects.create(
        ref="massa-ciabatta", name="Massa Ciabatta", output_sku="MASSA-CIABATTA",
        batch_size=Decimal("10"),
    )
    RecipeItem.objects.create(recipe=receita, input_sku=orfao, quantity=Decimal("1"), unit="kg")

    with pytest.raises(CommandError, match="linha"):
        _rodar(apply=True, sku=orfao)

    assert Material.objects.filter(sku=orfao).exists()


def test_o_relatorio_cobra_o_seed_quando_o_codigo_ainda_diz_o_nome_antigo():
    """O `seed.py` é a FONTE da lista: renomear só no banco é meia correção."""
    _insumo("MANTEIGA-FR", "Manteiga francesa")
    saida = _rodar()
    assert "seed.py" in saida


def test_a_criacao_declara_quem_decidiu():
    for criacao in CRIACOES:
        assert criacao["curadoria"].strip(), f"{criacao['sku']} nasce sem procedência"
        assert criacao["unit"] in dict(Material.Unit.choices)


def test_a_varredura_de_colisao_enxerga_o_quant_e_nao_so_o_campo_unico():
    """A coordenada do quant é `UniqueConstraint`, não `unique=True`.

    Uma varredura que só olhasse `field.unique` acharia o `Material.sku` e
    passaria batido pelo `unique_quant_coordinate` — que é
    `(sku, position, target_date, batch)` com `NULLS NOT DISTINCT`, e é onde os
    dois quants de água colidem: mesmo depósito, `target_date` nulo.

    O teste mede a varredura, e não o erro do banco de propósito: a suíte cai
    para SQLite sem `DATABASE_URL`, e ali NULL é distinto — a constraint não
    dispararia, e o teste passaria dizendo que não há colisão nenhuma.
    """
    from config.management.commands.apply_material_skus import _colisoes_por_campo_unico

    orfao = _agua_com_historia()
    achados = _colisoes_por_campo_unico("AGUA-FILTRADA", orfao)

    assert any("stockman.Quant" in a for a in achados), achados
    assert any("buyman.Material" in a for a in achados), achados
