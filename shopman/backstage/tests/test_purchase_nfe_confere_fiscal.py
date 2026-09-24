"""O recebimento com NF-e confere o cadastro fiscal do produto de revenda.

Decisão do dono (24/09/2026): "pendências que sobrarem confirmamos nas próximas
NFs". A nota que diverge do cadastro deixa SUGESTÃO (NCM/CEST, no rascunho de
enriquecimento) e AVISO (``OperatorAlert``) — e nunca muda o cadastro sozinha.

Os perfis são achados pelo que emitem (CSOSN 500 = ST), não pela chave, que
está para ser renomeada.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from shopman.buyman.models import Material, Supplier
from shopman.fiscalman.classification import FISCAL_PROFILES
from shopman.offerman.models import Product
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import purchase as purchase_service

CHAVE = "41260812345678000190550010000012341000123459"
ST_KEY = next(k for k, p in FISCAL_PROFILES.items() if p.csosn == "500")
SEM_ST_KEY = next(k for k, p in FISCAL_PROFILES.items() if p.csosn != "500" and p.carries_cest)
TIPO = purchase_service.FISCAL_DIVERGENCE_ALERT_TYPE


@pytest.fixture
def operador(db):
    return User.objects.create_user("compras-fiscal", password="pw", is_staff=True)


@pytest.fixture
def fornecedor(db):
    Position.objects.get_or_create(
        ref="estoque",
        defaults={"name": "Estoque", "kind": PositionKind.PHYSICAL, "is_saleable": False},
    )
    return Supplier.objects.create(ref="my-chai", name="My Chai", document="12.345.678/0001-90")


def _produto(fiscal: dict) -> Product:
    produto = Product.objects.create(
        sku="INTU_P50",
        name="Intuição Chai — Pouch 50g",
        unit="un",
        base_price_q=7300,
        is_sellable=True,
        metadata={"fiscal": fiscal},
    )
    Material.objects.create(sku=produto.sku, name=produto.name, unit="un")
    return produto


def _receber(fornecedor, operador, **nota):
    linha = {"id": "l1", "materialSku": "INTU_P50", "purchaseQty": "2", "costInput": "84,80", "checked": True}
    linha.update(nota)
    purchase_service.confirm_receipt(
        {"mode": "invoice", "supplierRef": fornecedor.ref, "invoiceAccessKey": CHAVE, "note": "", "lines": [linha]},
        user=operador,
    )


def test_nota_igual_ao_cadastro_nao_avisa_nada(fornecedor, operador):
    produto = _produto({"profile": ST_KEY, "ncm": "21069090", "cest": "1709900", "unit": "UN"})

    _receber(fornecedor, operador, invoiceNcm="21069090", invoiceCest="1709900", invoiceIcmsCsosn="500")

    assert not OperatorAlert.objects.filter(type=TIPO).exists()
    produto.refresh_from_db()
    assert "detail" not in produto.metadata["enrichment"]["fields"]["ncm"]


def test_ncm_diferente_vira_sugestao_e_aviso_sem_tocar_o_produto(fornecedor, operador):
    fiscal = {"profile": SEM_ST_KEY, "ncm": "09024000", "unit": "UN"}
    produto = _produto(fiscal)

    _receber(fornecedor, operador, invoiceNcm="21069090", invoiceIcmsCsosn="102")

    produto.refresh_from_db()
    assert produto.metadata["fiscal"] == fiscal
    sugestao = produto.metadata["enrichment"]["fields"]["ncm"]
    assert (sugestao["value"], sugestao["source"], sugestao["source_ref"]) == ("21069090", "nfe", CHAVE)
    assert sugestao["detail"] == "NCM diverge: o cadastro diz 09024000, a nota diz 21069090."
    alerta = OperatorAlert.objects.get(type=TIPO)
    assert "INTU_P50" in alerta.message
    assert "o cadastro diz 09024000, a nota diz 21069090" in alerta.message
    assert "Nada mudou no cadastro" in alerta.message


def test_cest_ausente_no_cadastro_vira_sugestao(fornecedor, operador):
    produto = _produto({"profile": SEM_ST_KEY, "ncm": "21069090", "unit": "UN"})

    _receber(fornecedor, operador, invoiceNcm="21069090", invoiceCest="1709900", invoiceIcmsCsosn="102")

    produto.refresh_from_db()
    assert "cest" not in produto.metadata["fiscal"]
    sugestao = produto.metadata["enrichment"]["fields"]["cest"]
    assert sugestao["value"] == "1709900"
    assert sugestao["detail"] == "O cadastro não tem CEST; a nota diz 1709900."
    assert "CEST" in OperatorAlert.objects.get(type=TIPO).message


def test_nota_com_st_e_cadastro_sem_st_avisa(fornecedor, operador):
    produto = _produto({"profile": SEM_ST_KEY, "ncm": "21069090", "unit": "UN"})

    _receber(fornecedor, operador, invoiceNcm="21069090", invoiceIcmsCsosn="500", invoiceStValueQ="1234")

    alerta = OperatorAlert.objects.get(type=TIPO)
    assert "veio com ICMS-ST (CSOSN 500)" in alerta.message
    assert FISCAL_PROFILES[ST_KEY].name in alerta.message
    produto.refresh_from_db()
    assert produto.metadata["fiscal"]["profile"] == SEM_ST_KEY


def test_st_retida_pelo_valor_tambem_conta(fornecedor, operador):
    _produto({"profile": SEM_ST_KEY, "ncm": "21069090", "unit": "UN"})

    _receber(fornecedor, operador, invoiceNcm="21069090", invoiceIcmsCst="10", invoiceStValueQ="750")

    assert "veio com ICMS-ST (CST 10)" in OperatorAlert.objects.get(type=TIPO).message


def test_nota_sem_st_e_cadastro_com_st_avisa(fornecedor, operador):
    produto = _produto({"profile": ST_KEY, "ncm": "21069090", "cest": "1709900", "unit": "UN"})

    _receber(fornecedor, operador, invoiceNcm="21069090", invoiceIcmsCsosn="102")

    alerta = OperatorAlert.objects.get(type=TIPO)
    assert "veio sem ICMS-ST (CSOSN 102)" in alerta.message
    assert FISCAL_PROFILES[SEM_ST_KEY].name in alerta.message
    produto.refresh_from_db()
    assert produto.metadata["fiscal"]["profile"] == ST_KEY


def test_a_mesma_divergencia_na_proxima_nota_nao_repete_o_aviso(fornecedor, operador):
    _produto({"profile": SEM_ST_KEY, "ncm": "09024000", "unit": "UN"})
    _receber(fornecedor, operador, invoiceNcm="21069090", invoiceIcmsCsosn="102")

    outra_chave = "41260812345678000190550010000012351000123456"
    linha = {
        "id": "l1", "materialSku": "INTU_P50", "purchaseQty": "1", "costInput": "42,40", "checked": True,
        "invoiceNcm": "21069090", "invoiceIcmsCsosn": "102",
    }
    purchase_service.confirm_receipt(
        {"mode": "invoice", "supplierRef": fornecedor.ref, "invoiceAccessKey": outra_chave, "note": "", "lines": [linha]},
        user=operador,
    )

    assert OperatorAlert.objects.filter(type=TIPO).count() == 1
