"""Persistência canônica: conversa lógica separada de transporte e tentativas."""

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, connection, connections, router, transaction
from django.db.migrations.executor import MigrationExecutor

from shopman.shop.models.concierge import (
    Conversation,
    ConversationBinding,
    ConversationMessage,
    OutboundAttempt,
)

pytestmark = pytest.mark.django_db(transaction=True)


class _MigrationAliasRouter:
    """Keep historical RunPython operations inside the isolated database."""

    def __init__(self, alias):
        self.alias = alias

    def db_for_read(self, model, **hints):
        return self.alias

    def db_for_write(self, model, **hints):
        return self.alias


def test_0051_moves_transport_without_losing_logical_conversation(tmp_path, django_db_blocker):
    before = [("shop", "0050_concierge_admin_labels")]
    after = [("shop", "0051_concierge_transport_bindings")]
    alias = "transport_migration"
    database_access = django_db_blocker.unblock()
    database_access.__enter__()
    isolated = None
    alias_router = _MigrationAliasRouter(alias)

    try:
        connections.databases[alias] = {
            **connections.databases["default"],
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(tmp_path / "transport-migration.sqlite3"),
            "OPTIONS": {},
            "TEST": {"CHARSET": None, "COLLATION": None, "MIGRATE": True, "MIRROR": None, "NAME": None},
        }
        router.routers.insert(0, alias_router)
        isolated = connections[alias]
        executor = MigrationExecutor(isolated)
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        OldConversation = old_apps.get_model("shop", "Conversation")
        OldMessage = old_apps.get_model("shop", "ConversationMessage")
        conversation = OldConversation.objects.using(alias).create(
            subscriber_id="subject-123",
            provider="manychat",
            account="account-1",
            transport_channel="whatsapp",
            customer_ref="customer-1",
            session_key="cart-1",
            quote={"token": "quote-1"},
            handoff_sync_state="accepted",
        )
        inbound = OldMessage.objects.using(alias).create(
            conversation=conversation,
            role="user",
            kind="inbound",
            text="Quero pão",
            external_id="event-digest",
        )
        reply = OldMessage.objects.using(alias).create(
            conversation=conversation,
            role="assistant",
            kind="reply",
            text="Claro.",
            transport_state="accepted",
            delivered=True,
        )
        tool = OldMessage.objects.using(alias).create(
            conversation=conversation,
            role="assistant",
            kind="tool_call",
            content=[{"type": "tool_use", "name": "browse_menu"}],
        )

        executor = MigrationExecutor(isolated)
        executor.migrate(after)
        new_apps = executor.loader.project_state(after).apps
        NewConversation = new_apps.get_model("shop", "Conversation")
        Binding = new_apps.get_model("shop", "ConversationBinding")
        Message = new_apps.get_model("shop", "ConversationMessage")
        Attempt = new_apps.get_model("shop", "OutboundAttempt")

        current = NewConversation.objects.using(alias).get(pk=conversation.pk)
        assert current.customer_ref == "customer-1"
        assert current.session_key == "cart-1"
        assert current.quote == {"token": "quote-1"}
        for removed in ("subscriber_id", "provider", "account", "transport_channel", "handoff_sync_state"):
            with pytest.raises(FieldDoesNotExist):
                NewConversation._meta.get_field(removed)

        binding = Binding.objects.using(alias).get(conversation_id=current.pk)
        assert (
            binding.provider,
            binding.account,
            binding.transport_channel,
            binding.subject,
            binding.status,
            binding.handoff_sync_state,
        ) == ("manychat", "account-1", "whatsapp", "subject-123", "active", "accepted")
        assert binding.connection_key == "manychat-whatsapp-primary"
        assert Message.objects.using(alias).get(pk=inbound.pk).binding_id == binding.pk
        assert Message.objects.using(alias).get(pk=reply.pk).binding_id == binding.pk
        assert Message.objects.using(alias).get(pk=tool.pk).binding_id is None
        with pytest.raises(FieldDoesNotExist):
            Message._meta.get_field("delivered")

        attempt = Attempt.objects.using(alias).get(message_id=reply.pk)
        assert attempt.binding_id == binding.pk
        assert attempt.attempt_no == 1
        assert attempt.state == "delivered"
        assert attempt.code == "migrated_delivery_evidence"
        assert len(attempt.payload_hash) == 64

        executor = MigrationExecutor(isolated)
        executor.migrate(before)
        restored_apps = executor.loader.project_state(before).apps
        RestoredConversation = restored_apps.get_model("shop", "Conversation")
        RestoredMessage = restored_apps.get_model("shop", "ConversationMessage")
        restored = RestoredConversation.objects.using(alias).get(pk=conversation.pk)
        assert (
            restored.provider,
            restored.account,
            restored.transport_channel,
            restored.subscriber_id,
            restored.handoff_sync_state,
        ) == ("manychat", "account-1", "whatsapp", "subject-123", "accepted")
        assert RestoredMessage.objects.using(alias).get(pk=reply.pk).delivered is True
    finally:
        router.routers.remove(alias_router)
        if isolated is not None:
            isolated.close()
        connections.databases.pop(alias, None)
        database_access.__exit__(None, None, None)


