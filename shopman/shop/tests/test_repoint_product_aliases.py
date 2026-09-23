"""`repoint_product_aliases`: a venda histórica volta para o produto que a fez.

A curadoria de 19/08 apontou 15 códigos do Yooga para outros produtos, porque
naquele dia eram a melhor correspondência. O catálogo mudou desde então. Este
comando corrige o de-para — e nada além dele.
"""

from __future__ import annotations

import itertools
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.offerman.models import Product

from config.management.commands.repoint_product_aliases import (
    FONTE,
    REAPONTAR,
    REAPONTAR_PARA,
)

pytestmark = pytest.mark.django_db

_PROXIMA_VENDA = itertools.count(1)


def _product(sku: str, name: str = "") -> Product:
    return Product.objects.create(sku=sku, name=name or sku, unit="un", base_price_q=1000)


def _venda(sku: str, *, nome: str):
    from django.utils import timezone

    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem
    from shopman.backstage.tests.support import historical_batch

    venda = HistoricalSale.objects.create(
        batch=historical_batch(FONTE), source=FONTE,
        external_id=next(_PROXIMA_VENDA), occurred_at=timezone.now(), total_q=1000,
    )
    HistoricalSaleItem.objects.create(
        sale=venda, seq=1, sku=sku, product_name=nome, qty=1,
        unit_price_q=1000, line_total_q=1000,
    )


def _alias(external_sku: str, *, para: Product | None, nome: str = "x"):
    from shopman.backstage.models import AliasStatus, ProductAlias

    return ProductAlias.objects.create(
        source=FONTE, external_sku=external_sku, external_name=nome,
        product=para, status=AliasStatus.CONFIRMED,
        note="curadoria 19/08 (Pablo): chás Kãnfa lata/pouch = Chá da Casa (lata)",
    )


def _serie_creditada_a_outro(sku: str, *, dono, nome: str) -> None:
    """Uma venda histórica naquele código, creditada ao produto errado."""
    _venda(sku, nome=nome)
    _alias(sku, para=dono, nome=nome)


def test_a_tabela_nao_repete_codigo():
    codigos = [sku for sku, _nota in REAPONTAR]
    assert len(set(codigos)) == len(codigos)
    assert all(nota.strip() for _sku, nota in REAPONTAR)


def test_ensaio_nao_grava():
    from shopman.backstage.models import ProductAlias

    unidade = _product("BBB", "Brioche Burger Bun")
    pacote = _product("BBB2", "Brioche Burger Bun (pc. 2un.)")
    _alias("BBB", para=pacote, nome="Brioche Burger Bun - Unidade")

    out = StringIO()
    call_command("repoint_product_aliases", stdout=out)

    assert ProductAlias.objects.get(external_sku="BBB").product_id == pacote.pk
    assert unidade.sku in out.getvalue()
    assert "nada gravado" in out.getvalue()


def test_apply_devolve_a_venda_ao_produto_certo():
    from shopman.backstage.models import ProductAlias

    unidade = _product("BBB", "Brioche Burger Bun")
    pacote = _product("BBB2", "Brioche Burger Bun (pc. 2un.)")
    _alias("BBB", para=pacote, nome="Brioche Burger Bun - Unidade")
    _venda("BBB", nome="Brioche Burger Bun - Unidade")

    out = StringIO()
    call_command("repoint_product_aliases", "--apply", stdout=out)

    alias = ProductAlias.objects.get(external_sku="BBB")
    assert alias.product_id == unidade.pk
    assert "BBB2" in alias.note  # de onde veio fica escrito
    assert "1 linha" in out.getvalue()


def test_de_para_sem_produto_ganha_o_produto():
    from shopman.backstage.models import ProductAlias

    chai = _product("CHAI_A", "Soft Chai Cítrico")
    _alias("CHAI_A", para=None, nome="Soft Chai Cítrico")

    call_command("repoint_product_aliases", "--apply", stdout=StringIO())

    assert ProductAlias.objects.get(external_sku="CHAI_A").product_id == chai.pk


