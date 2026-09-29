"""O aviso de nova data diz a data por extenso — a mesma que a tela mostra."""
from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.notification_copy import CUSTOMER_COPY
from shopman.shop.services.notification import _status_note

pytestmark = pytest.mark.django_db


def _order(day, slot="") -> Order:
    return Order.objects.create(
        ref="ENC-NOVA-DATA", status="accepted", total_q=1000,
        data={"delivery_date": day.isoformat(), "delivery_time_slot": slot},
    )


def test_a_data_nova_sai_por_extenso_com_a_janela_e_sem_ponto():
    day = timezone.localdate() + timedelta(days=5)
    nota = _status_note(_order(day, "14:00-14:30"), "order_rescheduled", None)

    assert nota.endswith("14:00 às 14:30")
    assert day.strftime("%d/%m") in nota
    assert not nota.endswith(".")


def test_amanha_se_diz_amanha():
    nota = _status_note(_order(timezone.localdate() + timedelta(days=1)), "order_rescheduled", None)

    assert nota == "amanhã"


def test_sem_data_legivel_a_frase_nunca_fica_vazia():
    """O template da Meta não aceita variável vazia."""
    order = Order.objects.create(ref="ENC-SEM-DATA", status="accepted", total_q=1000, data={})

    assert _status_note(order, "order_rescheduled", None) == "a nova data que está no pedido"


def test_a_voz_e_a_da_casa():
    corpo = CUSTOMER_COPY["order_rescheduled"]["body"]

    assert corpo.startswith("Oi{customer_name_greeting}!")
    assert "{status_note}" in corpo and "{tracking_url}" in corpo
