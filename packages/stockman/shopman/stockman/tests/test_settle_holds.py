"""
``StockPlanning.settle_holds``: a reserva acompanha o saldo planejado.

O plano de um SKU numa data pode morar em mais de um quant: o que já entrou em
produção (``batch='started'``) e o que segue só planejado. Cada reserva ancora
em UM quant, e o ``realize`` só materializa as do quant de onde o lote sai.
Quando a quantidade muda de quant e a reserva fica, ela passa a apontar para um
saldo zerado: a leitura deixa de descontá-la, e o pão vai para a prateleira sem
reserva (issue #2709, medido em 18/11/2026 com a fiação real do Craftsman).

Estes testes prendem a regra no Stockman, sem o Craftsman: o "início" aqui é o
que a ponte faz (baixa do planejado, entrada no ``started``).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.stockman import StockError, stock
from shopman.stockman.models import Hold, Quant
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.services.planning import StockPlanning, _service_order

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
STARTED = "started"


@pytest.fixture
def baguete():
    return SimpleNamespace(sku=SKU, name="Baguete", shelf_life_days=None, availability_policy="planned_ok")


def _plan(baguete, qty, day, position) -> Quant:
    return stock.plan(Decimal(str(qty)), baguete, day, position=position, reason="plano")


def _hold(baguete, qty, day, **metadata) -> Hold:
    hold_id = stock.hold(Decimal(str(qty)), baguete, target_date=day, **metadata)
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def _start(planned: Quant, qty, position) -> Quant:
    """O que a ponte do Craftsman faz no início: baixa do planejado, entra no ``started``."""
    planned.refresh_from_db()
    stock.adjust(planned, max(planned.quantity - Decimal(str(qty)), Decimal("0")), reason="entrada em produção")
    return stock.receive(
        Decimal(str(qty)), SKU, position, target_date=planned.target_date, batch=STARTED, reason="produção do lote",
    )


def _where(*holds) -> list[int | None]:
    for hold in holds:
        hold.refresh_from_db()
    return [hold.quant_id for hold in holds]


# ── A ordem de atendimento é uma só ──────────────────────────────────────────


def test_service_order_is_priority_then_fifo(baguete, producao, today):
    _plan(baguete, 30, today, producao)
    sacola = _hold(baguete, 2, today)
    pedido_tarde = _hold(baguete, 2, today, priority=0)
    pedido_urgente = _hold(baguete, 2, today, priority=-1)

    assert [h.pk for h in _service_order([sacola, pedido_tarde, pedido_urgente])] == [
        pedido_urgente.pk, pedido_tarde.pk, sacola.pk,
    ]


# ── O lote abre: as reservas vão com a quantidade ────────────────────────────


def test_holds_follow_the_quantity_when_the_lot_starts(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    encomenda = _hold(baguete, 4, today, reference="order:ENC-1")
    started = _start(planned, 10, producao)
    assert _where(encomenda) == [planned.pk], "sem reassentar, a reserva fica no saldo zerado"

    moved = StockPlanning.settle_holds([started, planned])

    assert moved == [encomenda.hold_id]
    assert _where(encomenda) == [started.pk]
    started.refresh_from_db()
    planned.refresh_from_db()
    assert (started.held, planned.held) == (Decimal("4"), Decimal("0"))


def test_settle_changes_nothing_but_the_anchor(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    encomenda = _hold(baguete, 4, today, reference="order:ENC-1", priority=0)
    before = Hold.objects.filter(pk=encomenda.pk).values("status", "quantity", "expires_at", "metadata", "target_date").get()
    started = _start(planned, 10, producao)

    StockPlanning.settle_holds([started, planned])

    after = Hold.objects.filter(pk=encomenda.pk).values("status", "quantity", "expires_at", "metadata", "target_date").get()
    assert after == before
    assert after["expires_at"] is None, "o relógio da reserva só começa no realize"


def test_realize_materializes_the_holds_that_followed_the_lot(baguete, producao, vitrine, today):
    """Ponta a ponta no Stockman: plano, reserva, início, fechamento."""
    planned = _plan(baguete, 10, today, producao)
    encomenda = _hold(baguete, 4, today, reference="order:ENC-1")
    started = _start(planned, 10, producao)
    StockPlanning.settle_holds([started, planned])

    physical = stock.realize(baguete, today, Decimal("10"), vitrine, from_position=producao, from_batch=STARTED)

    assert _where(encomenda) == [physical.pk]
    physical.refresh_from_db()
    assert (physical.quantity, physical.held) == (Decimal("10"), Decimal("4"))
    encomenda.refresh_from_db()
    assert encomenda.expires_at is not None, "materializou: o relógio começou"


def test_without_settle_realize_leaves_the_hold_behind(baguete, producao, vitrine, today):
    """O defeito, que continua sendo o resultado de quem move a quantidade e não reassenta."""
    planned = _plan(baguete, 10, today, producao)
    encomenda = _hold(baguete, 4, today, reference="order:ENC-1")
    _start(planned, 10, producao)

    physical = stock.realize(baguete, today, Decimal("10"), vitrine, from_position=producao, from_batch=STARTED)

    assert _where(encomenda) == [planned.pk]
    physical.refresh_from_db()
    assert physical.held == Decimal("0")


# ── Reserva inteira, primeiro saldo em que cabe ──────────────────────────────


def test_partial_start_takes_only_what_fits_whole(baguete, producao, today):
    """Lote de 10, entram 6: a de 4 vai com o lote; a de 6 não cabe no que sobrou do
    aberto (2) e fica no planejado, que ainda tem 4... onde também não cabe inteira."""
    planned = _plan(baguete, 10, today, producao)
    de_quatro = _hold(baguete, 4, today)
    de_seis = _hold(baguete, 6, today)
    started = _start(planned, 6, producao)

    moved = StockPlanning.settle_holds([started, planned])

    assert moved == [de_quatro.hold_id]
    assert _where(de_quatro, de_seis) == [started.pk, planned.pk]


def test_a_later_hold_that_fits_fills_the_open_lot(baguete, producao, today):
    """Primeiro saldo em que CABE: a de 8 não cabe no resto do lote aberto, a de 6 cabe."""
    planned = _plan(baguete, 20, today, producao)
    x = _hold(baguete, 4, today)
    y = _hold(baguete, 8, today)
    z = _hold(baguete, 6, today)
    started = _start(planned, 10, producao)

    StockPlanning.settle_holds([started, planned])

    assert _where(x, y, z) == [started.pk, planned.pk, started.pk]
    started.refresh_from_db()
    planned.refresh_from_db()
    assert (started.held, planned.held) == (Decimal("10"), Decimal("8"))


def test_priority_decides_who_goes_with_the_open_lot(baguete, producao, today):
    planned = _plan(baguete, 20, today, producao)
    sacola = _hold(baguete, 8, today)
    pedido = _hold(baguete, 8, today, priority=0)
    started = _start(planned, 10, producao)

    StockPlanning.settle_holds([started, planned])

    assert _where(sacola, pedido) == [planned.pk, started.pk]


def test_start_above_the_plan_carries_everything(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    a = _hold(baguete, 4, today)
    b = _hold(baguete, 6, today)
    started = _start(planned, 12, producao)

    StockPlanning.settle_holds([started, planned])

    assert _where(a, b) == [started.pk, started.pk]


# ── Voltar também é reassentar ───────────────────────────────────────────────


def test_open_lot_cancelled_sends_the_holds_back_to_the_plan(baguete, producao, today):
    """Dois lotes de 10; o aberto é cancelado: a reserva volta para o que segue planejado."""
    planned = _plan(baguete, 20, today, producao)
    encomenda = _hold(baguete, 4, today)
    started = _start(planned, 10, producao)
    StockPlanning.settle_holds([started, planned])
    assert _where(encomenda) == [started.pk]

    stock.adjust(started, Decimal("0"), reason="lote aberto cancelado")
    moved = StockPlanning.settle_holds([started, planned])

    assert moved == [encomenda.hold_id]
    assert _where(encomenda) == [planned.pk]


def test_plan_cancelled_moves_its_holds_to_the_open_lot(baguete, producao, today):
    """O lote aberto tem lugar: cancelar o outro não deixa a reserva sem lastro."""
    planned = _plan(baguete, 20, today, producao)
    x = _hold(baguete, 4, today)
    y = _hold(baguete, 8, today)
    started = _start(planned, 10, producao)
    StockPlanning.settle_holds([started, planned])
    assert _where(x, y) == [started.pk, planned.pk]

    planned.refresh_from_db()
    stock.adjust(planned, Decimal("0"), reason="outro lote cancelado")
    StockPlanning.settle_holds([started, planned])

    assert _where(x, y) == [started.pk, planned.pk], "8 não cabe no que resta do aberto (6): fica, sem lastro"

    y.status = HoldStatus.RELEASED
    y.save(update_fields=["status"])
    w = Hold.objects.create(
        sku=SKU, quant=planned, quantity=Decimal("5"), target_date=today, status=HoldStatus.PENDING, metadata={},
    )
    StockPlanning.settle_holds([started, planned])
    assert _where(w) == [started.pk], "5 cabe nos 6 livres do lote aberto"


def test_hold_that_fits_nowhere_stays_where_it_is(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    encomenda = _hold(baguete, 8, today)
    started = _start(planned, 10, producao)
    stock.adjust(started, Decimal("5"), reason="quebra")

    assert StockPlanning.settle_holds([started, planned]) == []
    assert _where(encomenda) == [planned.pk]


# ── Guardas ──────────────────────────────────────────────────────────────────


def test_settle_is_idempotent(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    _hold(baguete, 4, today)
    started = _start(planned, 10, producao)

    assert len(StockPlanning.settle_holds([started, planned])) == 1
    assert StockPlanning.settle_holds([started, planned]) == []


def test_released_and_expired_holds_are_left_alone(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    solta = _hold(baguete, 2, today)
    vencida = _hold(baguete, 2, today)
    stock.release(solta.hold_id)
    Hold.objects.filter(pk=vencida.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    started = _start(planned, 10, producao)

    assert StockPlanning.settle_holds([started, planned]) == []
    assert _where(solta, vencida) == [planned.pk, planned.pk]


def test_fewer_than_two_quants_is_a_no_op(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    _hold(baguete, 4, today)

    assert StockPlanning.settle_holds([planned]) == []
    assert StockPlanning.settle_holds([None, planned]) == []
    assert StockPlanning.settle_holds([planned, planned]) == []
    assert StockPlanning.settle_holds([]) == []


def test_only_planned_siblings_of_the_same_sku_and_date(baguete, producao, vitrine, today):
    planned = _plan(baguete, 10, today, producao)
    other_day = _plan(baguete, 10, today + timedelta(days=1), producao)
    other_sku = stock.plan(Decimal("10"), SimpleNamespace(sku="CROISSANT"), today, position=producao, reason="plano")
    physical = stock.receive(Decimal("10"), SKU, vitrine, reason="pronto")
    encomenda = _hold(baguete, 4, today)
    anchor = encomenda.quant_id

    for stranger in (other_day, other_sku, physical):
        with pytest.raises(StockError) as error:
            StockPlanning.settle_holds([stranger, planned])
        assert error.value.code == "INVALID_SETTLE"
    assert _where(encomenda) == [anchor]


def test_settle_is_on_the_public_facade(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    encomenda = _hold(baguete, 4, today)
    started = _start(planned, 10, producao)

    assert stock.settle_holds([started, planned]) == [encomenda.hold_id]
