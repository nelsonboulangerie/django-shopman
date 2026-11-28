"""Datas do checkout no fim do expediente (beta 06/11/2026).

Provado pela UI: às 18h, "Hoje" sumiu do seletor de data sem aviso, e às 17:54
(loja fechando às 18h) "Hoje" ainda aparecia e levava a uma lista de horários
vazia. Agora a grade de hoje (``fulfillment_window.delivery_windows_for``, a
mesma da retirada e da entrega) decide se "Hoje" entra, e ``today_over`` diz à
tela por que ele saiu. Relógio parado perto do fechamento.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Shop
from shopman.shop.projections.checkout import availability_dates

pytestmark = pytest.mark.django_db

EVERY_DAY = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _shop(open_at: str = "07:00", close_at: str = "18:00", **extra) -> Shop:
    return Shop.objects.create(
        name="Test Shop",
        brand_name="Test",
        opening_hours={day: {"open": open_at, "close": close_at} for day in EVERY_DAY},
        **extra,
    )


def _at(hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(timezone.localdate(), time(hour, minute)))


def _iso(days: int) -> str:
    return (timezone.localdate() + timedelta(days=days)).isoformat()


def test_com_horario_sobrando_hoje_e_a_primeira_data():
    _shop("07:00", "18:00")

    dates, _weekdays, today_over = availability_dates(30, now=_at(16, 0))

    assert dates == (_iso(0), _iso(1))
    assert today_over is False


def test_perto_do_fechamento_hoje_sai_e_a_tela_sabe_por_que():
    """17:54, fechando às 18h: a meia hora já não cabe. Hoje não é oferecido."""
    _shop("07:00", "18:00")

    dates, _weekdays, today_over = availability_dates(30, now=_at(17, 54))

    assert dates == (_iso(1), _iso(2))
    assert today_over is True


def test_depois_do_fechamento_hoje_sai_e_a_tela_sabe_por_que():
    """18:00 em ponto: antes "Hoje" sumia calado; agora vem ``today_over``."""
    _shop("07:00", "18:00")

    dates, _weekdays, today_over = availability_dates(30, now=_at(18, 0))

    assert dates[0] == _iso(1)
    assert today_over is True


def test_dia_em_que_a_loja_nao_abre_nao_e_hoje_encerrado():
    """Feriado hoje: "Hoje" não aparece, mas não houve expediente para encerrar."""
    _shop("07:00", "18:00", defaults={"closed_dates": [{"date": _iso(0), "label": "Feriado"}]})

    dates, _weekdays, today_over = availability_dates(30, now=_at(10, 0))

    assert dates[0] == _iso(1)
    assert today_over is False
