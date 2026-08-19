"""Tests for shopman.utils.units — a física da unidade, tabela fechada.

O que estes testes cobram (UNIT-CONVERSION-PLAN, Fase 1): ida e volta sem
perda, precisão decimal de verdade, e **recusa** de par sem caminho — kg → un
levanta, nunca devolve palpite (ADR-024, regra R4).
"""

from decimal import Decimal

import pytest

from shopman.utils.units import (
    COUNT,
    MASS,
    VOLUME,
    UnitError,
    convert,
    dimension,
    is_known,
    known_units,
    normalize,
    same_dimension,
)


class TestNormalize:
    def test_canonical_units_pass_through(self):
        for unit in known_units():
            assert normalize(unit) == unit

    def test_liter_uppercase_is_the_same_liter(self):
        assert normalize("L") == "l"

    def test_aliases_from_the_recipe_sheet(self):
        assert normalize("un.") == "un"
        assert normalize("unit") == "un"
        assert normalize("units") == "un"
        for alias in ("lt", "lts", "liter", "liters", "litro", "litros"):
            assert normalize(alias) == "l"

    def test_case_and_whitespace_do_not_create_a_new_unit(self):
        assert normalize("  KG ") == "kg"
        assert normalize("Litros") == "l"

    def test_unknown_comes_back_as_it_went_in(self):
        # Não levanta: quem decide se recusa é o chamador.
        assert normalize("saco") == "saco"
        assert normalize("") == ""
        assert normalize(None) == ""

    def test_is_known(self):
        assert is_known("L") is True
        assert is_known("dz") is True
        assert is_known("saco") is False
        assert is_known(None) is False


class TestDimension:
    def test_three_dimensions(self):
        assert dimension("kg") == MASS
        assert dimension("mg") == MASS
        assert dimension("L") == VOLUME
        assert dimension("ml") == VOLUME
        assert dimension("un") == COUNT
        assert dimension("dz") == COUNT

    def test_unknown_has_no_dimension(self):
        assert dimension("cartela") == ""

    def test_same_dimension(self):
        assert same_dimension("kg", "g") is True
        assert same_dimension("kg", "un") is False
        assert same_dimension("cartela", "cartela") is False


class TestConvert:
    def test_mass(self):
        assert convert(Decimal("1"), "kg", "g") == Decimal("1000")
        assert convert(Decimal("0.300"), "kg", "g") == Decimal("300.000")
        assert convert(Decimal("500"), "g", "kg") == Decimal("0.5")
        assert convert(Decimal("1"), "g", "mg") == Decimal("1000")

    def test_volume(self):
        assert convert(Decimal("1"), "L", "ml") == Decimal("1000")
        assert convert(Decimal("250"), "ml", "l") == Decimal("0.25")

    def test_count(self):
        assert convert(Decimal("2"), "dz", "un") == Decimal("24")
        assert convert(Decimal("36"), "un", "dz") == Decimal("3")

    def test_identity_keeps_the_number(self):
        assert convert(Decimal("2.500"), "kg", "kg") == Decimal("2.500")

    def test_accepts_str_and_int(self):
        assert convert("1.5", "kg", "g") == Decimal("1500")
        assert convert(2, "l", "ml") == Decimal("2000")

    @pytest.mark.parametrize(
        ("quantity", "unit", "through"),
        [
            ("1", "kg", "mg"),
            ("0.001", "kg", "g"),
            ("7.125", "l", "ml"),
            ("5", "dz", "un"),
            ("123.456", "g", "mg"),
        ],
    )
    def test_round_trip_loses_nothing(self, quantity, unit, through):
        value = Decimal(quantity)
        assert convert(convert(value, unit, through), through, unit) == value

    def test_no_binary_float_drift(self):
        # 0,1 + 0,2 em float dá 0,30000000000000004; aqui a soma tem de fechar.
        total = convert(Decimal("0.1"), "kg", "g") + convert(Decimal("0.2"), "kg", "g")
        assert total == Decimal("300")

    def test_non_terminating_ratio_keeps_decimal_precision(self):
        # 1 un em dúzias não termina: o resultado é Decimal, não float.
        result = convert(Decimal("1"), "un", "dz")
        assert isinstance(result, Decimal)
        assert convert(result, "dz", "un") == Decimal("1")


class TestRefusal:
    def test_mass_to_count_raises(self):
        with pytest.raises(UnitError) as exc:
            convert(Decimal("0.300"), "kg", "un")
        assert exc.value.code == "incompatible_units"

    def test_volume_to_mass_raises(self):
        # Densidade é perfil do insumo, não física geral: aqui recusa.
        with pytest.raises(UnitError) as exc:
            convert(Decimal("1"), "l", "kg")
        assert exc.value.code == "incompatible_units"

    def test_unknown_unit_raises_and_lists_what_is_known(self):
        with pytest.raises(UnitError) as exc:
            convert(Decimal("1"), "saco", "kg")
        assert exc.value.code == "unknown_unit"
        assert "saco" in str(exc.value)
        assert "kg" in str(exc.value)

    def test_unknown_target_raises(self):
        with pytest.raises(UnitError) as exc:
            convert(Decimal("1"), "kg", "cartela")
        assert exc.value.code == "unknown_unit"

    def test_invalid_quantity_raises(self):
        with pytest.raises(UnitError) as exc:
            convert("meio quilo", "kg", "g")
        assert exc.value.code == "invalid_quantity"
