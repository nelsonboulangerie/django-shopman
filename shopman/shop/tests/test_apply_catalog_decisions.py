"""`apply_catalog_decisions` apaga o que o dono marcou `excluir` — e deixa a lápide.

A lápide tem de nascer ANTES do delete e na mesma transação: o vínculo com a
coleção é CASCADE, e depois do delete a prateleira de origem não existe mais em
lugar nenhum (ver `shop.services.retired_urls`).
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import RetiredProduct

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _sem_lapides_da_migracao():
    """A 0068 semeia as oito lápides de 23/09 no banco de teste; aqui partimos do zero."""
    RetiredProduct.objects.all().delete()


def _produto_na_prateleira(sku: str, ref: str) -> Product:
    produto = Product.objects.create(sku=sku, name=sku, unit="un", base_price_q=1000)
    colecao = Collection.objects.create(ref=ref, name=ref.title(), is_active=True)
    CollectionItem.objects.create(collection=colecao, product=produto)
    return produto


def test_apagar_grava_a_lapide_com_a_prateleira_de_origem():
    _produto_na_prateleira("PU", "doces")

    call_command("apply_catalog_decisions", "--apply", stdout=None)

    assert not Product.objects.filter(sku="PU").exists()
    lapide = RetiredProduct.objects.get(sku="PU")
    assert lapide.collection_refs == "doces"
    assert lapide.note == "era ideia, não virou produto"


def test_o_ensaio_nao_grava_nem_a_lapide():
    _produto_na_prateleira("PU", "doces")

    call_command("apply_catalog_decisions", stdout=None)

    assert Product.objects.filter(sku="PU").exists()
    assert not RetiredProduct.objects.filter(sku="PU").exists()


def test_a_cream_soda_sai_apagada_mesmo_tendo_saido_em_pedido():
    """Decisão de 24/09. Pré-go-live o pedido é sintético, e o item guarda o SKU como texto."""
    from shopman.orderman.models import Order, OrderItem

    _produto_na_prateleira("CV", "bebidas-geladas")
    pedido = Order.objects.create(ref="PDV-CV", channel_ref="pdv", status="completed", total_q=2100)
    OrderItem.objects.create(
        order=pedido, line_id="L1", sku="CV", name="Cream Soda do dia",
        qty=1, unit_price_q=2100, line_total_q=2100,
    )

    call_command("apply_catalog_decisions", "--apply", stdout=None)

    assert not Product.objects.filter(sku="CV").exists()
    assert OrderItem.objects.filter(sku="CV").exists()
    assert RetiredProduct.objects.get(sku="CV").collection_refs == "bebidas-geladas"
