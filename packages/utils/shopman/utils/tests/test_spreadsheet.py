"""Tests for shopman.utils.spreadsheet."""

from shopman.utils.spreadsheet import escape_cell, is_plain_number, needs_escape, unescape_cell


class TestNeedsEscape:
    """needs_escape() decide o que uma planilha leria como fórmula."""

    def test_empty_is_safe(self):
        assert needs_escape("") is False

    def test_formula_leads_are_dangerous(self):
        for lead in ("=1+1", "@SUM(A1)", "\tcmd", "\rcmd", "\ncmd"):
            assert needs_escape(lead) is True

    def test_plain_text_is_safe(self):
        assert needs_escape("Pão francês") is False

    def test_sign_followed_by_non_number_is_dangerous(self):
        assert needs_escape("-2+cmd()") is True
        assert needs_escape("+cmd") is True


class TestIsPlainNumber:
    """Número puro em qualquer notação de planilha fica intacto."""

    def test_integers_and_dot_decimals(self):
        assert is_plain_number("-10") is True
        assert is_plain_number("+3") is True
        assert is_plain_number("-1.5") is True

    def test_comma_decimal_pt_br(self):
        assert is_plain_number("-1,5") is True

    def test_decimal_literals(self):
        assert is_plain_number("-1e5") is True
        assert is_plain_number("-.5") is True

    def test_non_numbers(self):
        assert is_plain_number("-2+3") is False
        assert is_plain_number("+NaN") is False


class TestEscapeCell:
    """escape_cell() neutraliza sem sujar dado inofensivo."""

    def test_numbers_stay_clean(self):
        assert escape_cell("-10") == "-10"
        assert escape_cell("-10.5") == "-10.5"
        assert escape_cell("-10,5") == "-10,5"

    def test_formulas_get_the_prefix(self):
        assert escape_cell("=1+1") == "'=1+1"
        assert escape_cell("-2+cmd") == "'-2+cmd"
        assert escape_cell("@SUM(A1)") == "'@SUM(A1)"

    def test_already_quoted_dangerous_text_is_escaped_again(self):
        assert escape_cell("'=literal") == "''=literal"


class TestRoundTrip:
    """unescape_cell(escape_cell(x)) == x — a bijeção do cofre."""

    def test_round_trip(self):
        for original in (
            "",
            "Pão francês",
            "-10",
            "-1,5",
            "=1+1",
            '=HYPERLINK("http://evil","x")',
            "-2+cmd",
            "'=literal",
            "'texto com aspa inofensiva",
            "\ncomeça com quebra",
        ):
            assert unescape_cell(escape_cell(original)) == original
