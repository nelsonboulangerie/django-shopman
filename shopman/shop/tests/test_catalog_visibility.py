"""Produto invisível-por-categoria — a regra e o sino.

O cardápio agrupa por coleção ATIVA e recolhe no fim quem não tem coleção
nenhuma. Quem tem só coleção DESATIVADA não cabe em nenhum dos dois e some da
loja inteira. Aqui pinamos os três casos que a regra precisa separar (órfão,
coleção ativa, sem coleção nenhuma) e a promessa do sino: um alerta enquanto o
estado durar, não um por varredura.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.backstage.models import OperatorAlert
from shopman.shop.management.commands.check_catalog_visibility import ALERT_TYPE
from shopman.shop.services import catalog_visibility

pytestmark = pytest.mark.django_db


@pytest.fixture
def vitrine(db):
    return Listing.objects.create(ref="web", name="Web", is_active=True)


def _product(sku: str, name: str, listing, *, published: bool = True):
    product = Product.objects.create(
        sku=sku, name=name, unit="un", base_price_q=500,
        is_published=published, is_sellable=True,
    )
    ListingItem.objects.create(listing=listing, product=product, price_q=500)
    return product


def _in_collection(product, ref: str, name: str, *, active: bool):
    collection, _ = Collection.objects.get_or_create(
        ref=ref, defaults={"name": name, "is_active": active}
    )
    if collection.is_active != active:
        collection.is_active = active
        collection.save(update_fields=["is_active"])
    CollectionItem.objects.create(collection=collection, product=product)
    return collection


# ── a regra ──


class TestRegra:
    def test_produto_so_em_colecao_inativa_e_detectado(self, vitrine):
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)

        assert catalog_visibility.hidden_by_inactive_collection_skus() == {"PAO"}

    def test_produto_em_colecao_ativa_nao_e_detectado(self, vitrine):
        bolo = _product("BOLO", "Bolo", vitrine)
        _in_collection(bolo, "doces", "Doces", active=True)

        assert catalog_visibility.hidden_by_inactive_collection_skus() == set()

    def test_produto_sem_vinculo_nenhum_nao_e_detectado(self, vitrine):
        """O "sem categoria" legítimo: o cardápio já o mostra no balde final."""
        _product("CAFE", "Café", vitrine)

        assert catalog_visibility.hidden_by_inactive_collection_skus() == set()

    def test_um_vinculo_ativo_basta_para_salvar_o_produto(self, vitrine):
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)
        _in_collection(pao, "promo", "Promoções", active=True)

        assert catalog_visibility.hidden_by_inactive_collection_skus() == set()

    def test_produto_despublicado_fica_de_fora(self, vitrine):
        """Despublicar é escolha da casa — a linha já diz "Oculto"."""
        pao = _product("PAO", "Pão", vitrine, published=False)
        _in_collection(pao, "paes", "Pães", active=False)

        assert catalog_visibility.hidden_by_inactive_collection_skus() == set()

    def test_produto_fora_de_vitrine_ativa_fica_de_fora(self, vitrine):
        """Sem ListingItem publicado ele não estava no cardápio de qualquer jeito."""
        orfao = Product.objects.create(
            sku="ORFAO", name="Órfão", unit="un", base_price_q=500,
            is_published=True, is_sellable=True,
        )
        _in_collection(orfao, "paes", "Pães", active=False)

        assert catalog_visibility.hidden_by_inactive_collection_skus() == set()

    def test_detalhe_nomeia_as_colecoes_inativas_a_consertar(self, vitrine):
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)

        hidden = catalog_visibility.hidden_by_inactive_collection()
        assert [h.sku for h in hidden] == ["PAO"]
        assert hidden[0].collection_refs == ("paes",)
        assert hidden[0].collection_names == ("Pães",)


# ── o sino ──


class TestAlerta:
    def _alerts(self):
        return OperatorAlert.objects.filter(type=ALERT_TYPE)

    def test_varredura_alerta_e_nomeia_os_skus(self, vitrine):
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)

        call_command("check_catalog_visibility")

        alert = self._alerts().get()
        assert alert.severity == "warning"
        assert "PAO" in alert.message
        assert "Pães" in alert.message

    def test_nao_duplica_em_duas_varreduras_seguidas(self, vitrine):
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)

        call_command("check_catalog_visibility")
        call_command("check_catalog_visibility")

        assert self._alerts().count() == 1

    def test_reconhecer_nao_traz_o_mesmo_aviso_de_volta(self, vitrine):
        """Dar ciente não é consertar — mas também não pode reabrir o sino."""
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)

        call_command("check_catalog_visibility")
        self._alerts().update(acknowledged=True)
        call_command("check_catalog_visibility")

        assert self._alerts().count() == 1

    def test_outra_colecao_desativada_e_fato_novo(self, vitrine):
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)
        call_command("check_catalog_visibility")

        bolo = _product("BOLO", "Bolo", vitrine)
        _in_collection(bolo, "doces", "Doces", active=False)
        call_command("check_catalog_visibility")

        assert self._alerts().count() == 2

    def test_catalogo_saudavel_nao_alerta(self, vitrine):
        bolo = _product("BOLO", "Bolo", vitrine)
        _in_collection(bolo, "doces", "Doces", active=True)

        call_command("check_catalog_visibility")

        assert not self._alerts().exists()

    def test_dry_run_nao_grava(self, vitrine):
        pao = _product("PAO", "Pão", vitrine)
        _in_collection(pao, "paes", "Pães", active=False)

        call_command("check_catalog_visibility", "--dry-run")

        assert not self._alerts().exists()

    def test_mensagem_resume_quando_ha_muitos_skus(self, vitrine):
        for index in range(10):
            product = _product(f"SKU{index}", f"Produto {index}", vitrine)
            _in_collection(product, "paes", "Pães", active=False)

        call_command("check_catalog_visibility")

        assert "e mais 2" in self._alerts().get().message
