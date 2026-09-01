"""Um receiver cosmético que estoura no ``finish`` não pode derrubar a fornada.

Bateria adversarial da cauda de ``production_changed`` no caminho REAL do
operador (``backstage.services.production.apply_finish``). Prova, ponta a ponta:

1. Um cosmético que estoura NÃO propaga 500 e a perna de estoque (que roda
   antes) fica correta.
2. Um cosmético que estoura ANTES do sync de pedido não o deixa órfão — o sync
   roda no mesmo ``send``, porque o cosmético não aborta mais a cadeia.

E o CONTRASTE, que precisa continuar valendo: uma falha na perna de ESTOQUE
ainda GRITA (não vira 500 silencioso nem sucesso falso).

Companheiro de ``test_finish_retry_idempotency.py`` — lá o receiver frágil é
um estranho conectado no fim (e o retry idempotente salva); aqui os receivers
frágeis são os REAIS da cauda, e a blindagem os impede de derrubar o finish.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.craftsman.signals import production_changed
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Position, PositionKind, Quant

from shopman.backstage.services import production as backstage_production
from shopman.shop.handlers import production_alerts, production_order_sync
from shopman.shop.handlers.production_order_sync import (
    ORDER_AWAITING_WO_REFS_KEY,
    WORK_ORDER_COMMITTED_ORDER_REFS_KEY,
)

pytestmark = pytest.mark.django_db

SKU = "PAO-COSMETIC"


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def recipe(db, vitrine):
    return Recipe.objects.create(
        ref="rc-cosmetic", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )


def _vitrine_qty(vitrine) -> Decimal:
    quant = Quant.objects.filter(sku=SKU, position=vitrine, target_date=None).first()
    return quant.quantity if quant else Decimal("0")


def _started_work_order(recipe):
    from django.utils import timezone

    wo = craft.plan(recipe, Decimal("40"), date=timezone.localdate())
    craft.start(wo, quantity=Decimal("40"), actor="test")
    return wo


def _blow_up_a_cosmetic_receiver(monkeypatch):
    """Faz o receiver de ALERTAS (cosmético, roda ANTES do sync de pedido) estourar."""

    def _boom(*args, **kwargs):
        raise RuntimeError("alerta cosmético estourou")

    monkeypatch.setattr(production_alerts, "ensure_late_check_scheduled", _boom)


def _active_order(ref: str, *, qty: int = 2) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status="accepted",
        total_q=1000,
        data={"target_date": date.today().isoformat()},
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-l1", sku=SKU, name=SKU,
        qty=qty, unit_price_q=500, line_total_q=1000,
    )
    return order


def test_cosmetic_receiver_failure_neither_500s_nor_corrupts_stock(recipe, vitrine, monkeypatch):
    wo = _started_work_order(recipe)
    _blow_up_a_cosmetic_receiver(monkeypatch)

    # Sem a blindagem, o alerta estourado propagaria e isto levantaria RuntimeError.
    ref, total = backstage_production.apply_finish(
        work_order_id=wo.pk, quantity="40", actor="test"
    )

    assert ref == wo.ref
    assert total == Decimal("40")
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.FINISHED
    # A perna de estoque (receiver #0, antes do cosmético) rodou e está correta.
    assert _vitrine_qty(vitrine) == Decimal("40")


def test_cosmetic_failure_before_order_sync_leaves_no_orphan(recipe, vitrine, monkeypatch):
    """Alertas (#2) estoura ANTES do sync de pedido (#3): o sync ainda roda."""
    wo = _started_work_order(recipe)

    order = _active_order("COSMETIC-ORD-1")

    _blow_up_a_cosmetic_receiver(monkeypatch)

    ref, total = backstage_production.apply_finish(
        work_order_id=wo.pk, quantity="40", actor="test"
    )
    assert ref == wo.ref  # o finish concluiu, apesar do cosmético estourado

    # O sync de pedido (posterior ao cosmético) NÃO ficou órfão: ligou os dois lados.
    order.refresh_from_db()
    wo.refresh_from_db()
    assert order.data.get("awaiting_wo_refs") == [wo.ref]
    assert wo.meta.get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) == [order.ref]


def test_stock_leg_failure_still_screams(recipe, vitrine, monkeypatch):
    """CONTRASTE: a perna de estoque não é blindada — se ela falha, o finish grita.

    Blindar isto seria o oposto do que a casa quer: insumo consumido e vitrine
    zerada não pode virar 200 OK silencioso.
    """
    from shopman.stockman.services.planning import StockPlanning

    wo = _started_work_order(recipe)

    def _boom(*args, **kwargs):
        raise RuntimeError("realize da vitrine falhou")

    monkeypatch.setattr(StockPlanning, "realize", _boom)

    # A perna de estoque re-levanta (contrib/stockman ``_realize_output_leg``), e
    # ``apply_finish`` não engole erro que não é ``CraftError``: o finish grita.
    with pytest.raises(RuntimeError, match="realize da vitrine falhou"):
        backstage_production.apply_finish(work_order_id=wo.pk, quantity="40", actor="test")

    # A falha é real: a vitrine não foi creditada (o carimbo da perna volta atrás
    # junto com a transação), então o sweeper de recuperação ainda a reconhece.
    assert _vitrine_qty(vitrine) == Decimal("0")


# ── Sync de pedido: blindado E recuperável (approach B) ──────────────────────


def test_order_sync_failure_never_aborts_the_finish(recipe, vitrine, monkeypatch):
    """O sync de pedido é cosmético: um erro nele não pode derrubar a fornada.

    Quebra o linker em CHEIO (falha no receiver de sinal E na rede de segurança):
    o finish ainda conclui e o estoque fica correto. O vínculo é o que se perde —
    e é a única coisa que pode se perder, porque o resto grita ou é recuperável.
    """
    wo = _started_work_order(recipe)
    _active_order("ORDSYNC-ORD-1")

    def _boom(*args, **kwargs):
        raise RuntimeError("sync de pedido estourou")

    monkeypatch.setattr(production_order_sync, "link_active_orders_to_work_order", _boom)

    ref, total = backstage_production.apply_finish(
        work_order_id=wo.pk, quantity="40", actor="test"
    )
    assert ref == wo.ref
    assert total == Decimal("40")
    assert _vitrine_qty(vitrine) == Decimal("40")


def test_guarded_path_rebuilds_order_links_even_without_the_signal(recipe, vitrine):
    """A rede de segurança liga o pedido mesmo quando o SINAL não roda.

    É o caso do replay idempotente: o ``finish`` devolve a WO existente ANTES do
    ``.send()``, então o receiver de sinal do sync não dispara. Aqui simulamos
    isso desconectando o receiver: o vínculo tem de nascer assim mesmo, porque
    ``_ensure_order_links_closed`` roda no caminho guardado do finish.
    """
    wo = _started_work_order(recipe)
    order = _active_order("ORDSYNC-ORD-2")

    uid = "shopman.shop.handlers.production_order_sync.link_work_order_to_orders"
    production_changed.disconnect(dispatch_uid=uid)
    try:
        ref, _ = backstage_production.apply_finish(
            work_order_id=wo.pk, quantity="40", actor="test"
        )
    finally:
        production_order_sync.connect()  # reconecta (idempotente por dispatch_uid)

    assert ref == wo.ref
    order.refresh_from_db()
    wo.refresh_from_db()
    # Só a rede de segurança pôde ter ligado — o sinal estava mudo.
    assert order.data.get(ORDER_AWAITING_WO_REFS_KEY) == [wo.ref]
    assert wo.meta.get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) == [order.ref]
