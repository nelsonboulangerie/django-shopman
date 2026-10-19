"""O Stockman é o dono da decisão de promessa: quem lê a decisão não a refaz.

Os testes comparam COMPORTAMENTO, não texto. Para cada cenário da matriz
(rastreado com e sem saldo, sem ledger, ``demand_ok``, pausado, peso, reserva
da própria sessão), a decisão do Stockman (``decision_from_availability`` sobre
a leitura dele), a do orquestrador (``availability.check``) e a da sacola
(``projections.cart``) têm que dar a MESMA resposta.
Uma segunda implementação da regra em qualquer uma das portas diverge em
algum cenário e quebra aqui, em qualquer arquivo e com qualquer grafia.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import PositionKind
from shopman.stockman.models import Position, Quant
from shopman.stockman.services.availability import availability_for_sku, decision_from_availability

from shopman.shop.adapters import get_adapter
from shopman.shop.models import Channel, Shop
from shopman.shop.services import availability

pytestmark = pytest.mark.django_db

SESSION = "sacola-matriz"


@dataclass(frozen=True)
class Scenario:
    name: str
    qty: str
    stock: str | None  # None = sem ledger (nenhum Quant)
    policy: str = "planned_ok"
    sellable: bool = True
    unit: str = "un"
    own_hold: str | None = None  # quanto a própria sessão já reservou
    approved: bool = True
    reason: str | None = None
    ceiling: Decimal | int | None = None  # teto desta sessão (None = sem teto finito)


MATRIX = [
    Scenario("rastreado_com_saldo", qty="2", stock="5", ceiling=5),
    Scenario("rastreado_sem_saldo", qty="6", stock="5", approved=False,
             reason="insufficient_supply", ceiling=5),
    Scenario("sem_ledger", qty="2", stock=None),
    Scenario("demand_ok_sem_saldo", qty="4", stock="0", policy="demand_ok"),
    Scenario("pausado", qty="1", stock="5", sellable=False, approved=False,
             reason="paused", ceiling=0),
    Scenario("pausado_sem_ledger", qty="1", stock=None, sellable=False, approved=False,
             reason="paused", ceiling=0),
    Scenario("peso_cabe", qty="1.2", stock="1.5", unit="kg", ceiling=Decimal("1.5")),
    Scenario("peso_nao_cabe", qty="1.6", stock="1.5", unit="kg", approved=False,
             reason="insufficient_supply", ceiling=Decimal("1.5")),
    Scenario("reserva_propria_cobre", qty="3", stock="3", own_hold="3", ceiling=3),
    Scenario("reserva_propria_mais_um", qty="4", stock="3", own_hold="3", approved=False,
             reason="insufficient_supply", ceiling=3),
]


def _world(scenario: Scenario) -> str:
    Shop.objects.create(name="Casa", brand_name="Casa")
    Channel.objects.create(ref="web", name="Loja online", is_active=True)
    sku = f"MATRIZ-{scenario.name.upper()}"
    Product.objects.create(
        sku=sku,
        name=scenario.name,
        base_price_q=500,
        unit=scenario.unit,
        availability_policy=scenario.policy,
        is_published=True,
        is_sellable=True,
    )
    if scenario.stock is not None:
        vitrine, _ = Position.objects.get_or_create(
            ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
        )
        Quant.objects.create(sku=sku, position=vitrine, _quantity=Decimal(scenario.stock))
    if scenario.own_hold is not None:
        result = get_adapter("stock").create_hold(
            sku=sku, qty=Decimal(scenario.own_hold), reference=SESSION, target_date=timezone.localdate(),
        )
        assert result["success"], result
    if not scenario.sellable:
        Product.objects.filter(sku=sku).update(is_sellable=False)
    return sku


@pytest.mark.parametrize("scenario", MATRIX, ids=lambda s: s.name)
def test_every_door_gives_stockmans_answer(scenario: Scenario):
    from shopman.shop.projections import cart

    sku = _world(scenario)
    qty = Decimal(scenario.qty)
    own = Decimal(scenario.own_hold or "0")

    # Quem não é a sessão pergunta só pelo que falta a ela.
    stockman = decision_from_availability(sku, qty - own, availability_for_sku(sku))
    check = availability.check(sku, qty - own, channel_ref="web", target_date=timezone.localdate())
    readings, own_holds = cart._availability([sku], SESSION, "web")
    cart_line = cart._line_availability(sku, qty, readings[sku], own_holds)

    reason = stockman.reason_code.value if stockman.reason_code else None
    assert (stockman.approved, reason) == (scenario.approved, scenario.reason)
    assert (check["ok"], availability._reason_value(check["error_code"])) == (scenario.approved, scenario.reason)
    assert cart_line == (scenario.approved, scenario.ceiling)


def test_untracked_hold_marker_has_one_canonical_shape():
    from shopman.shop.services.stock import untracked_hold_entry

    assert untracked_hold_entry("NO-LEDGER") == {
        "sku": "NO-LEDGER",
        "hold_id": None,
        "qty": 0,
        "is_tracked": False,
    }


def test_untracked_hold_reader_rejects_historical_shapes():
    from shopman.shop.services.stock import is_untracked_hold_entry

    assert is_untracked_hold_entry({"is_tracked": False}) is True
    assert is_untracked_hold_entry({"is_tracked": True}) is False
    assert is_untracked_hold_entry({"untracked": True}) is False
    assert is_untracked_hold_entry({"source": "stock.untracked"}) is False
    assert is_untracked_hold_entry({"is_tracked": True, "untracked": True}) is False


def test_cached_availability_accepts_only_canonical_tracking_flag():
    from shopman.shop.services.stock import _is_untracked

    assert _is_untracked("NO-LEDGER", {"NO-LEDGER": {"is_tracked": False}}, None) is True
    assert _is_untracked("NO-LEDGER", {"NO-LEDGER": {"untracked": True}}, None) is False
    assert _is_untracked(
        "NO-LEDGER",
        {"NO-LEDGER": {"source": "stock.untracked"}},
        None,
    ) is False


def test_stockman_decision_refuses_a_reading_without_tracking_flag():
    """Dict sem ``is_tracked`` não é leitura do Stockman: falha, não adivinha."""
    with pytest.raises(KeyError):
        decision_from_availability("X", Decimal("1"), {"total_promisable": 0, "positions": []})


def test_hold_ids_reader_accepts_only_the_canonical_shape():
    from shopman.shop.services.stock import hold_pks, untracked_hold_entry

    assert hold_pks([
        {"sku": "A", "hold_id": "hold:7", "qty": 1.0},
        untracked_hold_entry("B"),
    ]) == [7]
    assert hold_pks(None) == []
    with pytest.raises(ValueError):
        hold_pks([7])
    with pytest.raises(ValueError):
        hold_pks([{"sku": "A", "hold_id": "7", "qty": 1.0}])
