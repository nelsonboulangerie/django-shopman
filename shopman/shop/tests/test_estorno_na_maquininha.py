"""Cancelar ou devolver venda paga na maquininha manda estornar NA maquininha (P0-2).

A maquininha é física: o sistema só atesta a captura, e só pode atestar o
estorno depois que alguém o fez no cartão do cliente. Até 13/10/2026 o cancel
gravava ``REFUND`` no Payman sozinho (``_refund_without_gateway``) e ninguém era
mandado estornar: o livro dizia "estornado", o cliente seguia cobrado.

O que esta suíte prende:

- cancelar, devolver tudo ou devolver parte de uma venda no crédito/débito NÃO
  estorna no livro; vira a pendência "Estornar na maquininha", com valor,
  forma, motivo, caixa e hora da venda;
- a pendência aparece no PDV (de qualquer canal: a maquininha não é a gaveta)
  e no sino do Gestor (aviso que leva à Sessão de caixa do PDV);
- só o gesto "Estornei na maquininha" (quem, quando, quem autorizou) grava o
  estorno no Payman, fecha a pendência e resolve o aviso;
- na venda mista, o dinheiro segue na pendência da gaveta e só a parte da
  maquininha vai para a maquininha.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Channel, Shop
from shopman.shop.services import cancellation
from shopman.shop.services import payment as payment_service
from shopman.shop.services import pos as pos_service

pytestmark = pytest.mark.django_db


class _Balcao:
    """Venda direta no PDV, com catálogo mínimo e um turno de caixa aberto."""

    def __init__(self):
        from shopman.cashman import services as cash
        from shopman.offerman.models import Product

        self.operator = get_user_model().objects.create_user(username="marina", password="x")
        self.manager = get_user_model().objects.create_user(username="gerente", password="x")
        self.shift = cash.open_shift(operator=self.operator, float_q=10000)
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False},
            },
        )
        Product.objects.create(
            sku="POS-ITEM", name="Item de balcão", base_price_q=1200, is_published=True, is_sellable=True,
        )

    def vender(self, *, client_request_id: str, **overrides) -> Order:
        payload = {
            "items": [{"sku": "POS-ITEM", "name": "Item de balcão", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente PDV",
            "payment_method": "credit",
            "client_request_id": client_request_id,
            "cash_shift_id": self.shift.pk,
        }
        payload.update(overrides)
        result = pos_service.close_sale(
            channel_ref="pdv", payload=payload, actor="pos:marina", operator_username="marina",
        )
        return Order.objects.get(ref=result.order_ref)


@pytest.fixture
def balcao():
    return _Balcao()


def _cancelar(order, capture):
    with capture(execute=True):
        pos_service.cancel_recent_order(order_ref=order.ref, actor="pos:marina")
    order.refresh_from_db()
    return order


def _concluir(order) -> None:
    """A venda já entregue ao cliente (o caminho até lá não é o assunto aqui)."""
    Order.objects.filter(pk=order.pk).update(status=Order.Status.COMPLETED)
    order.refresh_from_db()


def _refunds(order_ref: str) -> int:
    return sum(
        PaymentTransaction.objects.filter(intent__order_ref=order_ref, type="refund").values_list("amount_q", flat=True)
    )


def test_cancelar_venda_no_credito_nao_marca_estornado_e_manda_estornar(balcao, django_capture_on_commit_callbacks):
    order = _cancelar(balcao.vender(client_request_id="cm-cancel"), django_capture_on_commit_callbacks)

    assert order.status == Order.Status.CANCELLED
    (intent,) = PaymentIntent.objects.filter(order_ref=order.ref)
    # O livro não diz que o dinheiro voltou: ninguém estornou no cartão ainda.
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert _refunds(order.ref) == 0

    (pendente,) = payment_service.pending_card_machine_refunds()
    assert (pendente.order_ref, pendente.amount_q, pendente.method, pendente.reason) == (
        order.ref, 1200, "credit", "cancelled",
    )
    assert pendente.paid_at, "a hora da venda é como se acha a transação na maquininha"

    alerta = OperatorAlert.objects.get(type="card_machine_refund_due", order_ref=order.ref)
    assert alerta.audience == "orders"
    assert "R$ 12,00" in alerta.message and "crédito" in alerta.message
    assert "Estornei na maquininha" in alerta.message
    assert not alerta.resolved_at
    # No sino do Gestor, o aviso leva aonde o gesto mora: a Sessão de caixa do PDV.
    from shopman.backstage.projections.alerts import alert_context_href

    assert alert_context_href(alerta, surface="") == ("/session", "Registrar o estorno no PDV")
    # E o cancelamento no balcão diz na hora o estorno a fazer.
    from shopman.backstage.api.operations import _card_machine_refund_due

    assert _card_machine_refund_due(order.ref) == {
        "amount_q": 1200, "amount_display": "R$ 12,00", "method_label": "crédito",
    }


def test_so_o_estornei_grava_o_estorno_com_quem_e_fecha_a_pendencia(balcao, django_capture_on_commit_callbacks):
    order = _cancelar(balcao.vender(client_request_id="cm-estornei"), django_capture_on_commit_callbacks)

    with django_capture_on_commit_callbacks(execute=True):
        gravado = payment_service.record_card_machine_refund(order, actor="marina", approved_by=balcao.manager)

    assert gravado == 1200
    (intent,) = PaymentIntent.objects.filter(order_ref=order.ref)
    assert PaymentService.refunded_total(intent.ref) == 1200
    assert payment_service.pending_card_machine_refunds() == []
    evento = order.events.get(type="card_machine_refund_recorded")
    assert evento.actor == "marina"
    assert evento.payload["amount_q"] == 1200 and evento.payload["approved_by"] == "gerente"
    assert OperatorAlert.objects.get(type="card_machine_refund_due", order_ref=order.ref).resolved_at
    # A segunda vez não acha o que registrar.
    assert payment_service.record_card_machine_refund(order, actor="marina") == 0


def test_venda_mista_separa_a_gaveta_da_maquininha(balcao, django_capture_on_commit_callbacks):
    order = balcao.vender(
        client_request_id="cm-mista",
        payment_method="mixed",
        payment_tenders=[
            {"method": "cash", "amount_q": 500, "collection": "terminal"},
            {"method": "debit", "amount_q": 700, "collection": "terminal"},
        ],
    )
    # Cancelar fora da janela do balcão (Gestor, de noite): nada sai da gaveta agora.
    with django_capture_on_commit_callbacks(execute=True):
        cancellation.cancel(order, reason="gestor", actor="gestor")
    order.refresh_from_db()

    assert _refunds(order.ref) == 0
    (dinheiro,) = payment_service.pending_cash_refunds()
    assert dinheiro.amount_q == 500
    (maquininha,) = payment_service.pending_card_machine_refunds()
    assert (maquininha.amount_q, maquininha.method) == (700, "debit")


def test_devolucao_total_vira_pendencia_na_maquininha(balcao, django_capture_on_commit_callbacks):
    order = balcao.vender(client_request_id="cm-devolve-tudo")
    _concluir(order)
    with django_capture_on_commit_callbacks(execute=True):
        order.transition_status(Order.Status.RETURNED, actor="test")

    assert _refunds(order.ref) == 0
    (pendente,) = payment_service.pending_card_machine_refunds()
    assert (pendente.amount_q, pendente.reason) == (1200, "returned")


def test_devolucao_parcial_estorna_so_o_devolvido(balcao, django_capture_on_commit_callbacks):
    from shopman.shop.handlers.returns import ReturnService

    order = balcao.vender(
        client_request_id="cm-devolve-parte",
        items=[{"sku": "POS-ITEM", "name": "Item de balcão", "qty": 2, "unit_price_q": 1200}],
    )
    _concluir(order)
    line_id = order.items.first().line_id
    result = ReturnService.initiate_return(order, [{"line_id": line_id, "qty": 1}], reason="defeito", actor="gestor")
    assert result.success, result.error
    order.refresh_from_db()
    ReturnService.process_refund(order, 1200, "return.process", refund_reference=f"return:{order.ref}:0")

    assert _refunds(order.ref) == 0
    (pendente,) = payment_service.pending_card_machine_refunds()
    assert (pendente.amount_q, pendente.reason) == (1200, "partial_return")

    order.refresh_from_db()
    assert payment_service.record_card_machine_refund(order, actor="marina", approved_by=balcao.manager) == 1200
    (intent,) = PaymentIntent.objects.filter(order_ref=order.ref)
    # O que o cliente ficou continua pago.
    assert PaymentService.captured_total(intent.ref) - PaymentService.refunded_total(intent.ref) == 1200
    assert payment_service.pending_card_machine_refunds() == []


def test_pendencia_da_maquininha_aparece_no_pdv_qualquer_que_seja_o_canal(balcao, django_capture_on_commit_callbacks):
    """A maquininha não é a gaveta: a entrega cobrada no cartão também se estorna no balcão."""
    order = balcao.vender(client_request_id="cm-canal")
    Order.objects.filter(pk=order.pk).update(channel_ref="delivery")
    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        cancellation.cancel(order, reason="gestor", actor="gestor")

    from shopman.backstage.projections.pos import _pending_card_machine_refunds

    (linha,) = _pending_card_machine_refunds(balcao.shift)
    assert linha.order_ref == order.ref
    assert linha.reason_label == "Venda cancelada"
    assert linha.amount_display == "R$ 12,00"
