"""O custo lança pela unidade de compra (UNIT-CONVERSION-PLAN, Fase 3).

O operador copia da nota — "1 saco", "R$ 180,00" — e quem divide é a máquina
(ADR-024, R2). O custo por unidade-base é derivado em ``Decimal`` e arredonda
só na ponta; fator incoerente recusa em vez de virar custo 25× errado (R4).
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from shopman.buyman.models import (
    Material,
    MaterialConversion,
    Supplier,
    SupplierMaterialCost,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def farinha():
    return Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")


@pytest.fixture
def ovos():
    return Material.objects.create(sku="OVOS", name="Ovos", unit="kg")


@pytest.fixture
def moinho():
    return Supplier.objects.create(ref="SUP-MOINHO", name="Moinho SP")


@pytest.fixture
def cooperativa():
    return Supplier.objects.create(ref="SUP-COOP", name="Cooperativa")


@pytest.fixture
def saco_25(farinha):
    return MaterialConversion.objects.create(
        material=farinha, label="saco 25 kg", to_base_factor=Decimal("25"),
    )


class TestCustoPorUnidadeBase:
    def test_o_operador_copia_a_nota_e_a_maquina_divide(self, farinha, moinho, saco_25):
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, conversion=saco_25, cost_q=18000,
        )
        # R$ 180,00 o saco de 25 kg = R$ 7,20 o quilo.
        assert cost.cost_per_base_unit == Decimal("720")
        assert cost.cost_per_base_unit_q == 720
        assert cost.purchase_unit_label == "saco 25 kg"

    def test_sem_conversao_a_unidade_de_compra_e_a_propria_base(self, farinha, moinho):
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, cost_q=720,
        )
        assert cost.base_factor == Decimal("1")
        assert cost.cost_per_base_unit == Decimal("720")
        assert cost.purchase_unit_label == "kg"

    def test_a_divisao_nao_arredonda_no_meio_da_conta(self, farinha, moinho):
        # R$ 100,00 por saco de 30 kg = 333,333… centavos por quilo. O Decimal
        # guarda a fração; o inteiro só aparece quando alguém pede o inteiro.
        conversion = MaterialConversion.objects.create(
            material=farinha, label="saco 30 kg", to_base_factor=Decimal("30"),
        )
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, conversion=conversion, cost_q=10000,
        )
        assert cost.cost_per_base_unit > Decimal("333.33")
        assert cost.cost_per_base_unit < Decimal("333.34")
        assert cost.cost_per_base_unit_q == 333

    def test_arredonda_meio_centavo_para_cima_na_ponta(self, farinha, moinho):
        conversion = MaterialConversion.objects.create(
            material=farinha, label="fardo 2 kg", to_base_factor=Decimal("2"),
        )
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, conversion=conversion, cost_q=701,
        )
        assert cost.cost_per_base_unit == Decimal("350.5")
        assert cost.cost_per_base_unit_q == 351

    def test_corrigir_o_fator_reprecifica_sem_tocar_no_custo(self, farinha, moinho, saco_25):
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, conversion=saco_25, cost_q=18000,
        )
        assert cost.cost_per_base_unit_q == 720

        # O moinho passou a embalar 20 kg pelo mesmo preço.
        saco_25.to_base_factor = Decimal("20")
        saco_25.label = "saco 20 kg"
        saco_25.save()
        cost.refresh_from_db()

        assert cost.cost_q == 18000  # o número da nota não mudou
        assert cost.cost_per_base_unit_q == 900


class TestOCarimboDaAproximacao:
    def test_custo_por_ponte_aproximada_e_estimado(self, ovos, moinho):
        # Compra-se ovo por cartela; consome-se ovo por peso. A ponte existe,
        # mas o número que sai dela carrega o "≈".
        cartela = MaterialConversion.objects.create(
            material=ovos, label="cartela", to_base_factor=Decimal("1.5"),
            kind=MaterialConversion.Kind.APPROXIMATE,
        )
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=ovos, conversion=cartela, cost_q=2400,
        )
        assert cost.is_approximate is True
        assert cost.cost_per_base_unit_q == 1600

    def test_custo_na_base_nao_ganha_enfeite(self, farinha, moinho, saco_25):
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, conversion=saco_25, cost_q=18000,
        )
        assert cost.is_approximate is False

    def test_sem_conversao_nao_ha_aproximacao(self, farinha, moinho):
        cost = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, cost_q=720,
        )
        assert cost.is_approximate is False


class TestRecusaDeConversaoIncoerente:
    def test_conversao_de_outro_insumo_e_recusada(self, farinha, ovos, moinho, saco_25):
        cost = SupplierMaterialCost(
            supplier=moinho, material=ovos, conversion=saco_25, cost_q=2400,
        )
        with pytest.raises(ValidationError) as exc:
            cost.full_clean()
        assert "conversion" in exc.value.message_dict
        assert "OVOS" in str(exc.value)

    def test_conversao_de_outro_fornecedor_e_recusada(
        self, farinha, moinho, cooperativa
    ):
        saco_do_moinho = MaterialConversion.objects.create(
            material=farinha, supplier=moinho, label="saco", to_base_factor=Decimal("25"),
        )
        cost = SupplierMaterialCost(
            supplier=cooperativa, material=farinha,
            conversion=saco_do_moinho, cost_q=18000,
        )
        with pytest.raises(ValidationError) as exc:
            cost.full_clean()
        assert "conversion" in exc.value.message_dict
        assert "Cooperativa" in str(exc.value)

    def test_conversao_sem_dono_serve_a_qualquer_fornecedor(
        self, farinha, cooperativa, saco_25
    ):
        cost = SupplierMaterialCost(
            supplier=cooperativa, material=farinha, conversion=saco_25, cost_q=18000,
        )
        cost.full_clean()  # não levanta

    def test_conversao_inativa_e_recusada(self, farinha, moinho, saco_25):
        saco_25.is_active = False
        saco_25.save()
        cost = SupplierMaterialCost(
            supplier=moinho, material=farinha, conversion=saco_25, cost_q=18000,
        )
        with pytest.raises(ValidationError) as exc:
            cost.full_clean()
        assert "conversion" in exc.value.message_dict

    def test_a_recusa_vale_no_save_tambem_nao_so_no_formulario(
        self, farinha, ovos, moinho, saco_25
    ):
        # O contrato é do modelo, não da tela: quem grava direto também esbarra.
        with pytest.raises(ValidationError):
            SupplierMaterialCost.objects.create(
                supplier=moinho, material=ovos, conversion=saco_25, cost_q=2400,
            )
