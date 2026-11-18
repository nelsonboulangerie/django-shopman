"""A encomenda se anuncia (WP-G01, EXCELENCIA-GESTOR P1-01, P1-06, P1-07).

O card do Gestor conhecia só o DIA da encomenda, e só enquanto ele era futuro. O
operador tinha 60 min para aceitar um pedido sem ver a data nem a hora que estava
prometendo. Esta suíte prende:

- o card publica o combinado na MESMA frase do detalhe (``schedule_label``);
- o estado do combinado: ``future``, ``today`` (hoje, com hora) e ``overdue``;
- o passado tem nome próprio: "Era para ontem · A partir das 15h";
- o pedido de agora, e o combinado já cumprido, não dizem nada no card;
- o sino do Gestor leva a mesma frase ao lado do "Aceitar".
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.alerts import build_operator_alerts_projection
from shopman.backstage.projections.order_queue import build_operator_order, build_order_card
from shopman.shop.models import Shop
from shopman.shop.services.fulfillment_window import window_label

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


def _order(ref: str, *, status: str = Order.Status.NEW, day=None, slot: str | None = None) -> Order:
    data = {
        "customer": {"name": f"Cliente {ref}"},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
        "availability_decision": {"approved": True, "decisions": []},
    }
    if day is not None:
        data["delivery_date"] = day.isoformat()
    if slot:
        data["delivery_time_slot"] = slot
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=1870, data=data,
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAIN", name="Pain de Campagne", qty=1,
        unit_price_q=1870, line_total_q=1870,
    )
    return order


def _today():
    return timezone.localdate()


def test_encomenda_para_amanha_com_janela_diz_o_dia_e_a_janela():
    order = _order("G01-AMANHA", day=_today() + timedelta(days=1), slot="slot-15")

    card = build_order_card(order)

    assert (card.schedule_label, card.schedule_state) == ("Amanhã · A partir das 15h", "future")
    # A mesma frase do detalhe: uma função só para as duas formas.
    assert build_operator_order(order).schedule_label == card.schedule_label
    # O que já existia continua igual para quem o lê (Central, PDV, busca).
    assert (card.is_preorder, card.commitment_date_display) == (True, "amanhã")


def test_encomenda_de_outro_dia_sem_janela_diz_que_nao_ha_horario():
    order = _order("G01-SEM-HORA", day=_today() + timedelta(days=1))

    card = build_order_card(order)

    assert (card.schedule_label, card.schedule_state) == ("Amanhã · sem horário combinado", "future")


def test_janela_fora_da_grade_nao_vaza_o_ref():
    """O ref que a grade da casa não conhece não aparece cru, e grita no log."""
    order = _order("G01-MANHA", day=_today() + timedelta(days=1), slot="manha")

    with patch("shopman.shop.services.fulfillment_window.logger") as log:
        card = build_order_card(order)

    assert card.schedule_label == "Amanhã · horário não reconhecido"
    assert "manha" not in card.schedule_label
    assert log.error.called and "manha" in log.error.call_args.args


def test_encomenda_para_daqui_a_dois_dias_diz_a_data():
    day = _today() + timedelta(days=2)
    card = build_order_card(_order("G01-DOIS", day=day, slot="slot-09"))

    assert card.schedule_state == "future"
    assert card.schedule_label.endswith(f"{day:%d/%m} · A partir das 9h")
    assert card.schedule_label[:1].isupper()


def test_pedido_de_hoje_com_hora_combinada_mostra_a_hora():
    card = build_order_card(_order("G01-HOJE", day=_today(), slot="14:00-14:30"))

    # A hora sai do formatador da janela (a frente "12h45" muda o formato ali, num ponto só).
    assert (card.schedule_label, card.schedule_state) == (f"Hoje · {window_label('14:00-14:30')}", "today")
    assert card.is_preorder is False


def test_pedido_de_hoje_com_janela_e_sem_data_e_do_dia_da_venda():
    """A meia hora do PDV para hoje vem sem ``delivery_date``: o dia é o da venda."""
    card = build_order_card(_order("G01-PDV", slot="14:00-14:30"))

    assert (card.schedule_label, card.schedule_state) == (f"Hoje · {window_label('14:00-14:30')}", "today")


def test_pedido_de_agora_nao_tem_o_que_dizer():
    card = build_order_card(_order("G01-AGORA"))
    assert (card.schedule_label, card.schedule_state) == ("", "")
    # Hoje sem hora combinada também é o pedido de agora, para o card.
    card = build_order_card(_order("G01-HOJE-SEM-HORA", day=_today()))
    assert (card.schedule_label, card.schedule_state) == ("", "")


def test_encomenda_vencida_tem_nome_proprio():
    order = _order("G01-ONTEM", status=Order.Status.ACCEPTED, day=_today() - timedelta(days=1), slot="slot-15")

    card = build_order_card(order)

    assert (card.schedule_label, card.schedule_state) == ("Era para ontem · A partir das 15h", "overdue")
    assert build_operator_order(order).schedule_label == "Era para ontem · A partir das 15h"


def test_encomenda_vencida_sem_janela_diz_so_o_dia():
    day = _today() - timedelta(days=3)
    card = build_order_card(_order("G01-SAB", status=Order.Status.READY, day=day))

    assert card.schedule_state == "overdue"
    assert card.schedule_label.startswith("Era para ")
    assert card.schedule_label.endswith(f"{day:%d/%m}")


def test_combinado_cumprido_nao_venceu():
    """Concluído não "era para": o card cala e o detalhe mostra só a data."""
    order = _order("G01-FEITO", status=Order.Status.COMPLETED, day=_today() - timedelta(days=1), slot="slot-15")

    card = build_order_card(order)

    assert (card.schedule_label, card.schedule_state) == ("", "")
    assert build_operator_order(order).schedule_label == "Ontem · A partir das 15h"


# ── O sino ──────────────────────────────────────────────────────────────────


@pytest.fixture
def gestor(db):
    Shop.objects.create(name="Nelson Boulangerie")
    user = User.objects.create_user("gestor-g01", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


def test_o_aceitar_do_sino_leva_o_combinado(client, gestor):
    order = _order("G01-SINO", day=_today() + timedelta(days=1), slot="slot-15")
    OperatorAlert.objects.create(type="stale_new_order", severity="warning", message="espera aceite", order_ref=order.ref)
    client.force_login(gestor)

    alerta = client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()["alerts"][0]

    assert (alerta["order_schedule_label"], alerta["order_schedule_state"]) == ("Amanhã · A partir das 15h", "future")
    assert "confirm_order" in {acao["kind"] for acao in alerta["actions"]}


def test_aviso_de_pedido_sem_combinado_nao_diz_nada():
    order = _order("G01-SINO-AGORA")
    alert = OperatorAlert.objects.create(type="stale_new_order", severity="warning", message="x", order_ref=order.ref)

    row = build_operator_alerts_projection(alerts=[alert], counts=_counts(), surface="orders").alerts[0]

    assert (row.order_schedule_label, row.order_schedule_state) == ("", "")


def test_fora_do_gestor_o_aviso_nao_le_o_pedido():
    order = _order("G01-SINO-PROD", day=_today() + timedelta(days=1), slot="slot-15")
    alert = OperatorAlert.objects.create(type="stale_new_order", severity="warning", message="x", order_ref=order.ref)

    row = build_operator_alerts_projection(alerts=[alert], counts=_counts(), surface="production").alerts[0]

    assert row.order_schedule_label == ""


def _counts():
    class _Counts:
        active = 1
        critical = 0

    return _Counts()
