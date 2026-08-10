"""`POST /api/v1/offers/<ref>/claim/` — o fim do anúncio, do lado do cliente.

O que este arquivo protege:

1. **Sem login.** O link dorme horas numa conversa de WhatsApp. Se o endpoint exigisse
   sessão autenticada, o anúncio só funcionaria para quem já estava logado, e a alternativa
   (magic link) morre em 5 minutos. Este é o teste que mais importa aqui.
2. **Sacola do cliente não é apagada sem perguntar.** 409 quando ela já tem itens.
3. **Oferta morta responde 404 com o motivo**, porque "não deu" não ajuda quem clicou.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Promotion, Shop

pytestmark = pytest.mark.django_db

URL = "/api/v1/offers/relampago-17h30/claim/"


@pytest.fixture
def croissant(db):
    """Loja de pé, produto vendável e com estoque — a sacola é real neste teste."""
    Shop.objects.create(name="Test Shop")
    Channel.objects.create(ref="web", name="Web")
    product = Product.objects.create(
        sku="CRO-001", name="Croissant", base_price_q=1200,
        is_published=True, is_sellable=True,
    )
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    ListingItem.objects.create(
        listing=listing, product=product, price_q=1200, is_published=True, is_sellable=True
    )
    _seed_stock(product.sku)
    return product


def _seed_stock(sku: str) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(
        quantity=Decimal("100"), sku=sku, position=position,
        target_date=date.today(), reason="seed",
    )


def _promotion(**over) -> Promotion:
    now = timezone.now()
    defaults = {
        "ref": "relampago-17h30",
        "name": "Relâmpago das 17h30",
        "type": Promotion.PERCENT,
        "value": 20,
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=1),
        "skus": ["CRO-001"],
        "is_active": True,
    }
    return Promotion.objects.create(**{**defaults, **over})


def _claim(client: Client, **body):
    return client.post(URL, data=json.dumps(body), content_type="application/json")


def test_an_anonymous_visitor_can_claim_the_offer(client, croissant):
    """⚠️ O teste que guarda o desenho.

    Ninguém precisa estar logado para encher uma sacola. Exigir sessão aqui faria o
    anúncio funcionar só para quem já estava logado, e a alternativa — magic link — expira
    em 5 minutos e é de uso único: morreria antes do clique.
    """
    _promotion()

    response = _claim(client)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["ok"] is True
    assert body["added"] == ["CRO-001"]
    assert body["offer"]["name"] == "Relâmpago das 17h30"


def test_the_claim_is_idempotent_under_the_same_key(client, croissant):
    """Toque duplo no link não dobra a sacola."""
    _promotion()

    first = _claim(client, idempotency_key="abc")
    second = _claim(client, idempotency_key="abc")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["added"] == ["CRO-001"]
    assert sum(item["qty"] for item in second.json()["cart"]["items"]) == 1


def test_a_dead_offer_answers_404_with_the_reason(client, croissant):
    _promotion(valid_until=timezone.now() - timedelta(minutes=1))

    response = _claim(client)

    assert response.status_code == 404
    assert "terminou" in response.json()["detail"]


def test_an_unknown_offer_answers_404(client):
    assert client.post("/api/v1/offers/nunca-existiu/claim/").status_code == 404


def test_an_offer_for_the_whole_menu_says_so_instead_of_pretending(client, croissant):
    """Não existe sacola de "tudo": melhor dizer que montar uma sacola errada."""
    _promotion(skus=[], collections=[])

    response = _claim(client)

    assert response.status_code == 409
    assert response.json()["error_code"] == "offer_has_no_items"


def _browse_and_add(client: Client, qty: int = 2) -> None:
    """Sacola montada pelo cliente navegando — não pela oferta."""
    client.put(
        "/api/v1/cart/skus/CRO-001/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )


def test_a_cart_with_items_is_never_replaced_without_asking(client, croissant):
    """⚠️ Trocar sem perguntar apagaria uma sacola que o cliente montou.

    O caso real é este: a pessoa estava navegando, tem sacola, e **então** toca no link
    do anúncio. Não é o toque duplo no mesmo link — esse a idempotência resolve
    repetindo a resposta, e é o que `test_the_claim_is_idempotent_under_the_same_key`
    protege.
    """
    _promotion()
    _browse_and_add(client)

    response = _claim(client)

    assert response.status_code == 409
    assert response.json()["error_code"] == "cart_not_empty"


def test_append_adds_to_what_was_already_there(client, croissant):
    _promotion()
    _browse_and_add(client, qty=2)

    response = _claim(client, mode="append")

    assert response.status_code == 200
    assert sum(item["qty"] for item in response.json()["cart"]["items"]) == 3


def test_replace_starts_a_fresh_bag(client, croissant):
    """Só depois de o cliente escolher trocar. A escolha é dele, e é explícita."""
    _promotion()
    _browse_and_add(client, qty=2)

    response = _claim(client, mode="replace")

    assert response.status_code == 200
    assert sum(item["qty"] for item in response.json()["cart"]["items"]) == 1


def test_what_could_not_be_added_comes_back_to_be_explained(client, croissant):
    """A tela precisa poder contar o que ficou de fora, em vez de o cliente descobrir."""
    _promotion(skus=["CRO-001", "FANTASMA-404"])

    body = _claim(client).json()

    assert body["added"] == ["CRO-001"]
    assert body["skipped"] == ["FANTASMA-404"]
