"""MoneyReaisField: reais na tela, centavos no banco (beta test 05/11/2026, ADM-09)."""

from __future__ import annotations

import pytest
from django import forms

from shopman.utils.contrib.admin_unfold.money import MoneyReaisField, parse_reais


class _PriceForm(forms.Form):
    price_q = MoneyReaisField(label="Preço")


@pytest.mark.parametrize(
    ("typed", "expected_q"),
    [
        ("15", 1500),
        ("15,00", 1500),
        ("15,5", 1550),
        ("R$ 1.234,56", 123456),
        ("15.50", 1550),
        ("0,05", 5),
    ],
)
def test_parse_reais(typed, expected_q):
    assert parse_reais(typed) == expected_q


def test_quem_digita_15_grava_1500_e_nao_15():
    form = _PriceForm(data={"price_q": "15"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["price_q"] == 1500


def test_valor_gravado_aparece_em_reais():
    form = _PriceForm(initial={"price_q": 1500})
    assert 'value="15,00"' in str(form["price_q"])


@pytest.mark.parametrize("typed", ["quinze", "1,2,3", "-1"])
def test_valor_invalido_ou_negativo_e_recusado(typed):
    form = _PriceForm(data={"price_q": typed})
    assert not form.is_valid()
    assert "price_q" in form.errors
