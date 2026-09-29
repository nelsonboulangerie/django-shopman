"""ORDER_PATCHED, Etapa 2: o pedido local passa a refletir a alteração.

A Etapa 1 (#897) parou de mentir — o evento ganhou processador, o fato ficou
gravado em ``order.data["ifood"]["patches"]`` com ``reconciled: False`` e o
operador passou a ser avisado. O que faltava era reconciliar: o pedido local
seguia com os itens originais.

A decisão do dono (24/09/2026): guardar a alteração como **ajuste em
``order.data``**, com cozinha, separação e B.I. lendo **"pedido + ajustes"**.
Nada de cancelar e recriar (no iFood, cancelar localmente PEDE ao iFood que
cancele o pedido do cliente); nada de abrir exceção nos campos selados
(``Order.total_q`` e ``Order.snapshot`` são ``SEALED_FIELDS``).

Este arquivo prova as três coisas que a decisão exige:

1. o ajuste é gravado a partir do pedido RELIDO (estado final, não o delta do
   evento) e o pedido selado não é tocado;
2. estoque e cozinha acompanham, sem duplicar nem perder;
3. **existe UMA leitura composta** e os consumidores leem ela — cozinha, card
   do Gestor, vias impressas, fechamento do dia, nota e B.I. dão a MESMA
   resposta sobre o mesmo pedido.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order
from shopman.stockman import HoldStatus, PositionKind
from shopman.stockman.models import Hold, Move, Position, Quant

from shopman.backstage.models import KDSInstance, KDSTicket, OperatorAlert
from shopman.shop.models import Channel
from shopman.shop.services import ifood_events, ifood_orders, kds, order_composition, stock

pytestmark = pytest.mark.django_db

ORDER_ID = "ifood-order-2"
PAO = "PAO-FRANCES"
CAFE = "CAFE-COADO"


# ── Mundo ─────────────────────────────────────────────────────────────────────


def _world(*, pao_stock=100, cafe_stock=100) -> None:
    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    KDSInstance.objects.create(ref="ifood-picking", name="Separação", type="picking")
    position, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    for sku, name, qty in ((PAO, "Pão francês", pao_stock), (CAFE, "Café coado", cafe_stock)):
        Product.objects.create(
            sku=sku, name=name, base_price_q=500, is_published=True, is_sellable=True
        )
        Quant.objects.create(sku=sku, position=position, _quantity=Decimal(str(qty)))


def _ifood_order(items: list[dict], *, total: float | None = None) -> dict:
    """Um pedido do iFood como o ``GET /order/v1.0/orders/{id}`` devolve."""
    subtotal = sum(item["totalPrice"] for item in items)
    return {
        "id": ORDER_ID,
        "displayId": "1234",
        "orderType": "DELIVERY",
        "merchant": {"id": "merchant"},
        "customer": {"name": "Cliente"},
        "items": [
            {
                "id": item["id"],
                "externalCode": item["sku"],
                "name": item["name"],
                "quantity": item["quantity"],
                "unitPrice": item["unitPrice"],
                "totalPrice": item["totalPrice"],
            }
            for item in items
        ],
        "total": {"subTotal": subtotal, "orderAmount": subtotal if total is None else total},
        "payments": {"prepaid": subtotal if total is None else total, "pending": 0},
    }


def _line(sku, name, quantity, unit=5.0, line_id=None) -> dict:
    return {
        "id": line_id or f"line-{sku}",
        "sku": sku,
        "name": name,
        "quantity": quantity,
        "unitPrice": unit,
        "totalPrice": round(unit * quantity, 2),
    }


_ORIGINAL = [_line(PAO, "Pão francês", 2), _line(CAFE, "Café coado", 1)]


def _ingest(*, is_test: bool = False) -> Order:
    from shopman.shop.services import ifood_ingest

    payload = ifood_orders.map_order(_ifood_order(_ORIGINAL))
    payload["is_test"] = is_test
    payload["merchant_id"] = "merchant"
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    order.refresh_from_db()
    return order


def _patch_event(*, change_type="UPDATE_ITEMS", items=None, event_id="evt-p2", old_total=15.0,
                 new_total=20.0) -> dict:
    return {
        "id": event_id,
        "code": "ORDER_PATCHED",
        "fullCode": "ORDER_PATCHED",
        "orderId": ORDER_ID,
        "metadata": {
            "id": ORDER_ID,
            "changeType": change_type,
            "items": items or [],
            "oldTotal": old_total,
            "newTotal": new_total,
        },
    }


def _process(event, *, final_items):
    """Roda o evento com a releitura do pedido devolvendo ``final_items``."""
    with (
        patch.object(ifood_events, "acknowledge", return_value=True) as ack,
        patch.object(ifood_orders, "fetch_order", return_value=_ifood_order(final_items)) as fetch,
    ):
        summary = ifood_events.process_events([event])
    return summary, ack, fetch


def _held_qty(order, sku: str) -> Decimal:
    return sum(
        (Decimal(str(entry.get("qty") or 0)) for entry in order.data["hold_ids"] if entry["sku"] == sku),
        Decimal("0"),
    )


def _sold(sku: str) -> Decimal:
    return -sum((m.delta for m in Move.objects.filter(kind=Move.Kind.SELL, quant__sku=sku)), Decimal("0"))


def _returned(sku: str) -> Decimal:
    return sum((m.delta for m in Move.objects.filter(kind=Move.Kind.RETURN, quant__sku=sku)), Decimal("0"))


# ── 1. O ajuste: estado final, ao lado do pedido selado ───────────────────────


def test_the_change_reaches_the_local_order():
    """A prova da Etapa 2: antes disto o pedido local ficava com os itens velhos."""
    _world()
    order = _ingest()
    final = [_line(PAO, "Pão francês", 4), _line(CAFE, "Café coado", 1)]

    summary, _ack, _fetch = _process(_patch_event(), final_items=final)

    assert summary["ingested"] == 1
    order.refresh_from_db()
    items = order_composition.effective_items(order)
    assert {item.sku: item.qty for item in items} == {PAO: Decimal("4"), CAFE: Decimal("1")}
    assert order_composition.effective_total_q(order) == 2500
    assert order.data["ifood"]["patches"][0]["reconciled"] is True


def test_the_sealed_order_is_never_touched():
    """``total_q`` e ``snapshot`` são selados: o ajuste vive AO LADO, não por cima."""
    _world()
    order = _ingest()
    sealed_snapshot = dict(order.snapshot)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 4)])

    order.refresh_from_db()
    assert order.total_q == 1500  # 2×5,00 + 1×5,00, como o pedido nasceu
    assert order.snapshot == sealed_snapshot
    assert order_composition.effective_total_q(order) == 2000


def test_the_reconciliation_rereads_the_order_instead_of_applying_the_delta():
    """O ``metadata`` é DELTA. Aplicar delta é frágil contra reentrega e fora de ordem."""
    _world()
    _ingest()
    event = _patch_event(items=[{"id": f"line-{PAO}", "name": "Pão", "oldQuantity": 2, "newQuantity": 4}])

    _summary, _ack, fetch = _process(event, final_items=[_line(PAO, "Pão francês", 4)])

    fetch.assert_called_once_with(ORDER_ID)
    order = Order.objects.get(external_ref=ORDER_ID)
    # O café SUMIU do pedido relido — e some do pedido local também. Somar o
    # delta o teria mantido, porque ele não estava no evento.
    assert [item.sku for item in order_composition.effective_items(order)] == [PAO]


@pytest.mark.parametrize(
    ("change_type", "final", "expected"),
    [
        ("ADD_ITEMS", [*_ORIGINAL, _line("AGUA", "Água", 1)], {PAO: 2, CAFE: 1, "AGUA": 1}),
        ("DELETE_ITEMS", [_line(PAO, "Pão francês", 2)], {PAO: 2}),
        ("UPDATE_ITEMS", [_line(PAO, "Pão francês", 5), _line(CAFE, "Café coado", 1)], {PAO: 5, CAFE: 1}),
    ],
)
def test_the_three_documented_change_types_all_reconcile(change_type, final, expected):
    _world()
    _ingest()

    _process(_patch_event(change_type=change_type), final_items=final)

    order = Order.objects.get(external_ref=ORDER_ID)
    assert {i.sku: int(i.qty) for i in order_composition.effective_items(order)} == expected


def test_a_second_change_replaces_the_first_and_counts_the_revision():
    """Estado final substitui estado final — duas alterações não se somam."""
    _world()
    _ingest()

    _process(_patch_event(event_id="evt-a"), final_items=[_line(PAO, "Pão francês", 4)])
    _process(_patch_event(event_id="evt-b"), final_items=[_line(PAO, "Pão francês", 3)])

    order = Order.objects.get(external_ref=ORDER_ID)
    assert {i.sku: int(i.qty) for i in order_composition.effective_items(order)} == {PAO: 3}
    assert order.data["adjustment"]["revision"] == 2
    assert len(order.data["ifood"]["patches"]) == 2


def test_a_redelivered_event_changes_nothing_twice():
    _world()
    _ingest()
    event = _patch_event()

    _process(event, final_items=[_line(PAO, "Pão francês", 4)])
    summary, _ack, _fetch = _process(event, final_items=[_line(PAO, "Pão francês", 4)])

    assert summary["deduped"] == 1
    order = Order.objects.get(external_ref=ORDER_ID)
    assert order.data["adjustment"]["revision"] == 1
    assert len(order.data["ifood"]["patches"]) == 1


# ── 2. Estoque: reconciliar, nunca duplicar nem perder ────────────────────────


def test_more_items_reserve_the_difference_only():
    _world()
    order = _ingest()
    stock.hold(order)
    order.refresh_from_db()
    assert _held_qty(order, PAO) == Decimal("2")

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 5), _line(CAFE, "Café coado", 1)])

    order.refresh_from_db()
    assert _held_qty(order, PAO) == Decimal("5")  # 2 + 3, não 2 + 5
    assert _held_qty(order, CAFE) == Decimal("1")


def test_fewer_items_release_the_reservation_that_is_no_longer_needed():
    _world()
    order = _ingest()
    stock.hold(order)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 1), _line(CAFE, "Café coado", 1)])

    order.refresh_from_db()
    assert _held_qty(order, PAO) == Decimal("1")
    # Liberação parcial não existe no Stockman: o hold de 2 é solto inteiro e um
    # de 1 nasce no lugar. O que não pode é sobrar reserva para 2.
    active = Hold.objects.filter(sku=PAO).exclude(status=HoldStatus.RELEASED)
    assert sum((Decimal(str(h.quantity)) for h in active), Decimal("0")) == Decimal("1")


def test_an_item_removed_from_a_paid_order_goes_back_to_the_ledger():
    """Pedido do iFood já baixou o estoque no aceite: tirar item DEVOLVE, não libera."""
    _world()
    order = _ingest()
    stock.hold(order)
    stock.fulfill(order)
    order.refresh_from_db()
    assert _sold(PAO) == Decimal("2")

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 1), _line(CAFE, "Café coado", 1)])

    assert _returned(PAO) == Decimal("1")
    order.refresh_from_db()
    assert _held_qty(order, PAO) == Decimal("1")


def test_an_item_added_to_a_paid_order_is_reserved_AND_written_off():
    """Senão o sistema conta como disponível o pão que a cozinha vai embalar."""
    _world()
    order = _ingest()
    stock.hold(order)
    stock.fulfill(order)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 5), _line(CAFE, "Café coado", 1)])

    assert _sold(PAO) == Decimal("5")


def test_a_late_cancellation_does_not_return_the_bread_twice():
    """O ``hold_ids`` encolhe junto com a devolução — senão o cancel credita de novo."""
    _world()
    order = _ingest()
    stock.hold(order)
    stock.fulfill(order)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 1), _line(CAFE, "Café coado", 1)])
    order.refresh_from_db()
    stock.revert_fulfilled(order)

    # 1 devolvido pela alteração + 1 que sobrou no pedido = os 2 que saíram.
    assert _returned(PAO) == Decimal("2")
    assert _sold(PAO) == Decimal("2")


def test_a_shortfall_on_the_added_item_shouts_instead_of_overselling_in_silence():
    _world(pao_stock=2)
    order = _ingest()
    stock.hold(order)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 9), _line(CAFE, "Café coado", 1)])

    assert OperatorAlert.objects.filter(type="stock_hold_gap").exists()


# ── 3. Cozinha: a comanda muda, e a cozinha fica sabendo ──────────────────────


def test_the_kitchen_gets_the_new_comanda():
    _world()
    order = _ingest()
    kds.dispatch(order)
    assert KDSTicket.objects.filter(session_key=order.session_key).count() == 1

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 4), _line(CAFE, "Café coado", 1)])

    live = KDSTicket.objects.filter(session_key=order.session_key).exclude(status="cancelled")
    quantities = {item["sku"]: item["qty"] for ticket in live for item in ticket.items}
    assert quantities[PAO] == 4


def test_a_line_the_customer_dropped_leaves_a_cancelled_ticket_for_the_kitchen():
    """Parar de fazer algo não pode ser descoberto por adivinhação."""
    _world()
    order = _ingest()
    kds.dispatch(order)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 2)])

    cancelled = KDSTicket.objects.filter(session_key=order.session_key, status="cancelled")
    assert cancelled.exists()
    assert any(item["sku"] == CAFE for ticket in cancelled for item in ticket.items)
    live = KDSTicket.objects.filter(session_key=order.session_key).exclude(status="cancelled")
    assert all(item["sku"] != CAFE for ticket in live for item in ticket.items)


def test_a_line_that_did_not_change_is_not_fired_again():
    _world()
    order = _ingest()
    kds.dispatch(order)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 2), _line(CAFE, "Café coado", 3)])

    live = KDSTicket.objects.filter(session_key=order.session_key).exclude(status="cancelled")
    pao_lines = [item for ticket in live for item in ticket.items if item["sku"] == PAO]
    assert len(pao_lines) == 1


# ── 4. A leitura composta é UMA, e todo mundo lê ela ──────────────────────────


def test_every_consumer_gives_the_same_answer_about_the_same_order():
    """A regra que existe para impedir divergência: cozinha, Gestor, vias,
    fechamento, nota e B.I. não podem discordar sobre o que o pedido é."""
    from shopman.backstage.bi.sources import orderman as bi_orderman
    from shopman.backstage.projections import order_queue
    from shopman.backstage.services import receipt_escpos
    from shopman.shop.services import fiscal

    _world()
    order = _ingest()
    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 4)])
    order.refresh_from_db()

    # cozinha / separação
    assert {line["sku"]: line["qty"] for line in kds.order_lines(order)} == {PAO: 4}
    # card e detalhe do Gestor
    detail = order_queue.build_operator_order(order)
    assert [item.sku for item in detail.items] == [PAO]
    assert detail.total_display == "R$ 20,00"
    # via impressa
    assert "Café" not in receipt_escpos.order_ticket(order).decode("cp860")
    # nota fiscal
    assert [item["sku"] for item in fiscal._build_fiscal_items(order)] == [PAO]
    # B.I.
    from django.utils import timezone

    window = (order.created_at - timezone.timedelta(days=1), order.created_at + timezone.timedelta(days=1))
    sales, _cancelled = bi_orderman.read_sales(window)
    assert [sale.total_q for sale in sales] == [2000]
    lines = bi_orderman.read_lines(window)
    assert {line.product_ref: int(line.qty) for line in lines} == {PAO: 4}


def test_an_order_nobody_changed_reads_exactly_as_before():
    """A leitura composta é no-op sem ajuste — senão ela seria uma regressão
    para os 99% dos pedidos que ninguém altera."""
    _world()
    order = _ingest()

    assert order_composition.is_adjusted(order) is False
    assert order_composition.effective_total_q(order) == order.total_q
    assert {i.sku: i.qty for i in order_composition.effective_items(order)} == {
        item.sku: item.qty for item in order.items.all()
    }


# ── 5. O que NÃO é reconciliado, e por quê ────────────────────────────────────


def test_a_test_order_touches_nothing():
    """A supressão da #887: homologação não põe a padaria para trabalhar."""
    _world()
    order = _ingest(is_test=True)
    kds.dispatch(order)

    summary, _ack, fetch = _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 9)])

    assert summary["ingested"] == 1
    fetch.assert_not_called()
    order.refresh_from_db()
    assert order_composition.is_adjusted(order) is False
    assert order.data["ifood"]["patches"][0]["reconciliation"] == "blocked:test_order"
    assert KDSTicket.objects.filter(session_key=order.session_key).count() == 0
    assert not OperatorAlert.objects.filter(type="ifood_order_patched").exists()


