"""WP10: expansão sintética e contenção preservam dados/recibos, sem provider."""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Directive, IdempotencyKey, Order

from shopman.shop.models import Conversation, ConversationBinding, OutboundAttempt
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import service, transport

pytestmark = pytest.mark.django_db(transaction=True)


def config(settings, *, enabled=False):
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    settings.SHOPMAN_CONCIERGE = {
        "enabled": enabled,
        "contract_version": 3,
        "connections": {
            "synthetic": {
                "active": True,
                "provider": "opaque-test",
                "account": "test-account",
                "channel": "text-only-test",
                "adapter_path": "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter",
                "options": {"allowed_subjects": ["synthetic"]},
            }
        },
    }


def binding_for(conversation, subject="synthetic"):
    return ConversationBinding.objects.create(
        conversation=conversation,
        provider="opaque-test",
        account="test-account",
        transport_channel="text-only-test",
        subject=subject,
        connection_key="synthetic",
        status="active",
    )


def test_recovery_during_containment_preserves_receipts_and_does_not_send(settings, monkeypatch):
    config(settings)
    conversation = Conversation.objects.create(customer_ref="customer", claim_until=timezone.now()-timedelta(minutes=5), turn_fence=4, last_inbound_at=timezone.now())
    binding = binding_for(conversation)
    inbound = Message.objects.create(conversation=conversation, binding=binding, role="user", kind="inbound", text="Minha próxima ação?", envelope={"version": 3})
    output = Message.objects.create(conversation=conversation, binding=binding, role="assistant", kind="reply", text="Pedido registrado", transport_state="executing", envelope={"version": 3, "turn_fence": 4})
    OutboundAttempt.objects.create(
        message=output,
        binding=binding,
        attempt_no=1,
        state="executing",
        payload_hash="0" * 64,
    )
    prepared = service._prepare_reply(conversation, binding, "Meio de pagamento pendente")
    order = Order.objects.create(ref="ROLLBACK-ORDER", session_key="rollback-cart", channel_ref="web", data={})
    receipt = IdempotencyKey.objects.create(scope="synthetic-rollback", key="stable-intent", status="done", response_body={"order_ref": order.ref})
    monkeypatch.setattr(transport, "send_for", lambda *args: pytest.fail("containment attempted provider"))
    result = StringIO()
    call_command("recover_concierge", stdout=result)
    conversation.refresh_from_db()
    inbound.refresh_from_db()
    output.refresh_from_db()
    prepared.refresh_from_db()
    assert conversation.turn_fence == 5 and conversation.claim_until is None
    assert output.transport_state == "unknown"
    assert prepared.transport_state == "not_applied"
    assert inbound.consumed_by is None
    assert Order.objects.get(pk=order.pk).ref == order.ref
    assert IdempotencyKey.objects.get(pk=receipt.pk).response_body["order_ref"] == order.ref
    assert not Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").exists()
    assert '"unknown": 1' in result.getvalue()


def test_recovery_reaches_pending_conversation_after_hundred_idle_rows(settings):
    config(settings, enabled=True)
    Conversation.objects.bulk_create([Conversation() for _ in range(100)])
    conversation = Conversation.objects.create(customer_ref="customer")
    binding = binding_for(conversation)
    Message.objects.create(conversation=conversation, binding=binding, role="user", kind="inbound", text="Retomar", envelope={"version": 3})
    service.recover_pending(limit=100)
    assert Directive.objects.filter(topic=service.TURN_TOPIC, payload__conversation_id=conversation.pk, status="queued").count() == 1


def test_interrupted_handoff_sync_becomes_unknown_without_reactivation(settings, monkeypatch):
    config(settings)
    conversation = Conversation.objects.create(state="handoff", handoff_at=timezone.now()-timedelta(minutes=5))
    binding = binding_for(conversation)
    ConversationBinding.objects.filter(pk=binding.pk).update(
        handoff_sync_state="executing", updated_at=timezone.now()-timedelta(minutes=5)
    )
    monkeypatch.setattr(transport, "handoff_for", lambda *args: pytest.fail("must not retry uncertain remote handoff"))
    service.recover_pending()
    conversation.refresh_from_db()
    binding.refresh_from_db()
    assert conversation.state == "handoff"
    assert binding.handoff_sync_state == "unknown"
