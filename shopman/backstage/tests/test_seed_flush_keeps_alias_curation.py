"""O `seed --flush` não pode custar a curadoria de de-paras — nem quebrar por ela.

A cena que quase aconteceu no staging (19/08/2026): 98 `ProductAlias` confirmados
apontando para o catálogo (FK PROTECT, de propósito) e um `seed --flush` a caminho.
Sem tratamento, o `Product.objects.all().delete()` do flush estoura `ProtectedError`
— e como o flush não é transacional, pararia com metade do banco já apagada.

O contrato: o flush solta a FK guardando o SKU e religa por SKU quando o catálogo
renasce. A assinatura da curadoria (status, quem, quando) não se move; produto que
não volta no seed fica com FK vazia — a semântica existente de produto extinto.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.backstage.models import AliasStatus, ProductAlias

pytestmark = pytest.mark.django_db


@pytest.fixture
def curated(django_user_model):
    curator = django_user_model.objects.create_user("curadora-da-casa")
    # SKU deliberadamente DIFERENTE do que o seed cria ("CT"): é o cenário do
    # staging, onde o catálogo vivo tem SKUs editados à mão. O nome é a ponte.
    croissant = Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=1200)
    saudade = Product.objects.create(sku="PRODUTO-QUE-NAO-VOLTA", name="Só desta base", base_price_q=100)
    kept = ProductAlias.objects.create(
        source="yooga", external_sku="CT", external_name="Croissant Tradicional",
        product=croissant, status=AliasStatus.CONFIRMED,
        confirmed_by=curator, confirmed_at=timezone.now(),
    )
    orphaned = ProductAlias.objects.create(
        source="yooga", external_sku="XX", external_name="Coisa antiga",
        product=saudade, status=AliasStatus.CONFIRMED,
        confirmed_by=curator, confirmed_at=timezone.now(),
    )
    return kept, orphaned, curator


def test_flush_survives_confirmed_aliases_and_relinks_them_by_sku(curated, monkeypatch):
    kept, orphaned, curator = curated
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")

    # Antes do fix: ProtectedError aqui, com metade do flush já executada.
    call_command("seed", "--flush", stdout=StringIO())

    kept.refresh_from_db()
    orphaned.refresh_from_db()

    # A curadoria atravessou inteira: linha, estado e assinatura.
    assert kept.status == AliasStatus.CONFIRMED
    assert kept.confirmed_by_id == curator.pk
    assert kept.confirmed_at is not None

    # Religado ao catálogo NOVO. O SKU mudou junto com o catálogo (o seed cria
    # "CT"); o que atravessa é o produto, encontrado pelo nome único "Croissant".
    assert kept.product is not None
    assert kept.product.sku == "CT"
    assert kept.product.name == "Croissant"

    # Produto que o seed não recria: FK vazia, alias vivo — produto extinto.
    assert orphaned.product is None
    assert orphaned.status == AliasStatus.CONFIRMED
