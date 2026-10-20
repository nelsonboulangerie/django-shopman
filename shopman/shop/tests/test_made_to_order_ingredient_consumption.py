"""A venda do item feito na hora baixa o insumo da ficha (ADR-040, dono 20/10/2026).

O que estes testes travam:

- a venda baixa o insumo UMA vez (directive com recibo permanente + guarda no
  ledger), com ``kind=MAKE`` e ``metadata.source="sale"``;
- a ficha desce UM nível: o bechamel do croque sai como bechamel, nunca como a
  farinha e o leite dele (que a fornada do bechamel já descontou);
- só a ficha MARCADA ``made_to_order`` baixa; a inativa sem marca é ficha
  desligada;
- falta de insumo não trava: baixa o que existe e vira alerta;
- cancelamento ANTES de preparado devolve (``RETURN``); DEPOIS de preparado é
  perda (``WASTE``), e o item sem ticket de KDS conta como preparado.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.stockman import stock
from shopman.stockman.models import Move, Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import KDSInstance, KDSTicket, OperatorAlert
from shopman.shop.directives import (
    STOCK_CONSUME_MADE_TO_ORDER,
    STOCK_SETTLE_MADE_TO_ORDER_CANCELLATION,
)
from shopman.shop.handlers.made_to_order import (
    MadeToOrderCancellationHandler,
    MadeToOrderConsumeHandler,
)
from shopman.shop.services import made_to_order
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalogo(db):
    from shopman.offerman.models import Product

    from shopman.shop.models import Channel

    Channel.objects.create(ref="pdv", name="PDV", is_active=True)
    for sku in ("SP", "CQMO", "PAO"):
        Product.objects.create(sku=sku, name=sku, base_price_q=500, is_published=True, is_sellable=True)


@pytest.fixture
def deposito(db):
    return Position.objects.create(
        ref="deposito-mto", name="Depósito", kind=PositionKind.PHYSICAL, is_saleable=False,
    )


def _ficha(ref: str, output_sku: str, items, *, made_to_order: bool = True, batch: str = "1") -> Recipe:
    recipe = Recipe.objects.create(
        ref=ref, name=ref, output_sku=output_sku, batch_size=Decimal(batch),
        is_active=False, meta={"made_to_order": True} if made_to_order else {},
    )
    for order, (sku, qty, *factor) in enumerate(items):
        RecipeItem.objects.create(
            recipe=recipe, input_sku=sku, quantity=Decimal(qty), unit="g", sort_order=order,
            usable_factor=Decimal(factor[0]) if factor else Decimal("1"),
        )
    return recipe


def _pedido(ref: str, lines, *, status=Order.Status.ACCEPTED) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="pdv", session_key=f"SESS-{ref}", status=status, total_q=1000, data={},
        snapshot={"items": [{"line_id": str(n), "sku": sku, "qty": qty} for n, (sku, qty) in enumerate(lines, 1)]},
    )
    for n, (sku, qty) in enumerate(lines, start=1):
        OrderItem.objects.create(
            order=order, line_id=str(n), sku=sku, name=sku, qty=qty, unit_price_q=500, line_total_q=500 * qty,
        )
    return order


def _saldo(sku: str) -> Decimal:
    return sum((q.quantity for q in Quant.objects.filter(sku=sku)), Decimal("0"))


def _sale_moves(order_ref: str):
    return Move.objects.filter(metadata__source="sale", metadata__order_ref=order_ref)


def _cancelar(order: Order) -> None:
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()


def _ticket(order: Order, items, **fields) -> KDSTicket:
    station, _ = KDSInstance.objects.get_or_create(ref="cafes-mto", defaults={"name": "Cafés", "type": "prep"})
    return KDSTicket.objects.create(
        session_key=order.session_key, kds_instance=station, items=items, **fields,
    )


# ── Venda ──────────────────────────────────────────────────────────────


def test_a_venda_agenda_a_baixa_uma_vez_so(deposito):
    _ficha("espresso", "SP", [("CAFE-GRAO", "7")])
    order = _pedido("MTO-1", [("SP", 2)])

    stock_service.fulfill(order)
    stock_service.fulfill(order)  # fulfill repetido não agenda outra baixa

    assert Directive.objects.filter(topic=STOCK_CONSUME_MADE_TO_ORDER, dedupe_key="MTO-1").count() == 1


def test_pedido_sem_item_feito_na_hora_nao_agenda_nada(deposito):
    _ficha("espresso", "SP", [("CAFE-GRAO", "7")])
    order = _pedido("MTO-2", [("PAO", 1)])

    stock_service.fulfill(order)

    assert not Directive.objects.filter(topic=STOCK_CONSUME_MADE_TO_ORDER).exists()


def test_a_venda_baixa_o_insumo_uma_vez_com_a_origem_no_movimento(deposito):
    _ficha("espresso", "SP", [("CAFE-GRAO", "7")])
    stock.receive(quantity=Decimal("1000"), sku="CAFE-GRAO", position=deposito, reason="compra")
    order = _pedido("MTO-3", [("SP", 2)])

    made_to_order.consume(order)
    made_to_order.consume(order)  # a directive que roda de novo não baixa outra vez

    assert _saldo("CAFE-GRAO") == Decimal("986")
    move = _sale_moves("MTO-3").get()
    assert move.kind == Move.Kind.MAKE
    assert move.delta == Decimal("-14")
    assert move.metadata["sold_sku"] == "SP"
    order.refresh_from_db()
    record = order.data["made_to_order_consumption"]
    assert record["lines"][0]["items"] == [
        {"sku": "CAFE-GRAO", "unit": "g", "needed": "14.000", "issued": "14.000"},
    ]


def test_o_handler_da_directive_baixa(deposito):
    _ficha("espresso", "SP", [("CAFE-GRAO", "7")])
    stock.receive(quantity=Decimal("100"), sku="CAFE-GRAO", position=deposito, reason="compra")
    order = _pedido("MTO-4", [("SP", 1)])
    stock_service.fulfill(order)
    directive = Directive.objects.get(topic=STOCK_CONSUME_MADE_TO_ORDER, dedupe_key="MTO-4")

    MadeToOrderConsumeHandler().handle(message=directive, ctx={})

    assert _saldo("CAFE-GRAO") == Decimal("93")


def test_a_ficha_desce_um_nivel_so_o_bechamel_sai_como_bechamel(deposito):
    # O bechamel tem ficha própria (ATIVA, é fornada) com farinha e leite.
    bechamel = Recipe.objects.create(ref="bechamel", name="Bechamel", output_sku="MOLHO-BECHAMEL", batch_size=1000)
    RecipeItem.objects.create(recipe=bechamel, input_sku="FARINHA", quantity=Decimal("60"), unit="g")
    RecipeItem.objects.create(recipe=bechamel, input_sku="LEITE", quantity=Decimal("900"), unit="g")
    _ficha("croque", "CQMO", [("MOLHO-BECHAMEL", "70"), ("QUEIJO-GOUDA", "50", "0.95")])
    for sku in ("MOLHO-BECHAMEL", "QUEIJO-GOUDA", "FARINHA", "LEITE"):
        stock.receive(quantity=Decimal("1000"), sku=sku, position=deposito, reason="compra")
    order = _pedido("MTO-5", [("CQMO", 1)])

    made_to_order.consume(order)

    assert _saldo("MOLHO-BECHAMEL") == Decimal("930")
    # A BRUTA do gouda: 50 g líquidos com 95% de aproveitamento.
    assert _saldo("QUEIJO-GOUDA") == Decimal("1000") - Decimal("52.632")
    # A farinha e o leite do bechamel já saíram na fornada dele: não contam duas vezes.
    assert _saldo("FARINHA") == Decimal("1000")
    assert _saldo("LEITE") == Decimal("1000")


def test_ficha_inativa_sem_marca_e_ficha_desligada_e_nao_baixa(deposito):
    _ficha("espresso-velho", "SP", [("CAFE-GRAO", "7")], made_to_order=False)
    stock.receive(quantity=Decimal("100"), sku="CAFE-GRAO", position=deposito, reason="compra")
    order = _pedido("MTO-6", [("SP", 1)])

    stock_service.fulfill(order)
    made_to_order.consume(order)

    assert not Directive.objects.filter(topic=STOCK_CONSUME_MADE_TO_ORDER).exists()
    assert _saldo("CAFE-GRAO") == Decimal("100")


def test_falta_de_insumo_nao_trava_baixa_o_que_existe_e_alerta(deposito):
    _ficha("espresso", "SP", [("CAFE-GRAO", "7")])
    stock.receive(quantity=Decimal("10"), sku="CAFE-GRAO", position=deposito, reason="compra")
    order = _pedido("MTO-7", [("SP", 2)])

    record = made_to_order.consume(order)

    assert _saldo("CAFE-GRAO") == Decimal("0")
    assert record["shortfalls"] == [
        {"sku": "CAFE-GRAO", "unit": "g", "sold_sku": "SP", "needed": "14.000", "issued": "10.000", "short": "4.000"},
    ]
    alert = OperatorAlert.objects.get(type="stock_sale_ingredient_short")
    assert "CAFE-GRAO" in alert.message and "MTO-7" in alert.message
    assert "—" not in alert.message
    assert alert.get_type_display() == "Venda baixou menos insumo que a ficha"


def test_duas_fichas_marcadas_para_o_mesmo_produto_nao_escolhe_e_alerta(deposito):
    _ficha("espresso-a", "SP", [("CAFE-GRAO", "7")])
    _ficha("espresso-b", "SP", [("CAFE-GRAO", "9")])
    stock.receive(quantity=Decimal("100"), sku="CAFE-GRAO", position=deposito, reason="compra")
    order = _pedido("MTO-8", [("SP", 1)])

    made_to_order.consume(order)

    assert _saldo("CAFE-GRAO") == Decimal("100")
    assert OperatorAlert.objects.filter(type="stock_sale_recipe_ambiguous").exists()


# ── Cancelamento: antes ou depois de preparado ─────────────────────────


def _vendido(deposito, ref: str, qty: int = 2) -> Order:
    _ficha("espresso", "SP", [("CAFE-GRAO", "7")])
    stock.receive(quantity=Decimal("1000"), sku="CAFE-GRAO", position=deposito, reason="compra")
    order = _pedido(ref, [("SP", qty)])
    stock_service.fulfill(order)
    made_to_order.consume(order)
    assert _saldo("CAFE-GRAO") == Decimal("1000") - 7 * qty
    return order


def test_cancelado_antes_de_preparar_devolve_o_insumo(deposito):
    order = _vendido(deposito, "MTO-10")
    ticket = _ticket(order, [{"sku": "SP", "qty": 2, "line_id": "1"}])
    _cancelar(order)
    # O cancelamento fecha o ticket que a estação nunca começou.
    KDSTicket.objects.filter(pk=ticket.pk).update(status="cancelled", cancelled_at=timezone.now())

    settlement = made_to_order.settle_cancellation(order)
    made_to_order.settle_cancellation(order)  # idempotente

    assert _saldo("CAFE-GRAO") == Decimal("1000")
    assert settlement["returned"] == {"CAFE-GRAO": "14.000"}
    assert settlement["wasted"] == {}
    assert Move.objects.filter(kind=Move.Kind.RETURN, metadata__order_ref="MTO-10").count() == 1
    assert not Move.objects.filter(kind=Move.Kind.WASTE).exists()


def test_cancelado_depois_de_preparado_vira_perda(deposito):
    order = _vendido(deposito, "MTO-11")
    _ticket(order, [{"sku": "SP", "qty": 2, "line_id": "1"}], status="done", completed_at=timezone.now())
    _cancelar(order)

    settlement = made_to_order.settle_cancellation(order)

    # O café não volta para o pacote: o saldo fica onde a venda o deixou…
    assert _saldo("CAFE-GRAO") == Decimal("986")
    assert settlement["returned"] == {}
    assert settlement["wasted"] == {"CAFE-GRAO": "14.000"}
    # …e a saída deixa de ser consumo de venda para ser perda.
    waste = Move.objects.get(kind=Move.Kind.WASTE)
    assert waste.delta == Decimal("-14")
    assert waste.metadata["source"] == "sale_cancel"
    assert waste.metadata["outcome"] == "wasted"


def test_preparo_iniciado_ja_conta_como_preparado(deposito):
    order = _vendido(deposito, "MTO-12")
    # A estação começou e o cancelamento fechou o ticket no meio do preparo.
    _ticket(
        order, [{"sku": "SP", "qty": 2, "line_id": "1"}],
        status="cancelled", started_at=timezone.now(), cancelled_at=timezone.now(),
    )
    _cancelar(order)

    settlement = made_to_order.settle_cancellation(order)

    assert settlement["wasted"] == {"CAFE-GRAO": "14.000"}
    assert _saldo("CAFE-GRAO") == Decimal("986")


def test_parte_preparada_parte_nao(deposito):
    order = _vendido(deposito, "MTO-13", qty=2)
    _ticket(order, [{"sku": "SP", "qty": 1, "line_id": "1"}], status="done", completed_at=timezone.now())
    _ticket(order, [{"sku": "SP", "qty": 1, "line_id": "1"}], status="cancelled", cancelled_at=timezone.now())
    _cancelar(order)

    settlement = made_to_order.settle_cancellation(order)

    assert settlement == {**settlement, "returned": {"CAFE-GRAO": "7.000"}, "wasted": {"CAFE-GRAO": "7.000"}}
    assert _saldo("CAFE-GRAO") == Decimal("993")


def test_sem_ticket_de_kds_conta_como_preparado(deposito):
    """Balcão que tira o café sem KDS: nenhum fato diz que não foi feito."""
    order = _vendido(deposito, "MTO-14")
    _cancelar(order)

    settlement = made_to_order.settle_cancellation(order)

    assert settlement["returned"] == {}
    assert settlement["wasted"] == {"CAFE-GRAO": "14.000"}


def test_o_cancelamento_agenda_o_acerto_so_quando_a_venda_agendou_baixa(deposito):
    from shopman.shop.config import ChannelConfig
    from shopman.shop.lifecycle import _on_cancelled

    order = _vendido(deposito, "MTO-15")
    _ticket(order, [{"sku": "SP", "qty": 2, "line_id": "1"}])
    _cancelar(order)

    _on_cancelled(order, ChannelConfig.for_channel(order.channel_ref))
    _on_cancelled(order, ChannelConfig.for_channel(order.channel_ref))

    directive = Directive.objects.get(topic=STOCK_SETTLE_MADE_TO_ORDER_CANCELLATION, dedupe_key="MTO-15")
    MadeToOrderCancellationHandler().handle(message=directive, ctx={})
    # O on_cancelled fechou o ticket pendente: a estação não tinha começado, volta.
    assert _saldo("CAFE-GRAO") == Decimal("1000")

    sem_venda = _pedido("MTO-16", [("SP", 1)])
    _cancelar(sem_venda)
    assert made_to_order.schedule_cancellation_settlement(sem_venda) is False


def test_cancelado_antes_do_worker_baixa_e_acerta_na_mesma_passada(deposito):
    _ficha("espresso", "SP", [("CAFE-GRAO", "7")])
    stock.receive(quantity=Decimal("100"), sku="CAFE-GRAO", position=deposito, reason="compra")
    order = _pedido("MTO-17", [("SP", 1)])
    _ticket(order, [{"sku": "SP", "qty": 1, "line_id": "1"}], status="cancelled", cancelled_at=timezone.now())
    _cancelar(order)

    made_to_order.consume(order)

    assert _saldo("CAFE-GRAO") == Decimal("100")
    assert Move.objects.filter(kind=Move.Kind.RETURN, metadata__order_ref="MTO-17").exists()
