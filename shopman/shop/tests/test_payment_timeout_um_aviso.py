"""Pix vencido: o cliente recebe UM aviso só (P1-9, 14/10/2026).

Antes, o vencimento mandava dois: ``payment_expired`` ("liberamos a reserva") e,
logo atrás, o ``order_cancelled`` genérico do lifecycle ("seu pedido foi
cancelado"). Duas mensagens sobre o mesmo fato, a segunda sem dizer por quê.

Agora o vencimento é o ``order_cancelled`` com a frase do prazo vencido no
``status_note``: o que aconteceu, que nada foi cobrado e o que fazer se ainda
quiser. Vale para os dois caminhos que vencem o prazo (a directive
``payment.timeout`` e o vencimento preguiçoso do acompanhamento), e o registro
operacional (``cancellation_reason``, ``payment_timeout_at``) continua no pedido.
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
from shopman.shop.services import cancel_reasons
from shopman.shop.services import payment as payment_service
from shopman.shop.services.customer_orders import resolve_payment_timeout_if_due

pytestmark = pytest.mark.django_db


def _overdue_order(ref: str, method: str) -> Order:
    from shopman.payman import PaymentService

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    intent_ref = f"INT-{ref}"
    PaymentService.create_intent(ref, 5000, method, gateway="efi", ref=intent_ref)
    expired = (timezone.now() - timedelta(minutes=5)).isoformat()
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=5000,
        handle_type="phone",
        handle_ref="+5543999990001",
        data={
            "fulfillment_type": "pickup",
            "customer": {"name": "Joyce", "phone": "+5543999990001"},
            "payment": {"method": method, "intent_ref": intent_ref, "expires_at": expired},
        },
    )


def _unpaid_gateway():
    adapter = SimpleNamespace(check_gateway_status=lambda intent_ref: "pending", capture=lambda intent_ref: None)
    return patch.object(payment_service, "_adapter_for_persisted_intent", return_value=adapter)


def _customer_notices(order: Order) -> list[Directive]:
    return list(Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref))


def _assert_one_notice(order: Order, expected_key: str) -> None:
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    # O registro operacional não se perde: o código de máquina e a hora do vencimento.
    assert order.data["cancellation_reason"] == "payment_timeout"
    assert order.data["payment_timeout_at"]
    assert order.data["cancellation_reason_key"] == expected_key

    notices = _customer_notices(order)
    assert [n.payload["template"] for n in notices] == ["order_cancelled"]
    assert notices[0].payload["status_note"] == cancel_reasons.cancel_reason(expected_key).customer_text


@pytest.mark.parametrize(("method", "key"), [("pix", "pix_expired"), ("card", "payment_deadline_passed")])
def test_directive_do_vencimento_manda_um_aviso_so(method, key, django_capture_on_commit_callbacks):
    order = _overdue_order(f"ORD-1AVISO-DIR-{method}", method)
    directive = Directive.objects.create(
        topic=PAYMENT_TIMEOUT,
        payload={"order_ref": order.ref, "intent_ref": order.data["payment"]["intent_ref"]},
    )

    with _unpaid_gateway(), django_capture_on_commit_callbacks(execute=True):
        PaymentTimeoutHandler().handle(message=directive, ctx={})

    _assert_one_notice(order, key)


def test_vencimento_preguicoso_do_acompanhamento_manda_um_aviso_so(django_capture_on_commit_callbacks):
    order = _overdue_order("ORD-1AVISO-LAZY", "pix")

    with _unpaid_gateway(), django_capture_on_commit_callbacks(execute=True):
        assert resolve_payment_timeout_if_due(order) is True

    _assert_one_notice(order, "pix_expired")


def test_a_frase_diz_o_que_houve_o_dinheiro_e_o_que_fazer():
    for key in ("pix_expired", "payment_deadline_passed"):
        text = cancel_reasons.cancel_reason(key).customer_text
        assert "nada foi cobrado" in text
        assert "Se ainda quiser, é só fazer um novo pedido." in text
        assert "—" not in text
        # Frase inteira com ponto: entra no meio do template aprovado `pedido_cancelado`.
        assert text.endswith(".")