def test_an_authorized_nfce_still_stops_and_names_the_fiscal_path():
    """A nota já saiu: o pedido NÃO é reconciliado, e o aviso diz o que fazer.

    Reconciliar aqui faria pedido e nota divergirem em silêncio — isso não
    mudou. O que mudou é o fim da frase: era "fale com o contador", agora é
    qual dos dois caminhos de lei vale, medido pelo relógio do art. 35.
    """
    _world()
    order = _ingest()
    order.data = {
        **order.data,
        "nfce_access_key": "3526...chave",
        "nfce_authorized_at": (timezone.now() - timedelta(minutes=2)).isoformat(),
    }
    order.save(update_fields=["data", "updated_at"])

    _summary, _ack, fetch = _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 9)])

    fetch.assert_not_called()
    order.refresh_from_db()
    assert order_composition.is_adjusted(order) is False
    assert order.data["ifood"]["patches"][0]["reconciliation"] == "blocked:fiscal_authorized"
    alert = OperatorAlert.objects.get(type="ifood_order_patched")
    assert alert.severity == "error"
    assert "AINDA DÁ TEMPO DE CANCELAR" in alert.message


@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_a_closed_order_is_recorded_but_not_reopened(status):
    _world()
    order = _ingest()
    Order.objects.filter(pk=order.pk).update(status=status)

    _summary, _ack, fetch = _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 9)])

    fetch.assert_not_called()
    order.refresh_from_db()
    assert order.status == status
    assert order.data["ifood"]["patches"][0]["reconciliation"] == "blocked:terminal"


