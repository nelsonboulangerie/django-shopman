"""A tabela de conversões do insumo (UNIT-CONVERSION-PLAN, Fase 2).

Três coisas que a ADR-024 cobra desta tabela e que o banco tem de garantir
sozinho: fator positivo, rótulo que não se duplica dentro do mesmo escopo, e a
aproximada nunca se passando por exata.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from shopman.buyman.models import Material, MaterialConversion, Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture
def ovos():
    return Material.objects.create(sku="OVOS", name="Ovos", unit="kg")


@pytest.fixture
def farinha():
    return Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")


@pytest.fixture
def moinho():
    return Supplier.objects.create(ref="moinho", name="Moinho SP")


@pytest.fixture
def cooperativa():
    return Supplier.objects.create(ref="coop", name="Cooperativa")


class TestFatorPositivo:
    def test_fator_zero_nao_entra_no_banco(self, farinha):
        with pytest.raises(IntegrityError), transaction.atomic():
            MaterialConversion.objects.create(
                material=farinha, label="saco", to_base_factor=Decimal("0"),
            )

    def test_fator_negativo_nao_entra_no_banco(self, farinha):
        with pytest.raises(IntegrityError), transaction.atomic():
            MaterialConversion.objects.create(
                material=farinha, label="saco", to_base_factor=Decimal("-25"),
            )

    def test_full_clean_explica_antes_do_banco(self, farinha):
        conversion = MaterialConversion(
            material=farinha, label="saco", to_base_factor=Decimal("0"),
        )
        with pytest.raises(ValidationError) as exc:
            conversion.full_clean()
        assert "to_base_factor" in exc.value.message_dict


class TestRotuloUnicoNoEscopo:
    def test_mesmo_rotulo_duas_vezes_sem_fornecedor_e_recusado(self, farinha):
        MaterialConversion.objects.create(
            material=farinha, label="saco 25 kg", to_base_factor=Decimal("25"),
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            MaterialConversion.objects.create(
                material=farinha, label="saco 25 kg", to_base_factor=Decimal("20"),
            )

    def test_mesmo_rotulo_duas_vezes_no_mesmo_fornecedor_e_recusado(self, farinha, moinho):
        MaterialConversion.objects.create(
            material=farinha, supplier=moinho, label="saco", to_base_factor=Decimal("25"),
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            MaterialConversion.objects.create(
                material=farinha, supplier=moinho, label="saco", to_base_factor=Decimal("20"),
            )

    def test_o_mesmo_rotulo_pode_ter_fator_proprio_por_fornecedor(
        self, farinha, moinho, cooperativa
    ):
        # O saco do moinho tem 25 kg; o da cooperativa, 20. É o caso que a ADR
        # previu quando deu escopo de fornecedor à linha.
        MaterialConversion.objects.create(
            material=farinha, supplier=moinho, label="saco", to_base_factor=Decimal("25"),
        )
        MaterialConversion.objects.create(
            material=farinha, supplier=cooperativa, label="saco", to_base_factor=Decimal("20"),
        )
        assert farinha.conversions.count() == 2

    def test_rotulo_repetido_em_outro_insumo_e_normal(self, farinha, ovos):
        MaterialConversion.objects.create(
            material=farinha, label="caixa", to_base_factor=Decimal("10"),
        )
        MaterialConversion.objects.create(
            material=ovos, label="caixa", to_base_factor=Decimal("1.5"),
        )
        assert MaterialConversion.objects.filter(label="caixa").count() == 2

    def test_rotulo_em_branco_e_recusado(self, farinha):
        conversion = MaterialConversion(
            material=farinha, label="   ", to_base_factor=Decimal("25"),
        )
        with pytest.raises(ValidationError) as exc:
            conversion.full_clean()
        assert "label" in exc.value.message_dict


class TestAproximadaNaoPassaPorExata:
    def test_o_padrao_e_convencionada(self, farinha):
        conversion = MaterialConversion.objects.create(
            material=farinha, label="saco 25 kg", to_base_factor=Decimal("25"),
        )
        assert conversion.kind == MaterialConversion.Kind.CONVENTIONAL
        assert conversion.is_approximate is False

    def test_aproximada_se_declara(self, ovos):
        conversion = MaterialConversion.objects.create(
            material=ovos, label="ovos", to_base_factor=Decimal("0.05"),
            kind=MaterialConversion.Kind.APPROXIMATE,
        )
        assert conversion.is_approximate is True
        # O carimbo aparece já na representação: número aproximado não circula liso.
        assert "≈" in str(conversion)

    def test_convencionada_nao_ganha_enfeite(self, farinha):
        conversion = MaterialConversion.objects.create(
            material=farinha, label="saco 25 kg", to_base_factor=Decimal("25"),
        )
        assert "≈" not in str(conversion)
        assert "kg" in str(conversion)

    def test_o_insumo_pode_ter_as_duas_sem_se_confundirem(self, ovos):
        MaterialConversion.objects.create(
            material=ovos, label="cartela", to_base_factor=Decimal("1.5"),
            kind=MaterialConversion.Kind.APPROXIMATE,
        )
        MaterialConversion.objects.create(
            material=ovos, label="caixa 12 cartelas", to_base_factor=Decimal("18"),
            kind=MaterialConversion.Kind.APPROXIMATE,
        )
        MaterialConversion.objects.create(
            material=ovos, label="pote 1 kg", to_base_factor=Decimal("1"),
        )
        approximate = set(
            ovos.conversions.filter(
                kind=MaterialConversion.Kind.APPROXIMATE
            ).values_list("label", flat=True)
        )
        assert approximate == {"cartela", "caixa 12 cartelas"}
