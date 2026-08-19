"""O rename tem de atravessar os apps, e tem de ser seguro de repetir (F3).

O que estes testes protegem não é o mapa — é o comportamento em volta dele:
que o cascade alcance estoque e curadoria, que rodar duas vezes não quebre, que
o ensaio realmente desfaça, e que os dois casos de mudança de unidade fiquem
retidos até alguém decidir.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from shopman.offerman.models import Product
from shopman.stockman.models import Position, Quant

from config.management.commands.rename_skus_to_real import RENAMES, RETIDOS


@pytest.fixture
def croissant(db):
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)
    produto = Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=1300)
    Quant.objects.create(sku="CROISSANT", position=vitrine)
    return produto


class TestOMapa:
    def test_nenhum_codigo_real_repetido(self):
        # Dois produtos com o mesmo código real fariam o segundo rename morrer
        # no unique — depois de o primeiro já ter passado.
        reais = [real for _antigo, real in RENAMES]
        assert len(reais) == len(set(reais))

    def test_nenhum_sku_de_origem_repetido(self):
        antigos = [antigo for antigo, _real in RENAMES]
        assert len(antigos) == len(set(antigos))

    def test_retidos_estao_fora_do_mapa(self):
        # O mapa e a lista de retidos não podem se sobrepor: seria renomear
        # justamente o que se decidiu segurar.
        assert not {antigo for antigo, _ in RENAMES} & set(RETIDOS)


class TestExecucao:
    @pytest.mark.django_db
    def test_atravessa_catalogo_e_estoque(self, croissant):
        call_command("rename_skus_to_real", "--only", "CROISSANT", stdout=StringIO())

        assert Product.objects.filter(sku="CT").exists()
        assert not Product.objects.filter(sku="CROISSANT").exists()
        assert Quant.objects.filter(sku="CT").exists()

    @pytest.mark.django_db
    def test_rodar_de_novo_nao_quebra(self, croissant):
        call_command("rename_skus_to_real", "--only", "CROISSANT", stdout=StringIO())
        saida = StringIO()
        call_command("rename_skus_to_real", "--only", "CROISSANT", stdout=saida)

        assert "Nada a renomear" in saida.getvalue()
        assert Product.objects.filter(sku="CT").count() == 1

    @pytest.mark.django_db
    def test_ensaio_desfaz(self, croissant):
        saida = StringIO()
        call_command("rename_skus_to_real", "--only", "CROISSANT", "--dry-run", stdout=saida)

        assert "Faria" in saida.getvalue()
        assert Product.objects.filter(sku="CROISSANT").exists()
        assert not Product.objects.filter(sku="CT").exists()

    @pytest.mark.django_db
    def test_nao_funde_dois_produtos(self, croissant):
        # Alguém criou o CT à mão antes de rodar. Renomear fundiria os dois.
        Product.objects.create(sku="CT", name="Croissant Tradicional", base_price_q=1300)

        saida = StringIO()
        call_command("rename_skus_to_real", "--only", "CROISSANT", stdout=saida)

        assert "existem os dois" in saida.getvalue()
        assert Product.objects.filter(sku="CROISSANT").exists()
        assert Product.objects.filter(sku="CT").exists()

    @pytest.mark.django_db
    def test_retido_recusa_com_motivo(self):
        erro = StringIO()
        call_command("rename_skus_to_real", "--only", "PAO-HOTDOG", stderr=erro)

        saida = erro.getvalue()
        assert "retido" in saida
        assert "pacote de 4" in saida

    @pytest.mark.django_db
    def test_catalogo_vazio_nao_e_erro(self):
        saida = StringIO()
        call_command("rename_skus_to_real", stdout=saida)

        assert "Nada a renomear" in saida.getvalue()
