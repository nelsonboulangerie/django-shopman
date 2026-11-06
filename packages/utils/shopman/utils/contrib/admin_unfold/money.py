"""Campo de dinheiro do Admin: digita-se em reais, grava-se em centavos.

A convenção ``_q`` (centavos inteiros) é de ARMAZENAMENTO, não de digitação. Com o
``IntegerField`` cru na tela, quem digitava 15 publicava o produto a R$ 0,15
(beta test 05/11/2026, ADM-09). Este campo mostra "15,00", aceita "15", "15,5",
"15,50", "R$ 1.234,56" ou "15.50", e devolve 1500 para o modelo.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from unfold.widgets import UnfoldAdminTextInputWidget

from shopman.utils.monetary import format_money

#: "1.500" ou "12.345.678": ponto só como separador de milhar, sem vírgula.
_THOUSANDS_ONLY = re.compile(r"[1-9]\d{0,2}(\.\d{3})+")


def parse_reais(text: str) -> int:
    """"15,50" / "R$ 1.234,56" / "15.50" / "15" em centavos. ``ValueError`` se não for número.

    Sem vírgula, "1.500" é mil e quinhentos reais, como o gestor escreve, e não
    R$ 1,50. Mais de dois dígitos de centavos é recusado em vez de arredondado:
    "15,555" é erro de digitação, e arredondar em silêncio grava um preço que
    ninguém digitou.
    """
    cleaned = str(text).replace("R$", "").replace(" ", "").replace(" ", "").strip()
    if not cleaned:
        raise ValueError("vazio")
    if "," in cleaned:
        # Formato brasileiro: ponto separa milhar, vírgula separa os centavos.
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif _THOUSANDS_ONLY.fullmatch(cleaned):
        cleaned = cleaned.replace(".", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(cleaned) from exc
    if not amount.is_finite():
        raise ValueError(cleaned)
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(cleaned)
    return int(cents)


class MoneyReaisField(forms.Field):
    """Valor em reais na tela, centavos inteiros no ``cleaned_data``."""

    default_error_messages = {
        "invalid": "Informe o valor em reais, como 15,00.",
        "min_value": "O valor não pode ser menor que R$ %(limit)s.",
    }

    def __init__(self, *, min_value_q: int | None = 0, **kwargs):
        self.min_value_q = min_value_q
        kwargs.setdefault(
            "widget",
            UnfoldAdminTextInputWidget(attrs={"prefix": "R$", "inputmode": "decimal"}),
        )
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return format_money(value)
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        try:
            return parse_reais(value)
        except ValueError:
            raise ValidationError(self.error_messages["invalid"], code="invalid") from None

    def validate(self, value):
        super().validate(value)
        if value is not None and self.min_value_q is not None and value < self.min_value_q:
            raise ValidationError(
                self.error_messages["min_value"],
                code="min_value",
                params={"limit": format_money(self.min_value_q)},
            )

    def has_changed(self, initial, data):
        try:
            data_q = self.to_python(data)
        except ValidationError:
            return True
        return (initial if initial not in self.empty_values else None) != data_q
