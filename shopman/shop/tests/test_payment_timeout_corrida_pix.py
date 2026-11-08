"""Pix pago no limite do prazo: um dono só para o dinheiro (beta 06/11, PIXEXP-01).

O ``payment.timeout`` cancelava a COBRANÇA e só depois o PEDIDO, em transações
separadas. O Pix que caía nesse intervalo encontrava a cobrança morta e o pedido
vivo, e ia para o ramo que abre alerta crítico mandando "devolva pelo gateway".
Logo em seguida o cancelamento estornava sozinho o mesmo dinheiro, e o alerta
ficava aberto para sempre, convidando a um estorno em dobro.

Agora o pedido cancela primeiro e a cobrança morre no ``on_cancelled``. O Pix que
chega antes do cancelamento captura a cobrança viva e salva o pedido.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import PAYMENT_TIMEOUT
from shopman.shop.handlers.payment_timeout import PaymentTimeoutHandler
from shopman.shop.models import Channel
from shopman.shop.services import cancellation
from shopman.shop.services import payment as payment_service

pytestmark = pytest.mark.django_db

TXID = "txid-corrida-prazo-0001"


def _overdue_pix_order(ref: str) -> Order:
    from shopman.payman import PaymentService

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    intent_ref = f"INT-{ref}"
    PaymentService.create_intent(ref, 2200, "pix", gateway="efi", gateway_id=TXID, ref=intent_ref)
    expired = (timezone.now() - timedelta(minutes=1)).isoformat()
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=2200,
        handle_type="phone",
        handle_ref="+5543999990002",
        data={
            "fulfillment_type": "pickup",
            "customer": {"name": "Joyce", "phone": "+5543999990002"},
            "payment": {"method": "pix", "intent_ref": intent_ref, "expires_at": expired},
        },
    )


def _gateway_that_cancels_in_the_ledger():
    """Efí dizendo "não pago" e cancelando a cobrança de verdade no Payman."""
    from shopman.payman import PaymentService

    def _cancel(intent_ref, reason=""):
        PaymentService.cancel(intent_ref, reason=reason)
        return SimpleNamespace(success=True)

    adapter = SimpleNamespace(
        check_gateway_status=lambda intent_ref: "pending",
        capture=lambda intent_ref: None,
        cancel=_cancel,
    )
    return patch.object(payment_service, "_adapter_for_persisted_intent", return_value=adapter)


def test_pix_que_cai_no_limite_do_prazo_nao_abre_alerta_de_devolver_pelo_gateway(
    django_capture_on_commit_callbacks,
):
    from shopman.payman import PaymentService

    from shopman.backstage.models import OperatorAlert
    from shopman.shop.services.pix_confirmation import confirm_pix

    order = _overdue_pix_order("ORD-CORRIDA-PRAZO")
    directive = Directive.objects.create(
        topic=PAYMENT_TIMEOUT,
        payload={"order_ref": order.ref, "intent_ref": order.data["payment"]["intent_ref"]},
    )
    real_cancel = cancellation.cancel

    def _pix_lands_right_before_the_order_cancel(*args, **kwargs):
        # O instante da corrida: o handler já decidiu cancelar, e o Pix cai.
        confirm_pix(txid=TXID, e2e_id="E2E-CORRIDA", amount="22.00")
        return real_cancel(*args, **kwargs)

    with (
        _gateway_that_cancels_in_the_ledger(),
        patch.object(cancellation, "cancel", side_effect=_pix_lands_right_before_the_order_cancel),
        django_capture_on_commit_callbacks(execute=True),
    ):
        PaymentTimeoutHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    intent = PaymentService.get(order.data["payment"]["intent_ref"])
    # O Pix pago no limite salva o pedido: a cobrança estava viva quando ele caiu.
    assert intent.status == "captured"
    assert order.status != Order.Status.CANCELLED
    # E ninguém é mandado devolver um dinheiro que pertence ao pedido.
    assert not OperatorAlert.objects.filter(
        order_ref=order.ref, type__in=("payment_reconciliation_failed", "pix_on_closed_charge"),
    ).exists()


def test_vencimento_visto_pelo_acompanhamento_tambem_cancela_o_pedido_antes_da_cobranca(
    django_capture_on_commit_callbacks,
):
    """O mesmo vencimento, resolvido pelo acompanhamento da Loja (sem worker):
    ``customer_orders.resolve_payment_timeout_if_due`` tinha a mesma ordem
    invertida, e a corrida abria o mesmo alerta de "devolva pelo gateway"."""
    from shopman.payman import PaymentService

    from shopman.backstage.models import OperatorAlert
    from shopman.shop.services.customer_orders import resolve_payment_timeout_if_due
    from shopman.shop.services.pix_confirmation import confirm_pix

    order = _overdue_pix_order("ORD-CORRIDA-LOJA")
    real_cancel = cancellation.cancel

    def _pix_lands_right_before_the_order_cancel(*args, **kwargs):
        confirm_pix(txid=TXID, e2e_id="E2E-CORRIDA-LOJA", amount="22.00")
        return real_cancel(*args, **kwargs)

    with (
        _gateway_that_cancels_in_the_ledger(),
        patch.object(cancellation, "cancel", side_effect=_pix_lands_right_before_the_order_cancel),
        django_capture_on_commit_callbacks(execute=True),
    ):
        cancelled = resolve_payment_timeout_if_due(order)

    order.refresh_from_db()
    intent = PaymentService.get(order.data["payment"]["intent_ref"])
    assert cancelled is False
    assert intent.status == "captured"
    assert order.status != Order.Status.CANCELLED
    assert not OperatorAlert.objects.filter(
        order_ref=order.ref, type__in=("payment_reconciliation_failed", "pix_on_closed_charge"),
    ).exists()
