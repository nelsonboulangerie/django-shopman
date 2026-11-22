"""Entrar com a sacola cheia reprecifica a sacola (#3235).

A cliente monta a sacola anônima e entra pelo código. A identidade de preço (ref e
grupo) só ia para a sessão na próxima escrita da sacola: o Finalizar mostrava o total
do anônimo enquanto o servidor já devia o desconto dela (aniversário, grupo). Medido na
prévia do cupom × aniversário: a Maria do seed via R$ 39,00 com R$ 3,90 de aniversário
valendo.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from . import _journey as J

pytestmark = pytest.mark.django_db

CROISSANT = "CRO-REPRECIFICA"


def _birthday_promotion():
    from shopman.shop.models import Promotion

    now = timezone.now()
    return Promotion.objects.create(
        ref="aniversario-reprecifica",
        name="Desconto de aniversário",
        type=Promotion.PERCENT,
        value=10,
        valid_from=now - timezone.timedelta(days=1),
        valid_until=now + timezone.timedelta(days=1),
        birthday_only=True,
        is_active=True,
    )


def _cart(client) -> dict:
    return client.get("/api/v1/storefront/cart/").json()["cart"]


def test_entrar_com_a_sacola_cheia_poe_o_desconto_da_cliente_no_total(client):
    J.seed_shop()
    J.seed_web_channel()
    listing = J.seed_listing()
    collection = J.seed_collection()
    J.seed_product(CROISSANT, "Croissant", 1300, listing=listing, collection=collection, stock_qty=20)
    _birthday_promotion()
    maria = J.make_customer(first_name="Maria", last_name="Santos")
    maria.birthday = timezone.localdate()
    maria.save(update_fields=["birthday"])

    # Anônima: 3 Croissants, R$ 39,00, sem desconto (ninguém sabe quem ela é).
    status, _body = J.set_cart_qty(client, CROISSANT, 3)
    assert status == 200
    assert _cart(client)["discount_total_q"] == 0

    # Entra. O Finalizar já mostra o aniversário, sem outra mudança na sacola.
    J.authenticate(client, maria)
    checkout = client.get("/api/v1/storefront/checkout/")
    assert checkout.status_code == 200
    assert _cart(client)["discount_total_q"] == 390


def test_quem_continua_anonima_nao_ganha_desconto_de_identidade(client):
    J.seed_shop()
    J.seed_web_channel()
    listing = J.seed_listing()
    collection = J.seed_collection()
    J.seed_product(CROISSANT, "Croissant", 1300, listing=listing, collection=collection, stock_qty=20)
    _birthday_promotion()

    J.set_cart_qty(client, CROISSANT, 3)
    client.get("/api/v1/storefront/checkout/")
    assert _cart(client)["discount_total_q"] == 0
