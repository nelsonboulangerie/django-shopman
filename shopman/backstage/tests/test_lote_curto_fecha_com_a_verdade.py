"""O lote curto fecha com a verdade (WP-F06, P0-2 do plano de excelência da Produção).

Decisão 1 do dono (23/11/2026): o lote que rendeu menos que o encomendado fecha com
o que rendeu, o pão entra no estoque uma única vez, e os pedidos que ficaram sem pão
aparecem em "Promessa em risco" no Gestor. Antes, a tela mandava "informar pelo menos
6" e o botão de revisar não fazia nada: o pão assado ficava fora do estoque.

A recusa vira pergunta informada: a primeira tentativa devolve os pedidos que ficam
descobertos; a confirmação volta com o MESMO impacto e fecha. Tudo pelo caminho real
(pedido da loja, reserva pelo commit, lote pelos serviços da tela), como em
``test_iniciar_lote_leva_a_reserva``.
"""

# A fixture ``ficha`` vem do teste irmão e entra como parâmetro de cada teste.
# ruff: noqa: F811

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import WorkOrder, WorkOrderEvent
from shopman.orderman.models import OrderEvent

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production
from shopman.backstage.tests.test_iniciar_lote_leva_a_reserva import (  # noqa: F401 (fixtures)
    ACTOR,
    SKU,
    _hoje,
    _iniciar,
    _onde,
    _pedido_da_loja,
    _planejar,
    _saldos,
    ficha,
)

pytestmark = pytest.mark.django_db


def _fechar(work_order, qty, *, aprovado=None, chave=None):
    work_order.refresh_from_db()
    return production.apply_finish(
        work_order_id=work_order.pk,
        quantity=str(qty),
        actor=ACTOR,
        expected_rev=work_order.rev,
        idempotency_key=chave or f"finish-curto-{work_order.pk}",
        partition=[{"quantity": str(qty), "quality_grade_ref": "standard"}],
        yield_deviation_confirmed=True,
        yield_deviation_reason="Contagem conferida.",
        approved_short_lot=aprovado,
    )


def _recusa_ao_fechar(work_order, qty) -> production.ProductionOrderShortError:
    with pytest.raises(production.ProductionOrderShortError) as recusa:
        _fechar(work_order, qty)
    return recusa.value


def test_rendeu_4_de_6_encomendados_pergunta_e_fecha_com_a_verdade(ficha, django_capture_on_commit_callbacks):
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(6)
        _iniciar(lote, 10)

    recusa = _recusa_ao_fechar(lote, 4)
    assert recusa.confirmable is True
    assert recusa.required == Decimal("6")
    assert recusa.requested == Decimal("4")
    assert recusa.orders == ((order.ref, Decimal("6")),)
    lote.refresh_from_db()
    assert lote.status == WorkOrder.Status.STARTED, "sem a confirmação, nada fecha"

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, 4, aprovado=production.production_shortage_snapshot(recusa))

    lote.refresh_from_db()
    assert lote.status == WorkOrder.Status.FINISHED
    # O pão entra no estoque, inteiro. A reserva do pedido não coube e fica onde
    # estava, esperando quem cuida das encomendas: soltar é decisão de gente (#3149).
    assert _saldos() == {"vitrine": (Decimal("4"), Decimal("0")), "em_producao": (Decimal("0"), Decimal("6"))}
    assert _onde(order) == "em_producao"
    # O fato fica com o lote: quanto rendeu, quanto faltou, para quem, e quem confirmou.
    finished = lote.events.get(kind=WorkOrderEvent.Kind.FINISHED)
    shortfall = finished.payload["context"]["order_shortfall"]
    assert shortfall == {
        "required_qty": "6",
        "saleable_qty": "4",
        "short_qty": "2",
        "orders": [{"ref": order.ref, "qty": "6"}],
        "confirmed_by": ACTOR,
    }
    # O Gestor fica sabendo pelo caminho de sempre (#3149): "Promessa em risco".
    assert OperatorAlert.objects.filter(type="order_promise_lost", order_ref=order.ref).count() == 1
    assert OrderEvent.objects.filter(order=order, type="production_hold_short").exists()


