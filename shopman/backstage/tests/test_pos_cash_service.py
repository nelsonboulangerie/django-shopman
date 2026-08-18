"""Serviço de caixa do PDV sobre o ``cashman``: o balcão fala, o livro grava."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift, Terminal

from shopman.backstage.services import pos
from shopman.backstage.services.exceptions import POSError


@pytest.fixture
def operator(db):
    return User.objects.create_user(username="cash-service", password="x", is_staff=True)


@pytest.fixture
def manager(db):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from shopman.doorman.models import PinCredential

    user = User.objects.create_user(username="cash-manager", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="adjust_shift"))
    PinCredential.set_for(user, "4321")
    return user


@pytest.fixture
def manager_approval(manager):
    """Autorização válida de gerente para as RETIRADAS de gaveta.

    Sangria exige a segunda assinatura (ver ``register_cash_movement``); os
    testes que só querem exercitar valor e tipo passam a carregar esta credencial.
    """
    return {"username": manager.username, "pin": "4321"}


def test_parse_money_to_q_accepts_common_operator_inputs():
    assert pos.parse_money_to_q("12,34") == 1234
    assert pos.parse_money_to_q("12.34") == 1234
    assert pos.parse_money_to_q("-10") == -1000
    assert pos.parse_money_to_q("") == 0


def test_parse_money_to_q_rejects_garbage_loudly():
    # Fechamento CEGO: typo virar 0 silencioso = diferença gigante sem aviso.
    with pytest.raises(POSError):
        pos.parse_money_to_q("bad")
    with pytest.raises(POSError):
        pos.parse_money_to_q("12,,30")


@pytest.mark.django_db
def test_open_cash_shift_creates_or_returns_current_shift(operator):
    shift = pos.open_cash_shift(operator=operator, opening_amount_raw="50,00")
    same = pos.open_cash_shift(operator=operator, opening_amount_raw="99,00")

    assert shift.pk == same.pk
    assert isinstance(shift, Shift)
    assert Shift.objects.count() == 1
    assert shift.terminal == Terminal.default()
    # O fundo de troco é a primeira linha do livro, não coluna do turno.
    float_in = Entry.objects.get(shift=shift, kind=Entry.Kind.FLOAT_IN)
    assert float_in.amount_q == 5000
    assert cash.balance(shift) == 5000


@pytest.mark.django_db
def test_open_cash_shift_blocks_terminal_double_open(operator):
    other = User.objects.create_user(username="other-cash", password="x", is_staff=True)
    terminal = Terminal.default()
    pos.open_cash_shift(operator=operator, terminal_ref=terminal.ref)

    with pytest.raises(POSError, match="Terminal POS já possui turno aberto"):
        pos.open_cash_shift(operator=other, terminal_ref=terminal.ref)


@pytest.mark.django_db
def test_open_cash_shift_rejects_unknown_terminal(operator):
    with pytest.raises(POSError, match="Terminal POS inválido"):
        pos.open_cash_shift(operator=operator, terminal_ref="nao-existe")


@pytest.mark.django_db
def test_register_cash_movement_requires_open_session(operator):
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos.register_cash_movement(operator=operator, amount_raw="10")


@pytest.mark.django_db
def test_register_cash_movement_validates_amount_and_normalizes_type(operator, manager, manager_approval):
    shift = cash.open_shift(operator=operator, float_q=0)

    with pytest.raises(POSError):
        pos.register_cash_movement(operator=operator, amount_raw="0", manager_approval=manager_approval)

    entry = pos.register_cash_movement(
        operator=operator,
        movement_type="unknown",
        amount_raw="25,50",
        reason="troco",
        manager_approval=manager_approval,
    )

    assert entry.shift_id == shift.pk
    # Tipo desconhecido cai em sangria (o caminho que exige gerente), e o sinal
    # vive no tipo: sangria entra NEGATIVA no livro.
    assert entry.kind == Entry.Kind.CASH_OUT
    assert entry.amount_q == -2550
    assert entry.operator == operator
    assert entry.approved_by == manager
    assert entry.reason == "troco"
    assert Entry.objects.filter(shift=shift, kind=Entry.Kind.CASH_OUT).count() == 1


@pytest.mark.django_db
def test_suprimento_enters_positive_without_manager(operator):
    shift = cash.open_shift(operator=operator, float_q=1000)
    entry = pos.register_cash_movement(operator=operator, movement_type="suprimento", amount_raw="5,00", reason="troco")

    assert entry.kind == Entry.Kind.CASH_IN
    assert entry.amount_q == 500
    assert entry.approved_by is None
    assert cash.balance(shift) == 1500


@pytest.mark.django_db
def test_sangria_requires_manager_pin(operator):
    from shopman.shop.services.pos_intent import PosIntentError

    cash.open_shift(operator=operator, float_q=1000)
    with pytest.raises(PosIntentError) as exc:
        pos.register_cash_movement(operator=operator, movement_type="sangria", amount_raw="5,00")
    assert exc.value.code == "manager_approval_required"
    assert not Entry.objects.filter(kind=Entry.Kind.CASH_OUT).exists()


@pytest.mark.django_db
def test_sangria_reduz_o_esperado(operator, manager_approval):
    shift = cash.open_shift(operator=operator, float_q=1000)
    pos.register_cash_movement(
        operator=operator, movement_type="sangria", amount_raw="5,00",
        reason="Cofre", manager_approval=manager_approval,
    )

    pos.close_cash_shift(operator=operator, closing_amount_raw="5,00")
    assert cash.expected_before_count(shift) == 500
    assert cash.difference(shift) == 0


@pytest.mark.django_db
def test_close_cash_shift_requires_open_shift(operator):
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos.close_cash_shift(operator=operator, closing_amount_raw="0")


@pytest.mark.django_db
def test_close_cash_shift_closes_and_records_count_with_notes(operator):
    cash.open_shift(operator=operator, float_q=1000)

    shift = pos.close_cash_shift(operator=operator, closing_amount_raw="10,00", notes="fim do turno")

    assert shift.status == Shift.Status.CLOSED
    count = Entry.objects.get(shift=shift, kind=Entry.Kind.COUNT)
    assert count.payload["counted_q"] == 1000
    assert count.payload["notes"] == "fim do turno"
    assert count.payload["supervisory"] is False
    assert cash.counted(shift) == 1000
    assert cash.difference(shift) == 0


@pytest.mark.django_db
def test_close_cash_shift_rejects_negative_count(operator):
    cash.open_shift(operator=operator, float_q=1000)
    with pytest.raises(POSError):
        pos.close_cash_shift(operator=operator, closing_amount_raw="-10")
    assert cash.open_shift_for(operator) is not None


@pytest.mark.django_db
def test_cash_shift_result_is_blind_to_operator(operator):
    """The operator close response never exposes the expected amount or variance."""
    from shopman.backstage.api.operations import _cash_shift_result

    shift = cash.open_shift(operator=operator, float_q=1000)
    cash.close_shift(shift, counted_q=800, actor=operator)

    # O livro ainda prova a diferença para a retaguarda...
    assert cash.expected_before_count(shift) == 1000
    assert cash.difference(shift) == -200

    # ...mas o payload do operador esconde as duas.
    result = _cash_shift_result(shift)
    assert result["opening_amount_q"] == 1000
    assert result["blind_closing_amount_q"] == 800
    assert "expected_amount_q" not in result
    assert "difference_q" not in result
    assert "balance" not in result


def test_mixed_tender_change_comes_from_cash_not_electronic():
    """Troco de venda mista sai do dinheiro — a maquininha capturou inteiro."""
    from shopman.shop.services.pos import _reconcile_tenders_to_total

    tenders = [
        {"method": "cash", "amount_q": 5000, "collection": "terminal"},
        {"method": "pix", "amount_q": 2000, "collection": "terminal"},
    ]
    _reconcile_tenders_to_total(tenders, 6000)

    assert tenders[0]["amount_q"] == 4000  # cash absorve o troco de 10
    assert tenders[1]["amount_q"] == 2000  # pix intocado


@pytest.mark.django_db
def test_close_blocking_shift_owner_can_close(operator):
    shift = pos.open_cash_shift(operator=operator, opening_amount_raw="50,00")
    closed = pos.close_blocking_shift(actor_user=operator, shift_id=shift.pk, closing_amount_raw="50,00")
    assert closed.pk == shift.pk
    assert closed.status == Shift.Status.CLOSED
    count = Entry.objects.get(shift=shift, kind=Entry.Kind.COUNT)
    assert count.payload["supervisory"] is False


@pytest.mark.django_db
def test_close_blocking_shift_manager_can_close_others(operator):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import DayClosing

    shift = pos.open_cash_shift(operator=operator, opening_amount_raw="10,00")
    manager = User.objects.create_user(username="gerente", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(DayClosing)
    manager.user_permissions.add(Permission.objects.get(content_type=ct, codename="perform_closing"))
    manager = User.objects.get(pk=manager.pk)  # refresca cache de permissão

    closed = pos.close_blocking_shift(actor_user=manager, shift_id=shift.pk, closing_amount_raw="10,00")
    assert closed.status == Shift.Status.CLOSED
    # Fechamento supervisório: quem agiu foi o gerente, e o livro diz isso.
    count = Entry.objects.get(shift=shift, kind=Entry.Kind.COUNT)
    assert count.operator == manager
    assert count.payload["supervisory"] is True


@pytest.mark.django_db
def test_close_blocking_shift_regular_operator_forbidden(operator):
    from shopman.backstage.services.exceptions import POSPermissionError

    shift = pos.open_cash_shift(operator=operator, opening_amount_raw="10,00")
    stranger = User.objects.create_user(username="qualquer", password="x", is_staff=True)

    with pytest.raises(POSPermissionError):
        pos.close_blocking_shift(actor_user=stranger, shift_id=shift.pk, closing_amount_raw="10,00")
    shift.refresh_from_db()
    assert shift.status == Shift.Status.OPEN  # nada foi fechado


@pytest.mark.django_db
def test_close_blocking_shift_unknown_shift_errors(operator):
    with pytest.raises(POSError):
        pos.close_blocking_shift(actor_user=operator, shift_id=999999, closing_amount_raw="0")
    with pytest.raises(POSError):
        pos.close_blocking_shift(actor_user=operator, shift_id="abc", closing_amount_raw="0")
