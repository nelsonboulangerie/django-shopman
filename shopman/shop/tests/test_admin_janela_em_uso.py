"""O Admin não tira da grade uma janela que pedido aberto ainda usa (#2644).

Janela que sai da grade com pedido aberto nela faz o pedido perder o rótulo: a
equipe lê "horário não reconhecido" e o cliente "horário a confirmar" (#2555).
Falhar fechado é não deixar o dado chegar a esse estado, e dizer quais pedidos
a casa precisa reagendar antes.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order

from shopman.shop.admin.shop import ShopForm
from shopman.shop.models import Shop
from shopman.shop.policies import pickup_window_in_use
from shopman.shop.tests.test_admin import _shop_form_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Loja", brand_name="Loja", short_name="LJ", primary_color="#C5A55A", default_ddd="43",
        defaults={"pickup_slots": [
            {"ref": "slot-09", "label": "A partir das 9h", "starts_at": "09:00"},
            {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
        ]},
    )


def _order(ref: str, *, slot: str, status=Order.Status.ACCEPTED, day="2026-11-25"):
    return Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000,
        data={"delivery_date": day, "delivery_time_slot": slot},
    )


def _without_the_15h(shop):
    data = _shop_form_data(shop)
    data["defaults_pickup_slot_2_ref"] = ""
    data["defaults_pickup_slot_2_label"] = ""
    data["defaults_pickup_slot_2_starts_at"] = ""
    return ShopForm(data=data, instance=shop)


def test_tirar_a_janela_que_pedido_aberto_usa_e_recusado_e_diz_quais_pedidos(shop):
    _order("WEB-ABERTO-1", slot="slot-15")
    _order("WEB-ABERTO-2", slot="slot-15", status=Order.Status.READY, day="2026-11-26")

    form = _without_the_15h(shop)

    assert not form.is_valid()
    message = " ".join(form.non_field_errors())
    assert "“A partir das 15h”" in message
    assert "WEB-ABERTO-1 (25/11)" in message
    assert "WEB-ABERTO-2 (26/11)" in message
    assert "Reagende antes" in message
    shop.refresh_from_db()
    assert [slot["ref"] for slot in shop.defaults["pickup_slots"]] == ["slot-09", "slot-15"]


def test_trocar_o_ref_da_janela_em_uso_tambem_e_recusado(shop):
    _order("WEB-ABERTO", slot="slot-15")
    data = _shop_form_data(shop)
    data["defaults_pickup_slot_2_ref"] = "slot-16"

    form = ShopForm(data=data, instance=shop)

    assert not form.is_valid()
    assert "WEB-ABERTO" in " ".join(form.non_field_errors())


def test_janela_so_de_pedido_terminado_sai_da_grade(shop):
    for status in (Order.Status.COMPLETED, Order.Status.CANCELLED, Order.Status.RETURNED):
        _order(f"WEB-{status}", slot="slot-15", status=status)
    _order("WEB-OUTRA", slot="slot-09")

    form = _without_the_15h(shop)

    assert form.is_valid(), form.errors
    saved = form.save()
    assert [slot["ref"] for slot in saved.defaults["pickup_slots"]] == ["slot-09"]


def test_a_politica_lista_os_pedidos_e_resume_o_resto():
    grade = [{"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"}]
    assert pickup_window_in_use.removal_refusal(previous=grade, kept=set()) == ""

    for n in range(pickup_window_in_use.LISTED_ORDERS + 2):
        _order(f"WEB-{n:02d}", slot="slot-15")

    message = pickup_window_in_use.removal_refusal(previous=grade, kept=set())
    assert message.startswith("Não dá para tirar da grade a janela \u201cA partir das 15h\u201d")
    assert "WEB-00 (25/11)" in message
    assert message.endswith("e mais 2.")
    assert pickup_window_in_use.removal_refusal(previous=grade, kept={"slot-15"}) == ""
