"""Um SKU é uma coisa só — e o porteiro da coerência dele mora no orquestrador.

`offerman.Product.sku` (cadastro de venda) e `buyman.Material.sku` (cadastro de
compra) podem ser o mesmo SKU: é a coisa comprada que também se vende, e os dois
contam o mesmo estoque. A regra é de coerência: mesmo SKU → mesma unidade.

Cores não se importam (ADR-001): a coerência é pergunta de quem já compõe os dois.
"""

from __future__ import annotations

import contextlib
import logging

import pytest
from django.core.exceptions import ValidationError
from shopman.buyman.models import Material
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


CATALOG_LOGGER = "shopman.shop.adapters.catalog_backend"


@contextlib.contextmanager
def _capture_catalog_logs(caplog, level=logging.ERROR):
    """Captura records mesmo com ``propagate=False`` no logger ``shopman``."""
    catalog_logger = logging.getLogger(CATALOG_LOGGER)
    with caplog.at_level(level, logger=CATALOG_LOGGER):
        catalog_logger.addHandler(caplog.handler)
        prev_propagate = catalog_logger.propagate
        catalog_logger.propagate = False
        try:
            yield
        finally:
            catalog_logger.propagate = prev_propagate
            catalog_logger.removeHandler(caplog.handler)


def _material_behind_the_guard(**kwargs) -> Material:
    """Cria um Material sem passar pelo porteiro (bulk_create não emite pre_save)."""
    return Material.objects.bulk_create([Material(**kwargs)])[0]


class TestPorteiroDeCoerencia:
    def test_mesmo_sku_com_a_mesma_unidade_passa_dos_dois_lados(self):
        Product.objects.create(sku="GELEIA-FIGO-284", name="Geleia de Figo", unit="un", base_price_q=4200)
        material = Material.objects.create(sku="GELEIA-FIGO-284", name="Geleia de Figo", unit="un")
        assert material.pk is not None

    def test_grafias_da_mesma_unidade_sao_a_mesma_unidade(self):
        Material.objects.create(sku="AZEITE-GALAO", name="Azeite (galão)", unit="l")
        product = Product.objects.create(sku="AZEITE-GALAO", name="Azeite a granel", unit="lt", base_price_q=9000)
        assert product.pk is not None

    def test_cadastro_de_compra_recusa_unidade_divergente_da_venda(self):
        Product.objects.create(sku="CANELA-PO", name="Canela em pó (pote)", unit="un", base_price_q=1200)
        with pytest.raises(ValidationError) as exc:
            Material.objects.create(sku="CANELA-PO", name="Canela", unit="g")
        assert "CANELA-PO" in str(exc.value)
        assert "'un'" in str(exc.value)

    def test_cadastro_de_venda_recusa_unidade_divergente_da_compra(self):
        Material.objects.create(sku="FARINHA-NOVARA-T55", name="Farinha T65", unit="kg")
        with pytest.raises(ValidationError) as exc:
            Product.objects.create(sku="FARINHA-NOVARA-T55", name="Farinha (pacote)", unit="un", base_price_q=1800)
        assert "FARINHA-NOVARA-T55" in str(exc.value)

    def test_trocar_a_unidade_de_um_lado_so_e_recusado(self):
        Product.objects.create(sku="QUEIJO-GRUYERE", name="Gruyère", unit="kg", base_price_q=24900)
        material = Material.objects.create(sku="QUEIJO-GRUYERE", name="Gruyère", unit="kg")

        material.unit = "un"
        with pytest.raises(ValidationError):
            material.save()

    def test_salvar_outro_campo_de_linha_ja_incoerente_nao_trava(self):
        """Incoerência preexistente não pode trancar o dono para fora do conserto."""
        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        material = _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        material.name = "Água filtrada"
        material.save()  # mesmo sku e unidade, outro campo — o porteiro não se mete

        assert Material.objects.get(pk=material.pk).name == "Água filtrada"

    def test_renomear_para_sku_com_outra_unidade_e_recusado(self):
        Product.objects.create(sku="MALTE-EXTRATO", name="Malte (varejo)", unit="un", base_price_q=900)
        material = Material.objects.create(sku="MALTE-BR", name="Malte", unit="kg")

        material.sku = "MALTE-EXTRATO"
        with pytest.raises(ValidationError):
            material.save()


class TestVarreduraDeIncoerencias:
    def test_find_sku_incoherences_lista_so_a_unidade_divergente(self):
        from shopman.shop.services.sku_namespace import find_sku_incoherences

        Product.objects.create(sku="GELEIA-FIGO-284", name="Geleia", unit="un", base_price_q=4200)
        Material.objects.create(sku="GELEIA-FIGO-284", name="Geleia", unit="un")
        assert find_sku_incoherences() == []

        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        assert [item.sku for item in find_sku_incoherences()] == ["AGUA"]

    def test_system_check_grita_a_incoerencia(self):
        from shopman.shop.checks import check_sku_namespace_coherence

        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        messages = check_sku_namespace_coherence(None)
        assert [m.id for m in messages] == ["SHOPMAN_W015"]
        assert "AGUA (venda em un, compra em l)" in messages[0].msg

    def test_system_check_calado_quando_os_dois_cadastros_concordam(self):
        from shopman.shop.checks import check_sku_namespace_coherence

        Product.objects.create(sku="GELEIA-FIGO-284", name="Geleia", unit="un", base_price_q=4200)
        Material.objects.create(sku="GELEIA-FIGO-284", name="Geleia", unit="un")
        Material.objects.create(sku="FARINHA-NOVARA-T55", name="Farinha T65", unit="kg")

        assert check_sku_namespace_coherence(None) == []


class TestCatalogoComposto:
    def test_incoerencia_vira_log_de_erro_com_os_dois_lados(self, caplog):
        from shopman.shop.adapters.catalog_backend import ComposedCatalogBackend

        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        with _capture_catalog_logs(caplog):
            info = ComposedCatalogBackend().get_product("AGUA")

        assert info.unit == "un"
        assert any("AGUA" in record.getMessage() for record in caplog.records)
        assert any(record.levelno == logging.ERROR for record in caplog.records)

    def test_os_dois_cadastros_coerentes_ficam_calados(self, caplog):
        from shopman.shop.adapters.catalog_backend import ComposedCatalogBackend

        Product.objects.create(sku="GELEIA-FIGO-284", name="Geleia", unit="un", base_price_q=4200)
        Material.objects.create(sku="GELEIA-FIGO-284", name="Geleia", unit="un")
        Material.objects.create(sku="FARINHA-NOVARA-T55", name="Farinha T65", unit="kg")

        with _capture_catalog_logs(caplog):
            backend = ComposedCatalogBackend()
            assert backend.get_product("GELEIA-FIGO-284").unit == "un"
            assert backend.get_product("FARINHA-NOVARA-T55").unit == "kg"

        assert caplog.records == []
