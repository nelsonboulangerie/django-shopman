"""Carga sintética WP09; mede estágio local, sem certificar fornecedor ou UX."""

import json
import resource
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import connection as database_connection
from django.db import connections
from django.db.models import Min
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Conversation, ConversationBinding, OutboundAttempt
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import agent, service
from shopman.storefront.concierge.contracts import WindowEvidence
from shopman.storefront.tests.support.concierge_transport_v3 import connection, reset_adapter

pytestmark = pytest.mark.django_db(transaction=True)


def test_hundred_conversations_ten_thousand_history_and_burst_conserve_inputs(settings, monkeypatch):
    if database_connection.vendor != "postgresql":
        pytest.skip("Synthetic workload requires PostgreSQL")
    subjects = [f"synthetic-load-{index}" for index in range(100)]
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "channel_ref": "web",
        "connections": {
            "load": connection(
                provider="synthetic",
                account="test-load",
                channel="text",
                subjects=subjects,
            )
        },
    }
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    adapter = reset_adapter()
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)
    conversations = Conversation.objects.bulk_create(
        [
            Conversation(
                customer_ref=f"synthetic-customer-{index}",
                channel_ref="web",
                last_inbound_at=timezone.now(),
            )
            for index in range(100)
        ]
    )
    bindings = ConversationBinding.objects.bulk_create(
        [
            ConversationBinding(
                conversation=conversation,
                provider="synthetic",
                account="test-load",
                transport_channel="text",
                subject=subject,
                connection_key="load",
                status=ConversationBinding.Status.ACTIVE,
                activated_at=timezone.now(),
            )
            for conversation, subject in zip(conversations, subjects, strict=True)
        ]
    )
    by_conversation = {binding.conversation_id: binding for binding in bindings}
    observed_at = timezone.now()
    window_evidence = WindowEvidence(
        policy="test-window-v1",
        source="synthetic-load",
        observed_at=observed_at,
        valid_until=observed_at + timedelta(hours=24),
        assurance="provider_window",
    ).as_dict()
    history = [
        Message(
            conversation=conversation,
            binding=by_conversation[conversation.pk],
            role=Message.Role.ASSISTANT if index % 2 else Message.Role.USER,
            kind=Message.Kind.REPLY if index % 2 else Message.Kind.INBOUND,
            text="Contexto sintético histórico",
            consumed_by=1 if not index % 2 else None,
            envelope={"version": 3},
        )
        for conversation in conversations
        for index in range(100)
    ]
    Message.objects.bulk_create(history, batch_size=1000)
    Message.objects.bulk_create(
        [
            Message(
                conversation=conversation,
                binding=by_conversation[conversation.pk],
                role=Message.Role.USER,
                kind=Message.Kind.INBOUND,
                text="Retomar escolhas",
                    envelope={
                        "version": 3,
                        "input_assurance": "provider_event",
                        "window_evidence": window_evidence,
                    },
            )
            for conversation in conversations
        ]
    )
    Message.objects.bulk_create(
        [
            Message(
                conversation=conversations[0],
                binding=by_conversation[conversations[0].pk],
                role=Message.Role.USER,
                kind=Message.Kind.INBOUND,
                text="Complemento de escolha",
                    envelope={
                        "version": 3,
                        "input_assurance": "provider_event",
                        "window_evidence": window_evidence,
                    },
            )
            for _ in range(9)
        ]
    )
    with database_connection.cursor() as cursor:
        cursor.execute("SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
        deadlocks_before = cursor.fetchone()[0]
    input_created = dict(
        Message.objects.filter(kind=Message.Kind.INBOUND, consumed_by__isnull=True)
        .values("conversation_id")
        .annotate(first=Min("created_at"))
        .values_list("conversation_id", "first")
    )
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text="Escolhas preservadas. Qual opção deseja consultar?"),
    )

    def run(item):
        conversation, binding = item
        started = time.perf_counter()
        input_age = (timezone.now() - input_created[conversation.pk]).total_seconds()
        query_count = 0
        query_seconds = []
        with database_connection.cursor() as cursor:
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
            with database_connection.execute_wrapper(count):
                result = service.run_turn(conversation.pk, binding.pk)
            assert not result.pending_more
            return (
                time.perf_counter() - started,
                query_count,
                len(result.processed_message_ids),
                sum(query_seconds),
                max(query_seconds),
                backend_pid,
                input_age,
            )
        finally:
            connections.close_all()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(run, zip(conversations, bindings, strict=True)))
    elapsed = time.perf_counter() - started
    sent_subjects = [subject for _, subject, _ in adapter.sent]
    assert len(sent_subjects) == len(set(sent_subjects)) == 100
    assert sum(item[2] for item in counts) == 109
    assert not Message.objects.filter(kind=Message.Kind.INBOUND, consumed_by__isnull=True).exists()
    assert Message.objects.filter(kind=Message.Kind.REPLY, transport_state="accepted").count() == 100
    assert OutboundAttempt.objects.filter(state="accepted").count() == 100
    assert not Order.objects.exists()
    with database_connection.cursor() as cursor:
        cursor.execute("SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
        deadlocks_after = cursor.fetchone()[0]
        cursor.execute(
            "SELECT count(*) FROM pg_locks WHERE NOT granted "
            "AND database=(SELECT oid FROM pg_database WHERE datname=current_database())"
        )
        waiting_locks_at_end = cursor.fetchone()[0]
    assert deadlocks_after == deadlocks_before
    assert waiting_locks_at_end == 0
    latencies = sorted(item[0] for item in counts)
    print(
        "SYNTHETIC_LOAD "
        + json.dumps(
            {
                "conversations": 100,
                "history_messages": 10000,
                "new_inputs": 109,
                "burst": 10,
                "parallel_workers": 4,
                "seconds_total": round(elapsed, 3),
                "seconds_turn_median": round(statistics.median(latencies), 3),
                "seconds_turn_p95": round(latencies[94], 3),
                "seconds_turn_max": round(max(latencies), 3),
                "input_wait_to_worker_p95_seconds": round(sorted(item[6] for item in counts)[94], 3),
                "output_retries": sum(
                    (envelope.get("explicit_retry") or 0)
                    for envelope in Message.objects.filter(kind=Message.Kind.REPLY).values_list("envelope", flat=True)
                ),
                "queries_total": sum(item[1] for item in counts),
                "sql_seconds_total": round(sum(item[3] for item in counts), 3),
                "sql_seconds_max": round(max(item[4] for item in counts), 3),
                "backend_connections": len({item[5] for item in counts}),
                "deadlocks_delta": deadlocks_after - deadlocks_before,
                "waiting_locks_at_end": waiting_locks_at_end,
                "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * (1 if sys.platform == "darwin" else 1024),
                "largest_output_utf8_bytes": max(
                    len(text.encode("utf-8"))
                    for text in Message.objects.filter(kind=Message.Kind.REPLY).values_list("text", flat=True)
                ),
                "unknown_outputs": Message.objects.filter(transport_state="unknown").count(),
                "orders": 0,
                "accepted_by_fake": 100,
            },
            sort_keys=True,
        )
    )
