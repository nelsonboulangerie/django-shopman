"""
O saldo em produção e a lista de graus do canal (#2715).

O canal que lê com lista de graus (``allowed_quality_grade_refs``, o canal
remoto) só aceita lote nomeado que tenha ``Batch`` com grau permitido. Isso é
deliberado e continua: lote nomeado sem ``Batch`` é lote não classificado, e
falha fechado.

O saldo ``batch='started'`` não é lote. É o marcador que a ponte do Craftsman
escreve no saldo PLANEJADO quando o lote entra em produção; não existe
``Batch`` com esse ref. Como o portão o tratava como lote não classificado, o
canal com lista de graus prometia o lote planejado e deixava de prometê-lo no
instante em que ele começava. Medido em 18/11/2026: lote de 10, a loja lia 8
planejado, 0 com o lote aberto, 8 fechado.

Aqui: o marcador conta como o planejado sem lote na leitura, na reserva e na
baixa; só num saldo com data; e quem decide se a reserva acompanha o pão que
sai é o ``realize``, pelo grau da inspeção.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.stockman import StockError, stock
from shopman.stockman.models import Batch, Hold, Quant
from shopman.stockman.services.availability import (
    STARTED_BATCH,
    availability_for_sku,
    availability_for_skus,
    promise_for_sku,
)
from shopman.stockman.services.scope import in_production_q, is_in_production, quants_eligible_for

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
OK_GRADES = ("excellent", "standard")


@pytest.fixture
def today():
    """Hoje pelo relógio da loja, como o Stockman conta (a fixture do pacote usa o do sistema)."""
    return timezone.localdate()


@pytest.fixture
def baguete():
    return SimpleNamespace(sku=SKU, name="Baguete", shelf_life_days=None, availability_policy="planned_ok")


def _planned(baguete, qty, day, position) -> Quant:
    return stock.plan(Decimal(str(qty)), baguete, day, position=position, reason="plano")


def _start(planned: Quant, qty, position) -> Quant:
    """O que a ponte do Craftsman faz no início: baixa do planejado, entra no ``started``."""
    planned.refresh_from_db()
    stock.adjust(planned, max(planned.quantity - Decimal(str(qty)), Decimal("0")), reason="entrada em produção")
    return stock.receive(
        Decimal(str(qty)), SKU, position, target_date=planned.target_date, batch=STARTED_BATCH,
        reason="produção do lote",
    )


def _reads(day, **scope) -> tuple[Decimal, Decimal]:
    """(leitura de um SKU, leitura em lote): as duas têm de dizer a mesma coisa."""
    one = availability_for_sku(SKU, target_date=day, **scope)["total_promisable"]
    many = availability_for_skus([SKU], target_date=day, **scope)[SKU]["total_promisable"]
    return one, many


# ── O marcador ───────────────────────────────────────────────────────────────


def test_the_marker_is_only_a_planned_balance_with_the_started_batch(baguete, producao, vitrine, today):
    planned = _planned(baguete, 10, today, producao)
    started = _start(planned, 4, producao)
    physical = Quant.objects.create(sku=SKU, position=vitrine, batch=STARTED_BATCH, _quantity=Decimal("3"))

    assert is_in_production(started) is True
    assert is_in_production(planned) is False
    assert is_in_production(physical) is False, "no físico, 'started' é só um lote nomeado sem Batch"
    assert set(Quant.objects.filter(in_production_q()).values_list("pk", flat=True)) == {started.pk}


# ── Leitura: planejado → aberto, sem cair a zero ─────────────────────────────


def test_reading_under_a_grade_list_does_not_drop_when_the_lot_starts(baguete, producao, today):
    planned = _planned(baguete, 10, today, producao)
    assert _reads(today, allowed_quality_grade_refs=OK_GRADES) == (Decimal("10"), Decimal("10"))

    started = _start(planned, 10, producao)

    assert _reads(today, allowed_quality_grade_refs=OK_GRADES) == (Decimal("10"), Decimal("10"))
    eligible = quants_eligible_for(SKU, target_date=today, allowed_quality_grade_refs=OK_GRADES)
    assert [q.pk for q in eligible] == [started.pk]
    info = availability_for_skus([SKU], target_date=today, allowed_quality_grade_refs=OK_GRADES)[SKU]
    assert info["breakdown"] == {"ready": Decimal("0"), "in_production": Decimal("10"), "planned": Decimal("0")}


def test_partial_start_counts_both_balances(baguete, producao, today):
    planned = _planned(baguete, 10, today, producao)
    _start(planned, 6, producao)

    assert _reads(today, allowed_quality_grade_refs=OK_GRADES) == (Decimal("10"), Decimal("10"))


def test_the_safety_margin_is_the_same_before_and_after_the_start(baguete, producao, today):
    """A margem desconta do que é de hoje, planejado ou em produção: 10 − 2 nos dois momentos."""
    planned = _planned(baguete, 10, today, producao)
    before = _reads(today, allowed_quality_grade_refs=OK_GRADES, safety_margin=2)

    _start(planned, 10, producao)

    assert before == (Decimal("8"), Decimal("8"))
    assert _reads(today, allowed_quality_grade_refs=OK_GRADES, safety_margin=2) == before


def test_without_a_grade_list_nothing_changes(baguete, producao, today):
    """O balcão (sem lista de graus) já contava o lote aberto, e segue contando igual."""
    planned = _planned(baguete, 10, today, producao)
    before = _reads(today)

    _start(planned, 10, producao)

    assert before == (Decimal("10"), Decimal("10"))
    assert _reads(today) == before
    assert _reads(today, include_nonconforming=False) == before


# ── A porta continua fechada para lote nomeado sem Batch ─────────────────────


def test_named_lots_without_batch_stay_out_of_the_grade_list(baguete, producao, vitrine, today):
    """Só o marcador passa. Lote nomeado sem ``Batch``, com ``Batch`` sem grau ou com
    grau fora da lista continua fora, no físico e no planejado."""
    planned = _planned(baguete, 10, today, producao)
    started = _start(planned, 10, producao)
    Batch.objects.create(sku=SKU, ref="PADRAO", quality_grade_ref="standard")
    Batch.objects.create(sku=SKU, ref="SEM-GRAU", quality_grade_ref="")
    Batch.objects.create(sku=SKU, ref="COM-DESCONTO", quality_grade_ref="fair", nonconformity_percent=20)
    ok = Quant.objects.create(sku=SKU, position=vitrine, batch="PADRAO", _quantity=Decimal("1"))
    for ref in ("SEM-GRAU", "COM-DESCONTO", "ORFAO", STARTED_BATCH):
        Quant.objects.create(sku=SKU, position=vitrine, batch=ref, _quantity=Decimal("1"))
    Quant.objects.create(sku=SKU, position=producao, target_date=today, batch="ORFAO-PLANEJADO", _quantity=Decimal("1"))

    eligible = quants_eligible_for(SKU, target_date=today, allowed_quality_grade_refs=OK_GRADES)

    assert {q.pk for q in eligible} == {started.pk, ok.pk}
    assert _reads(today, allowed_quality_grade_refs=OK_GRADES) == (Decimal("11"), Decimal("11"))
    # Sem lista de graus, tudo isso conta, como sempre.
    assert _reads(today) == (Decimal("16"), Decimal("16"))


# ── Reserva: ancora no lote aberto e segue o pão pelo grau da inspeção ───────


def _hold_with_grade_list(baguete, qty, day) -> Hold:
    hold_id = stock.hold(Decimal(str(qty)), baguete, target_date=day, allowed_quality_grade_refs=OK_GRADES)
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def test_hold_under_a_grade_list_anchors_on_the_open_lot(baguete, producao, today):
    planned = _planned(baguete, 10, today, producao)
    started = _start(planned, 10, producao)

    hold = _hold_with_grade_list(baguete, 4, today)

    assert hold.quant_id == started.pk
    assert _reads(today, allowed_quality_grade_refs=OK_GRADES) == (Decimal("6"), Decimal("6"))


def test_read_and_hold_agree_on_the_open_lot(baguete, producao, today):
    """10 no lote aberto: a promessa aprova 10 e recusa 11, e a reserva faz o mesmo."""
    planned = _planned(baguete, 10, today, producao)
    _start(planned, 10, producao)

    assert promise_for_sku(SKU, Decimal("10"), target_date=today, allowed_quality_grade_refs=OK_GRADES).approved
    assert not promise_for_sku(SKU, Decimal("11"), target_date=today, allowed_quality_grade_refs=OK_GRADES).approved
    with pytest.raises(StockError):
        _hold_with_grade_list(baguete, 11, today)
    assert _hold_with_grade_list(baguete, 10, today).quant.batch == STARTED_BATCH


def test_the_hold_reaches_the_shelf_when_the_lot_comes_out_with_an_allowed_grade(baguete, producao, vitrine, today):
    planned = _planned(baguete, 10, today, producao)
    _start(planned, 10, producao)
    hold = _hold_with_grade_list(baguete, 4, today)

    physical = stock.realize(
        baguete, today, Decimal("10"), vitrine, from_position=producao, from_batch=STARTED_BATCH,
        to_batch="BAGUETE-HOJE", to_quality_grade_ref="standard",
    )

    hold.refresh_from_db()
    assert hold.quant_id == physical.pk
    assert _reads(today, allowed_quality_grade_refs=OK_GRADES) == (Decimal("6"), Decimal("6"))


def test_the_hold_does_not_follow_bread_that_comes_out_with_a_discount_grade(baguete, producao, vitrine, today):
    """Quem decide é o ``realize``: reserva de canal com lista de graus não é levada
    para pão que saiu fora da lista. Ela fica no saldo de produção, sem lastro."""
    planned = _planned(baguete, 10, today, producao)
    started = _start(planned, 10, producao)
    hold = _hold_with_grade_list(baguete, 4, today)

    physical = stock.realize(
        baguete, today, Decimal("10"), vitrine, from_position=producao, from_batch=STARTED_BATCH,
        to_batch="BAGUETE-HOJE", to_quality_grade_ref="fair",
    )

    hold.refresh_from_db()
    physical.refresh_from_db()
    assert hold.quant_id == started.pk, "a reserva não vai para o lote com desconto"
    assert physical.held == Decimal("0")
    assert _reads(today, allowed_quality_grade_refs=OK_GRADES) == (Decimal("0"), Decimal("0"))
    assert _reads(today) == (Decimal("10"), Decimal("10")), "quem vende com desconto vê o lote inteiro"


# ── Baixa: a mesma leitura do escopo ─────────────────────────────────────────


@pytest.mark.parametrize("aberto", [False, True], ids=["planejado", "em-producao"])
def test_fulfill_reads_the_open_lot_as_it_reads_the_planned_one(baguete, producao, today, aberto):
    """A baixa não nega, por "lote sem classificação", o que a reserva aceitou.

    O resultado é o mesmo com o lote só planejado (que nunca passou pela
    conferência de grau, porque não tem lote) e com ele aberto.
    """
    planned = _planned(baguete, 10, today, producao)
    if aberto:
        _start(planned, 10, producao)
    hold = _hold_with_grade_list(baguete, 4, today)
    stock.confirm(hold.hold_id)

    stock.fulfill(hold.hold_id)

    hold.refresh_from_db()
    assert hold.status == "fulfilled"
    assert Quant.objects.get(pk=hold.quant_id).quantity == Decimal("6")


def test_fulfill_still_refuses_a_named_lot_without_batch(baguete, vitrine, today):
    Batch.objects.create(sku=SKU, ref="PADRAO", quality_grade_ref="standard")
    stock.receive(Decimal("5"), SKU, vitrine, batch="PADRAO", reason="pronto")
    hold = _hold_with_grade_list(baguete, 2, today)
    stock.confirm(hold.hold_id)
    Quant.objects.filter(pk=hold.quant_id).update(batch="ORFAO")

    with pytest.raises(StockError) as error:
        stock.fulfill(hold.hold_id)

    assert error.value.code == "INELIGIBLE_BATCH"
