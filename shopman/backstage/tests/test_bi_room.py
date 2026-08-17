"""Salão: lotação, pico, giro e valor (BI-QUESTION-CATALOG §3.2/F4).

Medido **sem vínculo comanda↔mesa** — o dono vetou, com razão: no ato de abrir a
comanda ninguém sabe onde vai sentar. O que estes testes guardam:

- só quem **consumiu aqui** ocupa lugar; comanda de quem levou some da conta
  sozinha, sem filtro especial;
- **dia sem expediente carimbado não vira linha** — feriado fechado apareceria
  como um dia inteiro de salão vazio;
- a lotação sai em **faixa grossa**, porque a capacidade oficial da casa não é
  limite duro (o sofá aperta, o bistrô e o bancão ficam fora da conta);
- mesa cadastrada depois **não reescreve o passado**.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from shopman.backstage.models import (
    ConsumptionRole,
    DayContext,
    ProductConsumptionTag,
    Reading,
    SeatingSpot,
    SpotKind,
)
from shopman.backstage.projections.bi_explore import ExploreError, build_bi_explore, validate_config
from shopman.backstage.services.room import (
    BUSY,
    EMPTY,
    FULL,
    LIGHT,
    capacity_on,
    load_band,
    room_days,
    sweep_day,
)

DAY = date(2026, 8, 10)  # segunda-feira
OPENS = time(9, 0)
CLOSES = time(18, 0)


@pytest.fixture
def room(db):
    """Quatro lugares que contam e um que não conta."""
    for numero in range(1, 5):
        SeatingSpot.objects.create(ref=f"mesa-{numero}", label=f"Mesa {numero}",
                                   kind=SpotKind.TABLE, seats=2)
    SeatingSpot.objects.create(ref="bistro", label="Mesinha alta", kind=SpotKind.TABLE,
                               seats=2, counts_in_capacity=False)
    DayContext.objects.create(date=DAY, open_minutes=540, opens_at=OPENS, closes_at=CLOSES)


@pytest.fixture
def tagged(db):
    coffee = ConsumptionRole.objects.create(ref="consome-aqui", label="Consome aqui",
                                            reading=Reading.ANCHOR)
    bread = ConsumptionRole.objects.create(ref="leva", label="Leva",
                                           reading=Reading.TAKEAWAY)
    ProductConsumptionTag.objects.create(sku="CAFE", role=coffee)
    ProductConsumptionTag.objects.create(sku="PAO", role=bread)


def _tab(ref: str, *, sku: str, total_q: int, opens: time, closes: time, day: date = DAY):
    """Uma comanda aberta e fechada — o gesto que a casa já faz todo dia."""
    from shopman.orderman.models import Order, OrderItem, Session

    tz = timezone.get_current_timezone()
    session = Session.objects.create(
        session_key=f"sess-{ref}", channel_ref="pdv", state="committed",
        handle_type="pos_tab", handle_ref=ref,
    )
    Session.objects.filter(pk=session.pk).update(
        opened_at=datetime.combine(day, opens, tzinfo=tz),
        committed_at=datetime.combine(day, closes, tzinfo=tz),
    )
    order = Order.objects.create(
        ref=f"ORD-{ref}", channel_ref="pdv", session_key=session.session_key,
        status=Order.Status.COMPLETED, total_q=total_q,
    )
    OrderItem.objects.create(order=order, line_id="L1", sku=sku, name=sku,
                             qty=Decimal("1"), unit_price_q=total_q, line_total_q=total_q)
    Order.objects.filter(pk=order.pk).update(
        created_at=datetime.combine(day, closes, tzinfo=tz)
    )
    return order


# ── A faixa ──────────────────────────────────────────────────────────────────


def test_load_band_is_coarse_on_purpose():
    assert load_band(0, 4) == EMPTY
    assert load_band(1, 4) == LIGHT
    assert load_band(2, 4) == LIGHT
    assert load_band(3, 4) == BUSY
    assert load_band(4, 4) == FULL
    assert load_band(6, 4) == FULL  # apertou: acima do teto continua no teto


def test_people_seated_without_registered_spots_is_not_empty():
    """Salão sem cadastro não pode ler como vazio — seria o oposto do que houve."""
    assert load_band(2, 0) == BUSY


# ── A varredura ──────────────────────────────────────────────────────────────


def test_empty_day_counts_the_whole_shift_as_empty():
    minutes, peaks, peak = sweep_day([], day=DAY, capacity=4, opens_at=OPENS, closes_at=CLOSES)
    assert peak == 0
    assert sum(minutes.values()) == 540
    assert all(band == EMPTY for band, _hour in minutes)


def test_a_stretch_is_split_at_the_hour_boundary():
    """Sem partir na virada, um trecho das 9h05 às 11h20 leria tudo como 9h."""
    tz = timezone.get_current_timezone()
    interval = (
        datetime.combine(DAY, time(9, 5), tzinfo=tz),
        datetime.combine(DAY, time(11, 20), tzinfo=tz),
    )
    minutes, peaks, _ = sweep_day([interval], day=DAY, capacity=4,
                                  opens_at=OPENS, closes_at=CLOSES)
    occupied = {hour: m for (band, hour), m in minutes.items() if band != EMPTY}
    assert occupied == {9: 55, 10: 60, 11: 20}
    assert peaks[10] == 1


def test_time_outside_the_shift_costs_no_table():
    tz = timezone.get_current_timezone()
    interval = (
        datetime.combine(DAY, time(7, 0), tzinfo=tz),
        datetime.combine(DAY, time(10, 0), tzinfo=tz),
    )
    minutes, _peaks, _ = sweep_day([interval], day=DAY, capacity=4,
                                   opens_at=OPENS, closes_at=CLOSES)
    occupied = sum(m for (band, _h), m in minutes.items() if band != EMPTY)
    assert occupied == 60  # só das 9h às 10h


def test_peak_counts_groups_at_the_same_time():
    tz = timezone.get_current_timezone()
    overlapping = [
        (datetime.combine(DAY, time(9, 0), tzinfo=tz), datetime.combine(DAY, time(10, 0), tzinfo=tz)),
        (datetime.combine(DAY, time(9, 30), tzinfo=tz), datetime.combine(DAY, time(10, 30), tzinfo=tz)),
        (datetime.combine(DAY, time(9, 45), tzinfo=tz), datetime.combine(DAY, time(11, 0), tzinfo=tz)),
    ]
    _minutes, _peaks, peak = sweep_day(overlapping, day=DAY, capacity=4,
                                       opens_at=OPENS, closes_at=CLOSES)
    assert peak == 3


# ── A capacidade ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_capacity_ignores_what_only_exists_on_a_full_day(room):
    spots = list(SeatingSpot.objects.all())
    assert capacity_on(DAY, spots) == 4  # o bistrô não conta


@pytest.mark.django_db
def test_a_table_added_later_does_not_rewrite_the_past(room):
    SeatingSpot.objects.create(ref="mesa-nova", label="Mesa nova", kind=SpotKind.TABLE,
                               seats=2, active_from=DAY + timedelta(days=30))
    spots = list(SeatingSpot.objects.all())
    assert capacity_on(DAY, spots) == 4
    assert capacity_on(DAY + timedelta(days=40), spots) == 5


# ── No explorador ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_only_who_ate_here_takes_a_seat(room, tagged):
    _tab("1001", sku="CAFE", total_q=2000, opens=time(9, 0), closes=time(10, 0))
    _tab("1002", sku="PAO", total_q=1000, opens=time(9, 0), closes=time(9, 5))

    days = room_days(DAY, DAY)
    assert days[DAY].groups == 1  # a comanda de quem levou some sozinha
    assert days[DAY].revenue_q == 2000


@pytest.mark.django_db
def test_a_day_without_a_stamped_shift_has_no_line(tagged, db):
    """Feriado fechado apareceria como nove horas de salão vazio."""
    for numero in range(1, 5):
        SeatingSpot.objects.create(ref=f"mesa-{numero}", label=f"Mesa {numero}")
    _tab("1001", sku="CAFE", total_q=2000, opens=time(9, 0), closes=time(10, 0))
    assert room_days(DAY, DAY) == {}
    assert build_bi_explore(metric="room_minutes", by="room_load",
                            date_from=DAY, date_to=DAY).rows == ()


@pytest.mark.django_db
def test_idle_hours_are_the_question_about_when_the_room_is_empty(room, tagged):
    _tab("1001", sku="CAFE", total_q=2000, opens=time(9, 0), closes=time(10, 0))

    report = build_bi_explore(metric="room_minutes", by="room_load", by2="hour",
                              date_from=DAY, date_to=DAY)
    cells = {(row.key, row.key2): row.value for row in report.rows}
    assert cells[(LIGHT, "09")] == 60.0
    assert cells[(EMPTY, "10")] == 60.0
    assert report.unit == "minutes"


@pytest.mark.django_db
def test_peak_by_hour_says_when_the_room_hits_the_ceiling(room, tagged):
    for index in range(4):
        _tab(f"200{index}", sku="CAFE", total_q=1000,
             opens=time(10, 0), closes=time(11, 0))

    peak = build_bi_explore(metric="room_peak_groups", by="hour",
                            date_from=DAY, date_to=DAY)
    assert {row.key: row.value for row in peak.rows}["10"] == 4.0

    full = build_bi_explore(metric="room_full_minutes", by="hour",
                            date_from=DAY, date_to=DAY)
    assert {row.key: row.value for row in full.rows}["10"] == 60.0


@pytest.mark.django_db
def test_revenue_per_spot_hour_is_the_metric_that_answers_how_many_tables(room, tagged):
    _tab("1001", sku="CAFE", total_q=3600, opens=time(9, 0), closes=time(10, 0))
    # 4 lugares × 9 horas de expediente = 36 lugar-hora; R$ 36,00 → 100 centavos.
    report = build_bi_explore(metric="room_revenue_per_spot_hour", by="time",
                              date_from=DAY, date_to=DAY)
    assert {row.key: row.value for row in report.rows} == {DAY.isoformat(): 100.0}


@pytest.mark.django_db
def test_turns_per_spot(room, tagged):
    for index in range(8):
        _tab(f"300{index}", sku="CAFE", total_q=500,
             opens=time(9, 0), closes=time(9, 30))
    report = build_bi_explore(metric="room_turns", by="time", date_from=DAY, date_to=DAY)
    assert {row.key: row.value for row in report.rows} == {DAY.isoformat(): 2.0}


@pytest.mark.django_db
def test_tab_minutes_are_measured_not_assumed(room, tagged):
    """"Sempre abrimos comanda" é o que torna esta métrica medida."""
    _tab("1001", sku="CAFE", total_q=1000, opens=time(9, 0), closes=time(9, 40))
    _tab("1002", sku="CAFE", total_q=1000, opens=time(11, 0), closes=time(11, 20))
    report = build_bi_explore(metric="room_tab_minutes", by="time",
                              date_from=DAY, date_to=DAY)
    assert {row.key: row.value for row in report.rows} == {DAY.isoformat(): 30.0}


# ── Gramática ────────────────────────────────────────────────────────────────


def test_room_grammar():
    assert validate_config("room_minutes", "room_load", "hour").family == "room"
    # Valor por lugar-hora é do DIA: recortar por hora dividiria o faturamento
    # do dia por uma capacidade que não muda de hora em hora.
    with pytest.raises(ExploreError, match="não vale para Faturamento por lugar-hora"):
        validate_config("room_revenue_per_spot_hour", "hour", "")
    # Não existe "qual mesa rende mais": ela exigia o vínculo que foi vetado.
    with pytest.raises(ExploreError, match="Dimensão 'spot' não vale"):
        validate_config("room_turns", "spot", "")
