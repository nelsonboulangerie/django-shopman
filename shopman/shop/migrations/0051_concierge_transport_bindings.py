import hashlib

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
from django.db.models import Q


def move_transport_identity(apps, schema_editor):
    Conversation = apps.get_model("shop", "Conversation")
    Binding = apps.get_model("shop", "ConversationBinding")
    Message = apps.get_model("shop", "ConversationMessage")
    database = schema_editor.connection.alias

    pending = []
    conversations = Conversation.objects.using(database).all().iterator(chunk_size=1000)
    for conversation in conversations:
        unverified = conversation.account == "legacy_unverified"
        configured_manychat = (
            not unverified and conversation.provider == "manychat" and conversation.transport_channel == "whatsapp"
        )
        identity = ":".join(
            (
                conversation.provider,
                conversation.account,
                conversation.transport_channel,
                conversation.subscriber_id,
            )
        )
        pending.append(
            Binding(
                conversation_id=conversation.pk,
                provider=conversation.provider,
                account="unverified" if unverified else conversation.account,
                transport_channel=conversation.transport_channel,
                subject=conversation.subscriber_id,
                connection_key=(
                    "manychat-whatsapp-primary"
                    if configured_manychat
                    else "disabled-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
                ),
                status="active" if configured_manychat else "disabled",
                identity_assurance="unverified" if unverified else "configured_transport",
                handoff_sync_state=(
                    "not_applied" if conversation.handoff_sync_state == "legacy" else conversation.handoff_sync_state
                ),
                last_inbound_at=conversation.last_inbound_at,
                last_outbound_at=conversation.last_outbound_at,
                activated_at=conversation.created_at if configured_manychat else None,
            )
        )
        if len(pending) == 1000:
            Binding.objects.using(database).bulk_create(pending, batch_size=1000)
            pending = []
    if pending:
        Binding.objects.using(database).bulk_create(pending, batch_size=1000)

    bindings = Binding.objects.using(database).values_list("conversation_id", "id").iterator(chunk_size=1000)
    for conversation_id, binding_id in bindings:
        Message.objects.using(database).filter(
            conversation_id=conversation_id,
            kind__in=("inbound", "reply"),
        ).update(binding_id=binding_id)

    # ``transport_state`` permanece como projeção operacional. O bool legado é
    # convertido em evidência append-only antes de a coluna ser removida.
    Attempt = apps.get_model("shop", "OutboundAttempt")
    attempts = []
    terminal_states = {"executing", "accepted", "not_applied", "unknown", "delivered", "read"}
    Message.objects.using(database).filter(transport_state="legacy").exclude(kind="reply").update(
        transport_state="not_applicable"
    )
    replies = Message.objects.using(database).filter(kind="reply", binding_id__isnull=False).iterator(chunk_size=1000)
    for message in replies:
        state = message.transport_state
        code = ""
        if message.delivered is True:
            state = "delivered"
            code = "migrated_delivery_evidence"
        elif message.delivered is False and state == "legacy":
            state = "not_applied"
            code = "migrated_not_delivered"
        elif state == "legacy":
            state = "unknown"
            code = "migrated_without_delivery_evidence"
        elif state not in terminal_states:
            continue
        Message.objects.using(database).filter(pk=message.pk).update(transport_state=state)
        attempts.append(
            Attempt(
                message_id=message.pk,
                binding_id=message.binding_id,
                attempt_no=1,
                state=state,
                code=code,
                payload_hash=hashlib.sha256((message.text or "").encode()).hexdigest(),
                started_at=message.created_at,
                completed_at=None if state == "executing" else message.created_at,
            )
        )
        if len(attempts) == 1000:
            Attempt.objects.using(database).bulk_create(attempts, batch_size=1000)
            attempts = []
    if attempts:
        Attempt.objects.using(database).bulk_create(attempts, batch_size=1000)

    # PostgreSQL keeps Django's new foreign keys deferred until transaction
    # commit.  The constraints added by the next operations build indexes and
    # require those trigger events to be settled first.  The backend helper
    # validates them now and restores deferred mode without giving up the
    # all-or-nothing migration transaction.
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.connection.check_constraints()