def test_an_order_already_out_the_door_adjusts_the_money_but_not_the_stock():
    """A documentação não promete que ORDER_PATCHED pare no despacho.

    O pão já foi com o entregador: creditá-lo de volta inventaria pão que não
    está na prateleira. O AJUSTE vale — é o que a plataforma vai pagar —, e o
    aviso diz ao operador que o físico ficou por conta dele.
    """
    _world()
    order = _ingest()
    stock.hold(order)
    stock.fulfill(order)
    Order.objects.filter(pk=order.pk).update(status="dispatched")

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 1)])

    order.refresh_from_db()
    assert order_composition.effective_total_q(order) == 500
    assert _returned(PAO) == Decimal("0")
    assert order.data["ifood"]["patches"][0]["reconciliation"]["stock"] == {"skipped": "goods_left"}
    assert "estoque NÃO foi ajustado" in OperatorAlert.objects.get(type="ifood_order_patched").message


def test_a_failed_reread_falls_back_to_the_stage_one_behaviour():
    """Sem a releitura não há o que reconciliar — mas o operador não fica sem saber."""
    _world()
    _ingest()
    with (
        patch.object(ifood_events, "acknowledge", return_value=True) as ack,
        patch.object(ifood_orders, "fetch_order", side_effect=ifood_orders.IFoodOrderFetchError("403")),
    ):
        summary = ifood_events.process_events([_patch_event()])

    assert summary["ingested"] == 1
    ack.assert_called_once()  # ACK sai: o fato está gravado e alguém foi chamado
    order = Order.objects.get(external_ref=ORDER_ID)
    assert order.data["ifood"]["patches"][0]["reconciled"] is False
    assert order.data["ifood"]["patches"][0]["reconciliation"] == "blocked:fetch_failed"
    alert = OperatorAlert.objects.get(type="ifood_order_patched")
    assert alert.severity == "error"
    assert "portal do iFood" in alert.message


def test_a_patch_before_the_order_exists_is_still_left_unacknowledged():
    """Continua sendo a única exceção de pé: sem pedido, não há onde gravar."""
    _world()
    summary, ack, _fetch = _process(_patch_event(), final_items=_ORIGINAL)

    assert summary["failed"] == 1
    ack.assert_not_called()


# ── 6. O aviso ao operador conta a verdade dos dois casos ─────────────────────


def test_the_reconciled_warning_says_what_changed_and_that_the_shop_kept_up():
    _world()
    order = _ingest()
    kds.dispatch(order)
    stock.hold(order)

    _process(_patch_event(), final_items=[_line(PAO, "Pão francês", 4)])

    alert = OperatorAlert.objects.get(type="ifood_order_patched")
    # Reconciliado não é erro: é conferência. Vermelho aqui gastaria o alarme.
    assert alert.severity == "warning"
    assert alert.order_ref == order.ref
    assert "de 2 para 4" in alert.message
    assert "Café coado" in alert.message  # saiu do pedido
    assert "R$ 15,00" in alert.message and "R$ 20,00" in alert.message
    assert "a cozinha recebeu" in alert.message
