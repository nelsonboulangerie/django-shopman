"""Sair devolve a sacola ao anônimo (OC-09, resíduo de dispositivo compartilhado).

O logout preserva a sacola (``cart_session_key``) para quem sai não perder o que
montou. Mas a sacola carregava a identidade de preço de quem saiu
(``Session.data["customer"]``: ref e grupos), e nada a tirava até outro login
reprecificar. No celular emprestado, o próximo a abrir a loja via o preço da
cliente anterior (aniversário, grupo). Medido antes da correção: a Maria sai e a
sacola anônima segue com R$ 3,90 de aniversário dela.

Sair é comando: a identidade sai da sacola e a sacola é reprecificada pelo
mesmo caminho do login (``cart.reprice``), só que ao contrário.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from . import _journey as J

pytestmark = pytest.mark.django_db

CROISSANT = "CRO-SAIR"


def _birthday_promotion():
    from shopman.shop.models import Promotion

    now = timezone.now()
    return Promotion.objects.create(
        ref="aniversario-sair",
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


def _session_data(client) -> dict:
    from shopman.orderman.models import Session

    key = client.session.get("cart_session_key")
    return Session.objects.get(session_key=key).data or {}


def _maria_de_aniversario_logada_com_a_sacola(client):
    J.seed_shop()
    J.seed_web_channel()
    listing = J.seed_listing()
    collection = J.seed_collection()
    J.seed_product(CROISSANT, "Croissant", 1300, listing=listing, collection=collection, stock_qty=20)
    _birthday_promotion()
    maria = J.make_customer(first_name="Maria", last_name="Santos")
    maria.birthday = timezone.localdate()
    maria.save(update_fields=["birthday"])

    J.authenticate(client, maria)
    status, _body = J.set_cart_qty(client, CROISSANT, 3)
    assert status == 200
    # Logada: a sacola é dela, com o aniversário no total.
    assert _cart(client)["discount_total_q"] == 390
    assert _session_data(client)["customer"]["ref"] == maria.ref
    return maria


def _sair(client):
    response = client.post("/api/v1/auth/logout/", content_type="application/json")
    assert response.status_code == 200
    assert response.json()["is_authenticated"] is False


def test_depois_de_sair_o_proximo_ve_o_preco_publico(client):
    _maria_de_aniversario_logada_com_a_sacola(client)

    _sair(client)

    # A sacola fica (sair não joga fora o que foi montado), mas sem o preço dela.
    cart = _cart(client)
    assert cart["items"], "a sacola sobrevive ao sair"
    assert cart["discount_total_q"] == 0
    assert "customer" not in _session_data(client)


def test_quem_entra_depois_le_o_proprio_preco_sem_sobra_de_quem_saiu(client):
    maria = _maria_de_aniversario_logada_com_a_sacola(client)
    _sair(client)

    joao = J.make_customer(first_name="Joao", last_name="Lima", phone="+5543999990777", email="joao@example.com")
    J.authenticate(client, joao)
    status, _body = J.set_cart_qty(client, CROISSANT, 4)
    assert status == 200

    data = _session_data(client)
    assert data["customer"]["ref"] == joao.ref
    assert data["customer"]["ref"] != maria.ref
    assert _cart(client)["discount_total_q"] == 0


def test_sair_sem_sacola_nao_falha(client):
    J.seed_shop()
    J.seed_web_channel()
    maria = J.make_customer(first_name="Maria", last_name="Santos")
    J.authenticate(client, maria)

    _sair(client)

    assert client.session.get("cart_session_key") is None
