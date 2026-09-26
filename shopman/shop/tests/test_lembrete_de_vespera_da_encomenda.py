"""O lembrete de véspera espera dias na fila — e confere a encomenda antes de falar.

"Sua encomenda é amanhã" para quem cancelou (ou já buscou) é mentira dita na voz
da casa. O lembrete nasce no commit (orderman) e só é lido pelo handler na
véspera: é ali, na última leitura antes do envio, que o estado atual decide.
"""
from unittest.mock import patch

import pytest
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.notification import NotificationSendHandler
from shopman.shop.services import notification

pytestmark = pytest.mark.django_db


def _lembrete(order: Order) -> Directive:
    return Directive.objects.create(
        topic="notification.send",
        payload={
            "order_ref": order.ref,
            "template": "preorder_reminder",
            "context": {"customer_name": "Ana", "delivery_date": "2026-10-03", "delivery_time_slot": "slot-09"},
        },
    )


@pytest.mark.parametrize("status", ["cancelled", "returned", "dispatched", "delivered", "completed"])
def test_encomenda_que_morreu_ou_ja_saiu_nao_recebe_lembrete(status):
    order = Order.objects.create(ref=f"ENC-{status}", status=status, total_q=1000, data={"delivery_date": "2026-10-03"})
    directive = _lembrete(order)

    with patch.object(notification, "deliver_order_notification", return_value=(True, None)) as deliver:
        NotificationSendHandler().handle(message=directive, ctx={})
        deliver.assert_not_called()

    directive.refresh_from_db()
    assert directive.payload["notification_delivery"]["status"] == "skipped"
    assert directive.payload["notification_delivery"]["reason"] == "preorder_not_awaiting"


@pytest.mark.parametrize("status", ["new", "accepted", "preparing", "ready"])
def test_encomenda_viva_recebe_o_lembrete(status):
    order = Order.objects.create(ref=f"ENC-VIVA-{status}", status=status, total_q=1000, data={"delivery_date": "2026-10-03"})
    directive = _lembrete(order)

    with patch.object(notification, "deliver_order_notification", return_value=(True, None)) as deliver:
        NotificationSendHandler().handle(message=directive, ctx={})
        deliver.assert_called_once()
