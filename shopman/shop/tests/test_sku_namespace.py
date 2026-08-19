"""O namespace de SKU tem um porteiro — e ele mora no orquestrador.

`offerman.Product.sku` e `buyman.Material.sku` são únicos cada um na sua tabela;
nada no banco impede o mesmo SKU nas duas. Quando isso acontece, todo caminho
composto resolve o produto primeiro e o insumo homônimo some sem barulho.

Cores não se importam (ADR-001): a colisão é pergunta de quem já compõe os dois.
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
    """Captura records mesmo com ``propagate=False`` no logger ``shopman``.

    Mesmo motivo (e mesma receita) de ``test_maintenance_worker._capture_worker_logs``:
    o handler do ``caplog`` mora na raiz, e o settings corta a propagação antes.
    """
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
    """Cria um Material colidido sem passar pelo porteiro (bulk_create não emite pre_save).

    Simula o dado que chegou por caminho que o guarda não cobre: fixture antiga,
    shell, migração de outro sistema.
    """
    return Material.objects.bulk_create([Material(**kwargs)])[0]


class TestPorteiroDeSku:
    def test_insumo_recusa_sku_que_ja_e_produto(self):
        Product.objects.create(sku="CANELA", name="Canela em pó (varejo)", unit="un", base_price_q=1200)
        with pytest.raises(ValidationError) as exc:
            Material.objects.create(sku="CANELA", name="Canela", unit="g")
        assert "CANELA" in str(exc.value)

    def test_produto_recusa_sku_que_ja_e_insumo(self):
        Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")
        with pytest.raises(ValidationError) as exc:
            Product.objects.create(sku="FARINHA-T65", name="Farinha T65 (pacote)", unit="un", base_price_q=1800)
        assert "FARINHA-T65" in str(exc.value)

    def test_sku_livre_passa_dos_dois_lados(self):
        Material.objects.create(sku="FERMENTO-NAT", name="Levain", unit="kg")
        product = Product.objects.create(sku="CROISSANT", name="Croissant", unit="un", base_price_q=800)
        assert product.pk is not None

    def test_salvar_outro_campo_de_linha_ja_colidida_nao_trava(self):
        """Colisão preexistente não pode trancar o dono para fora do conserto."""
        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        material = _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        material.name = "Água filtrada"
        material.save()  # mesmo sku, outro campo — o porteiro não se mete

        assert Material.objects.get(pk=material.pk).name == "Água filtrada"

    def test_renomear_para_sku_ocupado_e_recusado(self):
        Product.objects.create(sku="MALTE", name="Malte (varejo)", unit="un", base_price_q=900)
        material = Material.objects.create(sku="MALTE-BR", name="Malte", unit="kg")

        material.sku = "MALTE"
        with pytest.raises(ValidationError):
            material.save()


class TestVarreduraDeColisoes:
    def test_find_sku_collisions_lista_o_que_ja_esta_no_banco(self):
        from shopman.shop.services.sku_namespace import find_sku_collisions

        assert find_sku_collisions() == []

        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        assert find_sku_collisions() == ["AGUA"]

    def test_system_check_grita_a_colisao(self):
        from shopman.shop.checks import check_sku_namespace_collision

        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        messages = check_sku_namespace_collision(None)
        assert [m.id for m in messages] == ["SHOPMAN_W015"]
        assert "AGUA" in messages[0].msg

    def test_system_check_calado_sem_colisao(self):
        from shopman.shop.checks import check_sku_namespace_collision

        Product.objects.create(sku="CROISSANT", name="Croissant", unit="un", base_price_q=800)
        Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")

        assert check_sku_namespace_collision(None) == []


class TestCatalogoCompostoNaoSombreiaEmSilencio:
    def test_colisao_vira_log_de_erro_com_os_dois_lados(self, caplog):
        from shopman.shop.adapters.catalog_backend import ComposedCatalogBackend

        Product.objects.create(sku="AGUA", name="Água mineral", unit="un", base_price_q=600)
        _material_behind_the_guard(sku="AGUA", name="Água", unit="l")

        with _capture_catalog_logs(caplog):
            info = ComposedCatalogBackend().get_product("AGUA")

        # A precedência continua determinística (produto), mas ela é anunciada.
        assert info.unit == "un"
        assert any("AGUA" in record.getMessage() for record in caplog.records)
        assert any(record.levelno == logging.ERROR for record in caplog.records)

    def test_sem_colisao_o_caminho_feliz_fica_calado(self, caplog):
        from shopman.shop.adapters.catalog_backend import ComposedCatalogBackend

        Product.objects.create(sku="CROISSANT", name="Croissant", unit="un", base_price_q=800)
        Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")

        with _capture_catalog_logs(caplog):
            backend = ComposedCatalogBackend()
            assert backend.get_product("CROISSANT").unit == "un"
            assert backend.get_product("FARINHA-T65").unit == "kg"

        assert caplog.records == []
