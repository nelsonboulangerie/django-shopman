"""Carga sintética WP09; mede estágio local, sem certificar WhatsApp ou UX."""
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest
from django.db import connection, connections
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import agent, service, transport

pytestmark = pytest.mark.django_db(transaction=True)


def test_hundred_conversations_ten_thousand_history_and_burst_conserve_inputs(settings, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Synthetic workload requires PostgreSQL")
    subjects = [f"synthetic-load-{i}" for i in range(100)]
    settings.SHOPMAN_CONCIERGE = {"enabled": True, "contract_version": 2, "account_id": "test-load", "allowed_subscribers": subjects}
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    conversations = Conversation.objects.bulk_create([
        Conversation(subscriber_id=subject, account="test-load", customer_ref=f"synthetic-customer-{i}", last_inbound_at=timezone.now()) for i, subject in enumerate(subjects)
    ])
    history = [Message(conversation=c, role="assistant" if i % 2 else "user", kind="reply" if i % 2 else "inbound", text="Contexto sintético histórico", consumed_by=1 if not i % 2 else None, envelope={"version": 2}) for c in conversations for i in range(100)]
    Message.objects.bulk_create(history, batch_size=1000)
    Message.objects.bulk_create([Message(conversation=c, role="user", kind="inbound", text="Retomar escolhas", envelope={"version": 2}) for c in conversations])
    Message.objects.bulk_create([Message(conversation=conversations[0], role="user", kind="inbound", text="Complemento de escolha", envelope={"version": 2}) for _ in range(9)])
    sent, counts = [], []
    mutex = Lock()
    monkeypatch.setattr(agent, "run_agent", lambda **kwargs: agent.AgentOutcome(reply_text="Escolhas preservadas. Qual opção deseja consultar?"))
    def send(subject, text):
        with mutex:
            sent.append(subject)
        return transport.SendOutcome("accepted", "synthetic")
    monkeypatch.setattr(transport, "send_text", send)
    def run(pk):
        started = time.perf_counter()
        query_count = 0
        def count(execute, sql, params, many, context):
            nonlocal query_count
            query_count += 1
            return execute(sql, params, many, context)
        try:
            with connection.execute_wrapper(count):
                result = service.run_turn(pk)
            assert not result.pending_more
            return time.perf_counter()-started, query_count, len(result.processed_message_ids)
        finally:
            connections.close_all()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(run, [c.pk for c in conversations]))
    elapsed = time.perf_counter()-started
    assert len(sent) == len(set(sent)) == 100
    assert sum(item[2] for item in counts) == 109
    assert not Message.objects.filter(kind="inbound", consumed_by__isnull=True).exists()
    assert Message.objects.filter(kind="reply", transport_state="accepted").count() == 100
    assert not Order.objects.exists()
    latencies = sorted(item[0] for item in counts)
    print("SYNTHETIC_LOAD " + json.dumps({"conversations": 100, "history_messages": 10000, "new_inputs": 109, "burst": 10, "parallel_workers": 4, "seconds_total": round(elapsed, 3), "seconds_turn_median": round(statistics.median(latencies), 3), "seconds_turn_p95": round(latencies[94], 3), "seconds_turn_max": round(max(latencies), 3), "queries_total": sum(item[1] for item in counts), "orders": 0, "accepted_by_fake": 100}, sort_keys=True))
