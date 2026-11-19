"""O estoque no cancelamento pós-baixa: o lote certo (#2604) e a perda do não retirado (WP-G11).

- Todo cancelamento: o que volta, volta ao MESMO lote de onde saiu. Entrar pela
  coordenada abria o lote do dia para o perecível, e o pão de ontem voltava à
  vitrine com a validade de hoje.
- Não retirado: a linha ``restock`` volta ao lote; a linha ``loss`` vira perda
  com motivo, no mesmo saldo; rodar de novo não escreve nada.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.stockman.models import Move, Quant

from shopman.shop.services import no_show
from shopman.shop.services import stock as stock_service
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


@pytest.fixture
def shop():
    return world.make_shop()


def _moves(quant, kind) -> list[Move]:
    return list(Move.objects.filter(quant=quant, kind=kind).order_by("pk"))


def _no_show_block(order, destinies: dict[str, str]) -> None:
    """Grava o bloco como o comando gravaria, com o destino dado por linha."""
    order.data["no_show"] = {
        "lines": [
            {
                "line_id": item.line_id, "sku": item.sku, "qty": str(item.qty),
                "destiny": destinies[item.sku], "value_q": int(item.unit_price_q * item.qty),
            }
            for item in order.items.all()
        ],
    }
    order.save(update_fields=["data", "updated_at"])


# ── #2604: todo cancelamento devolve no mesmo lote ───────────────────────────


def test_cancelled_order_returns_stock_to_the_lot_it_left(shop):
    """Produto do lote de ONTEM, cancelado hoje, volta ao lote de ontem."""
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    world.product("PAO", shelf_life_days=1)
    quant = world.lot("PAO", qty=10, produced=yesterday, expires=today)
    order = world.ready_order("LOTE-ONTEM", [("PAO", 3, 1000)])
    quant.refresh_from_db()
    assert quant.quantity == Decimal("7")

    stock_service.revert_fulfilled(order)

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")
    assert quant.batch == f"PAO-{yesterday:%Y%m%d}"
    # Nenhum saldo novo nasceu: nem o lote de hoje, nem um saldo sem lote.
    assert list(Quant.objects.filter(sku="PAO").values_list("batch", flat=True)) == [quant.batch]
    (back,) = _moves(quant, Move.Kind.RETURN)
    assert back.delta == Decimal("3")


def test_cancelled_order_return_is_not_repeated(shop):
    world.product("PAO")
    quant = world.lot("PAO", qty=10)
    order = world.ready_order("LOTE-DUAS", [("PAO", 3, 1000)])

    stock_service.revert_fulfilled(order)
    stock_service.revert_fulfilled(order)

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")
    assert len(_moves(quant, Move.Kind.RETURN)) == 1


# ── Não retirado: volta ao lote ou vira perda ────────────────────────────────


def test_restock_line_goes_back_to_its_lot_and_loss_line_becomes_waste(shop):
    world.product("CROIS")
    world.product("BOLO")
    crois = world.lot("CROIS", qty=10)
    bolo = world.lot("BOLO", qty=5)
    order = world.ready_order("NS-ESTOQUE", [("CROIS", 2, 935), ("BOLO", 1, 3000)])
    _no_show_block(order, {"CROIS": "restock", "BOLO": "loss"})

    stock_service.revert_fulfilled(order)

    crois.refresh_from_db()
    bolo.refresh_from_db()
    # O croissant voltou à venda, no lote dele.
    assert crois.quantity == Decimal("10")
    assert [move.delta for move in _moves(crois, Move.Kind.RETURN)] == [Decimal("2")]
    assert _moves(crois, Move.Kind.WASTE) == []
    # O bolo não voltou: a saída deixou de ser venda e virou perda, com motivo.
    assert bolo.quantity == Decimal("4")
    (waste,) = _moves(bolo, Move.Kind.WASTE)
    assert waste.delta == Decimal("-1")
    assert waste.reason == f"Perda: pedido não retirado ({order.ref})"
    assert waste.metadata["source"] == no_show.MOVE_SOURCE
    assert waste.metadata["order_ref"] == order.ref
    assert [move.delta for move in _moves(bolo, Move.Kind.RETURN)] == [Decimal("1")]


def test_no_show_stock_is_idempotent_even_without_the_order_mark(shop):
    world.product("CROIS")
    world.product("BOLO")
    crois = world.lot("CROIS", qty=10)
    bolo = world.lot("BOLO", qty=5)
    order = world.ready_order("NS-ESTOQUE-DUAS", [("CROIS", 2, 935), ("BOLO", 1, 3000)])
    _no_show_block(order, {"CROIS": "restock", "BOLO": "loss"})

    stock_service.revert_fulfilled(order)
    stock_service.revert_fulfilled(order)
    order.refresh_from_db()
    assert len(order.data["reverted_hold_ids"]) == 2

    # Mesmo que a marca do pedido se perca, a perda não é escrita duas vezes: o guarda é o ledger.
    bolo_hold = next(entry["hold_id"] for entry in order.data["hold_ids"] if entry["sku"] == "BOLO")
    order.data["reverted_hold_ids"] = [hid for hid in order.data["reverted_hold_ids"] if hid != bolo_hold]
    order.save(update_fields=["data", "updated_at"])
    stock_service.revert_fulfilled(order)

    crois.refresh_from_db()
    bolo.refresh_from_db()
    assert (crois.quantity, bolo.quantity) == (Decimal("10"), Decimal("4"))
    assert len(_moves(bolo, Move.Kind.WASTE)) == 1
    assert len(_moves(bolo, Move.Kind.RETURN)) == 1
    assert len(_moves(crois, Move.Kind.RETURN)) == 1


def test_stock_follows_the_line_when_the_same_sku_goes_both_ways(shop):
    """Duas reservas do mesmo SKU, só uma linha volta: volta a quantidade da linha, o resto é perda."""
    world.product("CROIS")
    quant = world.lot("CROIS", qty=10)
    order = world.ready_order("NS-ESTOQUE-MISTO", [("CROIS", 2, 935)], held=False)
    order.data["hold_ids"] = [
        world.fulfilled_hold("CROIS", 2, order_ref=order.ref),
        world.fulfilled_hold("CROIS", 3, order_ref=order.ref),
    ]
    order.data["no_show"] = {"lines": [{"line_id": "L1", "sku": "CROIS", "qty": "2", "destiny": "restock", "value_q": 1870}]}
    order.save(update_fields=["data", "updated_at"])

    first, second = (entry["hold_id"] for entry in order.data["hold_ids"])
    assert no_show.stock_plan(order) == {
        first: (Decimal("2"), Decimal("0")),
        second: (Decimal("0"), Decimal("3")),
    }

    stock_service.revert_fulfilled(order)

    quant.refresh_from_db()
    assert quant.quantity == Decimal("7")
    assert sum(move.delta for move in _moves(quant, Move.Kind.WASTE)) == Decimal("-3")


def test_made_to_order_hold_is_not_wasted_twice(shop):
    """O que a linha feita na hora gastou é insumo, e quem o acerta é o ``made_to_order``."""
    from shopman.craftsman.models import ProductionMode, Recipe

    world.product("CROQUE")
    quant = world.lot("CROQUE", qty=4)
    Recipe.objects.create(
        ref="croque-na-hora", name="Croque", output_sku="CROQUE", batch_size=Decimal("1"),
        is_active=True, production_mode=ProductionMode.MADE_TO_ORDER,
    )
    order = world.ready_order("NS-ESTOQUE-NA-HORA", [("CROQUE", 1, 2800)])
    _no_show_block(order, {"CROQUE": "loss"})

    (hold_id,) = (entry["hold_id"] for entry in order.data["hold_ids"])
    assert no_show.stock_plan(order) == {hold_id: (Decimal("1"), Decimal("0"))}

    stock_service.revert_fulfilled(order)

    quant.refresh_from_db()
    assert quant.quantity == Decimal("4")
    assert _moves(quant, Move.Kind.WASTE) == []


def test_common_cancel_has_no_plan_and_returns_everything(shop):
    world.product("CROIS")
    quant = world.lot("CROIS", qty=10)
    order = world.ready_order("CANCEL-COMUM", [("CROIS", 2, 935)])

    assert no_show.stock_plan(order) is None
    stock_service.revert_fulfilled(order)

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")
    assert not Move.objects.filter(kind=Move.Kind.WASTE).exists()


def test_the_whole_gesture_moves_the_stock_through_the_cancellation(shop, django_capture_on_commit_callbacks, monkeypatch):
    """Ponta a ponta: o comando cancela, e o ``on_cancelled`` de sempre lê o bloco."""
    today = timezone.localdate()
    world.product("CROIS")
    world.product("BRIOCHE")
    crois = world.lot("CROIS", qty=10)
    brioche = world.lot("BRIOCHE", qty=5, expires=today)
    morning, next_morning = world.at(10), world.at(8, days=1)
    monkeypatch.setattr(timezone, "now", lambda: morning)
    order = world.ready_order("NS-PONTA", [("CROIS", 2, 935), ("BRIOCHE", 1, 1200)])

    # No dia seguinte o lote do brioche venceu; o croissant (sem validade) ainda volta.
    monkeypatch.setattr(timezone, "now", lambda: next_morning)
    with django_capture_on_commit_callbacks(execute=True):
        block = no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")

    assert [(line["sku"], line["destiny"], line["reason"]) for line in block["lines"]] == [
        ("CROIS", "restock", ""),
        ("BRIOCHE", "loss", "lot_expired"),
    ]
    crois.refresh_from_db()
    brioche.refresh_from_db()
    assert (crois.quantity, brioche.quantity) == (Decimal("10"), Decimal("4"))
    (waste,) = _moves(brioche, Move.Kind.WASTE)
    assert waste.reason == f"Perda: pedido não retirado ({order.ref})"
