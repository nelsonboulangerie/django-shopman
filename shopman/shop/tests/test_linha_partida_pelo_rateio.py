"""A linha se parte só quando sobra centavo (#3240, decisão do dono 22/11).

O desconto de pedido de valor fixo (cupom ou promoção) é rateado no PREÇO UNITÁRIO,
em centavos inteiros. R$ 5,00 sobre 3 Croissants de R$ 13,00 não cabe (1,666… por
unidade): antes cada unidade levava R$ 1,67 e o desconto somava R$ 5,01. Agora a
linha se parte, 2 a R$ 11,33 e 1 a R$ 11,34, e o total fecha em R$ 34,00. Toda
linha segue com ``line_total_q == qty × unit_price_q``, e quem lê o unitário
(PDV, devolução, não retirado, NFC-e) segue certo sem mudança.

A partição é do preço, não da compra: no próximo preço as unidades voltam à
linha de origem (``SplitLineMergeModifier``) e o rateio parte de novo só se
ainda sobrar centavo.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order, Session

from shopman.shop.discount_spread import SPLIT_OF, SplitLineMergeModifier, split_line_id, spread_order_discount
from shopman.shop.models import Channel, Coupon, Promotion, Shop
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db

FISCAL = {"fiscal": {"profile": "standard", "ncm": "19059010"}}


@pytest.fixture
def web():
    Shop.objects.get_or_create(name="Test Shop")
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja online"})
    Product.objects.create(
        sku="CRO", name="Croissant", base_price_q=1300, is_published=True, is_sellable=True, metadata=FISCAL
    )
    return "web"


def _fixed_coupon(code: str, value_q: int) -> Coupon:
    now = timezone.now()
    promo = Promotion.objects.create(
        ref=f"cupom-{code.lower()}", name=code, type=Promotion.FIXED, value=value_q,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1), is_active=True,
    )
    return Coupon.objects.create(code=code, promotion=promo, max_uses=1, is_active=True)


def _cart(channel_ref: str, qty: int, *, origin: str | None = None) -> str:
    session = sessions.create_session(channel_ref)
    ops = [
        {"op": "add_line", "sku": "CRO", "name": "Croissant", "qty": qty, "unit_price_q": 1300},
        {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
    ]
    if origin:
        ops.append({"op": "set_data", "path": "origin_channel", "value": origin})
    sessions.modify_session(session_key=session.session_key, channel_ref=channel_ref, ops=ops)
    return session.session_key


def _lines(key: str) -> list[tuple]:
    session = Session.objects.get(session_key=key)
    return [(i["qty"], i["unit_price_q"], i["line_total_q"]) for i in session.items]


def _touch(key: str, channel_ref: str) -> None:
    """Um preço novo sem mudar a compra."""
    sessions.modify_session(
        session_key=key, channel_ref=channel_ref, ops=[{"op": "set_data", "path": "note", "value": "x"}]
    )


# ── o rateio ───────────────────────────────────────────────────────────────


def test_o_rateio_parte_a_linha_e_fecha_exato():
    line = {"line_id": "L1", "sku": "CRO", "qty": 3, "unit_price_q": 1300, "line_total_q": 3900, "meta": {}}

    touched = spread_order_discount([line], 500, at_least=True, split=True)

    sibling = next(item for item, _, _ in touched if item is not line)
    assert (line["qty"], line["unit_price_q"], line["line_total_q"]) == (2, 1133, 2266)
    assert (sibling["qty"], sibling["unit_price_q"], sibling["line_total_q"]) == (1, 1134, 1134)
    assert sibling["line_id"] == split_line_id("L1")
    assert sibling["meta"][SPLIT_OF] == "L1"
    assert sum(amount for _, _, amount in touched) == 500


def test_sem_split_o_rateio_segue_arredondando_para_quem_prometeu():
    line = {"line_id": "L1", "sku": "CRO", "qty": 3, "unit_price_q": 1300, "line_total_q": 3900, "meta": {}}

    touched = spread_order_discount([line], 500, at_least=True)

    assert [(item["qty"], item["unit_price_q"]) for item, _, _ in touched] == [(3, 1133)]
    assert sum(amount for _, _, amount in touched) == 501


def test_valor_que_divide_nao_parte_linha_nenhuma():
    line = {"line_id": "L1", "sku": "CRO", "qty": 4, "unit_price_q": 1300, "line_total_q": 5200, "meta": {}}

    touched = spread_order_discount([line], 500, at_least=True, split=True)

    assert [(item["qty"], item["unit_price_q"]) for item, _, _ in touched] == [(4, 1175)]


def test_linha_de_uma_unidade_absorve_o_resto_sem_partir():
    lines = [
        {"line_id": "L1", "sku": "CRO", "qty": 3, "unit_price_q": 1300, "line_total_q": 3900, "meta": {}},
        {"line_id": "L2", "sku": "CAF", "qty": 1, "unit_price_q": 1200, "line_total_q": 1200, "meta": {}},
    ]

    touched = spread_order_discount(lines, 500, at_least=True, split=True)

    assert len(touched) == 2
    assert sum(amount for _, _, amount in touched) == 500
    assert all(item["line_total_q"] == item["qty"] * item["unit_price_q"] for item, _, _ in touched)


def test_o_modificador_junta_a_parte_na_linha_de_origem_antes_do_preco():
    from types import SimpleNamespace

    session = SimpleNamespace(items=[
        {"line_id": "L1", "sku": "CRO", "qty": 2, "unit_price_q": 1133, "line_total_q": 2266, "meta": {}},
        {"line_id": "L1~r", "sku": "CRO", "qty": 1, "unit_price_q": 1134, "line_total_q": 1134,
         "meta": {SPLIT_OF: "L1"}},
        {"line_id": "L9~r", "sku": "CAF", "qty": 1, "unit_price_q": 1200, "line_total_q": 1200,
         "meta": {SPLIT_OF: "L9"}},
    ])
    session.update_items = lambda items: setattr(session, "items", items)

    SplitLineMergeModifier().apply(channel=None, session=session, ctx={})

    assert [(i["line_id"], i["qty"], i["meta"].get(SPLIT_OF)) for i in session.items] == [
        ("L1", 3, None),
        ("L9~r", 1, None),  # a de origem saiu da sacola: a parte fica como linha comum
    ]


# ── a sacola ───────────────────────────────────────────────────────────────


def test_a_sacola_da_maria_fecha_em_34_reais(web):
    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3)

    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")

    assert _lines(key) == [(2, 1133, 2266), (1, 1134, 1134)]
    session = Session.objects.get(session_key=key)
    assert session.pricing["coupon"]["discount_q"] == 500
    assert session.pricing["total_q"] == 3400


def test_preco_de_novo_nao_fragmenta_a_linha(web):
    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3)
    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")

    _touch(key, web)
    _touch(key, web)

    assert _lines(key) == [(2, 1133, 2266), (1, 1134, 1134)]


def test_mais_uma_unidade_na_parte_soma_e_o_rateio_volta_a_caber_numa_linha(web):
    """Quatro unidades repartem R$ 5,00 exato: a linha volta a ser uma só."""
    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3)
    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")
    sibling_id = Session.objects.get(session_key=key).items[1]["line_id"]

    sessions.modify_session(
        session_key=key, channel_ref=web, ops=[{"op": "set_qty", "line_id": sibling_id, "qty": 2}]
    )

    assert _lines(key) == [(4, 1175, 4700)]


def test_o_stepper_por_sku_poe_o_total_do_produto(web):
    """O stepper mostra a soma das duas linhas (3); pôr 2 deixa 2 Croissants, não 3."""
    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3)
    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")
    primary_id = Session.objects.get(session_key=key).items[0]["line_id"]

    cart_service.update_qty(
        session_key=key, channel_ref=web, line_id=primary_id, qty=2, sku="CRO", whole_product=True
    )

    assert _lines(key) == [(2, 1050, 2100)]


def test_tirar_o_produto_pelo_sku_leva_a_parte_junto(web):
    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3)
    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")
    primary_id = Session.objects.get(session_key=key).items[0]["line_id"]

    cart_service.remove_item(session_key=key, channel_ref=web, line_id=primary_id, sku="CRO", whole_product=True)

    assert _lines(key) == []


def test_tirar_so_a_linha_de_origem_deixa_a_parte_como_linha_comum(web):
    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3)
    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")
    primary_id = Session.objects.get(session_key=key).items[0]["line_id"]

    sessions.modify_session(
        session_key=key, channel_ref=web, ops=[{"op": "remove_line", "line_id": primary_id}]
    )

    # Uma unidade de R$ 13,00 abaixo do mínimo do cupom? Sem mínimo: R$ 5,00 nela.
    session = Session.objects.get(session_key=key)
    assert [(i["qty"], i["unit_price_q"]) for i in session.items] == [(1, 800)]
    assert SPLIT_OF not in session.items[0]["meta"]


def test_a_sacola_mostra_a_linha_inteira(web):
    """A partição é do preço gravado; a cliente comprou 3 Croissants e vê uma linha."""
    from shopman.shop.projections.cart import build_cart

    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3)
    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")

    cart = build_cart(key, web)

    assert [(line.sku, line.qty, line.line_total_q) for line in cart.lines] == [("CRO", 3, 3400)]
    assert cart.subtotal_q == 3400


def test_o_acompanhamento_mostra_a_linha_inteira(web):
    from shopman.shop.projections.order_tracking import _build_items

    order = Order.objects.create(ref="ORD-3240-T", channel_ref=web, status=Order.Status.NEW, total_q=3400)
    order.items.create(line_id="L1", sku="CRO", name="Croissant", qty=2, unit_price_q=1133, line_total_q=2266)
    order.items.create(
        line_id="L1~r", sku="CRO", name="Croissant", qty=1, unit_price_q=1134, line_total_q=1134,
        meta={SPLIT_OF: "L1"},
    )

    items = _build_items(order)

    assert [(i.sku, i.qty, i.line_total_q) for i in items] == [("CRO", 3, 3400)]


def test_o_pdv_nao_parte_linha(web):
    """A revisão da comanda e o disparo da cozinha casam a linha pela ``line_id`` do
    payload: no PDV o rateio segue com o centavo a mais para a cliente."""
    _fixed_coupon("PRIMEIRACOMPRA", 500)
    key = _cart(web, 3, origin="pos")

    cart_service.validate_and_apply_coupon(session_key=key, channel_ref=web, code="PRIMEIRACOMPRA")

    assert _lines(key) == [(3, 1133, 3399)]


# ── a NFC-e ────────────────────────────────────────────────────────────────


def test_a_nfce_leva_as_duas_linhas_coerentes(web):
    from shopman.shop.adapters.fiscal_focusnfe import _map_item
    from shopman.shop.services import fiscal as fiscal_service

    order = Order.objects.create(ref="ORD-3240", channel_ref=web, status=Order.Status.COMPLETED, total_q=3400)
    order.items.create(line_id="L1", sku="CRO", name="Croissant", qty=2, unit_price_q=1133, line_total_q=2266)
    order.items.create(line_id="L1~r", sku="CRO", name="Croissant", qty=1, unit_price_q=1134, line_total_q=1134)

    items = fiscal_service._build_fiscal_items(order)
    mapped = [_map_item(n, item, {}) for n, item in enumerate(items, start=1)]

    assert [
        (m["quantidade_comercial"], m["valor_unitario_comercial"], m["valor_bruto"]) for m in mapped
    ] == [("2.000", "11.33", "22.66"), ("1.000", "11.34", "11.34")]
