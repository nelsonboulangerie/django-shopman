"""Validação do horário de retirada no servidor (``validate_pickup_slot_selection``).

É a função que o checkout da loja chama (``storefront/api/views.py``) quando o
recebimento é retirada. Cobre:
- Slot inexistente → erro
- Slot passado hoje → erro
- Slot futuro hoje → OK
- Data futura → qualquer slot válido → OK
- Slot vazio → erro
"""

from __future__ import annotations

from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase

from shopman.storefront.services.pickup_slots import validate_pickup_slot_selection

FAKE_SLOTS = [
    {"ref": "slot-09", "label": "A partir das 9h", "starts_at": "09:00"},
    {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
    {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
]


def _today_str() -> str:
    return date.today().isoformat()


def _future_date_str() -> str:
    return (date.today() + timedelta(days=2)).isoformat()


def _validate(slot_ref: str, delivery_date: str, *, cart_skus, now) -> dict:
    error = validate_pickup_slot_selection(
        slot_ref, delivery_date=delivery_date, cart_skus=cart_skus, now=now,
    )
    return {"delivery_time_slot": error} if error else {}


class TestValidateSlot(TestCase):
    def _call(
        self,
        slot_ref: str,
        delivery_date: str = "",
        *,
        cart_skus: list[str] | None = None,
    ) -> dict:
        with patch("shopman.storefront.services.pickup_slots.get_slots", return_value=FAKE_SLOTS):
            return _validate(slot_ref, delivery_date, cart_skus=cart_skus, now=None)

    def _call_at_hour(
        self,
        slot_ref: str,
        delivery_date: str,
        hour: int,
        *,
        cart_skus: list[str] | None = None,
    ) -> dict:
        with patch("shopman.storefront.services.pickup_slots.get_slots", return_value=FAKE_SLOTS):
            return _validate(slot_ref, delivery_date, cart_skus=cart_skus, now=time(hour, 0))

    # ── Slot inexistente ──────────────────────────────────────────────────

    def test_slot_inexistente(self):
        errors = self._call("slot-99", _today_str())
        assert "delivery_time_slot" in errors
        assert "inválido" in errors["delivery_time_slot"].lower()

    # ── Slot passado (hoje às 15h → slot-09 e slot-12 já foram superados) ─

    def test_slot_09_passado_as_15h(self):
        errors = self._call_at_hour("slot-09", _today_str(), hour=15)
        assert "delivery_time_slot" in errors
        assert "passou" in errors["delivery_time_slot"].lower()

    def test_slot_12_passado_as_15h(self):
        errors = self._call_at_hour("slot-12", _today_str(), hour=15)
        assert "delivery_time_slot" in errors

    # ── Slot atual/futuro hoje ───────────────────────────────────────────

    def test_slot_09_atual_as_10h(self):
        errors = self._call_at_hour("slot-09", _today_str(), hour=10)
        assert errors == {}

    def test_slot_15_atual_as_15h(self):
        errors = self._call_at_hour("slot-15", _today_str(), hour=15)
        assert errors == {}

    def test_slot_15_atual_depois_das_15h(self):
        errors = self._call_at_hour("slot-15", _today_str(), hour=16)
        assert errors == {}

    def test_slot_12_futuro_as_10h(self):
        errors = self._call_at_hour("slot-12", _today_str(), hour=10)
        assert errors == {}

    def test_slot_15_futuro_as_10h(self):
        errors = self._call_at_hour("slot-15", _today_str(), hour=10)
        assert errors == {}

    # ── Data futura: qualquer slot válido é aceito ────────────────────────

    def test_slot_09_data_futura(self):
        # Even "past" slots are valid for a future date
        errors = self._call_at_hour("slot-09", _future_date_str(), hour=22)
        assert errors == {}

    def test_slot_12_data_futura(self):
        errors = self._call_at_hour("slot-12", _future_date_str(), hour=22)
        assert errors == {}

    def test_future_date_uses_sku_readiness_not_today_clock(self):
        with patch(
            "shopman.storefront.services.pickup_slots.get_earliest_slot_for_skus",
            return_value={"slot_ref": "slot-09", "ready_times": {"BREAD": "05:30"}, "bottleneck_sku": "BREAD"},
        ):
            errors = self._call_at_hour(
                "slot-09",
                _future_date_str(),
                hour=22,
                cart_skus=["BREAD"],
            )

        assert errors == {}

    def test_today_still_blocks_superseded_slot_even_when_sku_ready(self):
        with patch(
            "shopman.storefront.services.pickup_slots.get_earliest_slot_for_skus",
            return_value={"slot_ref": "slot-09", "ready_times": {"BREAD": "05:30"}, "bottleneck_sku": "BREAD"},
        ):
            errors = self._call_at_hour(
                "slot-09",
                _today_str(),
                hour=15,
                cart_skus=["BREAD"],
            )

        assert "delivery_time_slot" in errors
        assert "passou" in errors["delivery_time_slot"].lower()

    def test_future_date_blocks_slot_before_sku_ready_time(self):
        with patch(
            "shopman.storefront.services.pickup_slots.get_earliest_slot_for_skus",
            return_value={
                "slot_ref": "slot-15",
                "ready_times": {"BRIGADEIRO": "13:30"},
                "bottleneck_sku": "BRIGADEIRO",
            },
        ):
            errors = self._call_at_hour(
                "slot-09",
                _future_date_str(),
                hour=10,
                cart_skus=["BRIGADEIRO"],
            )

        assert "delivery_time_slot" in errors
        assert "preparo" in errors["delivery_time_slot"].lower()

    # ── Slot vazio + pickup → exige seleção ──────────────────────────────

    def test_slot_vazio_pickup(self):
        errors = self._call("", _today_str())
        assert "delivery_time_slot" in errors
        assert "horário" in errors["delivery_time_slot"].lower()

    def test_slot_vazio_pickup_sem_data(self):
        errors = self._call("", "")
        assert "delivery_time_slot" in errors
