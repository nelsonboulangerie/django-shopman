"""O iFood recusa o cancelamento que a loja pediu: o pedido destrava e alguém é avisado.

P0-4 do mapa de cenários de pedido. A loja pede o cancelamento
(``requestCancellation`` volta 202, estado ``sent``) e o pedido fica TRAVADO
esperando o CAN. Quando o iFood recusa, chega ``CANCELLATION_REQUEST_FAILED``.
Antes ele caía no alerta genérico de evento sem tratamento, e o pedido ficava
"cancelamento pendente" para sempre: ninguém aceitava, ninguém avançava.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections import ifood as ifood_projection
from shopman.shop.handlers.ifood_status import IFoodStatusCallbackHandler
from shopman.shop.models import Channel
from shopman.shop.services import cancellation, ifood_callbacks, ifood_cancellation, ifood_events, operator_orders

CFG = {"client_id": "test", "client_secret": "test", "cancellation_default_code": "501"}


def _refused(order_id="ifood-order", event_id="evt-refused", metadata=None):
    event = {"id": event_id, "code": "CANCELLATION_REQUEST_FAILED", "fullCode": "CANCELLATION_REQUEST_FAILED",
             "orderId": order_id, "createdAt": "2026-10-13T12:00:00Z"}
    if metadata is not None:
        event["metadata"] = metadata
    return event


@override_settings(SHOPMAN_IFOOD=CFG)
class IFoodCancellationRefusedTests(TestCase):
    def setUp(self):
        Channel.objects.create(ref="ifood", name="iFood", config={
            "confirmation": {"mode": "manual"}, "payment": {"method": "external", "timing": "external"},
            "stock": {"check_on_commit": False}, "notification": {"backend": "console"},
        })
        self.order = Order.objects.create(
            ref="IFD-RECUSA", channel_ref="ifood", external_ref="ifood-order", status="new",
            data={"payment": {"method": "external", "gateway": "ifood"}, "ifood": {"display_id": "4821"}},
        )
        cancellation.cancel(self.order, reason="Sem estoque", actor="operator:ana")
        directive = Directive.objects.get(topic="ifood.status_callback", payload__order_ref=self.order.ref)
        with patch.object(ifood_callbacks, "send_for_status", return_value=True):
            IFoodStatusCallbackHandler().handle(message=directive, ctx={})
        self.order.refresh_from_db()
        assert self.order.data[ifood_cancellation.KEY]["state"] == "sent"

    def process(self, events):
        with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
            summary = ifood_events.process_events(events)
        return summary, ack

    def test_refusal_unlocks_the_order_in_the_state_it_was(self):
        self.assertTrue(ifood_cancellation.is_pending(self.order))
        with self.assertRaises(operator_orders.OrderStateConflict):
            operator_orders.confirm_order(self.order, actor="operator:a")

        summary, ack = self.process([_refused(metadata={"reason": "Pedido já saiu para entrega."})])

        self.assertEqual(summary["ingested"], 1)
        self.assertEqual(ack.call_args[0][0], ["evt-refused"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")
        self.assertFalse(ifood_cancellation.is_pending(self.order))
        request = self.order.data[ifood_cancellation.KEY]
        self.assertEqual(request["state"], "refused")
        self.assertEqual(request["refusal_reason"], "Pedido já saiu para entrega.")
        self.assertEqual(request["refusal_event_id"], "evt-refused")
        # Destravado: o aceite volta a valer.
        self.assertEqual(operator_orders.confirmation_block_reason(self.order), "")
        operator_orders.confirm_order(self.order, actor="operator:a")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "accepted")

    def test_refusal_alert_carries_the_reason_and_both_ways_out(self):
        self.process([_refused(metadata={"reason": "Pedido já saiu para entrega."})])

        alert = OperatorAlert.objects.get(type=ifood_cancellation.REFUSED_ALERT_TYPE)
        self.assertEqual(alert.order_ref, self.order.ref)
        self.assertEqual(alert.severity, "error")
        self.assertEqual(alert.audience, "orders")
        self.assertIn("iFood #4821", alert.message)
        self.assertIn("Motivo do iFood: Pedido já saiu para entrega.", alert.message)
        self.assertIn("siga com ele ou tente cancelar de novo", alert.message)
        self.assertNotIn("—", alert.message)
        # Não cai mais no alerta genérico de evento sem tratamento.
        self.assertFalse(OperatorAlert.objects.filter(type="ifood_event_unhandled").exists())
        # O card do pedido diz o mesmo.
        self.order.refresh_from_db()
        notice = ifood_projection.cancellation_notice(self.order)
        self.assertIn("O iFood recusou o cancelamento", notice)
        self.assertIn("Pedido já saiu para entrega", notice)

    def test_refusal_without_reason_says_so(self):
        self.process([_refused()])

        alert = OperatorAlert.objects.get(type=ifood_cancellation.REFUSED_ALERT_TYPE)
        self.assertIn("O iFood não informou o motivo.", alert.message)
        self.order.refresh_from_db()
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["refusal_reason"], "")

    def test_cancel_again_after_refusal_queues_a_new_request(self):
        self.process([_refused()])
        self.order.refresh_from_db()

        cancellation.cancel(self.order, reason="Cliente desistiu", actor="operator:ana",
                            extra_data={"ifood_cancellation_code": "502"})

        self.order.refresh_from_db()
        self.assertTrue(ifood_cancellation.is_pending(self.order))
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["state"], "queued")
        self.assertEqual(Directive.objects.filter(topic="ifood.status_callback").count(), 2)

    def test_confirmation_held_while_pending_applies_after_refusal(self):
        # O iFood confirmou o pedido enquanto o cancelamento esperava: o CFM fica
        # sem aplicar (o aceite está travado). A recusa destrava e a
        # reconciliação aplica o fato guardado.
        data = dict(self.order.data)
        data["ifood"] = {**data["ifood"], "remote_confirmed": {"event_id": "evt-cfm", "observed_at": "2026-10-13T11:59:00Z"}}
        self.order.data = data
        self.order.save(update_fields=["data"])

        self.process([_refused()])

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "accepted")

    def test_redelivered_refusal_is_deduped_and_alerts_once(self):
        self.process([_refused()])
        summary, _ = self.process([_refused()])

        self.assertEqual(summary["deduped"], 1)
        self.assertEqual(OperatorAlert.objects.filter(type=ifood_cancellation.REFUSED_ALERT_TYPE).count(), 1)

    def test_refusal_with_nothing_pending_changes_nothing(self):
        cancellation.cancel(self.order, reason="iFood confirmou", actor="system:ifood", extra_data={"ifood_cancelled": True})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

        summary, ack = self.process([_refused()])

        self.assertEqual(summary["deduped"], 1)
        self.assertEqual(ack.call_args[0][0], ["evt-refused"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["state"], "confirmed")
        self.assertFalse(OperatorAlert.objects.filter(type=ifood_cancellation.REFUSED_ALERT_TYPE).exists())

    def test_refusal_for_unknown_order_stays_unacked_for_redelivery(self):
        summary, ack = self.process([_refused(order_id="outro-pedido")])

        self.assertEqual(summary["failed"], 1)
        ack.assert_not_called()

    def test_definite_send_failure_also_alerts(self):
        # A recusa também pode vir na hora do envio (4xx definitivo): o pedido já
        # destravava, mas ninguém era avisado.
        order = Order.objects.create(
            ref="IFD-RECUSA-ENVIO", channel_ref="ifood", external_ref="ifood-order-2", status="new",
            data={"payment": {"method": "external", "gateway": "ifood"}},
        )
        cancellation.cancel(order, reason="Sem estoque", actor="operator:ana")
        directive = Directive.objects.get(topic="ifood.status_callback", payload__order_ref=order.ref)
        with patch.object(ifood_callbacks, "send_for_status",
                          side_effect=ifood_callbacks.IFoodCallbackError("bad code", retryable=False)):
            with self.assertRaises(DirectiveTerminalError):
                IFoodStatusCallbackHandler().handle(message=directive, ctx={})

        order.refresh_from_db()
        self.assertFalse(ifood_cancellation.is_pending(order))
        alert = OperatorAlert.objects.get(type=ifood_cancellation.REFUSED_ALERT_TYPE, order_ref=order.ref)
        self.assertIn("O iFood recusou o cancelamento do pedido IFD-RECUSA-ENVIO", alert.message)
