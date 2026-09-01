"""Custos em lote: tornar muitos insumos compráveis sem passar pelo Django Admin.

Um insumo só vira pedido quando tem custo padrão E fornecedor preferencial
(`_queue_supplier_purchase_request` recusa sem isso). Com 54 insumos nesse
estado, o caminho de um-por-vez — dois selects, um valor, um botão, um
round-trip que devolve a projeção inteira — é trabalho de horas. O mesmo
fornecedor costuma cobrir dezenas de insumos, e é essa repetição que o lote
elimina.

O lote é tudo-ou-nada de propósito: custo é dado de dinheiro, e um lote
meio-aplicado deixa o operador sem saber o que entrou. Cada linha inválida volta
com seu índice e seu SKU para ser corrigida.
"""

from __future__ import annotations

import pytest
from django.apps import apps

from shopman.backstage.services import purchase as purchase_service
from shopman.backstage.services.purchase import PurchaseError


@pytest.fixture
def supplier(db):
    Supplier = apps.get_model("buyman", "Supplier")
    return Supplier.objects.create(ref="SUP-TAMURA", name="Tamura", document="12.345.678/0001-90")


@pytest.fixture
def outro_supplier(db):
    Supplier = apps.get_model("buyman", "Supplier")
    return Supplier.objects.create(ref="SUP-COFERPAN", name="Coferpan", document="98.765.432/0001-10")


@pytest.fixture
def materials(db):
    Material = apps.get_model("buyman", "Material")
    return [
        Material.objects.create(sku="CAFE-GRAO", name="Cafe em grao", unit="kg"),
        Material.objects.create(sku="FARINHA-T45", name="Farinha T45", unit="kg"),
        Material.objects.create(sku="ACUCAR", name="Acucar refinado", unit="kg"),
    ]


def _costs_for(material_sku: str):
    SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")
    return SupplierMaterialCost.objects.filter(material__sku=material_sku)


@pytest.mark.django_db
def test_lanca_varios_custos_de_uma_vez(supplier, materials):
    result = purchase_service.upsert_costs(
        {
            "supplierRef": "SUP-TAMURA",
            "makePreferred": True,
            "costs": [
                {"materialSku": "CAFE-GRAO", "costInput": "45,00"},
                {"materialSku": "FARINHA-T45", "costInput": "3,20"},
                {"materialSku": "ACUCAR", "costInput": "4,10"},
            ],
        }
    )

    assert result["saved"] == 3
    for sku, cents in (("CAFE-GRAO", 4500), ("FARINHA-T45", 320), ("ACUCAR", 410)):
        cost = _costs_for(sku).get()
        assert cost.cost_q == cents
        assert cost.supplier.ref == "SUP-TAMURA"
        # Sem preferencial o insumo não vira pedido — é o ponto do lote.
        assert cost.is_preferred is True


@pytest.mark.django_db
def test_o_fornecedor_da_linha_vence_o_do_lote(supplier, outro_supplier, materials):
    """Herança de fornecedor: o do lote é o padrão, a linha pode discordar."""
    purchase_service.upsert_costs(
        {
            "supplierRef": "SUP-TAMURA",
            "makePreferred": True,
            "costs": [
                {"materialSku": "CAFE-GRAO", "costInput": "45,00"},
                {"materialSku": "FARINHA-T45", "costInput": "3,20", "supplierRef": "SUP-COFERPAN"},
            ],
        }
    )

    assert _costs_for("CAFE-GRAO").get().supplier.ref == "SUP-TAMURA"
    assert _costs_for("FARINHA-T45").get().supplier.ref == "SUP-COFERPAN"


@pytest.mark.django_db
def test_linha_invalida_derruba_o_lote_inteiro(supplier, materials):
    """Tudo-ou-nada: dinheiro meio-aplicado é pior que lote recusado."""
    with pytest.raises(PurchaseError) as excinfo:
        purchase_service.upsert_costs(
            {
                "supplierRef": "SUP-TAMURA",
                "makePreferred": True,
                "costs": [
                    {"materialSku": "CAFE-GRAO", "costInput": "45,00"},
                    {"materialSku": "NAO-EXISTE", "costInput": "1,00"},
                ],
            }
        )

    assert excinfo.value.code == "cost_batch_invalid"
    # O erro tem de dizer QUAL linha, senão o operador procura no escuro.
    assert excinfo.value.lines[0]["index"] == 1
    assert excinfo.value.lines[0]["materialSku"] == "NAO-EXISTE"
    # E nada entrou.
    assert not _costs_for("CAFE-GRAO").exists()


@pytest.mark.django_db
def test_valor_zerado_e_recusado_com_a_linha_apontada(supplier, materials):
    with pytest.raises(PurchaseError) as excinfo:
        purchase_service.upsert_costs(
            {
                "supplierRef": "SUP-TAMURA",
                "costs": [
                    {"materialSku": "CAFE-GRAO", "costInput": "45,00"},
                    {"materialSku": "FARINHA-T45", "costInput": "0,00"},
                ],
            }
        )

    assert excinfo.value.lines[0]["index"] == 1
    assert excinfo.value.lines[0]["field"] == "costInput"
    assert not _costs_for("CAFE-GRAO").exists()


@pytest.mark.django_db
def test_linha_em_branco_e_ignorada(supplier, materials):
    """A tela lista TODOS os insumos; o operador preenche os que sabe."""
    result = purchase_service.upsert_costs(
        {
            "supplierRef": "SUP-TAMURA",
            "costs": [
                {"materialSku": "CAFE-GRAO", "costInput": "45,00"},
                {"materialSku": "FARINHA-T45", "costInput": ""},
                {"materialSku": "ACUCAR", "costInput": "   "},
            ],
        }
    )

    assert result["saved"] == 1
    assert not _costs_for("FARINHA-T45").exists()


@pytest.mark.django_db
def test_lote_sem_nenhuma_linha_preenchida_e_recusado(supplier, materials):
    with pytest.raises(PurchaseError) as excinfo:
        purchase_service.upsert_costs(
            {"supplierRef": "SUP-TAMURA", "costs": [{"materialSku": "CAFE-GRAO", "costInput": ""}]}
        )
    assert excinfo.value.code == "cost_batch_empty"


@pytest.mark.django_db
def test_o_mesmo_insumo_duas_vezes_no_lote_e_recusado(supplier, materials):
    """Duas linhas para o mesmo par (insumo, fornecedor) escondem qual venceu."""
    with pytest.raises(PurchaseError) as excinfo:
        purchase_service.upsert_costs(
            {
                "supplierRef": "SUP-TAMURA",
                "costs": [
                    {"materialSku": "CAFE-GRAO", "costInput": "45,00"},
                    {"materialSku": "CAFE-GRAO", "costInput": "47,00"},
                ],
            }
        )
    assert excinfo.value.code == "cost_batch_invalid"
    assert excinfo.value.lines[0]["index"] == 1


@pytest.mark.django_db
def test_devolve_a_projecao_para_a_tela_nao_precisar_de_outro_round_trip(supplier, materials):
    result = purchase_service.upsert_costs(
        {
            "supplierRef": "SUP-TAMURA",
            "makePreferred": True,
            "costs": [{"materialSku": "CAFE-GRAO", "costInput": "45,00"}],
        }
    )
    assert "purchase" in result
    skus = {material.sku for material in result["purchase"].materials}
    assert "CAFE-GRAO" in skus