def test_rodar_de_novo_nao_faz_nada():
    unidade = _product("BBB", "Brioche Burger Bun")
    _alias("BBB", para=unidade, nome="Brioche Burger Bun - Unidade")

    out = StringIO()
    call_command("repoint_product_aliases", "--apply", stdout=out)

    assert "Nada a reapontar" in out.getvalue()


def test_produto_ausente_para_aquele_codigo_e_avisa():
    """Sem produto de mesmo SKU não há para onde apontar — e isso se diz."""
    pacote = _product("BBB2", "Brioche Burger Bun (pc. 2un.)")
    _alias("BBB", para=pacote, nome="Brioche Burger Bun - Unidade")

    out = StringIO()
    call_command("repoint_product_aliases", "--apply", stdout=out)

    assert "não existe produto" in out.getvalue()


def test_a_venda_do_yooga_nao_e_tocada():
    from shopman.backstage.models import HistoricalSaleItem

    unidade = _product("BBB", "Brioche Burger Bun")
    pacote = _product("BBB2", "Brioche Burger Bun (pc. 2un.)")
    _alias("BBB", para=pacote, nome="Brioche Burger Bun - Unidade")
    _venda("BBB", nome="Brioche Burger Bun - Unidade")

    call_command("repoint_product_aliases", "--apply", stdout=StringIO())

    item = HistoricalSaleItem.objects.get(sku="BBB")
    assert item.product_name == "Brioche Burger Bun - Unidade"
    assert unidade.pk  # o produto existe; o registro de terceiro seguiu igual


def test_os_mesmos_codigos_que_o_rename_recusa():
    """As duas tabelas falam do mesmo problema; divergir seria deixar par preso."""
    from config.management.commands.apply_product_skus import RENAMES

    renomeaveis = {a for a, _n in RENAMES}
    codigos = {sku for sku, _nota in REAPONTAR}
    # CHAI_A e os 12 chás e BBB/PHO estão nos dois lados — menos o que saiu da
    # tabela de rename por outro motivo.
    assert codigos <= renomeaveis | {"GL"}


def test_a_segunda_leva_aponta_para_o_PAI_da_variante():
    """As "METADE DO PREÇO" não têm produto de mesmo código: têm um pai.

    `MJO` é a metade do Caranguejo (`JO`), e estava pendurada no Coelhinho
    porque em 19/08 o catálogo tinha um "Animalzinho" só. O destino aqui é o
    pai que o nome da linha nomeia, não um produto chamado `MJO`.
    """
    from shopman.backstage.models import ProductAlias

    coelhinho = _product("COE", "Coelhinho de Chocolate")
    caranguejo = _product("JO", "Caranguejo")
    _serie_creditada_a_outro("MJO", dono=coelhinho, nome="Caranguejo - METADE DO PREÇO")

    call_command("repoint_product_aliases", "--apply", stdout=StringIO())

    assert ProductAlias.objects.get(external_sku="MJO").product_id == caranguejo.pk


def test_pai_ausente_avisa_e_nao_inventa():
    _product("COE", "Coelhinho de Chocolate")
    _serie_creditada_a_outro(
        "MJO", dono=Product.objects.get(sku="COE"), nome="Caranguejo - METADE DO PREÇO"
    )

    out = StringIO()
    call_command("repoint_product_aliases", "--apply", stdout=out)

    assert "não existe produto 'JO'" in out.getvalue()


def test_as_duas_tabelas_nao_disputam_o_mesmo_codigo():
    de_um = {sku for sku, _nota in REAPONTAR}
    de_outro = {sku for sku, _destino, _nota in REAPONTAR_PARA}
    assert not (de_um & de_outro)
    assert all(nota.strip() for _s, _d, nota in REAPONTAR_PARA)
