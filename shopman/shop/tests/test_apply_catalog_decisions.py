"""Decisões de catálogo preservam os registros históricos do BI e dos pedidos."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.offerman.models import Collection, CollectionItem, Product

from config.management.commands.apply_catalog_decisions import UNPUBLISH

pytestmark = pytest.mark.django_db


def _produto_na_prateleira(sku: str, ref: str) -> Product:
    produto = Product.objects.create(sku=sku, name=sku, unit="un", base_price_q=1000)
    colecao = Collection.objects.create(ref=ref, name=ref.title(), is_active=True)
    CollectionItem.objects.create(collection=colecao, product=produto)
    return produto


def test_apagar_remove_o_produto():
    _produto_na_prateleira("PU", "doces")

    call_command("apply_catalog_decisions", "--apply", stdout=None)

    assert not Product.objects.filter(sku="PU").exists()


def test_o_ensaio_preserva_o_produto():
    _produto_na_prateleira("PU", "doces")

    call_command("apply_catalog_decisions", stdout=None)

    assert Product.objects.filter(sku="PU").exists()


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


def test_a_decisao_de_despublicar_nao_depende_de_ficha():
    """Produto fora da loja por DECISÃO continua fora depois de ganhar ficha.

    A Focaccia Cebola Roxa e a mini dela já nasciam despublicadas no seed, mas
    por um motivo de passagem: estavam no `sem_ficha`, que é a lista de quem
    ainda não tem alergênico e tabela nutricional. Quem preenchesse a ficha
    delas as publicaria de novo — e desfaria, sem querer, a decisão que o dono
    tomou em 24/09.
    """
    from pathlib import Path

    from django.conf import settings

    fonte = Path(settings.BASE_DIR, "config/management/commands/seed.py").read_text()
    assert 'fora_da_loja = {"FOC", "FOCP"}' in fonte
    assert '"is_published": sku not in sem_ficha and sku not in fora_da_loja,' in fonte
    despublicados = {sku for sku, _motivo in UNPUBLISH}
    assert {"FOC", "FOCP"} <= despublicados, (
        "a decisão mora em DOIS lugares e os dois precisam concordar: o seed, "
        "para um banco novo, e a tabela, para um banco que já roda"
    )
