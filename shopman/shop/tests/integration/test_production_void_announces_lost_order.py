"""Lote cancelado com encomenda paga vinculada vira fato do pedido (#2547).

Antes o cancelamento soltava a reserva do pedido aceito com "Produção cancelada"
e só a sacola aberta ficava sabendo. O cliente tinha lido "Pedido garantido para
amanhã", e o Gestor não mostrava nada. Agora o pedido ganha o evento na linha do
tempo e o Gestor, o aviso no sino com o pedido nomeado, sem ninguém abrir painel.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.service import CraftService as craft
from shopman.orderman.models import Order, OrderEvent
from shopman.stockman import stock
from shopman.stockman.models import Hold, HoldStatus

from shopman.backstage.models import OperatorAlert

pytestmark = pytest.mark.django_db


def _hold(product, qty, *, reference, target_date):
    hold_id = stock.hold(quantity=Decimal(qty), product=product, target_date=target_date, reference=reference)
    stock.confirm(hold_id)
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def _encomenda(ref, *, status="accepted", day):
    return Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=5000, data={"delivery_date": day.isoformat()},
    )


def test_cancelar_o_unico_lote_avisa_o_gestor_e_marca_o_pedido(recipe, croissant, position_loja, tomorrow):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    order = _encomenda("ENC-PAGA", day=tomorrow)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    hold = _hold(croissant, "4", reference="order:ENC-PAGA", target_date=tomorrow)

    craft.void(wo, reason="Cancelada")

    hold.refresh_from_db()
    assert hold.status == HoldStatus.RELEASED

    alert = OperatorAlert.objects.get(type="order_promise_lost", order_ref="ENC-PAGA")
    assert alert.audience == "orders"
    assert "Pedido ENC-PAGA" in alert.message
    assert "4 un." in alert.message
    assert "Avise o cliente" in alert.message

    event = OrderEvent.objects.get(order=order, type="production_hold_lost")
    assert event.payload["sku"] == croissant.sku
    assert event.payload["qty"] == "4"
    assert event.payload["work_order_ref"] == wo.ref


def test_pedido_coberto_pela_outra_fornada_nao_e_avisado(recipe, croissant, position_loja, tomorrow):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    _encomenda("ENC-COBERTA", day=tomorrow)
    wo_a = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    _hold(croissant, "8", reference="order:ENC-COBERTA", target_date=tomorrow)

    craft.void(wo_a, reason="Cancelada")

    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


def test_pedido_que_ja_acabou_nao_e_avisado(recipe, croissant, position_loja, tomorrow):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    _encomenda("ENC-CANCELADA", status="cancelled", day=tomorrow)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    _hold(croissant, "4", reference="order:ENC-CANCELADA", target_date=tomorrow)

    craft.void(wo, reason="Cancelada")

    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


def test_o_mesmo_cancelamento_nao_avisa_duas_vezes(recipe, croissant, position_loja, tomorrow):
    from shopman.shop.services import production_promise

    _encomenda("ENC-UMA-VEZ", day=tomorrow)
    for _ in range(2):
        production_promise.announce_lost_holds(
            {"ENC-UMA-VEZ": Decimal("4")}, sku=croissant.sku, date=tomorrow,
        )
    assert OperatorAlert.objects.filter(type="order_promise_lost", order_ref="ENC-UMA-VEZ").count() == 1


# ── #2594: o lote que rende menos e o lote atrasado também viram fato do pedido ──


def _reserva_no_lote(product, qty, *, reference, day):
    """A reserva da encomenda ancorada no saldo planejado do lote do dia.

    É onde o vínculo da encomenda põe a reserva. ``stock.hold`` para HOJE passa
    pela régua de venda (que não oferece o planejado de hoje), e o que se mede
    aqui é o fato do pedido, não a venda.
    """
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401
    from shopman.stockman.models import Quant
    from shopman.stockman.services.holds import (
        QUALITY_GRADE_POLICY_VERSION,
        QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    )

    quant = Quant.objects.filter(sku=product.sku, target_date=day).order_by("pk").first()
    assert quant is not None, "o lote do dia não criou o saldo planejado"
    return Hold.objects.create(
        sku=product.sku, quant=quant, quantity=Decimal(qty), target_date=day,
        status=HoldStatus.PENDING,
        # A marca que ``stock.hold`` grava: sem ela o fechamento do lote não leva a reserva.
        metadata={"reference": reference, QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION},
    )


def test_lote_que_rende_menos_que_a_reserva_avisa_sem_soltar(recipe, croissant, position_loja, today):
    """A reserva que não coube no rendimento fica presa ao saldo de produção zerado."""
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    order = _encomenda("ENC-CURTA", day=today)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
    hold = _reserva_no_lote(croissant, "8", reference="order:ENC-CURTA", day=today)

    craft.finish(wo, finished=Decimal("6"), actor="test")

    hold.refresh_from_db()
    assert hold.status != HoldStatus.RELEASED  # soltar é decisão de gente

    alert = OperatorAlert.objects.get(type="order_promise_lost", order_ref="ENC-CURTA")
    assert "rendeu menos que o reservado" in alert.message
    assert "faltam 8 un." in alert.message
    assert "Avise o cliente" in alert.message

    event = OrderEvent.objects.get(order=order, type="production_hold_short")
    assert event.payload["qty"] == "8"
    assert event.payload["reason"] == "production_short"
    assert event.payload["work_order_ref"] == wo.ref


def test_lote_que_rende_o_bastante_nao_avisa(recipe, croissant, position_loja, today):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    _encomenda("ENC-INTEIRA", day=today)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
    _reserva_no_lote(croissant, "6", reference="order:ENC-INTEIRA", day=today)

    craft.finish(wo, finished=Decimal("8"), actor="test")

    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()
    assert not OrderEvent.objects.filter(type="production_hold_short").exists()


def test_rendeu_menos_mas_o_outro_lote_do_dia_cobre(recipe, croissant, position_loja, today):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    _encomenda("ENC-OUTRO-LOTE", day=today)
    wo_a = craft.plan(recipe, quantity=Decimal("10"), date=today)
    craft.plan(recipe, quantity=Decimal("10"), date=today)
    _reserva_no_lote(croissant, "8", reference="order:ENC-OUTRO-LOTE", day=today)

    craft.finish(wo_a, finished=Decimal("6"), actor="test")

    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


@pytest.fixture
def _ponte_do_estoque():
    """A ponte craftsman→stockman: o plano cria o saldo planejado do lote."""
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401


def _ready_at(monkeypatch, sku, clock):
    from shopman.shop.services import product_readiness

    monkeypatch.setattr(product_readiness, "ready_times_for", lambda skus, **_: {sku: clock})


def _at(day, hour):
    from datetime import datetime, time

    from django.utils import timezone

    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


def test_lote_que_passou_da_hora_avisa_a_encomenda_uma_vez(_ponte_do_estoque, recipe, croissant, position_loja, today, monkeypatch):
    from datetime import time

    from shopman.shop.services import production_promise

    order = _encomenda("ENC-ATRASADA", day=today)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
    _reserva_no_lote(croissant, "4", reference="order:ENC-ATRASADA", day=today)
    _ready_at(monkeypatch, croissant.sku, time(9, 0))

    assert production_promise.announce_late_lots(now=_at(today, 10)) == 1
    assert production_promise.announce_late_lots(now=_at(today, 11)) == 0

    alert = OperatorAlert.objects.get(type="order_promise_lost", order_ref="ENC-ATRASADA")
    assert "passou da hora de ficar pronto" in alert.message
    assert "4 un. esperam por ele" in alert.message
    events = OrderEvent.objects.filter(order=order, type="production_lot_late")
    assert events.count() == 1
    assert events.get().payload["work_order_ref"] == wo.ref


def test_lote_antes_da_hora_nao_avisa(_ponte_do_estoque, recipe, croissant, position_loja, today, monkeypatch):
    from datetime import time

    from shopman.shop.services import production_promise

    _encomenda("ENC-NO-PRAZO", day=today)
    craft.plan(recipe, quantity=Decimal("10"), date=today)
    _reserva_no_lote(croissant, "4", reference="order:ENC-NO-PRAZO", day=today)
    _ready_at(monkeypatch, croissant.sku, time(15, 0))

    assert production_promise.announce_late_lots(now=_at(today, 10)) == 0
    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


def test_lote_de_amanha_nunca_esta_atrasado_hoje(_ponte_do_estoque, recipe, croissant, position_loja, today, tomorrow, monkeypatch):
    from datetime import time

    from shopman.shop.services import production_promise

    _encomenda("ENC-AMANHA", day=tomorrow)
    craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    _reserva_no_lote(croissant, "4", reference="order:ENC-AMANHA", day=tomorrow)
    _ready_at(monkeypatch, croissant.sku, time(6, 0))

    assert production_promise.announce_late_lots(now=_at(today, 23)) == 0


def test_lote_fechado_nao_esta_atrasado(recipe, croissant, position_loja, today, monkeypatch):
    from datetime import time

    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    from shopman.shop.services import production_promise

    _encomenda("ENC-PRONTA", day=today)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
    _reserva_no_lote(croissant, "4", reference="order:ENC-PRONTA", day=today)
    craft.finish(wo, finished=Decimal("10"), actor="test")
    _ready_at(monkeypatch, croissant.sku, time(6, 0))

    assert production_promise.announce_late_lots(now=_at(today, 23)) == 0


def test_atraso_que_vira_cancelamento_avisa_de_novo(recipe, croissant, position_loja, today, monkeypatch):
    """Atraso e cancelamento são fatos diferentes: o segundo não fica preso no debounce do primeiro."""
    from datetime import time

    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    from shopman.shop.services import production_promise

    _encomenda("ENC-ATRASO-E-FIM", day=today)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
    _reserva_no_lote(croissant, "4", reference="order:ENC-ATRASO-E-FIM", day=today)
    _ready_at(monkeypatch, croissant.sku, time(9, 0))
    production_promise.announce_late_lots(now=_at(today, 10))

    craft.void(wo, reason="Cancelada")

    assert OperatorAlert.objects.filter(type="order_promise_lost", order_ref="ENC-ATRASO-E-FIM").count() == 2



# ── #3229: a baixa que falha por reserva sem lastro diz a causa real ─────────


def test_baixa_do_pedido_sem_lastro_diz_o_fato_do_lote_e_nao_manda_contar_a_prateleira(
    recipe, croissant, position_loja, today,
):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    from shopman.shop.services import stock as stock_service

    order = _encomenda("ENC-SEM-LASTRO", day=today)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
    hold = _reserva_no_lote(croissant, "8", reference="order:ENC-SEM-LASTRO", day=today)
    order.data["hold_ids"] = [{"sku": croissant.sku, "hold_id": hold.hold_id, "qty": 8.0}]
    order.save(update_fields=["data"])
    craft.finish(wo, finished=Decimal("6"), actor="test")

    stock_service.fulfill(order)

    alert = OperatorAlert.objects.get(type="stock_fulfill_failed", order_ref="ENC-SEM-LASTRO")
    assert "rendeu menos que o reservado" in alert.message
    assert "faltam 8 un." in alert.message
    assert "A prateleira está certa. Resolva no pedido: avise o cliente, remarque ou cancele." in alert.message
    assert "Conte esses itens" not in alert.message


def test_baixa_que_falha_sem_fato_de_lote_segue_mandando_conferir_a_prateleira(croissant, position_loja, today):
    from shopman.shop.services import production_promise

    order = _encomenda("ENC-SEM-FATO", day=today)
    assert production_promise.fulfill_failure_fact(order, [croissant.sku]) == ""
