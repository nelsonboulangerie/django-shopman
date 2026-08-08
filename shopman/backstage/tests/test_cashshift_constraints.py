"""Os invariantes do turno de caixa, exercidos direto no banco.

Este arquivo substitui `test_cashshift_migration.py`, que exercitava uma data
migration histórica (`0008_cashshift_posterminal`) convertendo `CashRegisterSession`
legado em `CashShift` + `POSTerminal`. Com o reset de migrações não há migração nem
dado legado — mas o que aquele teste realmente protegia continua valendo: **um turno
aberto por operador, um turno aberto por terminal**, e valores não-negativos.

Testar a constraint é melhor do que testar a migração que a respeitava: a migração
rodou uma vez, a constraint vale para sempre. Antes o invariante só tinha cobertura
indireta, através de um evento que não se repete.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.backstage.models import CashShift, POSTerminal


@pytest.fixture
def terminals(db):
    return (
        POSTerminal.objects.create(ref="pdv-1", label="Balcão 1"),
        POSTerminal.objects.create(ref="pdv-2", label="Balcão 2"),
    )


@pytest.fixture
def operators(db):
    return (
        User.objects.create(username="caixa-1", is_staff=True),
        User.objects.create(username="caixa-2", is_staff=True),
    )


def _open(operator, terminal):
    return CashShift.objects.create(
        operator=operator,
        terminal=terminal,
        opened_at=timezone.now(),
        status="open",
        opening_amount_q=0,
    )


def test_operator_cannot_hold_two_open_shifts(operators, terminals):
    """Um operador não fica com dois turnos abertos — nem em terminais diferentes."""
    _open(operators[0], terminals[0])
    with pytest.raises(IntegrityError), transaction.atomic():
        _open(operators[0], terminals[1])


def test_terminal_cannot_host_two_open_shifts(operators, terminals):
    """Um terminal não hospeda dois turnos abertos — nem de operadores diferentes."""
    _open(operators[0], terminals[0])
    with pytest.raises(IntegrityError), transaction.atomic():
        _open(operators[1], terminals[0])


def test_two_operators_on_two_terminals_coexist(operators, terminals):
    """O caso legítimo que a constraint NÃO pode bloquear: dois balcões abertos."""
    _open(operators[0], terminals[0])
    _open(operators[1], terminals[1])
    assert CashShift.objects.filter(status="open").count() == 2


def test_closing_frees_the_operator_and_the_terminal(operators, terminals):
    """A unicidade é parcial (`status="open"`): fechado não ocupa o lugar."""
    shift = _open(operators[0], terminals[0])
    shift.status = "closed"
    shift.closed_at = timezone.now()
    shift.save(update_fields=["status", "closed_at"])

    reopened = _open(operators[0], terminals[0])
    assert reopened.pk != shift.pk
    assert CashShift.objects.filter(status="open").count() == 1


def test_opening_amount_cannot_be_negative(operators, terminals):
    with pytest.raises(IntegrityError), transaction.atomic():
        CashShift.objects.create(
            operator=operators[0],
            terminal=terminals[0],
            opened_at=timezone.now(),
            status="open",
            opening_amount_q=-1,
        )
