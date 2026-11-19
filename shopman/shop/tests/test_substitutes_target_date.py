"""Substituto para uma ENCOMENDA: a régua é o lote da data, não o estoque de hoje.

``substitutes.find(..., target_date=<data futura>)`` mede cada candidato pelo
lote planejado PARA a data menos o que dele já está prometido
(``stock.plan_backing_on``, a mesma conta do PDV). A sobra de hoje não lastreia
encomenda (dono, 18/11/2026: "não oferecemos pães de um dia para o outro!"),
então o pão que há na loja agora não é alternativa para amanhã.

Sem ``target_date`` (ou com a data de hoje) a busca é a de sempre: a
disponibilidade de agora, como a loja a usa no modal de falta de estoque.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.stockman import stock
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant

from shopman.shop.models import Channel
from shopman.shop.services import substitutes

pytestmark = pytest.mark.django_db

CHANNEL = "web"


@pytest.fixture(autouse=True)
def _fresh_caches():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def loja():
    Channel.objects.get_or_create(ref=CHANNEL, defaults={"name": "Web"})
    Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return Listing.objects.create(ref=CHANNEL, name="Web", is_active=True)


def _tomorrow():
    return timezone.localdate() + timedelta(days=1)


def _bread(sku: str, name: str, *, listing, price_q: int = 1100) -> Product:
    product = Product.objects.create(
        sku=sku, name=name, base_price_q=price_q, unit="un",
        is_published=True, is_sellable=True, availability_policy="planned_ok",
    )
    ListingItem.objects.create(listing=listing, product=product, price_q=price_q, is_published=True, is_sellable=True)
    return product


def _same_shelf(*products: Product) -> None:
    collection, _ = Collection.objects.get_or_create(ref="paes", defaults={"name": "Pães"})
    for index, product in enumerate(products):
        CollectionItem.objects.create(collection=collection, product=product, sort_order=index, is_primary=True)


def _on_the_shelf_today(product: Product, qty: str) -> None:
    stock.receive(quantity=Decimal(qty), sku=product.sku, position=Position.objects.get(ref="loja"), reason="vitrine de hoje")


def _planned_for(product: Product, qty: str, day) -> Quant:
    stock.plan(Decimal(qty), product, day)
    return Quant.objects.get(sku=product.sku, target_date=day)


def _promised(quant: Quant, qty: str, *, ref: str) -> Hold:
    """Uma encomenda já presa ao lote da data."""
    return Hold.objects.create(
        sku=quant.sku, quant=quant, quantity=Decimal(qty), target_date=quant.target_date,
        status=HoldStatus.CONFIRMED, metadata={"reference": f"order:{ref}", "planned": True},
    )


@pytest.fixture
def paes(loja):
    """A baguete que faltou e dois candidatos: um só com vitrine hoje, outro só com lote amanhã."""
    faltou = _bread("BAGUETE", "Baguete de tradição", listing=loja)
    de_hoje = _bread("CAMPAGNE", "Pain de Campagne", listing=loja)
    de_amanha = _bread("FENDU", "Fendu", listing=loja)
    _same_shelf(faltou, de_hoje, de_amanha)
    _on_the_shelf_today(de_hoje, "20")
    lote = _planned_for(de_amanha, "10", _tomorrow())
    _promised(lote, "4", ref="ENC-OUTRA")
    return faltou, de_hoje, de_amanha


def _by_sku(found: list[dict]) -> dict[str, dict]:
    return {row["sku"]: row for row in found}


def test_o_pao_de_hoje_nao_e_alternativa_para_amanha(paes):
    """Vitrine cheia hoje e nenhum lote planejado para amanhã: fica de fora."""
    found = _by_sku(substitutes.find("BAGUETE", qty=Decimal("4"), channel=CHANNEL, target_date=_tomorrow()))

    assert "CAMPAGNE" not in found, "a sobra de hoje entrou como alternativa para a encomenda de amanhã"


def test_o_candidato_com_lote_na_data_entra_com_o_que_sobra_sem_encomenda(paes):
    """10 planejados para amanhã, 4 já prometidos: 6 livres."""
    found = _by_sku(substitutes.find("BAGUETE", qty=Decimal("4"), channel=CHANNEL, target_date=_tomorrow()))

    assert list(found) == ["FENDU"]
    fendu = found["FENDU"]
    assert fendu["available_qty"] == 6
    assert fendu["target_qty"] == 4
    assert fendu["can_order"] is True
    assert fendu["name"] == "Fendu"
    assert fendu["price_display"] == "R$ 11,00"


def test_o_que_sobra_menor_que_o_pedido_entra_dizendo_quanto_ha(paes):
    """Pediram 8 e há 6 livres: a alternativa aparece com 6, e não cabe o pedido inteiro."""
    fendu = _by_sku(substitutes.find("BAGUETE", qty=Decimal("8"), channel=CHANNEL, target_date=_tomorrow()))["FENDU"]

    assert (fendu["available_qty"], fendu["target_qty"], fendu["can_order"]) == (6, 6, False)


def test_lote_da_data_todo_prometido_nao_e_alternativa(paes):
    lote = Quant.objects.get(sku="FENDU", target_date=_tomorrow())
    _promised(lote, "6", ref="ENC-MAIS-UMA")

    assert substitutes.find("BAGUETE", qty=Decimal("1"), channel=CHANNEL, target_date=_tomorrow()) == []


def test_sem_data_o_resultado_e_o_de_antes(paes):
    """O caso de controle: a loja segue lendo a disponibilidade de agora."""
    de_sempre = substitutes.find("BAGUETE", qty=Decimal("4"), channel=CHANNEL)

    # O pão que há hoje é o que a loja oferece hoje, com a quantidade de hoje.
    found = _by_sku(de_sempre)
    assert "CAMPAGNE" in found
    assert found["CAMPAGNE"]["available_qty"] == 20
    assert found["CAMPAGNE"]["can_order"] is True
    # `target_date` ausente, vazio ou de hoje: a mesma resposta, sem ler o lote da data.
    assert substitutes.find("BAGUETE", qty=Decimal("4"), channel=CHANNEL, target_date=None) == de_sempre
    assert substitutes.find("BAGUETE", qty=Decimal("4"), channel=CHANNEL, target_date=timezone.localdate()) == de_sempre
