"""`apply_product_skus`: a troca de endereço do catálogo, com a série do B.I. junto.

O que este teste cobra não é o cascade — esse é do
`test_sku_cascade_coverage`. É o que o comando acrescenta: a tabela ser
coerente consigo mesma, o de-para nascer antes do rename, e a recusa ser
fechada quando duas linhas disputam o mesmo código.
"""

from __future__ import annotations

import itertools
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.offerman.models import Product

from config.management.commands.apply_product_skus import (
    FONTE_HISTORICO,
    FORA_DA_TABELA,
    RENAMES,
    TABELAS_DE_CODIGO,
)

pytestmark = pytest.mark.django_db


def _product(sku: str, name: str = "") -> Product:
    return Product.objects.create(
        sku=sku, name=name or sku, unit="un", base_price_q=1000
    )


_PROXIMA_VENDA = itertools.count(1)


def _venda(sku: str, *, nome: str, qty: int = 1):
    from django.utils import timezone

    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem
    from shopman.backstage.tests.support import historical_batch

    sale = HistoricalSale.objects.create(
        batch=historical_batch(FONTE_HISTORICO),
        source=FONTE_HISTORICO,
        external_id=next(_PROXIMA_VENDA),
        occurred_at=timezone.now(),
        total_q=1000,
    )
    return HistoricalSaleItem.objects.create(
        sale=sale, seq=1, sku=sku, product_name=nome, qty=qty,
        unit_price_q=1000, line_total_q=1000,
    )


# --------------------------------------------------------------- a tabela


def test_a_tabela_nao_disputa_codigo_consigo_mesma():
    """Dois produtos não dividem endereço, nem na origem nem no destino."""
    antigos = [a for a, _n in RENAMES]
    novos = [n for _a, n in RENAMES]
    assert len(set(antigos)) == len(antigos), "código de hoje repetido na tabela"
    assert len(set(novos)) == len(novos), "código curado repetido na tabela"
    assert not (set(novos) & set(antigos)), (
        "um alvo é o código de hoje de outra linha: o rename teria de ser encadeado, "
        "e a ordem da tabela passaria a importar"
    )


def test_nenhum_par_renomeia_para_ele_mesmo():
    assert not [a for a, n in RENAMES if a == n]


def test_o_que_fica_de_fora_fica_com_motivo_escrito():
    assert all(motivo.strip() for motivo in FORA_DA_TABELA.values())
    assert not (set(FORA_DA_TABELA) & {a for a, _n in RENAMES}), (
        "um código não pode estar ao mesmo tempo na tabela e na lista do que ficou de fora"
    )


def test_as_tabelas_de_codigo_declaradas_existem():
    """Arquivo que sumiu vira contagem zero, e zero parece 'nada a fazer'."""
    from pathlib import Path

    from django.conf import settings

    raiz = Path(settings.BASE_DIR)
    ausentes = [rel for rel in TABELAS_DE_CODIGO if not (raiz / rel).is_file()]
    assert not ausentes, f"declarados e inexistentes: {ausentes}"


# --------------------------------------------------------------- o ensaio


def test_ensaio_nao_grava_e_mostra_o_que_faria():
    _product("CT", "Croissant")

    out = StringIO()
    call_command("apply_product_skus", "--sku", "CT", stdout=out)

    assert Product.objects.filter(sku="CT").exists()
    assert not Product.objects.filter(sku="CRO").exists()
    texto = out.getvalue()
    assert "CT" in texto and "CRO" in texto
    assert "nada gravado" in texto


def test_apply_troca_o_codigo():
    _product("CT", "Croissant")

    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert not Product.objects.filter(sku="CT").exists()
    assert Product.objects.get(sku="CRO").name == "Croissant"


def test_rodar_de_novo_nao_faz_nada():
    _product("CT", "Croissant")
    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    out = StringIO()
    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=out)

    assert Product.objects.filter(sku="CRO").count() == 1
    assert "sem produto no catálogo" in out.getvalue()


# ------------------------------------------------------------ série do B.I.


