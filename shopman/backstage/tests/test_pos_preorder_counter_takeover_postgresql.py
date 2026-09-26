"""Prova PostgreSQL da arbitragem webhook × cancelamento no balcão."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connection, connections
from django.utils import timezone
from rest_framework.response import Response
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.api import operations
from shopman.shop.adapters import payment_mock
from shopman.shop.adapters.payment_types import PaymentResult
from shopman.shop.services import counter_takeover

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


def test_duas_requisicoes_com_a_mesma_chave_executam_um_unico_efeito_remoto(monkeypatch):
    remote_started = Event()
    release_remote = Event()
    calls = []
    monkeypatch.setattr(operations, "_terminal_do_pedido", lambda _request: "POS-1")

    def execute_remote():
        calls.append("remote")
        remote_started.set()
        assert release_remote.wait(timeout=10)
        return Response({"ok": True}, status=200)

    def submit():
        close_old_connections()
        try:
            request = SimpleNamespace(
                data={"client_request_id": "same-concurrent-key", "amount_q": 3600},
                user=SimpleNamespace(pk=42),
                path="/api/v1/backstage/pos/preorders/PG-IDEM/hand-over/",
            )
            return operations._cash_remote_idempotent(
                request, acao="preorder-hand-over", executar=execute_remote,
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(submit)
        assert remote_started.wait(timeout=10)
        loser = pool.submit(submit)
        blocked = loser.result(timeout=10)
        assert blocked.status_code == 409
        assert blocked.data["error"]["code"] == "cash_mutation_in_progress"
        release_remote.set()
        applied = winner.result(timeout=10)

    assert applied.status_code == 200
    assert calls == ["remote"]


def test_webhook_vence_se_chega_entre_intencao_duravel_e_baixa_local(monkeypatch):
    order = Order.objects.create(
        ref="PIX-TAKEOVER-WINDOW",
        channel_ref="web",
        status="ready",
        total_q=3600,
        data={
            "fulfillment_type": "pickup",
            "delivery_date": timezone.localdate().isoformat(),
            "payment": {},
        },
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=3600, line_total_q=3600,
    )
    intent = PaymentService.create_intent(order.ref, 3600, "pix", gateway="mock", gateway_id="txid-window")
    order.data["payment"] = {
        "method": "pix",
        "intent_ref": intent.ref,
        "amount_q": 3600,
        "expires_at": (timezone.now() + timezone.timedelta(hours=1)).isoformat(),
    }
    order.save(update_fields=["data"])

    cancel_entered = Event()
    release_cancel = Event()

    def paused_cancel(*_args, **_kwargs):
        cancel_entered.set()
        assert release_cancel.wait(timeout=10)
        return PaymentResult(success=False, message="pagamento venceu a corrida")

    monkeypatch.setattr(payment_mock, "cancel", paused_cancel)

    def take_over():
        close_old_connections()
        try:
            current = Order.objects.get(pk=order.pk)
            with pytest.raises(counter_takeover.PaidOnline):
                counter_takeover.take_over_pending_digital_charge(
                    current, actor="pos:marina", attempt_id="window-attempt",
                )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(take_over)
        assert cancel_entered.wait(timeout=10)

        observed = Order.objects.get(pk=order.pk)
        marker = observed.data["payment"]["counter_takeover_intent"]
        assert marker["cancelled_intent_ref"] == intent.ref
        assert counter_takeover.arbitrate_pending_takeover_for_online_payment(observed, intent.ref) is True
        observed.refresh_from_db()
        assert observed.data["payment"]["counter_takeover_intent"]["state"] == "online_paid"
        PaymentService.authorize(intent.ref, gateway_id="e2e-window")
        PaymentService.capture(intent.ref, gateway_id="e2e-window")
        release_cancel.set()
        future.result(timeout=10)

    order.refresh_from_db()
    intent.refresh_from_db()
    assert intent.status == "captured"
    assert "counter_takeover_intent" not in order.data["payment"]
    assert "counter_takeover" not in order.data["payment"]
