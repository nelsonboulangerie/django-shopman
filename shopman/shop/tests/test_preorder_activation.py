"""Ativação de encomenda NA data — WP-C do AVAILABILITY-SALE-PRODUCTION-PLAN.

O lifecycle adia KDS e baixa de pedidos com ``delivery_date`` futura e agenda
a directive ``preorder.activate`` para a madrugada da data. Aqui fixamos o
comportamento do despertador (``lifecycle.activate_preorder``):

- antes da data → no-op (não dispara cozinha nem baixa);
- na data, hold materializado → baixa (fulfill) acontece;
- na data, hold de demanda ainda sem fornada → espera SEM alerta falso; a
  materialização (receiver de ``holds_materialized``) completa a baixa;
- na data, encomenda DIGITAL NÃO PAGA → nada dispara (regressão: a via
  ``holds_materialized`` levava o pedido a PREPARING, e depois a fiscal e
  loyalty, sem um centavo capturado).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.stockman.models import Hold, Position, PositionKind
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.services.holds import StockHolds
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning

from shopman.shop.lifecycle import activate_preorder
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"


@pytest.fixture(autouse=True)
def _noop_sku_validator(settings):
    from shopman.stockman.adapters.sku_validation import reset_sku_validator

    settings.STOCKMAN = {
        **getattr(settings, "STOCKMAN", {}),
        "SKU_VALIDATOR": "shopman.stockman.adapters.noop.NoopSkuValidator",
    }
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture(autouse=True)
def shop_and_channel(db):
    Shop.objects.create(name="Test Shop", brand_name="Test")
    # Pagamento no balcão: a baixa é liberada na ativação (sem passo digital).
    Channel.objects.create(
        ref="web",
        name="Loja Online",
        config={"payment": {"timing": "external", "method": "cash"}},
    )


@pytest.fixture
def tomorrow() -> date:
    return timezone.localdate() + timedelta(days=1)


def _preorder(tomorrow: date, hold: Hold | None) -> Order:
    hold_ids = []
    if hold is not None:
        hold_ids.append({"sku": SKU, "hold_id": hold.hold_id, "qty": 2.0})
    return Order.objects.create(
        ref="WEB-PRE-001",
        channel_ref="web",
        session_key="SESS-PRE",
        status=Order.Status.ACCEPTED,
        snapshot={"items": [{"line_id": "L1", "sku": SKU, "qty": 2, "unit_price_q": 1200}]},
        data={
            "delivery_date": tomorrow.isoformat(),
            "is_preorder": True,
            "hold_ids": hold_ids,
        },
        total_q=2400,
    )


class _Product:
    sku = SKU
    name = "Baguete"
    shelf_life_days = None


def _demand_hold(tomorrow: date) -> Hold:
    hold_id = StockHolds.hold(
        Decimal("2"), _Product(), tomorrow,
        allow_demand=True, reference="order:WEB-PRE-001", priority=0,
    )
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def test_activate_before_the_date_is_a_noop(tomorrow):
    hold = _demand_hold(tomorrow)
    order = _preorder(tomorrow, hold)

    activate_preorder(order)

    hold.refresh_from_db()
    assert hold.status == HoldStatus.PENDING, "antes da data nada baixa"
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED


def test_activate_on_the_date_with_demand_hold_waits_materialization(tomorrow):
    from shopman.backstage.models import OperatorAlert

    hold = _demand_hold(tomorrow)
    order = _preorder(tomorrow, hold)

    with patch("django.utils.timezone.localdate", return_value=tomorrow):
        activate_preorder(order)

    hold.refresh_from_db()
    assert hold.status in (HoldStatus.PENDING, HoldStatus.CONFIRMED), (
        "demanda sem fornada espera a materialização"
    )
    assert not OperatorAlert.objects.filter(type="stock_fulfill_failed").exists(), (
        "esperar fornada não é falha de baixa — alerta aqui seria ruído"
    )


def test_activation_on_the_day_notifies_the_customer(
    tomorrow, django_capture_on_commit_callbacks
):
    """WP-D: quando o despertador dispara o preparo na data, o cliente recebe
    o ``order_preparing`` pelo lifecycle normal (PREPARING → _on_preparing) —
    a promessa do tracking ("no dia, avisamos você quando o preparo começar")
    tem um envio real por trás, nunca só a tela."""
    hold = _demand_hold(tomorrow)
    order = _preorder(tomorrow, hold)

    with (
        patch("django.utils.timezone.localdate", return_value=tomorrow),
        patch("shopman.shop.lifecycle._dispatch_physical_work", return_value=True),
        patch("shopman.shop.services.notification.send") as send,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            activate_preorder(order)

    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    events = [call.args[1] for call in send.call_args_list]
    assert "order_preparing" in events


def test_materialization_completes_the_deferred_fulfill(
    tomorrow, django_capture_on_commit_callbacks
):
    from shopman.shop.handlers._stock_receivers import on_holds_materialized

    producao = Position.objects.create(
        ref="producao", name="Produção", kind=PositionKind.PHYSICAL, is_saleable=False
    )
    vitrine = Position.objects.create(
        ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True
    )

    hold = _demand_hold(tomorrow)
    order = _preorder(tomorrow, hold)

    with patch("django.utils.timezone.localdate", return_value=tomorrow):
        # Despertador tocou (demanda ainda flutuante — sem baixa)…
        activate_preorder(order)

        # …a fornada da data acontece e materializa a demanda…
        StockMovements.receive(
            quantity=Decimal("2"), sku=SKU, position=producao,
            target_date=tomorrow, reason="fornada do dia",
        )
        with django_capture_on_commit_callbacks(execute=True):
            StockPlanning.realize(
                _Product(), tomorrow, Decimal("2"), vitrine, from_position=producao
            )

        # …e o receiver completa a baixa do pedido (signal já executado acima,
        # mas garantimos a chamada direta para o contrato ficar explícito).
        on_holds_materialized(
            sender=None, hold_ids=[hold.hold_id], sku=SKU, target_date=tomorrow
        )

    hold.refresh_from_db()
    assert hold.quant is not None and hold.quant.target_date is None, (
        "a demanda ancorou no estoque físico na materialização"
    )
    assert hold.status == HoldStatus.FULFILLED, (
        "com pagamento de balcão e data chegada, a baixa completa na materialização"
    )
    assert hold.quant.quantity == Decimal("0"), "a venda saiu do físico"


# ══════════════════════════════════════════════════════════════════════
# Encomenda não paga não vai para a cozinha
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def pix_channel(db):
    """Canal digital com pagamento depois do commit (igual ao `web` semeado)."""
    from django.core.cache import cache

    Channel.objects.create(
        ref="web-pix",
        name="Loja Online (PIX)",
        config={
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5},
            "payment": {"method": ["pix"], "timing": "post_commit", "timeout_minutes": 10},
        },
    )
    cache.clear()
    yield
    cache.clear()


def _unpaid_pix_preorder(tomorrow: date, hold: Hold) -> Order:
    return Order.objects.create(
        ref="WEB-PRE-PIX-1",
        channel_ref="web-pix",
        session_key="SESS-PRE-PIX",
        status=Order.Status.ACCEPTED,
        snapshot={"items": [{"line_id": "L1", "sku": SKU, "qty": 2, "unit_price_q": 1200}]},
        data={
            "delivery_date": tomorrow.isoformat(),
            "is_preorder": True,
            "hold_ids": [{"sku": SKU, "hold_id": hold.hold_id, "qty": 2.0}],
            # Intent criado, nada capturado — o estado real de quem não pagou.
            "payment": {"method": "pix", "intent_ref": "PIX-INTENT-1", "status": "pending"},
        },
        total_q=2400,
    )


@pytest.mark.usefixtures("pix_channel")
def test_activate_on_the_date_blocks_unpaid_digital_preorder(tomorrow):
    """Encomenda PIX sem captura não abre ticket de KDS nem vira PREPARING."""
    from shopman.backstage.models import OperatorAlert

    hold = StockHolds.hold(
        Decimal("2"), _Product(), tomorrow,
        allow_demand=True, reference="order:WEB-PRE-PIX-1", priority=0,
    )
    hold = Hold.objects.get(pk=int(hold.split(":")[1]))
    order = _unpaid_pix_preorder(tomorrow, hold)

    with patch("django.utils.timezone.localdate", return_value=tomorrow):
        with patch("shopman.shop.lifecycle._dispatch_physical_work") as dispatch:
            activate_preorder(order)

    assert not dispatch.called, "cozinha não pode ser acionada sem pagamento"

    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED, "não pode avançar para PREPARING"

    hold.refresh_from_db()
    assert hold.status != HoldStatus.FULFILLED, "estoque não baixa sem pagamento"

    assert OperatorAlert.objects.filter(
        type="preorder_activation_blocked_unpaid"
    ).exists(), "o operador precisa saber que a encomenda travou por pagamento"


@pytest.mark.usefixtures("pix_channel")
def test_activate_on_the_date_runs_when_digital_preorder_is_paid(tomorrow):
    """Mesmo caminho, com pagamento capturado: o despertador dispara normalmente."""
    hold = StockHolds.hold(
        Decimal("2"), _Product(), tomorrow,
        allow_demand=True, reference="order:WEB-PRE-PIX-1", priority=0,
    )
    hold = Hold.objects.get(pk=int(hold.split(":")[1]))
    order = _unpaid_pix_preorder(tomorrow, hold)

    with patch("django.utils.timezone.localdate", return_value=tomorrow):
        with patch(
            "shopman.shop.lifecycle._payment_is_captured", return_value=True
        ):
            with patch("shopman.shop.lifecycle._dispatch_physical_work") as dispatch:
                activate_preorder(order)

    assert dispatch.called, "encomenda paga segue o fluxo normal"
