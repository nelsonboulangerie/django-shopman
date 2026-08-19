"""As telas do que entrou de fora no B.I. aguentam LINHAS e são só leitura.

`test_admin_renders_with_rows` cobre `ImportBatch` sozinho (não exige grafo),
mas pula `HistoricalSale` (FK obrigatória para o lote). Este módulo fecha a
fresta: uma venda com item embaixo, lista e formulário renderizados, colunas
calculadas (badge de total, canal, estado do lote) executadas — e a prova de
que ninguém adiciona, edita ou apaga por aqui.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.models import HistoricalSale, HistoricalSaleItem, ImportBatch
from shopman.shop.models import Shop


@pytest.fixture
def admin_client(client, db):
    Shop.objects.create(name="Loja")
    client.force_login(User.objects.create_superuser("bi-admin", "bi@test.com", "pw"))
    return client


@pytest.fixture
def rows(db):
    done = ImportBatch.objects.create(
        source="yooga", file_name="yooga.xlsx", file_sha256="a" * 64,
        rows_read=2, sales_created=1, sales_skipped=1, items_created=1,
    )
    ImportBatch.objects.create(
        source="yooga", file_name="quebrado.xlsx", file_sha256="b" * 64,
        status=ImportBatch.Status.FAILED, error="aba 'Vendas' sem as colunas valor",
    )
    sale = HistoricalSale.objects.create(
        batch=done, source="yooga", external_id=77, occurred_at=timezone.now(),
        total_q=1250, payment="Delivery - Pix", is_delivery=True,
        customer_name="Alice", metadata={"nfce_id": 9, "phone_last4": "4567"},
    )
    HistoricalSaleItem.objects.create(
        sale=sale, seq=1, product_name="Baguete", sku="BF", category="Pães Rústicos",
        qty=Decimal("2"), unit_price_q=625, line_total_q=1250,
    )
    return done, sale


def test_import_batches_list_and_detail_render_with_rows(admin_client, rows):
    done, _sale = rows
    listing = admin_client.get(reverse("admin:backstage_importbatch_changelist"))
    assert listing.status_code == 200
    body = listing.content.decode()
    assert "yooga.xlsx" in body and "quebrado.xlsx" in body
    assert "concluído" in body and "falhou" in body

    detail = admin_client.get(reverse("admin:backstage_importbatch_change", args=[done.pk]))
    assert detail.status_code == 200
    assert "a" * 64 in detail.content.decode()


def test_historical_sales_list_and_detail_render_with_items(admin_client, rows):
    _done, sale = rows
    listing = admin_client.get(reverse("admin:backstage_historicalsale_changelist"))
    assert listing.status_code == 200
    body = listing.content.decode()
    assert "R$&nbsp;12,50" in body or "12,50" in body
    assert "delivery" in body

    detail = admin_client.get(reverse("admin:backstage_historicalsale_change", args=[sale.pk]))
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "Baguete" in body and "Pães Rústicos" in body  # inline de itens
    assert "phone_last4" in body  # metadata visível, telefone nunca em claro


def test_screens_are_read_only(admin_client, rows):
    done, sale = rows
    for name in ("backstage_importbatch_add", "backstage_historicalsale_add"):
        assert admin_client.get(reverse(f"admin:{name}")).status_code == 403
    assert admin_client.post(
        reverse("admin:backstage_importbatch_delete", args=[done.pk]), {"post": "yes"}
    ).status_code == 403
    assert admin_client.post(
        reverse("admin:backstage_historicalsale_change", args=[sale.pk]), {"customer_name": "x"}
    ).status_code == 403
    assert HistoricalSale.objects.get(pk=sale.pk).customer_name == "Alice"
