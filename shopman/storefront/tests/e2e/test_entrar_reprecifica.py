"""Entrar com a sacola cheia reprecifica a sacola (#3235).

A cliente monta a sacola anônima e entra pelo código. A identidade de preço (ref e
grupo) só ia para a sessão na próxima escrita da sacola: o Finalizar mostrava o total
do anônimo enquanto o servidor já devia o desconto dela (aniversário, grupo). Medido na
prévia do cupom × aniversário: a Maria do seed via R$ 39,00 com R$ 3,90 de aniversário
valendo.

A reprecificação acontece no login, que é comando. As leituras da sacola e do checkout
não gravam nada (``test_get_handlers_do_not_invoke_commands_or_write``): elas só
mostram o preço que o login já pôs.
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


def _maria_de_aniversario_com_a_sacola_anonima(client):
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
    return maria


def test_entrar_com_a_sacola_cheia_poe_o_desconto_da_cliente_no_total(client):
    maria = _maria_de_aniversario_com_a_sacola_anonima(client)

    # Entra. A sacola e o Finalizar já mostram o aniversário, sem outra mudança na sacola.
    J.authenticate(client, maria)
    assert _cart(client)["discount_total_q"] == 390
    checkout = client.get("/api/v1/storefront/checkout/")
    assert checkout.status_code == 200
    assert _cart(client)["discount_total_q"] == 390


def test_entrar_pelo_codigo_reprecifica_a_sacola(client):
    """A porta de verdade: o código digitado no /entrar, pelo POST do verify-code."""
    _maria_de_aniversario_com_a_sacola_anonima(client)

    result = J.otp_login(client)
    assert result["status"] == 200, result
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