def test_quem_tem_venda_ganha_o_de_para_antes_de_perder_o_codigo():
    from shopman.backstage.models import ProductAlias

    produto = _product("CT", "Croissant")
    _venda("CT", nome="Croissant Tradicional")

    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    alias = ProductAlias.objects.get(source=FONTE_HISTORICO, external_sku="CT")
    assert alias.product_id == produto.pk
    assert alias.status == "confirmed"
    assert alias.external_name == "Croissant Tradicional"
    # E a tradução continua chegando ao código novo, que é o ponto de tudo isto.
    assert ProductAlias.objects.get(external_sku="CT").product.sku == "CRO"


def test_quem_nao_tem_venda_nao_ganha_de_para():
    from shopman.backstage.models import ProductAlias

    _product("CT", "Croissant")

    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert not ProductAlias.objects.filter(external_sku="CT").exists()


def test_de_para_ja_existente_e_respeitado():
    from shopman.backstage.models import AliasStatus, ProductAlias

    produto = _product("CT", "Croissant")
    _venda("CT", nome="Croissant Tradicional")
    ProductAlias.objects.create(
        source=FONTE_HISTORICO, external_sku="CT", external_name="curado à mão",
        product=produto, status=AliasStatus.CONFIRMED,
    )

    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert ProductAlias.objects.filter(external_sku="CT").count() == 1
    assert ProductAlias.objects.get(external_sku="CT").external_name == "curado à mão"


def _serie_creditada_a_outro(sku: str, *, dono: Product, nome: str) -> None:
    from shopman.backstage.models import AliasStatus, ProductAlias

    _venda(sku, nome=nome)
    ProductAlias.objects.create(
        source=FONTE_HISTORICO, external_sku=sku, external_name=nome,
        product=dono, status=AliasStatus.CONFIRMED,
        note="curadoria de quando o catálogo ainda não tinha o produto separado",
    )


def test_serie_creditada_a_outro_produto_impede_aquele_par():
    """O caso medido no alpha: 'yooga:BBB' credita a unidade ao pacote.

    O de-para não olha para o SKU do produto, então renomear não pioraria nada —
    mas apagaria a última pista barata de que o código antigo era deste produto.
    O par para; quem decide é a curadoria.
    """
    _product("BBB", "Brioche Burger Bun")
    pacote = _product("BBB2", "Brioche Burger Bun (pc. 2un.)")
    _serie_creditada_a_outro("BBB", dono=pacote, nome="Brioche Burger Bun - Unidade")

    with pytest.raises(CommandError) as erro:
        call_command("apply_product_skus", "--sku", "BBB", "--apply", stdout=StringIO())

    assert Product.objects.filter(sku="BBB").exists()
    assert "BBB2" in str(erro.value)
    assert "curadoria" in str(erro.value)


def test_o_par_impedido_nao_para_os_outros():
    """Um de-para vencido é problema daquela linha, não da leva inteira."""
    _product("BBB", "Brioche Burger Bun")
    pacote = _product("BBB2", "Brioche Burger Bun (pc. 2un.)")
    _product("CT", "Croissant")
    _serie_creditada_a_outro("BBB", dono=pacote, nome="Brioche Burger Bun - Unidade")

    out = StringIO()
    call_command("apply_product_skus", "--apply", stdout=out)

    assert Product.objects.filter(sku="BBB").exists()      # impedido
    assert Product.objects.filter(sku="CRO").exists()      # seguiu
    assert "NÃO renomeado" in out.getvalue()


def test_de_para_sem_produto_impede_aquele_par():
    """O outro caso do alpha: 'yooga:CHAI_A' foi marcado como produto extinto."""
    from shopman.backstage.models import AliasStatus, ProductAlias

    _product("CHAI_A", "Soft Chai Cítrico")
    _venda("CHAI_A", nome="Soft Chai Cítrico")
    ProductAlias.objects.create(
        source=FONTE_HISTORICO, external_sku="CHAI_A", external_name="Soft Chai Cítrico",
        product=None, status=AliasStatus.CONFIRMED,
    )

    with pytest.raises(CommandError):
        call_command("apply_product_skus", "--sku", "CHAI_A", "--apply", stdout=StringIO())

    assert Product.objects.filter(sku="CHAI_A").exists()


