"""Invariantes de dinheiro e do custo preferencial.

Três coisas que a casa cobra em toda tabela de dinheiro e faltavam aqui:
custo positivo garantido pelo banco, troca de preferencial sem IntegrityError
cru na tela, e preferencial que não aponta para par aposentado.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from shopman.buyman.models import Material, Supplier, SupplierMaterialCost

pytestmark = pytest.mark.django_db


@pytest.fixture
def farinha():
    return Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")


@pytest.fixture
def moinho():
    return Supplier.objects.create(ref="moinho", name="Moinho SP")


@pytest.fixture
def cooperativa():
    return Supplier.objects.create(ref="coop", name="Cooperativa")


class TestCustoPositivo:
    def test_custo_zero_nao_entra_no_banco(self, farinha, moinho):
        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierMaterialCost.objects.create(supplier=moinho, material=farinha, cost_q=0)

    def test_custo_negativo_nao_entra_no_banco(self, farinha, moinho):
        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierMaterialCost.objects.create(supplier=moinho, material=farinha, cost_q=-350)

    def test_full_clean_explica_antes_do_banco(self, farinha, moinho):
        cost = SupplierMaterialCost(supplier=moinho, material=farinha, cost_q=0)
        with pytest.raises(ValidationError) as exc:
            cost.full_clean()
        assert "zero" in str(exc.value).lower() or "maior" in str(exc.value).lower()


class TestPromocaoAtomicaDoPreferencial:
    def test_promover_o_segundo_demove_o_primeiro(self, farinha, moinho, cooperativa):
        primeiro = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, cost_q=350, is_preferred=True,
        )
        segundo = SupplierMaterialCost.objects.create(
            supplier=cooperativa, material=farinha, cost_q=300, is_preferred=True,
        )

        primeiro.refresh_from_db()
        segundo.refresh_from_db()
        assert primeiro.is_preferred is False
        assert segundo.is_preferred is True

    def test_promover_um_alternativo_existente_tambem_demove(self, farinha, moinho, cooperativa):
        primeiro = SupplierMaterialCost.objects.create(
            supplier=moinho, material=farinha, cost_q=350, is_preferred=True,
        )
        alternativo = SupplierMaterialCost.objects.create(
            supplier=cooperativa, material=farinha, cost_q=300,
        )

        alternativo.is_preferred = True
        alternativo.save()

        primeiro.refresh_from_db()
        assert primeiro.is_preferred is False
        assert SupplierMaterialCost.objects.filter(material=farinha, is_preferred=True).count() == 1

    def test_a_demissao_nao_atravessa_para_outro_insumo(self, farinha, moinho, cooperativa):
        centeio = Material.objects.create(sku="CENTEIO", name="Farinha de centeio", unit="kg")
        do_centeio = SupplierMaterialCost.objects.create(
            supplier=moinho, material=centeio, cost_q=700, is_preferred=True,
        )
        SupplierMaterialCost.objects.create(
            supplier=cooperativa, material=farinha, cost_q=300, is_preferred=True,
        )

        do_centeio.refresh_from_db()
        assert do_centeio.is_preferred is True


class TestPreferencialNaoApontaParaAposentado:
    def test_insumo_inativo_recusa_preferencial(self, moinho):
        aposentado = Material.objects.create(
            sku="MALTE", name="Malte", unit="kg", is_active=False,
        )
        with pytest.raises(ValidationError) as exc:
            SupplierMaterialCost.objects.create(
                supplier=moinho, material=aposentado, cost_q=900, is_preferred=True,
            )
        assert "inativo" in str(exc.value).lower()

    def test_fornecedor_inativo_recusa_preferencial(self, farinha):
        aposentado = Supplier.objects.create(ref="velho", name="Antigo", is_active=False)
        with pytest.raises(ValidationError) as exc:
            SupplierMaterialCost.objects.create(
                supplier=aposentado, material=farinha, cost_q=350, is_preferred=True,
            )
        assert "inativo" in str(exc.value).lower()

    def test_custo_alternativo_de_par_inativo_continua_valido(self, farinha):
        aposentado = Supplier.objects.create(ref="velho", name="Antigo", is_active=False)
        cost = SupplierMaterialCost.objects.create(
            supplier=aposentado, material=farinha, cost_q=350,
        )
        assert cost.pk is not None

    def test_full_clean_explica_o_veto(self, farinha):
        aposentado = Supplier.objects.create(ref="velho", name="Antigo", is_active=False)
        cost = SupplierMaterialCost(
            supplier=aposentado, material=farinha, cost_q=350, is_preferred=True,
        )
        with pytest.raises(ValidationError) as exc:
            cost.full_clean()
        assert "inativo" in str(exc.value).lower()
