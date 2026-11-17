"""Vários turnos por dia: o intervalo (``breaks``) parte o dia, de ponta a ponta.

O iFood pediu na homologação do módulo Merchant (chamado 36323618, 17/11/2026):
sábado 10:00-19:00; domingo 09:00-12:00, 13:00-16:00 e 17:00-23:00. A grade da casa
guardava uma janela por dia. Agora o dia guarda ``open``/``close`` (o dia inteiro,
que produção, B.I. e cozinha seguem lendo) e ``breaks`` (as pausas), e quem promete
venda ao cliente lê os turnos: a loja, as janelas de entrega, a regra de horário e o
iFood.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings

from shopman.shop.models import Shop
from shopman.shop.services import business_calendar, ifood_merchant

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("America/Sao_Paulo")
SUNDAY = date(2026, 11, 22)
HOMOLOGACAO = {
    "saturday": {"open": "10:00", "close": "19:00"},
    "sunday": {
        "open": "09:00",
        "close": "23:00",
        "breaks": [{"start": "12:00", "end": "13:00"}, {"start": "16:00", "end": "17:00"}],
    },
}


@pytest.fixture
def shop():
    return Shop.objects.create(name="Nelson", timezone="America/Sao_Paulo", opening_hours=HOMOLOGACAO)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(SUNDAY, time(hour, minute), tzinfo=TZ)


def test_o_intervalo_parte_o_dia_em_turnos(shop):
    assert business_calendar.shifts_for(SUNDAY, shop=shop) == [
        (time(9), time(12)),
        (time(13), time(16)),
        (time(17), time(23)),
    ]
    # O dia inteiro continua sendo o par de sempre (quem lê o dia não muda).
    assert business_calendar.selling_hours_for(SUNDAY, shop=shop) == (time(9), time(23))


def test_no_intervalo_a_loja_esta_fechada_e_diz_quando_volta(shop):
    state = business_calendar.current_business_state(now=_at(12, 30), shop=shop)

    assert state.is_open is False
    assert state.closure_source == "break"
    assert state.message == "Fechado. Voltamos às 13h"
    assert state.next_open_at == _at(13)


def test_aberta_no_turno_fecha_no_fim_do_turno(shop):
    state = business_calendar.current_business_state(now=_at(10), shop=shop)

    assert state.is_open is True
    assert state.message == "Aberto até 12h"
    assert state.closes_at == "12:00"


def test_prazo_de_loja_aberta_pula_o_intervalo(shop):
    deadline, _ = business_calendar.next_operational_deadline(timeout=timedelta(minutes=60), now=_at(11, 30), shop=shop)

    # 30 min até as 12h, o resto depois da volta às 13h.
    assert deadline == _at(13, 30)


def test_janela_de_entrega_nao_cai_no_intervalo(shop):
    refs = [slot["ref"] for slot in business_calendar.delivery_slots_for(SUNDAY, now=_at(6), shop=shop)]

    assert "11:30-12:00" in refs
    assert "12:00-12:30" not in refs
    assert "12:30-13:00" not in refs
    assert "13:00-13:30" in refs
    assert "16:30-17:00" not in refs


def test_intervalo_fora_do_dia_e_ignorado_sem_inventar_turno():
    entry = {"open": "09:00", "close": "18:00", "breaks": [{"start": "08:00", "end": "10:00"}]}

    assert business_calendar.entry_shifts(entry) == [(time(9), time(18))]


def test_a_frase_do_dia_lista_os_turnos():
    assert business_calendar.format_shifts(business_calendar.entry_shifts(HOMOLOGACAO["sunday"])) == (
        "9h às 12h, 13h às 16h e 17h às 23h"
    )


def test_regra_de_horario_marca_o_intervalo_como_fora_do_horario(shop, monkeypatch):
    from shopman.shop.rules.validation import BusinessHoursRule

    monkeypatch.setattr("django.utils.timezone.localtime", lambda *a, **k: _at(12, 30))
    assert BusinessHoursRule()._check_outside_hours() is True
    monkeypatch.setattr("django.utils.timezone.localtime", lambda *a, **k: _at(13, 30))
    assert BusinessHoursRule()._check_outside_hours() is False


@override_settings(SHOPMAN_IFOOD={"client_id": "c", "merchant_id": "m", "merchant_sync_enabled": True})
def test_o_ifood_recebe_um_turno_por_turno_da_casa(shop):
    shifts = ifood_merchant.desired_shifts(shop)

    assert sorted((s["dayOfWeek"], s["start"], s["duration"]) for s in shifts) == [
        ("SATURDAY", "10:00:00", 540),
        ("SUNDAY", "09:00:00", 180),
        ("SUNDAY", "13:00:00", 180),
        ("SUNDAY", "17:00:00", 360),
    ]


def test_a_loja_mostra_os_turnos_do_domingo(shop):
    from shopman.storefront.presentation.shop_status import _format_opening_hours

    lines = {line["label"]: line["hours"] for line in _format_opening_hours()}

    assert lines["Domingo"] == "9h às 12h, 13h às 16h e 17h às 23h"
    assert lines["Sábado"] == "10h às 19h"


def test_schema_org_tem_uma_especificacao_por_turno():
    from shopman.storefront.presentation.site import build_opening_hours

    specs = {(s.opens, s.closes): s.days for s in build_opening_hours(HOMOLOGACAO)}

    assert specs[("09:00", "12:00")] == ("Sunday",)
    assert specs[("17:00", "23:00")] == ("Sunday",)
    assert specs[("10:00", "19:00")] == ("Saturday",)


# ── Admin: o formulário guarda e recusa ───────────────────────────────────────


def _parse(raw, opens="09:00", closes="23:00"):
    from shopman.shop.admin.shop import _parse_breaks

    return _parse_breaks(raw, opens_at=time.fromisoformat(opens), closes_at=time.fromisoformat(closes), label="Domingo")


def test_admin_le_os_intervalos_em_ordem():
    assert _parse("16:00-17:00, 12:00-13:00") == [
        {"start": "12:00", "end": "13:00"},
        {"start": "16:00", "end": "17:00"},
    ]
    assert _parse("") == []


@pytest.mark.parametrize(
    ("raw", "trecho"),
    [
        ("12h-13h", "formato"),
        ("13:00-12:00", "termina antes"),
        ("08:00-10:00", "dentro do horário"),
        ("22:00-23:00", "dentro do horário"),
        ("12:00-14:00, 13:00-15:00", "sobrepõem"),
    ],
)
def test_admin_recusa_intervalo_que_nao_forma_turno(raw, trecho):
    from django import forms

    with pytest.raises(forms.ValidationError) as caught:
        _parse(raw)
    assert trecho in caught.value.messages[0]
