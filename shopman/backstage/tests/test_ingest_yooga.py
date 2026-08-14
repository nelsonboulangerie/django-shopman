"""Ingestão do histórico Yooga (BI-PLAN F6).

Cobre a conversão fiel (centavos sem float, datetime local), a derivação de
``is_delivery`` (único rótulo de canal confiável), o resolve de sku pelo mapa
de Produtos, a idempotência (rodar de novo não duplica) e o ``--rebuild``.
O fixture é um xlsx sintético em tmp_path — o export real nunca é tocado.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.backstage.models import HistoricalSale, HistoricalSaleItem

openpyxl = pytest.importorskip("openpyxl")

VENDAS_HEADER = (
    "pedido", "data", "hora", "ano", "mes", "dia_semana", "hora_cheia", "valor",
    "desconto", "acrescimo", "formas_pagamento", "taxa_pagamento", "operador",
    "cliente_id", "cliente", "telefone", "modalidade", "endereco", "bairro",
    "mesa", "observacao", "origem", "nfce_id",
)
ITENS_HEADER = (
    "pedido", "data", "hora", "mes", "dia_semana", "hora_cheia", "produto",
    "sku", "categoria", "quantidade", "valor_unitario", "desconto_item",
    "total_item", "observacao",
)
PRODUTOS_HEADER = ("produto_id", "produto", "sku", "categoria", "preco", "ativo")


@pytest.fixture
def export_file(tmp_path):
    wb = openpyxl.Workbook()
    vendas = wb.active
    vendas.title = "Vendas"
    vendas.append(VENDAS_HEADER)
    vendas.append((
        1001, "2025-03-10", "07:12:00", 2025, "2025-03", "segunda", 7, 37.48,
        0, 0, "Dinheiro", None, "Admin", None, None, None, "balcão", None,
        None, None, None, "PDV", 0,
    ))
    vendas.append((
        1002, "2025-03-10", "18:30:00", 2025, "2025-03", "segunda", 18, 6.49,
        1.0, 0, "Delivery - Pix", None, "Admin", 555, "Alice", None, "balcão",
        None, None, None, None, "DELIVERY", 42,
    ))
    itens = wb.create_sheet("Itens")
    itens.append(ITENS_HEADER)
    itens.append((1001, "2025-03-10", "07:12:00", "2025-03", "segunda", 7,
                  "Baguete Francesa", None, None, 2, 9, 0, 18, None))
    itens.append((1001, "2025-03-10", "07:12:00", "2025-03", "segunda", 7,
                  "Produto Extinto", None, None, 1, 19.48, 0, 19.48, None))
    itens.append((1002, "2025-03-10", "18:30:00", "2025-03", "segunda", 18,
                  "Baguete Francesa", "BF", "Pães Rústicos", 1, 6.49, 1.0, 6.49, None))
    produtos = wb.create_sheet("Produtos")
    produtos.append(PRODUTOS_HEADER)
    produtos.append((1, "Baguete Francesa", "BF", "Pães Rústicos", 13, None))
    path = tmp_path / "yooga.xlsx"
    wb.save(path)
    return str(path)


@pytest.mark.django_db
def test_ingest_converts_faithfully(export_file):
    call_command("ingest_yooga", "--file", export_file)

    assert HistoricalSale.objects.count() == 2
    balcao = HistoricalSale.objects.get(external_id=1001)
    assert balcao.source == "yooga"
    assert balcao.total_q == 3748  # centavos sem erro de float
    assert balcao.is_delivery is False
    assert timezone.localtime(balcao.occurred_at).hour == 7
    assert balcao.metadata == {}

    delivery = HistoricalSale.objects.get(external_id=1002)
    assert delivery.is_delivery is True  # origem DELIVERY + forma "Delivery -"
    assert delivery.discount_q == 100
    assert delivery.customer_external_id == 555
    assert delivery.metadata == {"nfce_id": 42}

    items = list(balcao.items.order_by("seq"))
    assert [item.seq for item in items] == [1, 2]
    # sku/categoria resolvidos pelo mapa de Produtos quando a linha não traz…
    assert items[0].sku == "BF"
    assert items[0].category == "Pães Rústicos"
    assert items[0].qty == Decimal("2")
    assert items[0].line_total_q == 1800
    # …e produto fora do catálogo fica honesto: sem sku, nome preservado.
    assert items[1].sku == ""
    assert items[1].product_name == "Produto Extinto"


@pytest.mark.django_db
def test_ingest_is_idempotent(export_file):
    call_command("ingest_yooga", "--file", export_file)
    call_command("ingest_yooga", "--file", export_file)
    assert HistoricalSale.objects.count() == 2
    assert HistoricalSaleItem.objects.count() == 3


@pytest.mark.django_db
def test_rebuild_reloads_from_scratch(export_file):
    call_command("ingest_yooga", "--file", export_file)
    HistoricalSale.objects.filter(external_id=1001).update(total_q=1)
    call_command("ingest_yooga", "--file", export_file, "--rebuild")
    assert HistoricalSale.objects.get(external_id=1001).total_q == 3748
    assert HistoricalSaleItem.objects.count() == 3