def test_o_reenvio_da_confirmacao_nao_dobra_estoque_nem_aviso(ficha, django_capture_on_commit_callbacks):
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(6)
        _iniciar(lote, 10)
    aprovado = production.production_shortage_snapshot(_recusa_ao_fechar(lote, 4))

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, 4, aprovado=aprovado, chave="finish-curto-mesma-tentativa")
    antes = (_saldos(), OperatorAlert.objects.filter(order_ref=order.ref).count(), OrderEvent.objects.count())

    # A resposta se perdeu e a tela manda de novo, na mesma tentativa.
    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, 4, aprovado=aprovado, chave="finish-curto-mesma-tentativa")

    assert (_saldos(), OperatorAlert.objects.filter(order_ref=order.ref).count(), OrderEvent.objects.count()) == antes
    assert lote.events.filter(kind=WorkOrderEvent.Kind.FINISHED).count() == 1


def test_confirmacao_de_outro_impacto_volta_a_perguntar(ficha, django_capture_on_commit_callbacks):
    """Outro pedido entrou depois da pergunta: a confirmação antiga não vale para o impacto novo."""
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        _pedido_da_loja(6)
        _iniciar(lote, 10)
    aprovado = production.production_shortage_snapshot(_recusa_ao_fechar(lote, 4))

    with pytest.raises(production.ProductionOrderShortError) as de_novo:
        _fechar(lote, 3, aprovado=aprovado)

    assert de_novo.value.requested == Decimal("3")
    lote.refresh_from_db()
    assert lote.status == WorkOrder.Status.STARTED


def test_abrir_abaixo_do_encomendado_pergunta_e_abre(ficha, django_capture_on_commit_callbacks):
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(6)

    lote.refresh_from_db()
    with pytest.raises(production.ProductionOrderShortError) as recusa:
        production.apply_start(
            work_order_id=lote.pk,
            quantity="4",
            actor=ACTOR,
            expected_rev=lote.rev,
            idempotency_key=f"start-curto-{lote.pk}",
        )
    assert recusa.value.confirmable is True
    assert recusa.value.orders == ((order.ref, Decimal("6")),)

    lote.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        production.apply_start(
            work_order_id=lote.pk,
            quantity="4",
            actor=ACTOR,
            expected_rev=lote.rev,
            idempotency_key=f"start-curto-{lote.pk}",
            approved_short_lot=production.production_shortage_snapshot(recusa.value),
        )

    lote.refresh_from_db()
    assert lote.status == WorkOrder.Status.STARTED
    assert lote.started_qty == Decimal("4")


def test_a_conta_desconta_o_que_o_pedido_ja_tem_na_prateleira(ficha, monkeypatch):
    """P1-03: a trava conta o que a produção deve, não as linhas seladas do pedido.

    O pedido de 6 que já tem 2 reservados na vitrine espera 4 do lote; o que já foi
    todo servido da vitrine não espera nada e nem aparece na pergunta.
    """
    from shopman.orderman.models import Order, OrderItem

    from shopman.shop.handlers import production_order_sync

    def pedido(ref, qty):
        order = Order.objects.create(ref=ref, channel_ref="web", status="accepted", total_q=0, data={})
        OrderItem.objects.create(
            order=order, line_id=f"{ref}-1", sku=SKU, name=SKU, qty=qty, unit_price_q=0, line_total_q=0
        )
        return order

    parcial, servido = pedido("P1-03-PARCIAL", 6), pedido("P1-03-SERVIDO", 3)
    monkeypatch.setattr(
        production_order_sync,
        "_shelf_quantities",
        lambda orders: {(parcial.ref, SKU): Decimal("2"), (servido.ref, SKU): Decimal("3")},
    )

    required, lines = production._production_demand([parcial, servido], SKU)

    assert required == Decimal("4")
    assert lines == ((parcial.ref, Decimal("4")),)
