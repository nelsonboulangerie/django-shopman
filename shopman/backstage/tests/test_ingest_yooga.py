"""Ingestão do histórico Yooga por lote (BI-PLAN F6; BI-DATA-FOUNDATION-PLAN P0).

Cobre a conversão fiel (centavos sem float, datetime local), a derivação de
``is_delivery`` (único rótulo de canal confiável), o resolve de sku pelo mapa
de Produtos — e o que o P0 acrescentou: lote com hash (o mesmo arquivo não
entra duas vezes), validação na fronteira (nada é gravado; a falha fica
registrada), uma transação, colunas antes descartadas em ``metadata``
(telefone só como hash + últimos 4), e "completar sem sobrescrever".
O fixture é um xlsx sintético em tmp_path — o export real nunca é tocado.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from shopman.backstage.bi.ingest import AlreadyImported, InvalidExport
from shopman.backstage.bi.ingest.yooga import ingest
from shopman.backstage.models import HistoricalSale, HistoricalSaleItem, ImportBatch

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

SALE_1001 = (
    1001, "2025-03-10", "07:12:00", 2025, "2025-03", "segunda", 7, 37.48,
    0, 0, "Dinheiro", None, "Admin", None, None, None, "balcão", None,
    None, None, None, "PDV", 0,
)
SALE_1002 = (
    1002, "2025-03-10", "18:30:00", 2025, "2025-03", "segunda", 18, 6.49,
    1.0, 0, "Delivery - Pix", 0.35, "Admin", 555, "Alice", "(43) 99123-4567",
    "balcão", "Rua das Flores, 10", "Centro", None, "sem cebola", "DELIVERY", 42,
)


def _write(path, *, sales=(SALE_1001, SALE_1002), items=None, vendas_header=VENDAS_HEADER):
    wb = openpyxl.Workbook()
    vendas = wb.active
    vendas.title = "Vendas"
    vendas.append(vendas_header)
    for row in sales:
        vendas.append(row)
    itens = wb.create_sheet("Itens")
    itens.append(ITENS_HEADER)
    for row in items if items is not None else (
        (1001, "2025-03-10", "07:12:00", "2025-03", "segunda", 7,
         "Baguete Francesa", None, None, 2, 9, 0, 18, None),
        (1001, "2025-03-10", "07:12:00", "2025-03", "segunda", 7,
         "Produto Extinto", None, None, 1, 19.48, 0, 19.48, None),
        (1002, "2025-03-10", "18:30:00", "2025-03", "segunda", 18,
         "Baguete Francesa", "BF", "Pães Rústicos", 1, 6.49, 1.0, 6.49, None),
    ):
        itens.append(row)
    products = wb.create_sheet("Produtos")
    products.append(PRODUTOS_HEADER)
    products.append((1, "Baguete Francesa", "BF", "Pães Rústicos", 13, None))
    wb.save(path)
    return str(path)


@pytest.fixture
def export_file(tmp_path):
    return _write(tmp_path / "yooga.xlsx")


# ── Conversão e forma ─────────────────────────────────────────────────────────


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
def test_discarded_columns_now_land_in_metadata(export_file):
    """As colunas que a versão anterior jogava fora entram em ``metadata``.

    Telefone só como hash do E.164 (o mesmo normalizador do guestman, para o
    join futuro) mais os quatro últimos dígitos: nunca em claro.
    """
    ingest(export_file)
    delivery = HistoricalSale.objects.get(external_id=1002)
    expected_hash = hashlib.sha256(b"+5543991234567").hexdigest()
    assert delivery.metadata == {
        "nfce_id": 42,
        "phone_hash": expected_hash,
        "phone_last4": "4567",
        "neighborhood": "Centro",
        "address": "Rua das Flores, 10",
        "payment_fee_q": 35,
        "note": "sem cebola",
    }
    assert "99123" not in str(delivery.metadata)


# ── Lote ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_every_import_is_a_batch_with_identity_and_counts(export_file):
    batch = ingest(export_file)
    assert batch.source == "yooga"
    assert batch.file_name == "yooga.xlsx"
    assert len(batch.file_sha256) == 64
    assert batch.status == ImportBatch.Status.DONE
    assert (batch.rows_read, batch.sales_created, batch.sales_skipped, batch.items_created) == (2, 2, 0, 3)
    assert HistoricalSale.objects.filter(batch=batch).count() == 2


@pytest.mark.django_db
def test_same_file_is_refused_not_duplicated(export_file):
    ingest(export_file)
    with pytest.raises(AlreadyImported, match="já foi importado"):
        ingest(export_file)
    assert HistoricalSale.objects.count() == 2
    assert ImportBatch.objects.count() == 1  # a recusa não vira lote

    with pytest.raises(CommandError, match="rebuild"):
        call_command("ingest_yooga", "--file", export_file)


@pytest.mark.django_db
def test_a_new_export_completes_without_overwriting(tmp_path, export_file):
    """Export posterior insere o que falta e preenche lacunas; nunca reescreve."""
    ingest(export_file)
    HistoricalSale.objects.filter(external_id=1002).update(
        metadata={"nfce_id": 42, "note": "anotação original"}
    )

    richer = list(SALE_1002)
    richer[VENDAS_HEADER.index("observacao")] = "anotação nova"
    sale_1003 = list(SALE_1001)
    sale_1003[0] = 1003
    second = _write(tmp_path / "yooga-v2.xlsx", sales=(SALE_1001, tuple(richer), tuple(sale_1003)))

    batch = ingest(second)
    assert (batch.sales_created, batch.sales_skipped, batch.sales_completed) == (1, 2, 1)
    completed = HistoricalSale.objects.get(external_id=1002).metadata
    assert completed["note"] == "anotação original"  # o que já havia fica
    assert completed["neighborhood"] == "Centro"  # o que faltava entra
    assert HistoricalSale.objects.get(external_id=1003).batch == batch
    assert HistoricalSaleItem.objects.count() == 3  # 1003 não tem itens no arquivo
    assert ImportBatch.objects.filter(status="done").count() == 2


@pytest.mark.django_db
def test_repeated_pedido_inside_one_file_counts_once(tmp_path):
    path = _write(tmp_path / "dup.xlsx", sales=(SALE_1001, SALE_1001, SALE_1002))
    batch = ingest(path)
    assert (batch.rows_read, batch.sales_created, batch.sales_skipped) == (3, 2, 1)
    assert HistoricalSale.objects.count() == 2


@pytest.mark.django_db
def test_rebuild_reloads_from_scratch(export_file):
    ingest(export_file)
    HistoricalSale.objects.filter(external_id=1001).update(total_q=1)
    call_command("ingest_yooga", "--file", export_file, "--rebuild")
    assert HistoricalSale.objects.get(external_id=1001).total_q == 3748
    assert HistoricalSaleItem.objects.count() == 3
    assert ImportBatch.objects.filter(source="yooga").count() == 1  # o lote velho foi junto


# ── Fronteira ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_missing_column_fails_at_the_boundary_and_is_recorded(tmp_path):
    header = tuple(name for name in VENDAS_HEADER if name != "valor")
    sales = tuple(tuple(v for i, v in enumerate(row) if VENDAS_HEADER[i] != "valor") for row in (SALE_1001,))
    path = _write(tmp_path / "sem-valor.xlsx", sales=sales, vendas_header=header)

    with pytest.raises(InvalidExport, match="aba 'Vendas' sem as colunas valor"):
        ingest(path)
    assert HistoricalSale.objects.count() == 0
    failed = ImportBatch.objects.get()
    assert failed.status == ImportBatch.Status.FAILED
    assert "valor" in failed.error


@pytest.mark.django_db
def test_bad_row_names_sheet_and_line_and_writes_nothing(tmp_path):
    broken = list(SALE_1002)
    broken[VENDAS_HEADER.index("valor")] = "seis e quarenta e nove"
    path = _write(tmp_path / "linha-ruim.xlsx", sales=(SALE_1001, tuple(broken)))

    with pytest.raises(InvalidExport, match=r"aba 'Vendas', linha 3: valor: .*ilegível"):
        ingest(path)
    # A venda 1001 era válida e veio antes: a transação única a desfez junto.
    assert HistoricalSale.objects.count() == 0
    assert HistoricalSaleItem.objects.count() == 0
    assert ImportBatch.objects.get().status == ImportBatch.Status.FAILED


@pytest.mark.django_db
def test_failed_batch_does_not_block_the_retry(tmp_path):
    """Um lote que falhou não pode trancar o mesmo hash: a restrição vale entre concluídos."""
    broken = list(SALE_1002)
    broken[VENDAS_HEADER.index("data")] = "ontem"
    path = _write(tmp_path / "retry.xlsx", sales=(SALE_1001, tuple(broken)))
    with pytest.raises(InvalidExport):
        ingest(path)
    # Mesmo arquivo, agora íntegro (mesmo nome, conteúdo diferente ⇒ hash diferente),
    # e um arquivo idêntico ao que falhou também pode tentar de novo:
    with pytest.raises(InvalidExport):
        ingest(path)
    assert ImportBatch.objects.filter(status="failed").count() == 2
    fixed = _write(tmp_path / "retry.xlsx")
    assert ingest(fixed).status == ImportBatch.Status.DONE
