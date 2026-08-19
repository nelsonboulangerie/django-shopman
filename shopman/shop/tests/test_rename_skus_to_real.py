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


class TestColisaoEmCampoUnico:
    """O que os testes de um produto por vez não pegavam.

    Só apareceu num ensaio sobre banco semeado: `ProductConsumptionTag.sku` é
    único, e o `propose_consumption_tags --include-historical` já tinha criado
    etiqueta para os códigos do Yooga. O rename estourava a constraint no meio
    da travessia, com seis pares afetados.
    """

    @pytest.fixture
    def etiquetas(self, croissant):
        from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

        papel = ConsumptionRole.objects.create(ref="hibrido", label="Híbrido", reading="hybrid")
        return papel, ProductConsumptionTag

    @pytest.mark.django_db
    def test_anotacao_funde_e_a_curada_sobrevive(self, etiquetas):
        papel, Tag = etiquetas
        Tag.objects.create(sku="CROISSANT", role=papel, reviewed=True, note="curada")
        Tag.objects.create(sku="CT", role=papel, reviewed=False, note="proposta pelo histórico")

        saida = StringIO()
        call_command("rename_skus_to_real", "--only", "CROISSANT", stdout=saida)

        assert "sobreviveu a curada" in saida.getvalue()
        sobreviveu = Tag.objects.get(sku="CT")
        assert sobreviveu.note == "curada"
        assert Tag.objects.filter(sku="CROISSANT").count() == 0

    @pytest.mark.django_db
    def test_a_curada_vence_mesmo_vindo_do_historico(self, etiquetas):
        papel, Tag = etiquetas
        Tag.objects.create(sku="CROISSANT", role=papel, reviewed=False, note="proposta")
        Tag.objects.create(sku="CT", role=papel, reviewed=True, note="curada no histórico")

        call_command("rename_skus_to_real", "--only", "CROISSANT", stdout=StringIO())

        assert Tag.objects.get(sku="CT").note == "curada no histórico"

    @pytest.mark.django_db
    def test_empate_fica_com_a_do_catalogo(self, etiquetas):
        papel, Tag = etiquetas
        Tag.objects.create(sku="CROISSANT", role=papel, reviewed=False, note="do catálogo")
        Tag.objects.create(sku="CT", role=papel, reviewed=False, note="do histórico")

        saida = StringIO()
        call_command("rename_skus_to_real", "--only", "CROISSANT", stdout=saida)

        assert "sobreviveu a do catálogo" in saida.getvalue()
        assert Tag.objects.get(sku="CT").note == "do catálogo"

    @pytest.mark.django_db
    def test_toda_politica_aponta_para_model_que_existe(self):
        # Política escrita para model que sumiu ou mudou de nome é guardrail
        # que não guarda nada.
        from django.apps import apps

        from config.management.commands.rename_skus_to_real import POLITICA_DE_COLISAO

        for label in POLITICA_DE_COLISAO:
            app_label, model_name = label.split(".", 1)
            campo = apps.get_model(app_label, model_name)._meta.get_field("sku")
            assert campo.unique, f"{label}.sku não é único — a política ali é morta"

    @pytest.mark.django_db
    def test_todo_campo_unico_de_sku_tem_politica(self):
        # O guardrail do guardrail: campo único novo sem política faria o
        # comando parar em produção, e é melhor descobrir aqui.
        from django.apps import apps
        from shopman.refs.registry import _ref_source_registry

        from config.management.commands.rename_skus_to_real import POLITICA_DE_COLISAO

        sem_politica = []
        for label, field_name in _ref_source_registry.get_sources_for_type("SKU"):
            app_label, model_name = label.split(".", 1)
            if apps.get_model(app_label, model_name)._meta.get_field(field_name).unique:
                if label not in POLITICA_DE_COLISAO:
                    sem_politica.append(label)
        assert not sem_politica, (
            f"campos de SKU únicos sem política de colisão: {sem_politica}. "
            "Decida entre 'fundir' e 'recusar' em POLITICA_DE_COLISAO."
        )
