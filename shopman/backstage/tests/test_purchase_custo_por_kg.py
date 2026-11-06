"""Custo de insumo em grama se guarda por quilo (beta 05/11, CMP-07; dono, 06/11).

O recebimento de 1200 g por R$ 110 gravava o custo em centavo inteiro por grama:
R$ 0,09/g (o real é 0,0917), e a reposição de 300 g saía R$ 27,00. Agora o custo
sem embalagem é do kg (ou do litro, para ml): R$ 91,67/kg, e 300 g = R$ 27,50.
O preço de venda continua centavo inteiro por unidade do produto, e por isso o
item contado em g não se coloca à venda: venda a granel é por kg.
"""

from __future__ import annotations

import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from shopman.buyman.models import Material, Supplier, SupplierMaterialCost
from shopman.offerman.models import Product
from shopman.stockman.models import Move, Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services import purchase as purchase_service


@pytest.fixture
def operador(db):
    return User.objects.create_user("compras-kg", password="pw", is_staff=True)


@pytest.fixture
def tonica(db):
    Position.objects.get_or_create(
        ref="estoque",
        defaults={"name": "Estoque", "kind": PositionKind.PHYSICAL, "is_saleable": False},
    )
    fornecedor = Supplier.objects.create(ref="ambev", name="Ambev")
    material = Material.objects.create(sku="TONICA-ANTARCTICA", name="Água tônica", unit="g")
    return fornecedor, material


def _receber(fornecedor, *, qty="1200", valor="110,00", user=None):
    purchase_service.confirm_receipt(
        {
            "mode": "manual",
            "supplierRef": fornecedor.ref,
            "note": "",
            "lines": [{
                "id": "l1", "materialSku": "TONICA-ANTARCTICA",
                "purchaseQty": qty, "costInput": valor, "checked": True,
            }],
        },
        user=user,
    )


def test_receber_1200_g_por_110_grava_91_67_o_kg(tonica, operador):
    fornecedor, material = tonica

    _receber(fornecedor, user=operador)

    custo = SupplierMaterialCost.objects.get(material=material, supplier=fornecedor)
    assert custo.cost_q == 9167
    assert custo.priced_unit_label == "kg"
    assert custo.cost_per_display_unit_q() == (9167, "kg")
    move = Move.objects.get()
    assert move.metadata["purchase_unit_cost_q"] == 9167
    assert move.metadata["purchase_total_cost_q"] == 11000


def test_a_reposicao_de_300_g_custa_27_50(tonica, operador, monkeypatch):
    fornecedor, material = tonica
    _receber(fornecedor, user=operador)
    custo = SupplierMaterialCost.objects.get(material=material, supplier=fornecedor)

    assert custo.cost_for_base_qty_q(Decimal("300")) == 2750
    monkeypatch.setattr(
        purchase_service, "build_purchase",
        lambda: SimpleNamespace(materials=[SimpleNamespace(sku=material.sku, suggestedQty=300)]),
    )
    snapshot = purchase_service._purchase_request_snapshot(material, custo)
    assert snapshot["estimated_total"].replace("\xa0", " ") == "R$ 27,50"
    assert snapshot["purchase_qty_display"] == "300 g"


def test_item_contado_em_g_nao_se_coloca_a_venda(tonica):
    _fornecedor, material = tonica

    with pytest.raises(purchase_service.PurchaseError) as exc:
        purchase_service.set_sale(material.sku, {"enabled": True, "priceInput": "0,06"})

    assert "perde os centavos" in str(exc.value)
    assert not Product.objects.filter(sku=material.sku).exists()


def test_sugestao_de_preco_nao_existe_para_item_em_g(tonica, operador):
    from shopman.shop.resale_markup import unit_costs_map

    fornecedor, material = tonica
    _receber(fornecedor, user=operador)

    assert unit_costs_map([material.sku]) == {}


def test_a_migracao_converte_o_custo_por_grama_para_o_quilo(tonica):
    fornecedor, material = tonica
    farinha = Material.objects.create(sku="FARINHA-UN", name="Pacote", unit="un")
    por_grama = SupplierMaterialCost.objects.create(supplier=fornecedor, material=material, cost_q=9)
    por_unidade = SupplierMaterialCost.objects.create(supplier=fornecedor, material=farinha, cost_q=450)

    migration = importlib.import_module("shopman.buyman.migrations.0012_cost_q_por_unidade_de_leitura")
    migration.forward(django_apps, None)

    por_grama.refresh_from_db()
    por_unidade.refresh_from_db()
    assert por_grama.cost_q == 9000
    assert por_unidade.cost_q == 450
