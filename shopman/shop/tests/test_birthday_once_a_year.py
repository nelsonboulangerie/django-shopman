"""O desconto de aniversário vale uma vez no dia do aniversário: uma vez por ano.

Beta adversarial do PDV (07/11/2026): com a aniversariante vinculada, toda venda
do dia levava 10%, em qualquer comanda e quantas vezes quisessem, sem passar pelo
teto de desconto do gerente. Decisão do dono no mesmo dia: "1 dia, mas por ano".
"""
from __future__ import annotations

from datetime import date

import pytest
from django.core.cache import cache
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.ids import generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services.modify import ModifyService

from shopman.shop.models import Channel, Promotion
from shopman.shop.services.promotions import birthday_benefit_available

pytestmark = pytest.mark.django_db


@pytest.fixture
def ana():
    today = timezone.localdate()
    Channel.objects.create(ref="pdv", name="PDV", is_active=True)
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=1000, is_published=True, is_sellable=True)
    Promotion.objects.create(
        ref="aniver", name="Aniversário", type=Promotion.PERCENT, value=10, is_active=True, birthday_only=True,
        valid_from=timezone.now() - timezone.timedelta(days=30), valid_until=timezone.now() + timezone.timedelta(days=30),
    )
    cache.clear()
    return Customer.objects.create(ref="ANA", first_name="Ana", birthday=date(1990, today.month, today.day))


def _priced_line(session_data=None) -> dict:
    key = generate_session_key()
    Session.objects.create(
        session_key=key, channel_ref="pdv", state="open", data={"customer": {"ref": "ANA"}, **(session_data or {})},
    )
    session = ModifyService.modify_session(
        session_key=key, channel_ref="pdv",
        ops=[{"op": "add_line", "sku": "BOLO", "qty": 1, "unit_price_q": 1000}],
    )
    return session


def _order_with(session, *, ref: str, status: str = "completed") -> Order:
    return Order.objects.create(
        ref=ref, channel_ref="pdv", status=status, total_q=900,
        data={"customer_ref": "ANA"}, snapshot={"pricing": session.pricing},
    )


def test_a_primeira_venda_do_aniversario_leva_e_marca_o_desconto(ana):
    session = _priced_line()
    assert session.items[0]["unit_price_q"] == 900
    (record,) = session.pricing["discount"]["items"]
    assert record["birthday"] is True


def test_a_segunda_venda_do_dia_nao_leva_de_novo(ana):
    first = _priced_line()
    _order_with(first, ref="PDV-1")
    assert birthday_benefit_available(ana, timezone.localdate()) is False
    assert _priced_line().items[0]["unit_price_q"] == 1000


def test_pedido_cancelado_devolve_o_beneficio(ana):
    _order_with(_priced_line(), ref="PDV-1", status="cancelled")
    assert _priced_line().items[0]["unit_price_q"] == 900


def test_a_edicao_do_proprio_pedido_nao_conta_contra_ele(ana):
    _order_with(_priced_line(), ref="PDV-1")
    edited = _priced_line({"pos_edit": {"order_ref": "PDV-1"}})
    assert edited.items[0]["unit_price_q"] == 900


def test_desconto_que_nao_e_de_aniversario_nao_consome_o_beneficio(ana):
    Order.objects.create(
        ref="PDV-0", channel_ref="pdv", status="completed", total_q=900, data={"customer_ref": "ANA"},
        snapshot={"pricing": {"discount": {"items": [{"type": "manual", "discount_q": 100}]}}},
    )
    assert birthday_benefit_available(ana, timezone.localdate()) is True


def test_fora_do_dia_nao_ha_beneficio(ana):
    other_day = timezone.localdate() + timezone.timedelta(days=1)
    assert birthday_benefit_available(ana, other_day) is False


def test_o_aviso_do_balcao_nao_promete_o_desconto_ja_usado(ana):
    from shopman.backstage.projections.pos import _birthday_projection

    assert _birthday_projection(ana)["birthday_promo_label"] == "Aniversário"
    _order_with(_priced_line(), ref="PDV-1")
    view = _birthday_projection(ana)
    assert view["is_birthday_today"] is True
    assert view["birthday_promo_label"] == ""
