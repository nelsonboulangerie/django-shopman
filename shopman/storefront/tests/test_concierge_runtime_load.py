"""Carga sintética WP09; mede estágio local, sem certificar WhatsApp ou UX."""
import json
import resource
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest
from django.db import connection, connections
from django.db.models import Min
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
    with connection.cursor() as cursor:
        cursor.execute("SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
        deadlocks_before = cursor.fetchone()[0]
    input_created = dict(Message.objects.filter(kind="inbound", consumed_by__isnull=True).values("conversation_id").annotate(first=Min("created_at")).values_list("conversation_id", "first"))
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
        input_age = (timezone.now()-input_created[pk]).total_seconds()
        query_count = 0
        query_seconds = []
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            backend_pid = cursor.fetchone()[0]
        def count(execute, sql, params, many, context):
            nonlocal query_count
            query_count += 1
            query_started = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                query_seconds.append(time.perf_counter() - query_started)
        try:
            with connection.execute_wrapper(count):
                result = service.run_turn(pk)
            assert not result.pending_more
            return time.perf_counter()-started, query_count, len(result.processed_message_ids), sum(query_seconds), max(query_seconds), backend_pid, input_age
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
    with connection.cursor() as cursor:
        cursor.execute("SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
        deadlocks_after = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM pg_locks WHERE NOT granted AND database=(SELECT oid FROM pg_database WHERE datname=current_database())")
        waiting_locks_at_end = cursor.fetchone()[0]
    assert deadlocks_after == deadlocks_before
    assert waiting_locks_at_end == 0
    latencies = sorted(item[0] for item in counts)
    print("SYNTHETIC_LOAD " + json.dumps({"conversations": 100, "history_messages": 10000, "new_inputs": 109, "burst": 10, "parallel_workers": 4, "seconds_total": round(elapsed, 3), "seconds_turn_median": round(statistics.median(latencies), 3), "seconds_turn_p95": round(latencies[94], 3), "seconds_turn_max": round(max(latencies), 3), "input_wait_to_worker_p95_seconds": round(sorted(item[6] for item in counts)[94], 3), "output_retries": sum((envelope.get("explicit_retry") or 0) for envelope in Message.objects.filter(kind="reply").values_list("envelope", flat=True)), "queries_total": sum(item[1] for item in counts), "sql_seconds_total": round(sum(item[3] for item in counts), 3), "sql_seconds_max": round(max(item[4] for item in counts), 3), "backend_connections": len({item[5] for item in counts}), "deadlocks_delta": deadlocks_after-deadlocks_before, "waiting_locks_at_end": waiting_locks_at_end, "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024), "largest_output_utf8_bytes": max(len(text.encode("utf-8")) for text in Message.objects.filter(kind="reply").values_list("text", flat=True)), "unknown_outputs": Message.objects.filter(transport_state="unknown").count(), "orders": 0, "accepted_by_fake": 100}, sort_keys=True))
