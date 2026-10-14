"""A grade de ENTREGA que o cliente escolhe sozinho: uma fonte, site e concierge.

Decisão do dono (14/10/2026, P2-30a): na entrega pelo site o cliente escolhe a
janela com a MESMA grade da concierge do WhatsApp (meia hora para hoje, turno
para encomenda), e o servidor confere contra ela. Antes, o site gravava sozinho
o primeiro turno de RETIRADA ("slot-09") em toda entrega, e nada conferia.

``fulfillment_window.delivery_windows_for`` é a grade; ``delivery_window_error``
é a conferência. Aqui se prova o que cada uma devolve com o relógio parado.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Shop
from shopman.shop.services import fulfillment_window
from shopman.shop.services.fulfillment_window import (
    DELIVERY_WINDOW_PASSED,
    DELIVERY_WINDOW_UNKNOWN,
    delivery_window_error,
    delivery_windows_for,
)

pytestmark = pytest.mark.django_db

EVERY_DAY = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@pytest.fixture
def loja():
    return Shop.objects.create(
        name="Test Shop",
        brand_name="Test",
        # Expediente curto de propósito: as janelas do dia cabem na asserção.
        opening_hours={day: {"open": "09:00", "close": "13:00"} for day in EVERY_DAY},
    )


def _at(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def test_hoje_e_meia_hora_cortada_pelo_relogio_e_pela_antecedencia(loja):
    today = timezone.localdate()
    now = _at(today, 10, 10)  # antecedência de 30 min: a primeira começa às 10:40 ou depois

    refs = [w["ref"] for w in delivery_windows_for(today, now=now)]

    assert refs == ["11:00-11:30", "11:30-12:00", "12:00-12:30", "12:30-13:00"]
    assert delivery_windows_for(today, now=now)[0]["label"] == "11:00 às 11:30"


def test_encomenda_e_turno_da_casa_dentro_do_expediente(loja):
    tomorrow = timezone.localdate() + timedelta(days=1)

    windows = delivery_windows_for(tomorrow, now=_at(timezone.localdate(), 10))

    # O turno das 15h não cabe numa loja que fecha às 13h.
    assert windows == [
        {"ref": "slot-09", "label": "A partir das 9h"},
        {"ref": "slot-12", "label": "A partir das 12h"},
    ]


def test_conferencia_aceita_so_o_que_a_grade_oferece(loja):
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    now = _at(today, 10, 10)

    assert delivery_window_error(today, "11:00-11:30", now=now) is None
    assert delivery_window_error(tomorrow, "slot-12", now=now) is None
    # Em branco é "a combinar": passa, como em toda superfície.
    assert delivery_window_error(today, "", now=now) is None


def test_janela_de_hoje_que_o_relogio_ja_tirou_e_recusada_como_passada(loja):
    today = timezone.localdate()
    now = _at(today, 10, 10)

    assert delivery_window_error(today, "09:00-09:30", now=now) == DELIVERY_WINDOW_PASSED
    # Ainda não começou, mas cai dentro da antecedência mínima: também já não dá.
    assert delivery_window_error(today, "10:30-11:00", now=now) == DELIVERY_WINDOW_PASSED


def test_turno_de_retirada_ou_hora_inventada_sao_recusados(loja):
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    now = _at(today, 10, 10)

    # O que o site gravava sozinho antes: o turno de retirada numa entrega de hoje.
    assert delivery_window_error(today, "slot-09", now=now) == DELIVERY_WINDOW_UNKNOWN
    # Meia hora numa encomenda: a grade de amanhã é de turnos.
    assert delivery_window_error(tomorrow, "11:00-11:30", now=now) == DELIVERY_WINDOW_UNKNOWN
    # Hora fora do expediente, e o rótulo no lugar do ref.
    assert delivery_window_error(today, "18:00-18:30", now=now) == DELIVERY_WINDOW_UNKNOWN
    assert delivery_window_error(today, "11:00 às 11:30", now=now) == DELIVERY_WINDOW_UNKNOWN


def test_dia_fechado_nao_tem_grade(loja):
    tomorrow = timezone.localdate() + timedelta(days=1)
    loja.defaults = {**(loja.defaults or {}), "closed_dates": [{"date": tomorrow.isoformat(), "label": "Feriado"}]}
    loja.save()
    now = _at(timezone.localdate(), 10)

    assert delivery_windows_for(tomorrow, now=now) == []
    assert delivery_window_error(tomorrow, "slot-09", now=now) == DELIVERY_WINDOW_UNKNOWN


def test_a_grade_da_concierge_e_a_do_site_sao_a_mesma_funcao():
    """A concierge e a projeção do checkout leem a grade daqui, e de nenhum outro lugar."""
    from pathlib import Path

    import shopman.storefront.concierge.tools as concierge_tools
    import shopman.storefront.presentation.checkout as checkout_presentation

    concierge = Path(concierge_tools.__file__).read_text()
    assert "delivery_slots_for" not in concierge
    assert "delivery_windows_for(day)" in concierge
    assert "delivery_window_error(" in concierge
    assert "fulfillment_window.annotate(day" in Path(checkout_presentation.__file__).read_text()
    assert fulfillment_window.annotate.__module__ == fulfillment_window.delivery_windows_for.__module__
