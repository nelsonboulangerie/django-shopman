"""Horários de retirada da loja: o expediente e o agora mandam (beta 06/11/2026).

Provado pela UI: às 18:36, com a loja aberta até 22h, o único horário de
retirada era "A partir das 15h" (marcado "Mais cedo"); o pedido entrou na
Cozinha já atrasado e o PDV mostrou "Retirada hoje às 15:00". Às 17:54, com a
loja fechando às 18h, o mesmo turno deixava 6 minutos reais. A entrega, no mesmo
checkout, já oferecia meias horas do expediente.

Agora a retirada lê a MESMA grade (``fulfillment_window``): hoje, as meias horas
que ainda dão (agora + antecedência até o fechamento); encomenda, os turnos da
casa que cabem no expediente do dia. Aqui se prova com o relógio parado.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Shop
from shopman.storefront.services.pickup_slots import (
    PICKUP_SLOT_PASSED,
    PICKUP_SLOT_REQUIRED,
    PICKUP_SLOT_UNKNOWN,
    PICKUP_TODAY_OVER,
    annotate_slots_for_checkout,
    get_slots,
    validate_pickup_slot_selection,
)

pytestmark = pytest.mark.django_db

EVERY_DAY = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _shop(open_at: str = "07:00", close_at: str = "22:00") -> Shop:
    return Shop.objects.create(
        name="Test Shop",
        brand_name="Test",
        opening_hours={day: {"open": open_at, "close": close_at} for day in EVERY_DAY},
    )


def _at(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    day = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def _refs(ctx: dict) -> list[str]:
    return [slot["ref"] for slot in ctx["pickup_slots"]]


class TestGradeDeHoje:
    def test_manha_comeca_depois_de_agora_mais_a_antecedencia(self):
        _shop("07:00", "12:00")

        ctx = annotate_slots_for_checkout([], now=_at(9, 10))

        assert ctx["grid"] == "half_hour"
        assert _refs(ctx) == ["10:00-10:30", "10:30-11:00", "11:00-11:30", "11:30-12:00"]
        assert ctx["earliest_slot_ref"] == "10:00-10:30"
        first = ctx["pickup_slots"][0]
        assert first == {
            "ref": "10:00-10:30",
            "label": "10:00 às 10:30",
            "starts_at": "10:00",
            "enabled": True,
            "reason": "",
            "is_earliest": True,
        }

    def test_fim_de_tarde_nunca_oferece_um_comeco_que_ja_passou(self):
        """O caso do beta: 18:36, loja até 22h. Nada de "A partir das 15h"."""
        _shop("07:00", "22:00")

        ctx = annotate_slots_for_checkout([], now=_at(18, 36))

        assert _refs(ctx)[0] == "19:30-20:00"
        assert _refs(ctx)[-1] == "21:30-22:00"
        assert ctx["earliest_slot_ref"] == "19:30-20:00"
        assert all(slot["starts_at"] >= "19:06" for slot in ctx["pickup_slots"])
        assert not any(slot["ref"].startswith("slot-") for slot in ctx["pickup_slots"])

    def test_perto_do_fechamento_hoje_nao_tem_horario_morto(self):
        """O caso do beta: 17:54, loja fechando às 18h. Hoje fica sem horário."""
        _shop("07:00", "18:00")

        ctx = annotate_slots_for_checkout([], now=_at(17, 54))

        assert ctx["pickup_slots"] == []
        assert ctx["earliest_slot_ref"] is None

    def test_loja_fechada_hoje_nao_tem_horario(self):
        Shop.objects.create(
            name="Test Shop",
            brand_name="Test",
            opening_hours={day: {"closed": True} for day in EVERY_DAY},
        )

        ctx = annotate_slots_for_checkout([], now=_at(10))

        assert ctx["pickup_slots"] == []
        assert ctx["earliest_slot_ref"] is None

    def test_prontidao_risca_com_o_produto_e_a_hora(self):
        _shop("07:00", "18:00")
        Product.objects.create(sku="FEN", name="Fendu", base_price_q=900, metadata={"ready_from": "15:00"})

        ctx = annotate_slots_for_checkout(["FEN"], now=_at(13, 0))

        by_ref = {slot["ref"]: slot for slot in ctx["pickup_slots"]}
        assert by_ref["14:00-14:30"]["enabled"] is False
        assert by_ref["14:00-14:30"]["reason"] == "Fendu sai às 15:00."
        assert by_ref["15:00-15:30"]["enabled"] is True
        assert ctx["earliest_slot_ref"] == "15:00-15:30"

    def test_horario_passado_nao_aparece_com_o_motivo_do_produto(self):
        """Antes: às 18:36 o turno das 9h saía riscado com "Fendu sai às 15:00",
        quando o motivo real era o relógio. Agora o que passou nem aparece."""
        _shop("07:00", "22:00")
        Product.objects.create(sku="FEN", name="Fendu", base_price_q=900, metadata={"ready_from": "15:00"})

        ctx = annotate_slots_for_checkout(["FEN"], now=_at(18, 36))

        assert all(slot["enabled"] for slot in ctx["pickup_slots"])
        assert all(slot["reason"] == "" for slot in ctx["pickup_slots"])


class TestEncomenda:
    def test_outro_dia_usa_os_turnos_da_casa_dentro_do_expediente(self):
        _shop("07:00", "13:00")
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

        ctx = annotate_slots_for_checkout([], delivery_date=tomorrow, now=_at(18, 36))

        assert ctx["grid"] == "canonical"
        # O turno das 15h não cabe numa loja que fecha às 13h.
        assert _refs(ctx) == ["slot-09", "slot-12"]
        assert ctx["pickup_slots"][0]["starts_at"] == "09:00"
        assert ctx["earliest_slot_ref"] == "slot-09"

    def test_encomenda_tambem_respeita_a_prontidao(self):
        _shop("07:00", "22:00")
        Product.objects.create(sku="FEN", name="Fendu", base_price_q=900, metadata={"ready_from": "11:37"})
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

        ctx = annotate_slots_for_checkout(["FEN"], delivery_date=tomorrow, now=_at(10))

        by_ref = {slot["ref"]: slot for slot in ctx["pickup_slots"]}
        assert by_ref["slot-09"]["enabled"] is False
        assert by_ref["slot-09"]["reason"] == "Fendu sai às 11:37."
        assert ctx["earliest_slot_ref"] == "slot-12"

    def test_turnos_vem_da_configuracao_da_casa(self):
        Shop.objects.create(
            name="Test Shop",
            defaults={"pickup_slots": [{"ref": "slot-10", "label": "A partir das 10h", "starts_at": "10:00"}]},
        )

        assert get_slots() == [{"ref": "slot-10", "label": "A partir das 10h", "starts_at": "10:00"}]


class TestConferencia:
    def test_em_branco_pede_horario(self):
        _shop()
        assert validate_pickup_slot_selection("", now=_at(10)) == PICKUP_SLOT_REQUIRED

    def test_aceita_o_que_a_grade_de_hoje_oferece(self):
        _shop("07:00", "22:00")
        assert validate_pickup_slot_selection("19:30-20:00", now=_at(18, 36)) is None

    def test_recusa_o_turno_do_meio_dia_gravado_no_fim_de_tarde(self):
        """O "A partir das 15h" às 18:36 não é mais aceito para hoje."""
        _shop("07:00", "22:00")
        today = timezone.localdate().isoformat()

        assert validate_pickup_slot_selection("slot-15", delivery_date=today, now=_at(18, 36)) == PICKUP_SLOT_UNKNOWN

    def test_meia_hora_que_o_relogio_ja_tirou_e_passada(self):
        _shop("07:00", "22:00")
        assert validate_pickup_slot_selection("15:00-15:30", now=_at(18, 36)) == PICKUP_SLOT_PASSED

    def test_perto_do_fechamento_hoje_acabou(self):
        _shop("07:00", "18:00")
        assert validate_pickup_slot_selection("17:30-18:00", now=_at(17, 54)) == PICKUP_TODAY_OVER

    def test_encomenda_aceita_turno_e_recusa_meia_hora(self):
        _shop("07:00", "22:00")
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

        assert validate_pickup_slot_selection("slot-15", delivery_date=tomorrow, now=_at(18, 36)) is None
        assert (
            validate_pickup_slot_selection("19:30-20:00", delivery_date=tomorrow, now=_at(18, 36))
            == PICKUP_SLOT_UNKNOWN
        )

    def test_prontidao_fecha_a_porta(self):
        _shop("07:00", "18:00")
        Product.objects.create(sku="FEN", name="Fendu", base_price_q=900, metadata={"ready_from": "15:00"})

        error = validate_pickup_slot_selection("14:00-14:30", cart_skus=["FEN"], now=_at(13, 0))

        assert error == "Fendu sai às 15:00. Escolha 15:00 às 15:30 ou mais tarde."
        assert validate_pickup_slot_selection("15:00-15:30", cart_skus=["FEN"], now=_at(13, 0)) is None
