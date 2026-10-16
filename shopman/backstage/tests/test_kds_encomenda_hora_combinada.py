"""P2-16: a encomenda chega à cozinha às 00:05, mas o prazo dela é a hora combinada.

O ticket da encomenda nasce na madrugada do dia (``preorder_activation_at``). O
card contava o tempo desde ali contra a meta da estação: às 10h a encomenda das
15h aparecia como "Atrasado", no topo da fila, e a gerente recebia "passou de
10 min" às 00:15. O prazo de quem tem hora combinada é a hora combinada.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_board
from shopman.shop.directives import KDS_TICKET_LATE
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


def _at(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    day = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


@pytest.fixture
def relogio(monkeypatch):
    """Crava o relógio: ``relogio(10)`` são 10h de hoje para todo o Django."""

    def set_now(hour: int, minute: int = 0) -> datetime:
        moment = _at(hour, minute)
        monkeypatch.setattr(timezone, "now", lambda: moment)
        return moment

    return set_now


@pytest.fixture
def forno(db):
    Shop.objects.get_or_create(name="Nelson Boulangerie")
    return KDSInstance.objects.create(ref="forno", name="Forno", type="prep", target_time_minutes=10)


def _order(ref: str, *, data: dict, channel_ref: str = "web", created_at: datetime) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        session_key=f"sk-{ref}",
        status=Order.Status.PREPARING,
        total_q=1500,
        data={"customer": {"name": "Café Parisiense"}, "fulfillment_type": "pickup", **data},
    )
    Order.objects.filter(pk=order.pk).update(created_at=created_at)
    order.refresh_from_db()
    return order


def _ticket(order: Order, station: KDSInstance, *, created_at: datetime) -> KDSTicket:
    ticket = KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=station,
        items=[{"sku": "PAO", "name": "Pão de Hambúrguer", "qty": 3, "line_id": "L1"}],
    )
    KDSTicket.objects.filter(pk=ticket.pk).update(created_at=created_at)
    ticket.refresh_from_db()
    return ticket


def _encomenda_das_15h(forno) -> Order:
    order = _order(
        "WEB-1-E15",
        data={"delivery_date": timezone.localdate().isoformat(), "delivery_time_slot": "slot-15"},
        created_at=_at(18, days=-2),
    )
    _ticket(order, forno, created_at=_at(0, 5))
    return order


def _cards(forno) -> dict:
    return {card.order_ref: card for card in build_kds_board(forno.ref).tickets}


def test_a_encomenda_das_15h_nao_esta_atrasada_as_10h_e_diz_a_hora(forno, relogio):
    relogio(10)
    _encomenda_das_15h(forno)

    card = _cards(forno)["WEB-1-E15"]

    assert card.is_preorder is True
    assert card.timer_class == "timer-ok"
    assert card.due_time_display == "retira a partir das 15h"
    assert card.due_clock_display == "15h"
    assert card.due_in_seconds == 5 * 3600


def test_passou_da_hora_combinada_a_encomenda_fica_atrasada(forno, relogio):
    relogio(15, 20)
    _encomenda_das_15h(forno)

    card = _cards(forno)["WEB-1-E15"]

    assert card.timer_class == "timer-late"
    assert card.due_in_seconds == -20 * 60


def test_a_venda_sem_hora_combinada_segue_a_meta_da_estacao(forno, relogio):
    relogio(10)
    balcao = _order("WEB-1-B01", data={}, created_at=_at(9, 30))
    _ticket(balcao, forno, created_at=_at(9, 30))

    card = _cards(forno)["WEB-1-B01"]

    assert card.timer_class == "timer-late"
    assert card.due_time_display == ""
    assert card.due_clock_display == ""
    assert card.due_in_seconds is None


def test_a_meia_hora_do_dia_e_o_ifood_agendado_dizem_a_hora_deles(forno, relogio):
    relogio(10)
    entrega = _order(
        "POS-1-D11",
        data={"fulfillment_type": "delivery", "delivery_time_slot": "11:30-12:00"},
        created_at=_at(9, 50),
    )
    _ticket(entrega, forno, created_at=_at(9, 50))
    ifood = _order(
        "IFOOD-1-A17",
        channel_ref="ifood",
        data={
            "fulfillment_type": "delivery",
            "ifood": {
                "order_timing": "SCHEDULED",
                "schedule": {
                    "preparation_start_at": _at(9, 45).isoformat(),
                    "delivery_start_at": _at(10, 30).isoformat(),
                    "delivery_end_at": _at(11).isoformat(),
                },
            },
        },
        created_at=_at(8),
    )
    _ticket(ifood, forno, created_at=_at(9, 45))

    cards = _cards(forno)

    assert cards["POS-1-D11"].due_time_display == "entrega das 11:30 às 12:00"
    assert cards["POS-1-D11"].due_clock_display == "11h30"
    assert cards["IFOOD-1-A17"].due_time_display == "entrega às 10:30"
    assert cards["IFOOD-1-A17"].due_in_seconds == 30 * 60


def test_o_despertador_do_atraso_da_encomenda_toca_na_hora_combinada(
    forno, relogio, django_capture_on_commit_callbacks
):
    relogio(0, 5)
    order = _order(
        "WEB-1-E16",
        data={"delivery_date": timezone.localdate().isoformat(), "delivery_time_slot": "slot-15"},
        created_at=_at(18, days=-2),
    )
    with django_capture_on_commit_callbacks(execute=True):
        ticket = KDSTicket.objects.create(
            session_key=order.session_key,
            kds_instance=forno,
            items=[{"sku": "PAO", "name": "Pão", "qty": 1, "line_id": "L1"}],
        )

    despertador = Directive.objects.get(topic=KDS_TICKET_LATE, payload__ticket_pk=ticket.pk)
    assert despertador.available_at == _at(15)
