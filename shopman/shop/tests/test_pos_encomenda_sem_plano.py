"""PDV: encomenda para data ainda sem lote planejado vira pedido à Produção (WP-E3).

P1-1 do EXCELENCIA-PDV-PLANO. Com a data a dez dias, a grade bloqueava trinta e
cinco pães da casa como "Sem saldo para 26/11", e o toque só repetia a frase. A
régua do Stockman responde zero por dois motivos, e a grade não os separava:

- **plano esgotado**: a data tem lote planejado e ele acabou. Segue bloqueado, e
  acima do plano só o gerente libera (WP-E2, D-041);
- **sem plano**: a data ainda não tem lote planejado do item. Decisão do dono (D2):
  a encomenda entra como pedido à Produção, e a tela diz isso.

Só o que a casa produz em lote vira pedido à Produção. Revenda e "Na hora" não têm
lote planejado, e o zero deles é falta de verdade.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from shopman.craftsman.models import ProductionMode, Recipe
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind

from shopman.backstage.projections.pos import build_pos_schedule
from shopman.shop.services import pos as pos_service
from shopman.shop.services import stock as stock_service
from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_scheduled_order import _payload, balcao  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def grade(balcao):  # noqa: F811
    """A grade do PDV: Croissant e Baguette da casa (em lote) e uma geleia de revenda.

    Todos têm saldo hoje (são rastreados pelo Stockman); nenhum tem saldo na data
    da encomenda até o teste planejar.
    """
    Product.objects.create(sku="GEL", name="Geleia de Morango", base_price_q=2900, is_published=True, is_sellable=True)
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    position = Position.objects.create(ref="loja", name="Loja", kind=PositionKind.PHYSICAL, is_saleable=True)
    for sku in ("CR", "BF", "GEL"):
        product = Product.objects.get(sku=sku)
        product.shelf_life_days = 0
        product.save(update_fields=["shelf_life_days"])
        ListingItem.objects.create(listing=listing, product=product, price_q=product.base_price_q)
        stock.receive(quantity=Decimal("10"), sku=sku, position=position, target_date=None, reason="vitrine de hoje")
    for sku in ("CR", "BF"):
        Recipe.objects.create(
            ref=f"ficha-{sku.lower()}", name=sku, output_sku=sku, batch_size=Decimal("1"),
            is_active=True, production_mode=ProductionMode.BATCH,
        )
    return balcao


def _dia():
    """Daqui a dez dias: a data do laudo (P1-1)."""
    return timezone.localdate() + timedelta(days=10)


def _plano(qty: str, *, sku: str, day=None):
    stock.plan(
        quantity=Decimal(qty), product=Product.objects.get(sku=sku), target_date=day or _dia(),
        position=Position.objects.get(ref="loja"), reason="lote planejado",
    )


def _encomenda(shift, items, *, client_request_id: str = "enc-sem-plano") -> dict:
    return _payload(shift, client_request_id=client_request_id, delivery_date=_dia().isoformat(), items=items)


def _croissants(qty: int) -> list[dict]:
    return [{"sku": "CR", "name": "Croissant", "qty": qty, "unit_price_q": 900}]


def _review(operator, payload):
    return pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)


def _fechar(operator, payload):
    payload["expected_total_q"] = _review(operator, dict(payload)).total_q
    return pos_service.close_sale(
        channel_ref="pdv", payload=payload, actor=f"pos:{operator.username}", operator_username=operator.username,
    )


# ── As duas réguas na grade ──────────────────────────────────────────────────


def test_a_grade_separa_plano_esgotado_de_data_sem_plano(grade):
    """Croissant sem lote na data: entra. Baguete com o lote todo prometido: bloqueada."""
    _plano("22", sku="BF")
    stock.hold(Decimal("22"), Product.objects.get(sku="BF"), target_date=_dia(), reference="outra-encomenda")

    schedule = build_pos_schedule(delivery_date=_dia().isoformat(), skus=["CR", "BF"])

    assert schedule["unplanned_skus"] == ["CR"], "sem lote planejado na data vira pedido à Produção"
    assert "CR" not in schedule["sold_out_skus"], "sem plano não é sem saldo (D2)"
    assert "BF" in schedule["sold_out_skus"], "plano esgotado segue bloqueado"
    assert schedule["plan_by_sku"] == {
        "CR": {"planned_qty": 0, "unclaimed_qty": 0},
        "BF": {"planned_qty": 22, "unclaimed_qty": 0},
    }


def test_revenda_sem_saldo_na_data_segue_sem_saldo(grade):
    """A Produção não planeja lote de geleia: o zero dela é falta de verdade."""
    schedule = build_pos_schedule(delivery_date=_dia().isoformat(), skus=["GEL"])

    assert "GEL" in schedule["sold_out_skus"]
    assert "GEL" not in schedule["unplanned_skus"]
    assert schedule["plan_by_sku"] == {}


def test_na_hora_nao_vira_pedido_a_producao(grade):
    """"Na hora" é feito quando vende, não tem lote planejado: fica com a régua de sempre."""
    Recipe.objects.filter(output_sku="CR").update(production_mode=ProductionMode.MADE_TO_ORDER)

    schedule = build_pos_schedule(delivery_date=_dia().isoformat(), skus=["CR"])

    assert "CR" in schedule["sold_out_skus"]
    assert "CR" not in schedule["unplanned_skus"]
    assert schedule["plan_by_sku"] == {}


def test_com_lote_planejado_a_data_diz_o_plano_e_nao_pedido_a_producao(grade):
    _plano("28", sku="CR")

    schedule = build_pos_schedule(delivery_date=_dia().isoformat(), skus=["CR"])

    assert "CR" not in schedule["unplanned_skus"]
    assert "CR" not in schedule["sold_out_skus"]
    assert schedule["plan_by_sku"] == {"CR": {"planned_qty": 28, "unclaimed_qty": 28}}


def test_hoje_nao_ha_pedido_a_producao(grade):
    schedule = build_pos_schedule(skus=["CR"])

    assert schedule["unplanned_skus"] == []
    assert schedule["sold_out_skus"] == []
    assert schedule["plan_by_sku"] == {}


def test_a_regua_e_do_orquestrador():
    """``unplanned_on`` não responde por hoje nem por data nenhuma."""
    assert stock_service.unplanned_on(["CR"], timezone.localdate()) == set()
    assert stock_service.unplanned_on(["CR"], None) == set()
    assert stock_service.unplanned_on([], _dia()) == set()


# ── A encomenda sem plano fecha, e a Produção vê a demanda ───────────────────


def test_a_review_diz_pedido_a_producao_e_nao_chama_o_gerente(grade):
    operator, shift = grade

    review = _review(operator, _encomenda(shift, _croissants(30)))

    assert not review.preorder_over_plan
    assert "preorder_over_plan" not in review.approval_reasons
    [remark] = [w for w in review.warnings if w.get("sku") == "CR"]
    day = _dia().strftime("%d/%m")
    assert remark["message"] == f"Croissant: ainda sem lote planejado para {day}. Vira pedido à Produção."


def test_plano_esgotado_continua_pedindo_o_gerente(grade):
    operator, shift = grade
    _plano("22", sku="BF")
    stock.hold(Decimal("22"), Product.objects.get(sku="BF"), target_date=_dia(), reference="outra-encomenda")
    payload = _encomenda(shift, [{"sku": "BF", "name": "Baguette de Tradition", "qty": 5, "unit_price_q": 1600}])

    review = _review(operator, dict(payload))
    assert "preorder_over_plan" in review.approval_reasons
    [line] = review.preorder_over_plan
    assert (line["planned_qty"], line["unclaimed_qty"]) == (Decimal("22"), Decimal("0"))

    with pytest.raises(PosIntentError) as exc:
        _fechar(operator, payload)
    assert exc.value.code == "manager_approval_required"


def test_fecha_sem_gerente_e_a_producao_ve_a_demanda(grade, django_capture_on_commit_callbacks):
    from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend
    from shopman.orderman.models import Order

    from shopman.backstage.models import OperatorAlert

    operator, shift = grade

    with django_capture_on_commit_callbacks(execute=True):
        result = _fechar(operator, _encomenda(shift, _croissants(30)))

    order = Order.objects.get(ref=result.order_ref)
    ids = [int(str(entry["hold_id"]).split(":")[1]) for entry in order.data.get("hold_ids", [])]
    holds = list(Hold.objects.filter(pk__in=ids, sku="CR"))
    assert holds
    assert sum(h.quantity for h in holds) == Decimal("30")
    assert all(h.quant_id is None for h in holds), "sem lote na data, a reserva é demanda"
    assert all(h.target_date == _dia() for h in holds)
    # A sugestão da Produção conta a demanda da data.
    assert OrderingDemandBackend().committed("CR", _dia()) == Decimal("30")
    # E o aviso sai para a Produção no fechamento.
    alert = OperatorAlert.objects.get(type="order_demand_over_plan", order_ref=order.ref)
    assert alert.audience == "production"
    day = _dia().strftime("%d/%m")
    assert f"30 Croissant para {day}" in alert.message
    assert f"Planeje mais 30 para {day}" in alert.message
