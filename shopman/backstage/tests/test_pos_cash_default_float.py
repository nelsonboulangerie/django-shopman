"""Sugestão fixa de fundo de troco na abertura guiada do caixa.

A antesala conduz a abertura: foco no valor, Enter abre, e o placeholder
sugere o fundo de troco que o GESTOR configurou no terminal
(``Terminal.metadata["default_float_q"]``, centavos — mesmo idioma do
``auto_lock_seconds``).

⚠️ O que este arquivo protege: a sugestão é ESCOLHA do gestor, nunca leitura
da gaveta. Se algum dia ela passar a derivar do contado/esperado de turnos, o
regime de contagem cega vaza pela porta da abertura — o operador veria no
placeholder o eco do que contou ontem.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal

from shopman.backstage.projections.pos import build_pos

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator():
    return get_user_model().objects.create_user(username="marina", password="x", is_staff=True)


def _shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def test_default_float_reads_terminal_config(operator):
    _shop()
    terminal = Terminal.default()
    terminal.metadata["default_float_q"] = 20000
    terminal.save(update_fields=["metadata"])

    runtime = build_pos(terminal=terminal, operator=operator).cash_runtime

    assert runtime.default_float_q == 20000
    assert runtime.default_float_display == "R$ 200,00"


def test_default_float_absent_means_no_suggestion(operator):
    _shop()
    runtime = build_pos(terminal=Terminal.default(), operator=operator).cash_runtime

    assert runtime.default_float_q == 0
    assert runtime.default_float_display == ""


def test_default_float_illegible_config_falls_back_to_zero(operator):
    """Config ilegível vale 0 — a antesala segue pedindo o valor digitado."""
    _shop()
    terminal = Terminal.default()
    terminal.metadata["default_float_q"] = "duzentos"
    terminal.save(update_fields=["metadata"])

    runtime = build_pos(terminal=terminal, operator=operator).cash_runtime

    assert runtime.default_float_q == 0
    assert runtime.default_float_display == ""


def test_default_float_survives_open_shift(operator):
    """Com turno aberto a sugestão continua a mesma: é config, não leitura."""
    _shop()
    terminal = Terminal.default()
    terminal.metadata["default_float_q"] = 15000
    terminal.save(update_fields=["metadata"])
    cash.open_shift(operator=operator, float_q=10000)

    runtime = build_pos(terminal=terminal, operator=operator).cash_runtime

    assert runtime.has_open_shift is True
    assert runtime.default_float_q == 15000
    assert runtime.default_float_display == "R$ 150,00"
