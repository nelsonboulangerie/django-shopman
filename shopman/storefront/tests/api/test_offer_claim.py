"""`POST /api/v1/offers/<ref>/claim/` — o fim do anúncio, do lado do cliente.

O que este arquivo protege:

1. **Sem login.** O link dorme horas numa conversa de WhatsApp. Se o endpoint exigisse
   sessão autenticada, o anúncio só funcionaria para quem já estava logado, e a alternativa
   (magic link) morre em 5 minutos. Este é o teste que mais importa aqui.
2. **A oferta sempre soma, e a sacola do cliente só é esvaziada a pedido dele.** Sem
   `mode`, o que já estava lá fica e a resposta diz `kept_existing_items`; `replace`
   é a resposta explícita "só a oferta".
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


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """O balde de 20/min por IP é do minuto, não do teste: sem limpar, a soma dos
    POSTs deste arquivo esbarra nele e o 429 vira falha de outro teste."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


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
    assert body["kept_existing_items"] is False


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


def _browse_and_add_other(client: Client) -> None:
    """Outro produto na sacola, escolhido navegando — não está na oferta."""
    product = Product.objects.create(
        sku="PAO-001", name="Pão", base_price_q=800, is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(
        listing=Listing.objects.get(ref="web"), product=product, price_q=800,
        is_published=True, is_sellable=True,
    )
    _seed_stock(product.sku)
    client.put("/api/v1/cart/skus/PAO-001/", data=json.dumps({"qty": 1}), content_type="application/json")


def test_opening_the_offer_on_a_bag_with_items_adds_and_keeps_everything(client, croissant):
    """⚠️ A oferta SEMPRE soma (decisão do dono, 24/09/2026) — nunca troca sem pedido.

    O caso real: a pessoa estava navegando, tem sacola, e **então** toca no link do
    anúncio. O que ela escolheu fica, a oferta entra, e `kept_existing_items` avisa a
    tela para perguntar se ela quer manter tudo.
    """
    _promotion()
    _browse_and_add_other(client)

    response = _claim(client)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["kept_existing_items"] is True
    assert body["added"] == ["CRO-001"]
    assert sorted(item["sku"] for item in body["cart"]["items"]) == ["CRO-001", "PAO-001"]


def test_the_same_sku_already_in_the_bag_is_summed(client, croissant):
    _promotion()
    _browse_and_add(client, qty=2)

    response = _claim(client)

    assert response.status_code == 200
    assert response.json()["kept_existing_items"] is True
    assert sum(item["qty"] for item in response.json()["cart"]["items"]) == 3


def test_opening_the_same_link_again_does_not_add_another_unit(client, croissant):
    """⚠️ A mesma oferta entra UMA vez na mesma sacola (decisão do dono, 06/11/2026).

    A segunda visita chega com intenção nova (a página esquece a chave depois do
    sucesso), e mesmo assim não soma: o recibo é da sacola. Nada a perguntar, e o
    destino é o da primeira visita.
    """
    _promotion()
    _browse_and_add_other(client)
    first = _claim(client, idempotency_key="first-visit").json()
    assert first["added"] == ["CRO-001"]

    second = _claim(client, idempotency_key="second-visit")

    assert second.status_code == 200, second.content
    body = second.json()
    assert body["ok"] is True
    assert body["already_claimed"] is True
    assert body["added"] == []
    assert body["kept_existing_items"] is False
    assert sorted((item["sku"], item["qty"]) for item in body["cart"]["items"]) == [("CRO-001", 1), ("PAO-001", 1)]


def test_the_same_bag_on_another_device_does_not_add_the_offer_again(client, croissant):
    """O recibo não mora no navegador: a sacola viaja para outro dispositivo no login."""
    _promotion()
    assert _claim(client, idempotency_key="phone").json()["added"] == ["CRO-001"]
    other_device = Client()
    session = other_device.session
    session["cart_session_key"] = client.session["cart_session_key"]
    session.save()

    body = other_device.post(
        URL, data=json.dumps({"idempotency_key": "laptop"}), content_type="application/json",
    ).json()

    assert body["already_claimed"] is True
    assert [(item["sku"], item["qty"]) for item in body["cart"]["items"]] == [("CRO-001", 1)]


def test_a_different_offer_for_the_same_item_still_adds(client, croissant):
    """Ofertas distintas continuam somando ("a oferta sempre soma", 24/09/2026)."""
    _promotion()
    _promotion(ref="cafe-da-tarde", name="Café da tarde")
    _claim(client, idempotency_key="relampago")

    response = client.post(
        "/api/v1/offers/cafe-da-tarde/claim/",
        data=json.dumps({"idempotency_key": "cafe"}), content_type="application/json",
    )

    body = response.json()
    assert body["already_claimed"] is False
    assert body["added"] == ["CRO-001"]
    assert sum(item["qty"] for item in body["cart"]["items"]) == 2


def test_another_bag_gets_the_offer_again(client, croissant):
    """O recibo é da sacola: quem recebeu o mesmo link monta a sua."""
    _promotion()
    _claim(client, idempotency_key="one")

    body = Client().post(URL, data=json.dumps({"idempotency_key": "one"}), content_type="application/json").json()

    assert body["already_claimed"] is False
    assert body["added"] == ["CRO-001"]


def test_only_the_offer_removes_what_was_there_before(client, croissant):
    """A resposta "Não, só a oferta": esvazia a sacola e deixa a oferta sozinha."""
    _promotion()
    _browse_and_add_other(client)
    assert _claim(client, idempotency_key="merge").json()["kept_existing_items"] is True

    response = _claim(client, mode="replace", idempotency_key="only-offer")

    assert response.status_code == 200
    body = response.json()
    assert body["kept_existing_items"] is False
    assert [(item["sku"], item["qty"]) for item in body["cart"]["items"]] == [("CRO-001", 1)]


def test_an_unknown_mode_is_refused_instead_of_guessed(client, croissant):
    """Modo que o servidor não conhece não vira soma nem troca por palpite."""
    _promotion()

    response = _claim(client, mode="append")

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_mode"


def test_what_could_not_be_added_comes_back_to_be_explained(client, croissant):
    """A tela precisa NOMEAR o que ficou de fora — e oferecer uma saída.

    Contar ("alguns itens ficaram de fora") deixava quem clicou num anúncio sem
    saber o quê e sem nada a fazer.
    """
    _promotion(skus=["CRO-001", "FANTASMA-404"])

    body = _claim(client).json()

    assert body["added"] == ["CRO-001"]
    assert body["skipped"] == [{
        "sku": "FANTASMA-404",
        "name": "FANTASMA-404",
        "is_notifiable": False,
        "is_notify_subscribed": False,
    }]


def test_confirmed_claim_replays_after_offer_expires_without_adding_again(client, croissant):
    promotion = _promotion()
    first = _claim(client, idempotency_key="lost-offer-response")
    assert first.status_code == 200
    promotion.is_active = False
    promotion.save(update_fields=["is_active"])
    second = _claim(client, idempotency_key="lost-offer-response")
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["cart"] == first.json()["cart"]
    new_intention = _claim(client, idempotency_key="new-offer-intention")
    assert new_intention.status_code == 404
