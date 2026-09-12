"""WP10: expansão sintética e contenção preservam dados/recibos, sem provider."""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from shopman.orderman.models import Directive, IdempotencyKey, Order

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import service, transport

pytestmark = pytest.mark.django_db(transaction=True)


def config(settings, *, enabled=False):
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    settings.SHOPMAN_CONCIERGE = {"enabled": enabled, "contract_version": 2, "account_id": "test-account", "allowed_subscribers": ["synthetic"]}


def test_expand_legacy_rows_preserves_evidence_without_inventing_authority(settings):
    config(settings)
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old_target = [("shop", "0047_rotulos_campos_auditoria_marketing")]
    try:
        executor.migrate(old_target)
        apps = executor.loader.project_state(old_target).apps
        OldConversation = apps.get_model("shop", "Conversation")
        OldMessage = apps.get_model("shop", "ConversationMessage")
        old = OldConversation.objects.create(subscriber_id="legacy-subject", session_key="legacy-cart", quote={"token": "legacy-quote"})
        inbound = OldMessage.objects.create(conversation=old, role="user", kind="inbound", text="sim", external_id="old-message-id")
        output = OldMessage.objects.create(conversation=old, role="assistant", kind="reply", text="Resposta histórica", delivered=True)
        order = Order.objects.create(ref="MIGRATION-ORDER", channel_ref="web", session_key="legacy-cart", data={})
        receipt = IdempotencyKey.objects.create(scope="synthetic-migration", key="stable-intent", status="done", response_body={"order_ref": order.ref})
        MigrationExecutor(connection).migrate(latest)
        current = Conversation.objects.get(pk=old.pk)
        incoming = Message.objects.get(pk=inbound.pk)
        outgoing = Message.objects.get(pk=output.pk)
        assert current.account == "legacy_unverified"
        assert current.turn_fence == 0 and current.claim_until is None
        assert current.session_key == "legacy-cart"
        assert incoming.external_id == "old-message-id"
        assert incoming.consumed_by is None and incoming.envelope == {}
        assert outgoing.delivered is True and outgoing.transport_state == "legacy"
        assert transport.adapter_for(current) is None
        assert service.unanswered_inbound(current) == []
        assert Order.objects.get(pk=order.pk).ref == "MIGRATION-ORDER"
        assert IdempotencyKey.objects.get(pk=receipt.pk).response_body == {"order_ref": order.ref}
        assert not Directive.objects.filter(topic=service.TURN_TOPIC).exists()
    finally:
        MigrationExecutor(connection).migrate(latest)


def test_recovery_during_containment_preserves_receipts_and_does_not_send(settings, monkeypatch):
    config(settings)
    conversation = Conversation.objects.create(subscriber_id="synthetic", account="test-account", customer_ref="customer", claim_until=timezone.now()-timedelta(minutes=5), turn_fence=4, last_inbound_at=timezone.now())
    inbound = Message.objects.create(conversation=conversation, role="user", kind="inbound", text="Minha próxima ação?", envelope={"version": 2})
    output = Message.objects.create(conversation=conversation, role="assistant", kind="reply", text="Pedido registrado", transport_state="executing", envelope={"version": 2, "turn_fence": 4})
    prepared = service._prepare_reply(conversation, "Meio de pagamento pendente")
    order = Order.objects.create(ref="ROLLBACK-ORDER", session_key="rollback-cart", channel_ref="web", data={})
    receipt = IdempotencyKey.objects.create(scope="synthetic-rollback", key="stable-intent", status="done", response_body={"order_ref": order.ref})
    monkeypatch.setattr(transport, "send_text", lambda *args: pytest.fail("containment attempted provider"))
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
    Conversation.objects.bulk_create([Conversation(subscriber_id=f"idle-{i}", account="test-account") for i in range(100)])
    conversation = Conversation.objects.create(subscriber_id="synthetic", account="test-account", customer_ref="customer")
    Message.objects.create(conversation=conversation, role="user", kind="inbound", text="Retomar", envelope={"version": 2})
    service.recover_pending(limit=100)
    assert Directive.objects.filter(topic=service.TURN_TOPIC, payload__conversation_id=conversation.pk, status="queued").count() == 1


def test_interrupted_handoff_sync_becomes_unknown_without_reactivation(settings, monkeypatch):
    config(settings)
    conversation = Conversation.objects.create(subscriber_id="synthetic", account="test-account", state="handoff", handoff_sync_state="executing", handoff_at=timezone.now()-timedelta(minutes=5))
    Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now()-timedelta(minutes=5))
    monkeypatch.setattr(transport, "set_handoff", lambda *args: pytest.fail("must not retry uncertain remote handoff"))
    service.recover_pending()
    conversation.refresh_from_db()
    assert conversation.state == "handoff"
    assert conversation.handoff_sync_state == "unknown"
