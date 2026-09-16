"""O Admin mostra a janela combinada em português, nunca o ref cru.

"Entrega em 2026-09-16 (slot-09)" no resumo e na coluna do changelist era o
identificador vazando para o gestor. Os dois lugares passam pelo mesmo
resolvedor das duas grades (``fulfillment_window.window_label``) — o
orderman (Core) segue cru porque Core não importa shop; o admin REGISTRADO é
o do shop, e é ele que resolve.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from shopman.orderman.models import Order

from shopman.shop.admin.orders import OrderAdmin, _order_data_rows

pytestmark = pytest.mark.django_db


def _rows(data: dict) -> dict[str, str]:
    return dict(_order_data_rows(data))


def test_o_resumo_resolve_o_canonico():
    rows = _rows({"delivery_date": "2026-09-16", "delivery_time_slot": "slot-09"})

    assert rows["Entrega em"] == "2026-09-16 (A partir das 09h)"


def test_o_resumo_resolve_a_meia_hora():
    rows = _rows({"delivery_date": "2026-09-16", "delivery_time_slot": "14:00-14:30"})

    assert rows["Entrega em"] == "2026-09-16 (14:00 às 14:30)"


def test_o_resumo_sem_janela_mostra_so_a_data():
    rows = _rows({"delivery_date": "2026-09-16"})

    assert rows["Entrega em"] == "2026-09-16"


def test_o_admin_registrado_e_o_do_shop_e_a_coluna_entrega_resolve_a_janela():
    model_admin = admin.site._registry[Order]
    assert isinstance(model_admin, OrderAdmin)

    order = Order.objects.create(
        ref="ADM-WINDOW", channel_ref="pdv", status="accepted", total_q=1000,
        data={"delivery_date": "2026-09-16", "delivery_time_slot": "slot-12", "is_preorder": True},
    )

    coluna = str(model_admin.delivery_date_display(order))

    assert "2026-09-16 (A partir das 12h)" in coluna
    assert "slot-12" not in coluna


def test_a_coluna_entrega_sem_data_fica_em_branco():
    model_admin = admin.site._registry[Order]
    order = Order.objects.create(ref="ADM-NO-DATE", channel_ref="pdv", status="accepted", total_q=1000, data={})

    assert model_admin.delivery_date_display(order) == "-"
