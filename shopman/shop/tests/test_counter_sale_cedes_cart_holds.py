"""O balcão sempre baixa; a reserva de carrinho cede; a de pedido não.

Antes: com as sacolas da loja online segurando todo o estoque da vitrine, a
venda de balcão (caminho otimista, ``payment.timing == "external"``) não
reservava nada — ``create_holds_up_to`` nunca reserva além do livre — e saía só
um alerta. O pão tinha saído pela porta e o sistema seguia contando com ele.

Agora a venda consumada fora cede as reservas de CARRINHO (sessão, com prazo,
sem ``order:``), as mais novas primeiro e só o que falta. Reserva de pedido não
cede; o que nem assim couber é venda acima do estoque e segue alertando.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from shopman.offerman.models import Product
from shopman.orderman.exceptions import ValidationError
from shopman.stockman import HoldStatus, PositionKind
from shopman.stockman.models import Hold, Move, Position, Quant

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import get_adapter
from shopman.shop.models import Channel
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db

SKU = "CEDE-BAGUETE"
EXTERNAL = {"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}}


def _world(stock_qty: int) -> None:
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config=EXTERNAL)
    Channel.objects.create(ref="ifood", name="iFood", is_active=True, config={
        "payment": {"method": "external", "timing": "external"}, "stock": {"check_on_commit": False},
    })
    Channel.objects.create(ref="web", name="Loja online", is_active=True)
    Product.objects.create(sku=SKU, name="Baguete", base_price_q=1000, is_published=True, is_sellable=True)
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    Quant.objects.create(sku=SKU, position=vitrine, _quantity=Decimal(str(stock_qty)))


def _hold(qty: int, reference: str) -> str:
    result = get_adapter("stock").create_hold(sku=SKU, qty=Decimal(str(qty)), reference=reference)
    assert result["success"], result
    return result["hold_id"]


def _get(hold_id: str) -> Hold:
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def _order(qty: int, *, ref: str = "BALCAO-1", channel_ref: str = "pdv", session_key=None):
    return SimpleNamespace(
        ref=ref,
        channel_ref=channel_ref,
        session_key=session_key,
        snapshot={"items": [{"sku": SKU, "qty": qty, "name": "Baguete"}]},
        data={},
        save=lambda update_fields=None: None,
    )


def _active_qty(reference: str) -> Decimal:
    return sum((h.quantity for h in Hold.objects.filter(metadata__reference=reference).active()), Decimal("0"))


def _sold() -> Decimal:
    return -sum((m.delta for m in Move.objects.filter(kind=Move.Kind.SELL)), Decimal("0"))


def test_counter_sale_takes_the_stock_carts_were_holding():
    """Carrinhos seguram tudo → o balcão reserva e baixa, sem alerta."""
    _world(stock_qty=3)
    _hold(1, "sacola-a")
    _hold(2, "sacola-b")

    order = _order(3)
    stock_service.hold(order)
    stock_service.fulfill(order)

    assert _sold() == Decimal("3")
    assert _active_qty("sacola-a") == 0
    assert _active_qty("sacola-b") == 0
    assert not OperatorAlert.objects.filter(type="stock_hold_gap").exists()
    assert {e["reference"] for e in order.data["stock_ceded_holds"]} == {"sacola-a", "sacola-b"}


def test_newest_cart_cedes_first_and_only_what_is_missing():
    """Falta 1: cede a sacola MAIS NOVA, só 1 unidade; o troco volta a ela."""
    _world(stock_qty=4)
    older = _hold(2, "sacola-antiga")
    newer = _hold(2, "sacola-nova")

    order = _order(1)
    stock_service.hold(order)
    stock_service.fulfill(order)

    assert _sold() == Decimal("1")
    # A sacola antiga não foi tocada.
    assert _get(older).status == HoldStatus.PENDING
    assert _active_qty("sacola-antiga") == Decimal("2")
    # A nova cedeu 1 e ficou com o troco, no mesmo prazo.
    ceded = _get(newer)
    assert ceded.status == HoldStatus.RELEASED
    assert ceded.metadata["ceded_to"] == "order:BALCAO-1"
    assert _active_qty("sacola-nova") == Decimal("1")
    [entry] = order.data["stock_ceded_holds"]
    assert entry["reference"] == "sacola-nova"
    assert entry["ceded_qty"] == 1
    remainder = _get(entry["remainder_hold_id"])
    assert remainder.expires_at == ceded.expires_at
    assert remainder.metadata["ceded_remainder_of"] == newer


def test_order_hold_never_cedes_and_the_real_gap_alerts():
    """Reserva de pedido é compromisso: não cede. O que falta de verdade alerta."""
    _world(stock_qty=3)
    web_order_hold = _hold(2, "order:WEB-9")
    _hold(1, "sacola-a")

    order = _order(3)
    stock_service.hold(order)
    stock_service.fulfill(order)

    assert _get(web_order_hold).status == HoldStatus.PENDING
    assert _sold() == Decimal("1")  # só o que a sacola cedeu
    alert = OperatorAlert.objects.get(type="stock_hold_gap", order_ref="BALCAO-1")
    assert "2×" in alert.message


def test_web_checkout_after_the_cession_is_refused_as_sold_out():
    """A sacola que cedeu descobre no checkout: pré-checagem "esgotado" e o gate
    de commit recusa (``insufficient_stock``), sem pedido nem reserva."""
    from shopman.shop.projections.checkout import cart_stock_shortfalls

    _world(stock_qty=2)
    _hold(2, "sacola-web")

    stock_service.hold(_order(2))

    line = SimpleNamespace(line_id="L1", sku=SKU, name="Baguete", qty=2)
    shortfalls, _ = cart_stock_shortfalls(session_key="sacola-web", cart_lines=[line], channel_ref="web")
    assert [(s.sku, s.available_qty) for s in shortfalls] == [(SKU, 0)]

    web = _order(2, ref="WEB-1", channel_ref="web", session_key="sacola-web")
    with pytest.raises(ValidationError) as exc:
        stock_service.hold(web, require_all=True)
    assert exc.value.code == "insufficient_stock"


def test_checkout_that_loaded_the_cart_before_the_cession_does_not_adopt_a_dead_hold(monkeypatch):
    """A corrida: o checkout leu os holds da sacola, o balcão cedeu no meio, o
    checkout tenta adotar. O ``retag`` devolve False e o pedido web NÃO pode
    nascer com uma reserva solta (pedido pago sem baixa) — ele é recusado."""
    _world(stock_qty=2)
    cart_hold = _hold(2, "sacola-web")

    original_load = stock_service._load_session_holds

    def _load_then_counter_sells(session_key):
        loaded = original_load(session_key)
        stock_service.hold(_order(2))  # o balcão chega entre a leitura e a adoção
        return loaded

    monkeypatch.setattr(stock_service, "_load_session_holds", _load_then_counter_sells)

    web = _order(2, ref="WEB-2", channel_ref="web", session_key="sacola-web")
    with pytest.raises(ValidationError) as exc:
        stock_service.hold(web, require_all=True)
    assert exc.value.code == "insufficient_stock"
    assert _get(cart_hold).metadata["reference"] == "sacola-web"
    assert _get(cart_hold).metadata["ceded_to"] == "order:BALCAO-1"


def test_checkout_that_adopted_first_keeps_its_hold():
    """A outra ordem da corrida: o checkout adotou antes (``order:``) — o balcão
    não toma a reserva do pedido e alerta."""
    _world(stock_qty=2)
    cart_hold = _hold(2, "sacola-web")
    stock_service.hold(_order(2, ref="WEB-3", channel_ref="web", session_key="sacola-web"), require_all=True)

    counter = _order(2)
    stock_service.hold(counter)

    assert _get(cart_hold).metadata["reference"] == "order:WEB-3"
    assert _get(cart_hold).status == HoldStatus.PENDING
    assert "stock_ceded_holds" not in counter.data
    assert OperatorAlert.objects.filter(type="stock_hold_gap", order_ref="BALCAO-1").exists()


def test_paid_marketplace_order_also_takes_from_carts():
    """iFood: pedido pago lá, não recusável aqui — pedido vale mais que sacola."""
    _world(stock_qty=1)
    _hold(1, "sacola-a")

    order = _order(1, ref="IFOOD-1", channel_ref="ifood")
    stock_service.hold(order)

    assert _active_qty("sacola-a") == 0
    assert sum(e["qty"] for e in order.data["hold_ids"] if e.get("hold_id")) == 1


def test_remote_channel_soft_path_does_not_touch_carts():
    """Só a venda consumada fora cede sacola alheia: canal remoto não."""
    _world(stock_qty=1)
    _hold(1, "sacola-a")

    order = _order(1, ref="WEB-SOFT", channel_ref="web")
    stock_service.hold(order)

    assert _active_qty("sacola-a") == Decimal("1")
    assert "stock_ceded_holds" not in order.data


def test_waitlist_and_manual_holds_do_not_cede():
    """Fila de fornada (sem prazo) e reserva manual (sem referência) são promessa."""
    _world(stock_qty=2)
    fila = _hold(1, "sacola-fila")
    Hold.objects.filter(pk=_get(fila).pk).update(expires_at=None)
    manual = get_adapter("stock").create_hold(sku=SKU, qty=Decimal("1"))["hold_id"]

    stock_service.hold(_order(2))

    assert _get(fila).status == HoldStatus.PENDING
    assert _get(manual).status == HoldStatus.PENDING
