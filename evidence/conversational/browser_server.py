"""Servidor sintético v3 para QA local do Admin do concierge.

Exige banco PostgreSQL isolado informado por ``CONCIERGE_BROWSER_DATABASE_URL``.
Nenhum adapter deste harness acessa rede ou credencial externa.
"""

import os
import sys
from pathlib import Path

root = Path.cwd()
sys.path[:0] = [str(root), *[str(path) for path in sorted((root / "packages").iterdir()) if path.is_dir()]]
database_url = os.environ.get("CONCIERGE_BROWSER_DATABASE_URL", "").strip()
if not database_url:
    raise SystemExit("CONCIERGE_BROWSER_DATABASE_URL precisa apontar para PostgreSQL isolado")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
os.environ["DATABASE_URL"] = database_url
os.environ.pop("REDIS_URL", None)
os.environ["AI_ASSIST_API_KEY"] = ""
os.environ["SHOPMAN_CONCIERGE_ENABLED"] = "false"

import django

django.setup()

from django.conf import settings

return_enabled = os.environ.get("BROWSER_RETURN_GATE") == "true"
settings.SHOPMAN_CONCIERGE = {
    "enabled": True,
    "contract_version": 3,
    "read_only": True,
    "human_return_enabled": return_enabled,
    "connections": {
        "browser-manychat-whatsapp": {
            "active": True,
            "provider": "manychat",
            "account": "browser-manychat-account",
            "channel": "whatsapp",
            "adapter_path": "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter",
            "options": {
                "allowed_subjects": ["synthetic-browser-wa"],
                "stable_event_identity_verified": False,
            },
        },
        "browser-tiktok-dm": {
            "active": True,
            "provider": "tiktok",
            "account": "browser-tiktok-account",
            "channel": "direct_message",
            "adapter_path": "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter",
            "options": {
                "allowed_subjects": ["synthetic-browser-tiktok"],
                "stable_event_identity_verified": False,
            },
        },
    },
}
settings.AI_ASSIST_API_KEY = "synthetic-no-network"
settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

from django.core.management import call_command

if sys.argv[1:] == ["seed"]:
    call_command("migrate", verbosity=0)

    from django.contrib.auth.models import Permission, User
    from django.utils import timezone

    from shopman.shop.models import (
        Conversation,
        ConversationBinding,
        ConversationMessage,
        OutboundAttempt,
        Shop,
    )

    Shop.objects.get_or_create(name="Loja Sintética", defaults={"brand_name": "QA Local", "short_name": "QA"})
    for name in ("synthetic-admin", "synthetic-viewer"):
        user, _ = User.objects.get_or_create(username=name)
        user.set_password("test-only-concierge-browser")
        user.is_staff = True
        user.is_superuser = name == "synthetic-admin"
        user.save()
        if not user.is_superuser:
            user.user_permissions.set(
                [
                    Permission.objects.get(
                        content_type__app_label="shop",
                        codename="view_conversation",
                    )
                ]
            )

    # A base é exclusiva deste harness. Limpar na ordem de PROTECT torna cada
    # execução determinística sem esconder qualquer dado de outro ambiente.
    OutboundAttempt.objects.all().delete()
    ConversationMessage.objects.all().delete()
    ConversationBinding.objects.all().delete()
    Conversation.objects.all().delete()

    now = timezone.now()
    conversation = Conversation.objects.create(
        customer_name="Cliente Sintético",
        customer_ref="customer-browser-v3",
        state=Conversation.State.HANDOFF,
        handoff_reason="Pedido de atendimento",
        handoff_at=now,
        last_inbound_at=now,
        last_outbound_at=now,
    )
    whatsapp = ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="browser-manychat-account",
        transport_channel="whatsapp",
        subject="synthetic-browser-wa",
        connection_key="browser-manychat-whatsapp",
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.CONFIGURED_TRANSPORT,
        handoff_sync_state="unknown",
        last_inbound_at=now,
        last_outbound_at=now,
        activated_at=now,
    )
    tiktok = ConversationBinding.objects.create(
        conversation=conversation,
        provider="tiktok",
        account="browser-tiktok-account",
        transport_channel="direct_message",
        subject="synthetic-browser-tiktok",
        connection_key="browser-tiktok-dm",
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.TRANSPORT_SUBJECT,
        handoff_sync_state="accepted",
        last_outbound_at=now,
        activated_at=now,
    )
    ConversationMessage.objects.create(
        conversation=conversation,
        binding=whatsapp,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="Quero falar com alguém e manter o contexto do meu pedido.",
        content=[{"type": "text", "text": "Quero falar com alguém e manter o contexto do meu pedido."}],
        envelope={
            "version": 3,
            "input_assurance": "at_least_once",
            "event_identity_assurance": "unavailable",
        },
    )
    unknown_reply = ConversationMessage.objects.create(
        conversation=conversation,
        binding=whatsapp,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text="Pedido registrado. O pagamento ainda precisa ser consultado.",
        content=[{"type": "text", "text": "Pedido registrado. O pagamento ainda precisa ser consultado."}],
        transport_state="unknown",
        envelope={"version": 3, "purpose": "reply"},
    )
    OutboundAttempt.objects.create(
        message=unknown_reply,
        binding=whatsapp,
        attempt_no=1,
        state=OutboundAttempt.State.UNKNOWN,
        code="synthetic_timeout",
        payload_hash="0" * 64,
        completed_at=now,
    )
    accepted_reply = ConversationMessage.objects.create(
        conversation=conversation,
        binding=tiktok,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text="Contexto preservado no segundo canal sintético.",
        content=[{"type": "text", "text": "Contexto preservado no segundo canal sintético."}],
        transport_state="accepted",
        envelope={"version": 3, "purpose": "reply"},
    )
    OutboundAttempt.objects.create(
        message=accepted_reply,
        binding=tiktok,
        attempt_no=1,
        state=OutboundAttempt.State.ACCEPTED,
        code="synthetic_acceptance",
        provider_receipt_ref="synthetic-tiktok-receipt",
        payload_hash="1" * 64,
        completed_at=now,
    )
    print(f"BROWSER_V3_CONVERSATION {conversation.pk}")
else:
    call_command("runserver", "127.0.0.1:58419", use_reloader=False)
