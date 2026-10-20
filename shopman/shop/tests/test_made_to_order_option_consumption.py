"""O adicional escolhido no produto baixa o insumo dele (ADR-040, extensão de 20/10/2026).

A linha guarda a escolha em ``meta["options"]`` com o ``consumes`` CONGELADO na
venda (``product_options.resolve_selection``). A baixa do feito na hora passa a
ler esse ``consumes``: mesma directive, mesmo ledger (``kind=MAKE``,
``metadata.source="sale"``), mesma regra de cancelamento pelo preparo, mesmo
alerta de falta sem travar a venda.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import ProductionMode, Recipe, RecipeItem
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.stockman import stock
from shopman.stockman.models import Move, Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import KDSInstance, KDSTicket, OperatorAlert
from shopman.shop.directives import STOCK_CONSUME_MADE_TO_ORDER
from shopman.shop.services import made_to_order
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db

OVO_FRITO = {
    "group": "adicionais", "group_label": "Adicionais", "ref": "ovo-frito", "name": "Ovo frito",
    "qty": 1, "unit_price_q": 400, "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}],
}
SALADA = {
    "group": "adicionais", "group_label": "Adicionais", "ref": "salada", "name": "Salada",
    "qty": 1, "unit_price_q": 300,
    "consumes": [
        {"sku": "ALFACE-AMERICANA", "qty": "20", "unit": "g"},
        {"sku": "RUCULA", "qty": "10", "unit": "g"},
    ],
}


@pytest.fixture(autouse=True)
def catalogo(db):
    from shopman.offerman.models import Product

    from shopman.shop.models import Channel

    Channel.objects.create(ref="pdv", name="PDV", is_active=True)
    for sku in ("CQMO", "FRAP"):
        Product.objects.create(sku=sku, name=sku, base_price_q=500, is_published=True, is_sellable=True)


@pytest.fixture
def deposito(db):
    position = Position.objects.create(
        ref="deposito-opt", name="Depósito", kind=PositionKind.PHYSICAL, is_saleable=False,
    )
    for sku in ("OVOS", "ALFACE-AMERICANA", "RUCULA", "PRESUNTO", "CAFE-GRAO"):
        stock.receive(quantity=Decimal("1000"), sku=sku, position=position, reason="compra")
    return position


def _croque_com_ficha() -> Recipe:
    recipe = Recipe.objects.create(
        ref="croque", name="croque", output_sku="CQMO", batch_size=Decimal("1"),
        is_active=True, production_mode=ProductionMode.MADE_TO_ORDER,
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="PRESUNTO", quantity=Decimal("60"), unit="g")
    return recipe


def _pedido(ref: str, lines, *, status=Order.Status.ACCEPTED) -> Order:
    """``lines`` = ``[(sku, qty, [opções])]``."""
    rows = [
        (str(n), sku, qty, {"options": options} if options else {})
        for n, (sku, qty, options) in enumerate(lines, start=1)
    ]
    order = Order.objects.create(
        ref=ref, channel_ref="pdv", session_key=f"SESS-{ref}", status=status, total_q=1000, data={},
        snapshot={"items": [{"line_id": n, "sku": sku, "qty": qty, "meta": meta} for n, sku, qty, meta in rows]},
    )
    for n, sku, qty, meta in rows:
        OrderItem.objects.create(
            order=order, line_id=n, sku=sku, name=sku, qty=qty, unit_price_q=500,
            line_total_q=500 * qty, meta=meta,
        )
    return order


def _saldo(sku: str) -> Decimal:
    return sum((q.quantity for q in Quant.objects.filter(sku=sku)), Decimal("0"))


def _cancelar(order: Order) -> None:
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()


def _ticket(order: Order, items, **fields) -> KDSTicket:
    station, _ = KDSInstance.objects.get_or_create(ref="cozinha-opt", defaults={"name": "Cozinha", "type": "prep"})
    return KDSTicket.objects.create(session_key=order.session_key, kds_instance=station, items=items, **fields)


# ── Venda ──────────────────────────────────────────────────────────────


def test_o_adicional_baixa_o_insumo_dele_junto_da_ficha(deposito):
    _croque_com_ficha()
    order = _pedido("OPT-1", [("CQMO", 2, [OVO_FRITO, SALADA])])

    record = made_to_order.consume(order)
    made_to_order.consume(order)  # a directive que roda de novo não baixa outra vez

    assert _saldo("PRESUNTO") == Decimal("880")  # a ficha: 60 g × 2
    assert _saldo("OVOS") == Decimal("900")  # o adicional: 50 g × 2
    assert _saldo("ALFACE-AMERICANA") == Decimal("960")
    assert _saldo("RUCULA") == Decimal("980")

    ovo = Move.objects.get(quant__sku="OVOS", metadata__source="sale")
    assert ovo.kind == Move.Kind.MAKE
    assert ovo.metadata == {
        "source": "sale", "order_ref": "OPT-1", "sold_sku": "CQMO", "sold_qty": "2",
        "option_group": "adicionais", "option_ref": "ovo-frito",
    }
    option_lines = [line for line in record["lines"] if "option" in line]
    assert option_lines[0] == {
        "sku": "CQMO", "qty": "2",
        "option": {"group": "adicionais", "ref": "ovo-frito", "name": "Ovo frito"},
        "items": [{"sku": "OVOS", "unit": "g", "needed": "100.000", "issued": "100.000"}],
    }


def test_adicional_baixa_mesmo_sem_ficha_feita_na_hora_e_agenda_a_directive(deposito):
    """O ``consumes`` cadastrado é a marca: nenhuma fornada conhece o adicional."""
    cafe = {
        "group": "sabor", "group_label": "Sabor", "ref": "cafe", "name": "Café",
        "qty": 1, "unit_price_q": 0, "consumes": [{"sku": "CAFE-GRAO", "qty": "18", "unit": "g"}],
    }
    order = _pedido("OPT-2", [("FRAP", 1, [cafe])])

    stock_service.fulfill(order)
    stock_service.fulfill(order)

    assert Directive.objects.filter(topic=STOCK_CONSUME_MADE_TO_ORDER, dedupe_key="OPT-2").count() == 1
    made_to_order.consume(order)
    assert _saldo("CAFE-GRAO") == Decimal("982")


def test_opcao_sem_ref_do_ifood_nao_baixa(deposito):
    ifood = {"name": "Ovo frito", "group": "Adicionais", "qty": 1, "unit_price_q": 400,
             "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]}
    order = _pedido("OPT-3", [("FRAP", 1, [ifood])])

    stock_service.fulfill(order)
    made_to_order.consume(order)

    assert not Directive.objects.filter(topic=STOCK_CONSUME_MADE_TO_ORDER).exists()
    assert _saldo("OVOS") == Decimal("1000")


def test_opcao_escolhida_duas_vezes_baixa_em_dobro(deposito):
    order = _pedido("OPT-4", [("CQMO", 1, [{**OVO_FRITO, "qty": 2}])])

    made_to_order.consume(order)

    assert _saldo("OVOS") == Decimal("900")


def test_insumo_em_kg_recebe_a_baixa_convertida(deposito):
    """O cadastro diz 50 g; o insumo conta em kg: sai 0,050 kg, não 50 kg."""
    from shopman.offerman.models import Product

    Product.objects.create(sku="QUEIJO-KG", name="Queijo", base_price_q=9000, unit="kg")
    stock.receive(quantity=Decimal("2"), sku="QUEIJO-KG", position=deposito, reason="compra")
    queijo = {**OVO_FRITO, "ref": "queijo", "name": "Queijo",
              "consumes": [{"sku": "QUEIJO-KG", "qty": "50", "unit": "g"}]}
    order = _pedido("OPT-5", [("FRAP", 1, [queijo])])

    record = made_to_order.consume(order)

    assert _saldo("QUEIJO-KG") == Decimal("1.950")
    assert record["lines"][0]["items"] == [{"sku": "QUEIJO-KG", "unit": "kg", "needed": "0.050", "issued": "0.050"}]


def test_falta_do_insumo_do_adicional_nao_trava_e_alerta(deposito):
    stock.receive(quantity=Decimal("30"), sku="OVOS-CAIPIRA", position=deposito, reason="compra")
    caipira = {**OVO_FRITO, "consumes": [{"sku": "OVOS-CAIPIRA", "qty": "50", "unit": "g"}]}
    order = _pedido("OPT-6", [("CQMO", 1, [caipira])])

    record = made_to_order.consume(order)

    assert _saldo("OVOS-CAIPIRA") == Decimal("0")
    assert record["shortfalls"] == [
        {"sku": "OVOS-CAIPIRA", "unit": "g", "sold_sku": "CQMO", "option": "Ovo frito",
         "needed": "50.000", "issued": "30.000", "short": "20.000"},
    ]
    alert = OperatorAlert.objects.get(type="stock_sale_ingredient_short")
    assert "o adicional Ovo frito de CQMO" in alert.message
    assert "—" not in alert.message


# ── Cancelamento: a mesma regra do preparo ─────────────────────────────


def test_cancelado_antes_de_preparar_devolve_o_insumo_do_adicional(deposito):
    _croque_com_ficha()
    order = _pedido("OPT-7", [("CQMO", 1, [OVO_FRITO])])
    made_to_order.consume(order)
    _ticket(order, [{"sku": "CQMO", "qty": 1, "line_id": "1"}], status="cancelled", cancelled_at=timezone.now())
    _cancelar(order)

    settlement = made_to_order.settle_cancellation(order)

    assert settlement["returned"] == {"PRESUNTO": "60.000", "OVOS": "50.000"}
    assert settlement["wasted"] == {}
    assert _saldo("OVOS") == Decimal("1000")


def test_cancelado_depois_de_preparado_o_adicional_vira_perda(deposito):
    order = _pedido("OPT-8", [("CQMO", 1, [OVO_FRITO])])
    made_to_order.consume(order)
    _ticket(order, [{"sku": "CQMO", "qty": 1, "line_id": "1"}], status="done", completed_at=timezone.now())
    _cancelar(order)

    settlement = made_to_order.settle_cancellation(order)

    assert settlement["wasted"] == {"OVOS": "50.000"}
    assert _saldo("OVOS") == Decimal("950")
    waste = Move.objects.get(kind=Move.Kind.WASTE)
    assert waste.metadata["sold_sku"] == "CQMO"


def test_parcial_o_adicional_acerta_na_proporcao_do_item(deposito):
    order = _pedido("OPT-9", [("CQMO", 2, [OVO_FRITO])])
    made_to_order.consume(order)
    _ticket(order, [{"sku": "CQMO", "qty": 1, "line_id": "1"}], status="done", completed_at=timezone.now())
    _ticket(order, [{"sku": "CQMO", "qty": 1, "line_id": "1"}], status="cancelled", cancelled_at=timezone.now())
    _cancelar(order)

    settlement = made_to_order.settle_cancellation(order)

    assert settlement["returned"] == {"OVOS": "50.000"}
    assert settlement["wasted"] == {"OVOS": "50.000"}
    assert _saldo("OVOS") == Decimal("950")