def test_0051_flushes_postgresql_deferred_fk_triggers():
    """The backfill must settle FK triggers before building new indexes."""
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL-only migration regression")

    before = [("shop", "0050_concierge_admin_labels")]
    after = [("shop", "0051_concierge_transport_bindings")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    executor.migrate(before)

    try:
        old_apps = MigrationExecutor(connection).loader.project_state(before).apps
        OldConversation = old_apps.get_model("shop", "Conversation")
        OldMessage = old_apps.get_model("shop", "ConversationMessage")
        conversation = OldConversation.objects.create(
            subscriber_id="subject-postgresql-regression",
            provider="manychat",
            account="account-1",
            transport_channel="whatsapp",
            customer_ref="customer-1",
            handoff_sync_state="accepted",
        )
        inbound = OldMessage.objects.create(
            conversation=conversation,
            role="user",
            kind="inbound",
            text="Quero pão",
            external_id="event-postgresql-regression",
        )
        reply = OldMessage.objects.create(
            conversation=conversation,
            role="assistant",
            kind="reply",
            text="Claro.",
            transport_state="accepted",
            delivered=True,
        )

        MigrationExecutor(connection).migrate(after)
        new_apps = MigrationExecutor(connection).loader.project_state(after).apps
        Binding = new_apps.get_model("shop", "ConversationBinding")
        Message = new_apps.get_model("shop", "ConversationMessage")
        Attempt = new_apps.get_model("shop", "OutboundAttempt")
        binding = Binding.objects.get(conversation_id=conversation.pk)

        assert Message.objects.get(pk=inbound.pk).binding_id == binding.pk
        assert Message.objects.get(pk=reply.pk).binding_id == binding.pk
        assert Attempt.objects.get(message_id=reply.pk).state == "delivered"
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, Message._meta.db_table)
        assert "shop_cmsg_binding_event_unique" in constraints
        assert "shop_cmsg_transport_binding_required" in constraints
    finally:
        MigrationExecutor(connection).migrate(latest)


def test_transport_constraints_are_scoped_to_binding():
    first = Conversation.objects.create(customer_ref="customer-1")
    second = Conversation.objects.create(customer_ref="customer-2")
    whatsapp = ConversationBinding.objects.create(
        conversation=first,
        provider="manychat",
        account="account-1",
        transport_channel="whatsapp",
        subject="subject-1",
        connection_key="manychat-whatsapp-primary",
        status="active",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ConversationBinding.objects.create(
            conversation=second,
            provider="manychat",
            account="account-1",
            transport_channel="whatsapp",
            subject="subject-1",
            connection_key="manychat-whatsapp-secondary",
            status="active",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        ConversationBinding.objects.create(
            conversation=first,
            provider="meta",
            account="waba-1",
            transport_channel="whatsapp",
            subject="subject-2",
            connection_key="meta-whatsapp-primary",
            status="active",
        )

    instagram = ConversationBinding.objects.create(
        conversation=first,
        provider="meta",
        account="instagram-1",
        transport_channel="instagram",
        subject="subject-1",
        connection_key="meta-instagram-primary",
        status="active",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ConversationMessage.objects.create(
            conversation=first,
            role="user",
            kind="inbound",
            text="Sem rota",
            external_id="event-without-binding",
        )

    first_event = ConversationMessage.objects.create(
        conversation=first,
        binding=whatsapp,
        role="user",
        kind="inbound",
        text="Oi no WhatsApp",
        external_id="same-provider-event",
    )
    ConversationMessage.objects.create(
        conversation=first,
        binding=instagram,
        role="user",
        kind="inbound",
        text="Oi no Instagram",
        external_id="same-provider-event",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ConversationMessage.objects.create(
            conversation=first,
            binding=whatsapp,
            role="user",
            kind="inbound",
            text="Duplicada",
            external_id=first_event.external_id,
        )


def test_outbound_attempts_keep_receipts_and_attempt_numbers_distinct():
    conversation = Conversation.objects.create(customer_ref="customer-1")
    whatsapp = ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="account-1",
        transport_channel="whatsapp",
        subject="subject-1",
        connection_key="manychat-whatsapp-primary",
        status="active",
    )
    instagram = ConversationBinding.objects.create(
        conversation=conversation,
        provider="meta",
        account="instagram-1",
        transport_channel="instagram",
        subject="subject-1",
        connection_key="meta-instagram-primary",
        status="active",
    )
    whatsapp_reply = ConversationMessage.objects.create(
        conversation=conversation,
        binding=whatsapp,
        role="assistant",
        kind="reply",
        text="Resposta",
        transport_state="accepted",
    )
    instagram_reply = ConversationMessage.objects.create(
        conversation=conversation,
        binding=instagram,
        role="assistant",
        kind="reply",
        text="Resposta",
        transport_state="accepted",
    )
    OutboundAttempt.objects.create(
        message=whatsapp_reply,
        binding=whatsapp,
        attempt_no=1,
        state="accepted",
        provider_receipt_ref="receipt-1",
        payload_hash="a" * 64,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OutboundAttempt.objects.create(
            message=whatsapp_reply,
            binding=whatsapp,
            attempt_no=1,
            state="unknown",
            payload_hash="a" * 64,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        OutboundAttempt.objects.create(
            message=whatsapp_reply,
            binding=whatsapp,
            attempt_no=2,
            state="accepted",
            provider_receipt_ref="receipt-1",
            payload_hash="a" * 64,
        )

    other_provider = OutboundAttempt.objects.create(
        message=instagram_reply,
        binding=instagram,
        attempt_no=1,
        state="accepted",
        provider_receipt_ref="receipt-1",
        payload_hash="a" * 64,
    )
    assert other_provider.pk
    assert not hasattr(whatsapp_reply, "provider_receipt_ref")
