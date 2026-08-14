"""
FEFO no hold — first-expired, first-out (C3 da aposentadoria do D-1).

Com a validade decidindo preço e oferta (C2), FIFO passou a ser errado:
deixaria encalhar o lote que vence hoje enquanto vende o de amanhã. O
``_find_quant_for_hold`` ordena por ``Batch.expiry_date`` (nulos por último) e
mantém ``created_at`` como desempate estável — estoque sem validade continua
no FIFO histórico. Gap A2 do VALIDITY-SHELFLIFE-REVIEW.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from shopman.stockman import stock
from shopman.stockman.models import Batch, Hold, Position, PositionKind, Quant

pytestmark = pytest.mark.django_db


@pytest.fixture
def pos(db):
    p, _ = Position.objects.get_or_create(
        ref="fefo-vitrine",
        defaults={"name": "Vitrine FEFO", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return p


@pytest.fixture
def prod():
    return SimpleNamespace(sku="FEFO-QUEIJO", name="Queijo", shelf_life_days=None)


def _lot(sku: str, ref: str, expiry: date | None, **fields) -> Batch:
    return Batch.objects.create(sku=sku, ref=ref, expiry_date=expiry, **fields)


def _held_batch(sku: str) -> str | None:
    hold = Hold.objects.filter(sku=sku).latest("pk")
    return hold.quant.batch if hold.quant else None


class TestFEFO:
    def test_earliest_expiry_wins_over_older_quant(self, prod, pos):
        """O lote que vence ANTES sai primeiro, mesmo tendo chegado depois."""
        today = date.today()
        _lot(prod.sku, "VENCE-DEPOIS", today + timedelta(days=5))
        _lot(prod.sku, "VENCE-ANTES", today + timedelta(days=1))
        # Ordem de chegada: o lote de vida longa entra PRIMEIRO (FIFO o
        # escolheria); o curto entra depois.
        stock.receive(Decimal("10"), prod.sku, pos, batch="VENCE-DEPOIS", reason="fornada 1")
        stock.receive(Decimal("10"), prod.sku, pos, batch="VENCE-ANTES", reason="fornada 2")

        stock.hold(Decimal("3"), prod, target_date=today)

        assert _held_batch(prod.sku) == "VENCE-ANTES"

    def test_dated_lot_beats_undated(self, prod, pos):
        """Lote sem validade (e quant sem lote) vai para o FIM da fila."""
        today = date.today()
        _lot(prod.sku, "SEM-VALIDADE", None)
        _lot(prod.sku, "DATADO", today + timedelta(days=3))
        stock.receive(Decimal("10"), prod.sku, pos, batch="SEM-VALIDADE", reason="fornada 1")
        stock.receive(Decimal("10"), prod.sku, pos, batch="DATADO", reason="fornada 2")

        stock.hold(Decimal("2"), prod, target_date=today)

        assert _held_batch(prod.sku) == "DATADO"

    def test_without_batches_fifo_is_preserved(self, prod, pos):
        """Estoque sem lote nenhum: o desempate mantém o FIFO histórico."""
        today = date.today()
        first = stock.receive(Decimal("5"), prod.sku, pos, reason="chegada 1")
        stock.receive(Decimal("5"), prod.sku, pos, reason="chegada 2")

        stock.hold(Decimal("2"), prod, target_date=today)

        hold = Hold.objects.filter(sku=prod.sku).latest("pk")
        assert hold.quant.pk == (first.pk if isinstance(first, Quant) else hold.quant.pk)
        # O primeiro quant criado é o escolhido (created_at como desempate).
        oldest = Quant.objects.filter(sku=prod.sku).order_by("created_at").first()
        assert hold.quant.pk == oldest.pk

    def test_fefo_respects_the_conformity_gate(self, prod, pos):
        """O lote que venceria a fila mas está MARCADO não vence no canal que
        não vende não conforme — FEFO decide só entre os elegíveis (C2)."""
        today = date.today()
        _lot(
            prod.sku, "CURTO-MARCADO", today + timedelta(days=1),
            nonconformity_reason="Assou demais", nonconformity_percent=20,
        )
        _lot(prod.sku, "LONGO-OK", today + timedelta(days=5))
        stock.receive(Decimal("10"), prod.sku, pos, batch="CURTO-MARCADO", reason="fornada 1")
        stock.receive(Decimal("10"), prod.sku, pos, batch="LONGO-OK", reason="fornada 2")

        stock.hold(Decimal("2"), prod, target_date=today, include_nonconforming=False)

        assert _held_batch(prod.sku) == "LONGO-OK"
