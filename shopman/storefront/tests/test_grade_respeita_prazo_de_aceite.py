"""A grade de horários não oferece o que começa antes do prazo de aceite (#3266).

No canal em que a loja aceita ou o pedido cancela (``auto_cancel``), o pedido
feito com a casa fechada tem o prazo longo, contado da abertura. A grade lia só
o expediente: às 6h, com a casa abrindo às 7h e o prazo de 3 h, oferecia
"7h às 7h30" para um pedido que a loja pode aceitar até as 10h. A cliente
chegaria antes do aceite, com o cartão ainda não cobrado.

Agora a janela que começa antes do prazo sai riscada, com a hora no motivo, na
retirada e na entrega; e o envio recusa a mesma janela (aba antiga). A régua é a
do checkout (``projections.checkout.acceptance_window``), a mesma de quem agenda
o cancelamento. Relógio parado, loja das 7h às 22h todo dia.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Channel, Shop
from shopman.storefront.services.pickup_slots import (
    acceptance_slot_error,
    annotate_delivery_windows_for_checkout,
    annotate_slots_for_checkout,
    validate_pickup_slot_selection,
)

pytestmark = pytest.mark.django_db

EVERY_DAY = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEB = "web"
PRAZO_DE_DIA = "A loja confirma o pedido até as 10h."


@pytest.fixture
def loja():
    Shop.objects.create(
        name="Test Shop",
        brand_name="Test",
        opening_hours={day: {"open": "07:00", "close": "22:00"} for day in EVERY_DAY},
    )
    return Channel.objects.create(
        ref=WEB,
        name="Loja online",
        is_active=True,
        config={"confirmation": {"mode": "auto_cancel", "timeout_minutes": 5, "preorder_timeout_minutes": 180}},
    )


def _at(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    day = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def _por_ref(slots: list[dict]) -> dict[str, dict]:
    return {slot["ref"]: slot for slot in slots}


class TestRetiradaDeHojeComACasaFechada:
    def test_o_primeiro_horario_e_depois_do_prazo(self, loja):
        ctx = annotate_slots_for_checkout([], channel_ref=WEB, now=_at(6, 0))

        slots = _por_ref(ctx["pickup_slots"])
        # A casa abre às 7h e o prazo longo (3 h) corre da abertura: até as 10h.
        assert ctx["earliest_slot_ref"] == "10:00-10:30"
        assert slots["10:00-10:30"]["is_earliest"] and slots["10:00-10:30"]["enabled"]
        for ref in ("07:00-07:30", "08:30-09:00", "09:30-10:00"):
            assert slots[ref]["enabled"] is False
            assert slots[ref]["reason"] == PRAZO_DE_DIA

    def test_sem_canal_a_grade_e_a_de_sempre(self, loja):
        ctx = annotate_slots_for_checkout([], now=_at(6, 0))

        assert ctx["earliest_slot_ref"] == "07:00-07:30"
        assert all(slot["enabled"] for slot in ctx["pickup_slots"])

    def test_o_envio_recusa_o_horario_riscado_com_o_mesmo_motivo(self, loja):
        error = validate_pickup_slot_selection("08:00-08:30", channel_ref=WEB, now=_at(6, 0))
        assert error == PRAZO_DE_DIA
        assert validate_pickup_slot_selection("10:00-10:30", channel_ref=WEB, now=_at(6, 0)) is None


class TestCasaAberta:
    def test_o_prazo_curto_cabe_na_antecedencia_e_nada_e_riscado(self, loja):
        """Às 9h10 o prazo é de 5 min (9h15); a grade já começa às 10h."""
        com_canal = annotate_slots_for_checkout([], channel_ref=WEB, now=_at(9, 10))
        sem_canal = annotate_slots_for_checkout([], now=_at(9, 10))

        assert com_canal == sem_canal
        assert com_canal["earliest_slot_ref"] == "10:00-10:30"

    def test_a_grade_lida_com_a_casa_fechada_e_enviada_com_ela_aberta_passa(self, loja):
        """O agora é o do envio: com a casa aberta o prazo é curto, e 8h às 8h30 cabe."""
        assert validate_pickup_slot_selection("08:00-08:30", channel_ref=WEB, now=_at(6, 0)) == PRAZO_DE_DIA
        assert validate_pickup_slot_selection("08:00-08:30", channel_ref=WEB, now=_at(7, 20)) is None

    def test_outro_modo_de_aceite_nao_tem_prazo_a_cortar(self, loja):
        loja.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5, "preorder_timeout_minutes": 180}}
        loja.save(update_fields=["config"])

        ctx = annotate_slots_for_checkout([], channel_ref=WEB, now=_at(6, 0))
        assert ctx["earliest_slot_ref"] == "07:00-07:30"


class TestEncomendaParaAmanha:
    def test_o_turno_que_comeca_antes_do_prazo_sai_riscado(self, loja):
        """Às 21h50, 10 min de casa aberta hoje e 170 amanhã a partir das 7h: até as 9h50."""
        amanha = (timezone.localdate() + timedelta(days=1)).isoformat()

        ctx = annotate_slots_for_checkout([], delivery_date=amanha, channel_ref=WEB, now=_at(21, 50))

        slots = _por_ref(ctx["pickup_slots"])
        assert ctx["grid"] == "canonical"
        assert slots["slot-09"]["enabled"] is False
        assert slots["slot-09"]["reason"] == "A loja confirma o pedido até as 9h50."
        assert ctx["earliest_slot_ref"] == "slot-12"

    def test_a_encomenda_com_prazo_que_cabe_hoje_nao_perde_turno(self, loja):
        """Às 15h, o prazo longo vence às 18h de hoje: amanhã inteiro fica."""
        amanha = (timezone.localdate() + timedelta(days=1)).isoformat()

        ctx = annotate_slots_for_checkout([], delivery_date=amanha, channel_ref=WEB, now=_at(15, 0))

        assert all(slot["enabled"] for slot in ctx["pickup_slots"])
        assert ctx["earliest_slot_ref"] == "slot-09"


class TestEntrega:
    def test_a_janela_de_entrega_antes_do_prazo_sai_riscada(self, loja):
        ctx = annotate_delivery_windows_for_checkout([], channel_ref=WEB, now=_at(6, 0))

        windows = _por_ref(ctx["windows"])
        assert ctx["earliest_ref"] == "10:00-10:30"
        assert windows["09:30-10:00"]["enabled"] is False
        assert windows["09:30-10:00"]["reason"] == PRAZO_DE_DIA

    def test_o_envio_da_entrega_recusa_pela_mesma_conta(self, loja):
        hoje = timezone.localdate()

        assert acceptance_slot_error(hoje, "07:30-08:00", WEB, now=_at(6, 0)) == PRAZO_DE_DIA
        assert acceptance_slot_error(hoje, "10:00-10:30", WEB, now=_at(6, 0)) is None
        assert acceptance_slot_error(hoje, "07:30-08:00", None, now=_at(6, 0)) is None
