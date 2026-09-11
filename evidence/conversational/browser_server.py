"""Servidor exclusivamente sintético para QA local do Admin concierge."""
import os
import sys
from pathlib import Path

root = Path.cwd()
sys.path[:0] = [str(root), *[str(path) for path in sorted((root / "packages").iterdir()) if path.is_dir()]]
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
os.environ["DATABASE_URL"] = "postgres://concierge_test@localhost:56419/concierge_browser"
os.environ["REDIS_URL"] = "redis://localhost:56420/10"
os.environ["AI_ASSIST_API_KEY"] = ""
os.environ["SHOPMAN_CONCIERGE_ENABLED"] = "false"
import django

django.setup()
from django.conf import settings

settings.SHOPMAN_CONCIERGE = {"enabled": True, "contract_version": 2, "account_id": "browser-test", "allowed_subscribers": ["synthetic-browser"], "human_return_enabled": os.environ.get("BROWSER_RETURN_GATE") == "true"}
settings.AI_ASSIST_API_KEY = "synthetic-no-network"
settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
from django.core.management import call_command

if sys.argv[1:] == ["seed"]:
    call_command("migrate", verbosity=0)
    from django.contrib.auth.models import Permission, User
    from django.utils import timezone

    from shopman.shop.models import Conversation, Shop
    from shopman.shop.models import ConversationMessage as Message
    Shop.objects.get_or_create(name="Loja Sintética", defaults={"brand_name": "QA Local", "short_name": "QA"})
    for name in ("synthetic-admin", "synthetic-viewer"):
        user, _ = User.objects.get_or_create(username=name)
        user.set_password("test-only-concierge-browser")
        user.is_staff = True
        user.is_superuser = name == "synthetic-admin"
        user.save()
        if not user.is_superuser:
            user.user_permissions.add(Permission.objects.get(codename="view_conversation"))
    conversation, _ = Conversation.objects.get_or_create(subscriber_id="synthetic-browser", account="browser-test", defaults={"customer_name": "Cliente Sintético", "state": "handoff", "handoff_sync_state": "unknown", "handoff_reason": "Pedido de atendimento", "last_inbound_at": timezone.now()})
    if not conversation.messages.exists():
        Message.objects.create(conversation=conversation, role="user", kind="inbound", text="Quero falar com alguém.", envelope={"version": 2})
        Message.objects.create(conversation=conversation, role="assistant", kind="reply", text="Pedido registrado. O pagamento ainda precisa ser consultado.", transport_state="unknown")
    print("BROWSER_CONVERSATION", conversation.pk)
else:
    call_command("runserver", "127.0.0.1:58419", use_reloader=False)
