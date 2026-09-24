"""A NF-e de compra confere o cadastro fiscal — função pura, sem banco.

Os perfis são achados pelo que EMITEM (CSOSN 500 = ST), não pela chave: as
chaves estão para ser renomeadas e a conferência não pode depender delas.
"""

from __future__ import annotations

import pytest
from shopman.fiscalman.classification import FISCAL_PROFILES

from shopman.shop.services.invoice_fiscal_check import check_invoice_fiscal, invoice_has_st

ST_KEY = next(k for k, p in FISCAL_PROFILES.items() if p.csosn == "500")
SEM_ST_KEY = next(k for k, p in FISCAL_PROFILES.items() if p.csosn != "500")


def _meta(profile: str, *, ncm: str = "21069090", cest: str = "") -> dict:
    fiscal = {"profile": profile, "ncm": ncm, "unit": "UN"}
    if cest:
        fiscal["cest"] = cest
    return {"fiscal": fiscal}


def test_nota_igual_ao_cadastro_nao_diverge():
    meta = _meta(ST_KEY, ncm="22021000", cest="0300700")

    assert check_invoice_fiscal(metadata=meta, ncm="22021000", cest="03.007.00", icms_csosn="500") == []


def test_ncm_diferente_diverge_com_os_dois_valores():
    [div] = check_invoice_fiscal(metadata=_meta(SEM_ST_KEY, ncm="09024000"), ncm="21069090", icms_csosn="102")

    assert (div.field, div.catalog_value, div.invoice_value) == ("ncm", "09024000", "21069090")
    assert "o cadastro diz 09024000" in div.message


def test_cest_na_nota_e_ausente_no_cadastro_diverge():
    [div] = check_invoice_fiscal(metadata=_meta(SEM_ST_KEY), ncm="21069090", cest="1709900", icms_csosn="102")

    assert (div.field, div.catalog_value, div.invoice_value) == ("cest", "", "1709900")
    assert div.message == "O cadastro não tem CEST; a nota diz 1709900."


def test_nota_sem_cest_nao_acusa_o_cadastro_que_tem():
    assert check_invoice_fiscal(metadata=_meta(ST_KEY, cest="0300700"), ncm="21069090", icms_csosn="500") == []


def test_nota_com_st_contra_cadastro_sem_st():
    [div] = check_invoice_fiscal(metadata=_meta(SEM_ST_KEY), ncm="21069090", icms_csosn="500")

    assert (div.field, div.catalog_value, div.invoice_value) == ("st", "sem ST", "com ST")
    assert "CSOSN 500" in div.message
    assert FISCAL_PROFILES[ST_KEY].name in div.message


def test_nota_sem_st_contra_cadastro_com_st():
    [div] = check_invoice_fiscal(metadata=_meta(ST_KEY), ncm="21069090", icms_cst="00")

    assert (div.field, div.catalog_value, div.invoice_value) == ("st", "com ST", "sem ST")
    assert FISCAL_PROFILES[SEM_ST_KEY].name in div.message


def test_produto_sem_classificacao_recebe_ncm_e_st_da_nota():
    divs = check_invoice_fiscal(metadata={}, ncm="21069090", icms_cst="60")

    assert [d.field for d in divs] == ["ncm", "st"]
    assert "sem perfil fiscal" in divs[1].message


def test_nota_sem_grupo_icms_nao_opina_sobre_st():
    assert check_invoice_fiscal(metadata=_meta(ST_KEY), ncm="21069090") == []


@pytest.mark.parametrize(
    ("cst", "csosn", "valor_q", "esperado"),
    [
        ("60", "", 0, True),  # ST retida antes, mesmo sem valor declarado
        ("", "500", 0, True),
        ("10", "", 1234, True),
        ("", "201", 500, True),
        ("10", "", 0, None),  # código de ST sem valor: ambíguo
        ("", "900", 0, None),
        ("00", "", 0, False),
        ("", "102", 0, False),
        ("", "", 0, None),  # sem grupo ICMS
        ("", "", 700, True),
    ],
)
def test_quando_a_nota_diz_st(cst, csosn, valor_q, esperado):
    assert invoice_has_st(icms_cst=cst, icms_csosn=csosn, st_value_q=valor_q) is esperado
