"""Ensaio pg_dump/restore somente nos bancos sintéticos privados deste trabalho."""
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

sys.argv = ["browser_server.py", "seed"]
runpy.run_path("evidence/conversational/browser_server.py", run_name="__main__")
from django.db import connections
from shopman.orderman.models import IdempotencyKey, Order

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message

order, _ = Order.objects.get_or_create(ref="SYNTHETIC-BACKUP-ORDER", defaults={"channel_ref": "web", "session_key": "synthetic-backup-session"})
receipt, _ = IdempotencyKey.objects.get_or_create(scope="synthetic-backup", key="same-intent", defaults={"status": "done", "response_body": {"order_ref": order.ref}})
conversation = Conversation.objects.get(subscriber_id="synthetic-browser")
unknown, _ = Message.objects.get_or_create(conversation=conversation, external_id="synthetic-backup-output", defaults={"role": "assistant", "kind": "reply", "text": "Estado sintético preservado", "transport_state": "unknown", "envelope": {"version": 2}})
connections.close_all()

import psycopg

source = "postgres://concierge_test@localhost:56419/concierge_browser"
target = "postgres://concierge_test@localhost:56419/concierge_restore"
with psycopg.connect("host=localhost port=56419 user=concierge_test dbname=postgres", autocommit=True) as admin:
    if admin.execute("SELECT 1 FROM pg_database WHERE datname = 'concierge_restore'").fetchone():
        raise RuntimeError("Synthetic restore database already exists; do not overwrite it")
    admin.execute("CREATE DATABASE concierge_restore")
with tempfile.TemporaryDirectory(prefix="concierge-synthetic-backup-") as directory:
    archive = Path(directory) / "synthetic.dump"
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--dbname", source, "--file", str(archive)], check=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    subprocess.run(["pg_restore", "--no-owner", "--no-acl", "--dbname", target, str(archive)], check=True)
    with psycopg.connect(target) as restored:
        order_count = restored.execute("SELECT COUNT(*) FROM orderman_order WHERE ref = %s", (order.ref,)).fetchone()[0]
        saved_receipt = restored.execute("SELECT response_body FROM orderman_idempotencykey WHERE scope = %s AND key = %s", ("synthetic-backup", "same-intent")).fetchone()[0]
        state, delivered = restored.execute("SELECT transport_state, delivered FROM shop_conversationmessage WHERE external_id = %s", ("synthetic-backup-output",)).fetchone()
        assert order_count == 1
        assert saved_receipt == {"order_ref": order.ref}
        assert state == "unknown" and delivered is None
    print("SYNTHETIC_BACKUP " + json.dumps({"source": "concierge_browser", "restored": "concierge_restore", "archive_sha256": digest, "order_count": order_count, "receipt_preserved": True, "output_state": state, "no_automatic_send": True}, sort_keys=True))
