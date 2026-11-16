"""Tests for shopman.utils.formatting."""

from datetime import UTC
from decimal import Decimal

from shopman.utils.formatting import format_quantity


class TestFormatQuantity:
    """format_quantity() with edge cases."""

    def test_none_returns_dash(self):
        assert format_quantity(None) == "-"

    def test_zero(self):
        assert format_quantity(Decimal("0")) == "0.00"

    def test_negative(self):
        assert format_quantity(Decimal("-5.5")) == "-5.50"

    def test_many_decimals_truncates(self):
        assert format_quantity(Decimal("1.23456789"), decimal_places=2) == "1.23"

    def test_many_decimals_with_custom_places(self):
        assert format_quantity(Decimal("1.23456789"), decimal_places=4) == "1.2346"

    def test_zero_decimal_places(self):
        assert format_quantity(Decimal("10.75"), decimal_places=0) == "11"

    def test_large_number(self):
        assert format_quantity(Decimal("999999.99")) == "999999.99"

    def test_very_small_number(self):
        assert format_quantity(Decimal("0.001"), decimal_places=3) == "0.001"

    def test_integer_decimal(self):
        assert format_quantity(Decimal("10")) == "10.00"

    def test_three_decimal_places(self):
        assert format_quantity(Decimal("1.955"), decimal_places=3) == "1.955"


class TestFormatLocal:
    """format_local() converte UTC para a hora da loja antes de formatar (ADM-04)."""

    def test_utc_13h_vira_10h_em_sao_paulo(self, settings):
        from datetime import datetime

        from shopman.utils.formatting import format_local

        settings.USE_TZ = True
        settings.TIME_ZONE = "America/Sao_Paulo"
        instant = datetime(2026, 11, 5, 13, 0, tzinfo=UTC)
        assert format_local(instant, "%d/%m {clock}") == "05/11 10h"
        assert format_local(instant) == "05/11/2026 10h"

    def test_none_devolve_o_vazio(self):
        from shopman.utils.formatting import format_local

        assert format_local(None) == "-"
        assert format_local(None, empty="—") == "—"


class TestFormatClock:
    """format_clock(): a hora lida por gente é "12h45" (dono, 16/11/2026)."""

    def test_hora_cheia_sem_minuto_e_sem_zero_a_esquerda(self):
        from datetime import time

        from shopman.utils.formatting import format_clock

        assert format_clock(time(12, 45)) == "12h45"
        assert format_clock(time(9, 5)) == "9h05"
        assert format_clock(time(9, 0)) == "9h"
        assert format_clock(time(0, 0)) == "0h"

    def test_instante_com_fuso_sai_na_hora_da_loja(self, settings):
        from datetime import datetime

        from shopman.utils.formatting import format_clock, format_local

        settings.USE_TZ = True
        settings.TIME_ZONE = "America/Sao_Paulo"
        instant = datetime(2026, 11, 5, 15, 45, tzinfo=UTC)
        assert format_clock(instant) == "12h45"
        assert format_local(instant, "%d/%m às {clock}") == "05/11 às 12h45"

    def test_texto_do_contrato_e_o_que_nao_se_le(self):
        from shopman.utils.formatting import format_clock

        assert format_clock("07:00") == "7h"
        assert format_clock("18:05:00") == "18h05"
        assert format_clock(None) == ""
        assert format_clock("") == ""
        assert format_clock("lixo", empty="?") == "?"
        assert format_clock("25:00") == ""
