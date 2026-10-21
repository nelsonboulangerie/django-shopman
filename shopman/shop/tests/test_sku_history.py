"""Resolução dos códigos históricos usados na curadoria do BI."""

from __future__ import annotations

from shopman.shop.services.sku_history import (
    current_sku,
    rename_map,
)


def test_o_mapa_junta_as_duas_levas():
    from config.management.commands.apply_product_skus import AJUSTES, RENAMES
    from config.management.commands.rename_skus_to_real import RENAMES as PRIMEIRA

    mapa = rename_map()
    for tabela in (PRIMEIRA, RENAMES, AJUSTES):
        assert {a for a, _n in tabela} <= set(mapa)


def test_a_cadeia_atravessa_as_duas_levas():
    """`CROISSANT` virou `CT` em agosto e `CT` virou `CRO` em setembro.

    Quem olhasse uma leva só pararia no `CT`, que hoje é 404.
    """
    assert current_sku("CROISSANT", {"CRO"}) == "CRO"
    assert current_sku("CT", {"CRO"}) == "CRO"


def test_a_cadeia_de_tres_saltos_chega_ao_fim():
    """`MICBT` → `FOBM` → `FOBP`: a segunda leva do mesmo dia."""
    assert current_sku("MICBT", {"FOBP"}) == "FOBP"


def test_o_codigo_que_voltou_nao_e_desviado():
    """`FENDU` virou `FE` em agosto e `FE` voltou a `FENDU` em setembro.

    No papel é um ciclo. Contra o catálogo não há dúvida: para-se no que
    existe — e é isso que impede um 301 de mandar a página boa do `FENDU`
    para o `FE`, que é 404.
    """
    assert current_sku("FENDU", {"FENDU"}) == "FENDU"
    assert current_sku("FE", {"FENDU"}) == "FENDU"


def test_codigo_sem_para_onde_ir_devolve_ele_mesmo():
    assert current_sku("NAO-EXISTE", {"CRO"}) == "NAO-EXISTE"