# ----------------------------------------------------------------- recusas


def test_alvo_que_ja_e_produto_recusa_fechado():
    _product("CT", "Croissant")
    _product("CRO", "outro que já mora no endereço")

    with pytest.raises(CommandError):
        call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert Product.objects.filter(sku="CT").exists()


def test_alvo_que_ja_e_insumo_recusa_fechado():
    from shopman.buyman.models import Material

    _product("CT", "Croissant")
    Material.objects.create(sku="CRO", name="insumo homônimo", unit="kg")

    with pytest.raises(CommandError):
        call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert Product.objects.filter(sku="CT").exists()


def test_sku_fora_da_tabela_diz_o_motivo():
    with pytest.raises(CommandError) as erro:
        call_command("apply_product_skus", "--sku", "MT", stdout=StringIO())

    assert "insumo" in str(erro.value).lower() or "mostarda" in str(erro.value).lower()


# --------------------------------------------------- o que o cascade arrasta


def test_a_ficha_acompanha_o_produto():
    from shopman.craftsman.models import Recipe

    _product("CT", "Croissant")
    Recipe.objects.create(ref="croissant", name="Croissant", output_sku="CT", batch_size=1)

    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert Recipe.objects.get(ref="croissant").output_sku == "CRO"


def test_o_estoque_acompanha_o_produto():
    from shopman.stockman.models import Position, Quant

    _product("CT", "Croissant")
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)
    Quant.objects.create(sku="CT", position=vitrine, _quantity=7)

    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert Quant.objects.get(position=vitrine).sku == "CRO"


def test_o_historico_do_yooga_nao_e_reescrito():
    """Registro de terceiro fica como a outra casa o emitiu."""
    from shopman.backstage.models import HistoricalSaleItem

    _product("CT", "Croissant")
    _venda("CT", nome="Croissant Tradicional")

    call_command("apply_product_skus", "--sku", "CT", "--apply", stdout=StringIO())

    assert HistoricalSaleItem.objects.filter(sku="CT").exists()
    assert not HistoricalSaleItem.objects.filter(sku="CRO").exists()


def test_etiqueta_de_consumo_dos_dois_codigos_se_funde():
    """O tropeço que só aparece em banco com operação.

    `ProductConsumptionTag.sku` é único, e o alpha guarda etiqueta tanto do
    código do Yooga (`FE`) quanto do código do cardápio 2027 (`FENDU`), que é
    justamente o alvo. Sem fundir, o `update` do cascade estoura a constraint
    no meio da travessia.
    """
    from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

    _product("FE", "Fendu")
    papel = ConsumptionRole.objects.create(ref="hibrido", label="Híbrido", reading="hybrid")
    ProductConsumptionTag.objects.create(sku="FE", role=papel, reviewed=True)
    ProductConsumptionTag.objects.create(sku="FENDU", role=papel, reviewed=True)

    out = StringIO()
    call_command("apply_product_skus", "--sku", "FE", "--apply", stdout=out)

    assert Product.objects.filter(sku="FENDU").exists()
    assert ProductConsumptionTag.objects.filter(sku="FENDU").count() == 1
    assert not ProductConsumptionTag.objects.filter(sku="FE").exists()
    assert "fundida" in out.getvalue()


def test_campo_unico_de_sku_sem_politica_recusa():
    """Campo de SKU único que nascer sem política para o comando, não o cascade."""
    from shopman.refs.registry import _ref_source_registry

    from config.management.commands.apply_product_skus import POLITICA_DE_COLISAO

    unicos = set()
    for label, campo in _ref_source_registry.get_sources_for_type("SKU"):
        from django.apps import apps

        try:
            Model = apps.get_model(label)
        except LookupError:
            continue
        if Model._meta.get_field(campo).unique:
            unicos.add(label)

    assert unicos <= set(POLITICA_DE_COLISAO), (
        f"campo de SKU único sem política: {sorted(unicos - set(POLITICA_DE_COLISAO))}"
    )