def restore_transport_identity(apps, schema_editor):
    """Collapse the transport split while the v2 schema still represents it.

    A v2 conversation can hold one transport identity.  Refuse a lossy rollback
    when v3 data already uses more than one binding; otherwise restore the old
    columns and its tri-state delivery evidence.
    """
    Conversation = apps.get_model("shop", "Conversation")
    Binding = apps.get_model("shop", "ConversationBinding")
    Message = apps.get_model("shop", "ConversationMessage")
    Attempt = apps.get_model("shop", "OutboundAttempt")
    database = schema_editor.connection.alias

    for conversation in Conversation.objects.using(database).all().iterator(chunk_size=1000):
        bindings = list(
            Binding.objects.using(database)
            .filter(conversation_id=conversation.pk)
            .order_by("id")[:2]
        )
        if len(bindings) != 1:
            raise RuntimeError(
                "shop.0051 rollback requires exactly one transport binding per conversation; "
                f"conversation {conversation.pk} has {len(bindings)}."
            )
        binding = bindings[0]
        Conversation.objects.using(database).filter(pk=conversation.pk).update(
            provider=binding.provider,
            account="legacy_unverified" if binding.account == "unverified" else binding.account,
            transport_channel=binding.transport_channel,
            subscriber_id=binding.subject,
            handoff_sync_state=(
                "legacy" if binding.handoff_sync_state == "not_applied" else binding.handoff_sync_state
            ),
        )

    replies = Message.objects.using(database).filter(kind="reply").iterator(chunk_size=1000)
    for message in replies:
        attempt = (
            Attempt.objects.using(database)
            .filter(message_id=message.pk)
            .order_by("-attempt_no")
            .first()
        )
        delivered = None
        if attempt is not None:
            if attempt.code == "migrated_not_delivered":
                delivered = False
            elif attempt.code == "migrated_delivery_evidence" or attempt.state in {"delivered", "read"}:
                delivered = True
            elif attempt.state == "not_applied":
                delivered = False
        Message.objects.using(database).filter(pk=message.pk).update(delivered=delivered)


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0050_concierge_admin_labels"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConversationBinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=40, verbose_name="provedor")),
                ("account", models.CharField(max_length=128, verbose_name="conta do provedor")),
                ("transport_channel", models.CharField(max_length=40, verbose_name="canal de comunicação")),
                ("subject", models.CharField(max_length=512, verbose_name="identificador no transporte")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendente"),
                            ("active", "Ativo"),
                            ("disabled", "Desativado"),
                        ],
                        default="pending",
                        max_length=16,
                        verbose_name="estado",
                    ),
                ),
                ("connection_key", models.CharField(max_length=80, verbose_name="conexão configurada")),
                (
                    "identity_assurance",
                    models.CharField(
                        choices=[
                            ("unverified", "Sem verificação"),
                            ("transport_subject", "Endereço autenticado do transporte"),
                            ("configured_transport", "Escopo configurado"),
                            ("verified_customer", "Cliente verificado"),
                        ],
                        default="unverified",
                        max_length=32,
                        verbose_name="garantia de identidade",
                    ),
                ),
                (
                    "handoff_sync_state",
                    models.CharField(
                        default="not_applied",
                        max_length=24,
                        verbose_name="sincronização do atendimento humano",
                    ),
                ),
                (
                    "last_inbound_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="última mensagem recebida"),
                ),
                (
                    "last_outbound_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="última resposta enviada"),
                ),
                ("activated_at", models.DateTimeField(blank=True, null=True, verbose_name="ativado em")),
                ("deactivated_at", models.DateTimeField(blank=True, null=True, verbose_name="desativado em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transport_bindings",
                        to="shop.conversation",
                        verbose_name="conversa",
                    ),
                ),
            ],
            options={
                "verbose_name": "vínculo de transporte do concierge",
                "verbose_name_plural": "vínculos de transporte do concierge",
                "ordering": ("conversation_id", "transport_channel", "id"),
                "indexes": [
                    models.Index(fields=["conversation", "status"], name="shop_cbind_conv_status_idx"),
                    models.Index(fields=["status", "last_inbound_at"], name="shop_cbind_status_in_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("provider", "account", "transport_channel", "subject"),
                        name="shop_cbind_identity_unique",
                    ),
                    models.UniqueConstraint(
                        condition=Q(status="active"),
                        fields=("conversation", "transport_channel"),
                        name="shop_cbind_active_channel_unique",
                    ),
                    models.CheckConstraint(
                        condition=(
                            ~Q(provider="")
                            & ~Q(account="")
                            & ~Q(transport_channel="")
                            & ~Q(subject="")
                            & ~Q(connection_key="")
                        ),
                        name="shop_cbind_identity_not_blank",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="conversationmessage",
            name="binding",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="messages",
                to="shop.conversationbinding",
                verbose_name="vínculo de transporte",
            ),
        ),
        migrations.CreateModel(
            name="OutboundAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("attempt_no", models.PositiveIntegerField(verbose_name="número da tentativa")),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("executing", "Em execução"),
                            ("accepted", "Aceita pelo fornecedor"),
                            ("not_applied", "Não aplicada"),
                            ("unknown", "Resultado desconhecido"),
                            ("delivered", "Entregue"),
                            ("read", "Lida"),
                        ],
                        default="executing",
                        max_length=24,
                        verbose_name="estado",
                    ),
                ),
                ("code", models.CharField(blank=True, max_length=80, verbose_name="código do resultado")),
                (
                    "provider_receipt_ref",
                    models.CharField(blank=True, max_length=512, verbose_name="referência no provedor"),
                ),
                ("payload_hash", models.CharField(max_length=64, verbose_name="hash do conteúdo")),
                (
                    "started_at",
                    models.DateTimeField(default=django.utils.timezone.now, verbose_name="iniciada em"),
                ),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="concluída em")),
                (
                    "binding",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="outbound_attempts",
                        to="shop.conversationbinding",
                        verbose_name="vínculo de transporte",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="outbound_attempts",
                        to="shop.conversationmessage",
                        verbose_name="mensagem",
                    ),
                ),
            ],
            options={
                "verbose_name": "tentativa de saída do concierge",
                "verbose_name_plural": "tentativas de saída do concierge",
                "ordering": ("message_id", "attempt_no"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("message", "attempt_no"),
                        name="shop_cattempt_message_no_unique",
                    ),
                    models.UniqueConstraint(
                        condition=~Q(provider_receipt_ref=""),
                        fields=("binding", "provider_receipt_ref"),
                        name="shop_cattempt_binding_receipt_unique",
                    ),
                    models.CheckConstraint(
                        condition=Q(attempt_no__gte=1),
                        name="shop_cattempt_no_positive",
                    ),
                ],
            },
        ),
        migrations.RemoveConstraint(
            model_name="conversationmessage",
            name="shop_convmsg_external_id_unique",
        ),
        migrations.RunPython(move_transport_identity, restore_transport_identity),
        migrations.AddConstraint(
            model_name="conversationmessage",
            constraint=models.UniqueConstraint(
                condition=~Q(external_id=""),
                fields=("binding", "external_id"),
                name="shop_cmsg_binding_event_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversationmessage",
            constraint=models.CheckConstraint(
                condition=Q(kind__in=["tool_call", "tool_result", "note"]) | Q(binding__isnull=False),
                name="shop_cmsg_transport_binding_required",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="conversation",
            name="shop_conv_transport_identity_unique",
        ),
        # The temporary default is used only if this migration is reversed:
        # Django must recreate the non-null v2 column before RunPython can
        # restore its value from ConversationBinding.
        migrations.AlterField(
            model_name="conversation",
            name="subscriber_id",
            field=models.CharField(default="", max_length=512, verbose_name="assinante ManyChat"),
        ),
        migrations.RemoveField(model_name="conversation", name="provider"),
        migrations.RemoveField(model_name="conversation", name="account"),
        migrations.RemoveField(model_name="conversation", name="transport_channel"),
        migrations.RemoveField(model_name="conversation", name="subscriber_id"),
        migrations.RemoveField(model_name="conversation", name="handoff_sync_state"),
        migrations.RemoveField(model_name="conversationmessage", name="delivered"),
        migrations.AlterField(
            model_name="conversationmessage",
            name="transport_state",
            field=models.CharField(
                db_index=True,
                default="not_applicable",
                max_length=24,
                verbose_name="estado do envio",
            ),
        ),
    ]
