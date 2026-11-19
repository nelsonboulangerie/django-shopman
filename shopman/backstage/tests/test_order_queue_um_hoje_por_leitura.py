"""Um "hoje" por leitura do quadro (WP-G09, EXCELENCIA-GESTOR P2-07).

O quadro do Gestor perguntava "que dia é hoje?" várias vezes na mesma leitura:
uma vez para decidir quem é trabalho do dia, outra para decidir quem é encomenda
de outro dia, outra em cada cartão, outra no ``service_day``. Na leitura que
cruza a meia-noite as respostas divergiam: a encomenda de "amanhã" deixava de
ser futura entre uma pergunta e a outra, saía das colunas do dia por ser de
amanhã e da lista de Encomendas por ser de hoje, e sumia da tela por um ciclo.

Esta suíte congela o relógio na virada (as primeiras N leituras antes da
meia-noite, as seguintes depois) e prende, para toda N:

- a encomenda aparece em UMA lista, nunca em nenhuma e nunca em duas;
- o cartão, a lista em que ele mora e o ``service_day`` falam do mesmo dia.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections import order_queue
from shopman.backstage.projections.order_queue import build_two_zone_queue

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

#: Quantas leituras do relógio a virada pode atravessar. Maior que o número de
#: leituras que uma projeção de um pedido faz, para cobrir a virada em qualquer
#: ponto dela (e depois dela: a última N é a leitura inteira antes da meia-noite).
MAX_READS = 60


class TurnOfDay:
    """O relógio da virada: ``flips_after`` leituras antes da meia-noite, o resto depois."""

    def __init__(self, before: datetime, after: datetime, flips_after: int) -> None:
        self.before, self.after, self.flips_after = before, after, flips_after
        self.reads = 0

    def __call__(self) -> datetime:
        self.reads += 1
        return self.before if self.reads <= self.flips_after else self.after


def _preorder(ref: str, day) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=Order.Status.ACCEPTED, total_q=1870,
        data={
            "customer": {"name": "Clara Teste"},
            "fulfillment_type": "pickup",
            "payment": {"method": "cash"},
            "delivery_date": day.isoformat(),
        },
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAIN", name="Pain de Campagne", qty=1,
        unit_price_q=1870, line_total_q=1870,
    )
    return order


def _appearances(queue, ref: str) -> dict[str, int]:
    """Em quantas posições de cada lista do quadro o pedido aparece."""
    lists = {
        "intake": queue.intake,
        "prep": queue.prep,
        "preorders": queue.preorders,
        "expedition_pickup": queue.expedition_pickup,
        "expedition_delivery": queue.expedition_delivery,
        "expedition_delivery_transit": queue.expedition_delivery_transit,
    }
    return {name: sum(1 for card in cards if card.ref == ref) for name, cards in lists.items()}


def test_a_leitura_que_cruza_a_meia_noite_nao_tira_a_encomenda_das_duas_listas(monkeypatch):
    zone = timezone.get_current_timezone()
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    before = timezone.make_aware(datetime.combine(today, time(23, 59, 59, 900_000)), zone)
    after = timezone.make_aware(datetime.combine(tomorrow, time(0, 0, 0, 100_000)), zone)
    order = _preorder("G09-VIRADA", tomorrow)

    lost: list[tuple[int, dict[str, int]]] = []
    torn: list[tuple[int, str]] = []
    for flips_after in range(MAX_READS + 1):
        clock = TurnOfDay(before, after, flips_after)
        monkeypatch.setattr(timezone, "now", clock)
        queue = build_two_zone_queue()
        seen = _appearances(queue, order.ref)
        if sum(seen.values()) != 1:
            lost.append((flips_after, seen))
            continue
        # O dia da leitura é o da PRIMEIRA leitura do relógio, e vale para tudo.
        read_day = today if flips_after >= 1 else tomorrow
        card = next(
            card for card in (*queue.prep, *queue.preorders) if card.ref == order.ref
        )
        facts = (queue.service_day, card.is_preorder, card.schedule_state, seen["preorders"])
        expected = (
            (today.isoformat(), True, "future", 1)
            if read_day == today
            # Depois da virada a encomenda é de hoje: sai do "futuro" inteira.
            else (tomorrow.isoformat(), False, card.schedule_state, seen["preorders"])
        )
        if facts != expected or (read_day == tomorrow and card.schedule_state == "future"):
            torn.append((flips_after, repr(facts)))

    assert not lost, f"a encomenda saiu das listas (ou entrou em duas) nestas viradas: {lost}"
    assert not torn, f"o cartão e o quadro falaram de dias diferentes nestas viradas: {torn}"


def test_o_quadro_le_o_relogio_uma_vez_e_passa_adiante(monkeypatch):
    """O ``now`` de todos os cartões é o mesmo instante: o da leitura do quadro."""
    today = timezone.localdate()
    _preorder("G09-A", today + timedelta(days=1))
    _preorder("G09-B", today)
    step = iter(range(10_000))
    base = timezone.now()
    monkeypatch.setattr(timezone, "now", lambda: base + timedelta(seconds=next(step)))

    queue = build_two_zone_queue()

    cards = (*queue.prep, *queue.preorders)
    assert {card.ref for card in cards} == {"G09-A", "G09-B"}
    assert {card.server_now_iso for card in cards} == {base.isoformat()}


def test_as_reguas_do_dia_aceitam_o_dia_de_quem_chama():
    """``today`` passado vence o relógio: é assim que a projeção fixa o dia dela."""
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    order = _preorder("G09-REGUA", tomorrow)

    assert order_queue._is_future_preorder(order, today=today) is True
    assert order_queue._is_future_preorder(order, today=tomorrow) is False
    assert order_queue._schedule(order, today=today)[1] == "future"
    assert order_queue._schedule(order, today=tomorrow)[1] != "future"
    assert order_queue._commitment_date_display(tomorrow, today=today) == "amanhã"
    assert order_queue._commitment_date_display(tomorrow, today=tomorrow) == "hoje"
