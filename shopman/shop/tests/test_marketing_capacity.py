"""MKT-043 — deterministic, provider-free Marketing capacity gates.

The full tests are opt-in because they intentionally materialize the agreed
peak plus 2x safety margin. They only write to pytest's disposable database and
never execute a provider adapter.
"""

from __future__ import annotations

import gc
import json
import os
import time
import tracemalloc
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    ConsentProofStatus,
    ConsentPurpose,
    ConsentStatus,
)
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.models import Customer

from shopman.shop.models import AudienceSnapshotMember, DeliveryTarget
from shopman.shop.services import audience
from shopman.shop.services.marketing_delivery_ledger import MAX_TARGETS_PER_COMMAND
from shopman.shop.services.marketing_delivery_worker import (
    DEFAULT_CLAIM_LIMIT,
    DEFAULT_FANOUT_CHUNK_SIZE,
    claim_due_targets,
    fanout_in_chunks,
)
from shopman.shop.tests.test_marketing_delivery_ledger import _graph

RUN_FULL_CAPACITY = os.environ.get("SHOPMAN_RUN_MARKETING_CAPACITY") == "1"
full_capacity = pytest.mark.skipif(
    not RUN_FULL_CAPACITY,
    reason="set SHOPMAN_RUN_MARKETING_CAPACITY=1 for the isolated load gate",
)

PEAK_CANDIDATES_2X = 200_000
MAX_AUDIENCE = 100_000
PEAK_TARGETS_2X = 20_000
TARGETS_PER_COMMAND = MAX_TARGETS_PER_COMMAND
SEED_BATCH_SIZE = 5_000
AUDIENCE_P95_SECONDS = 2.0
AUDIENCE_QUERY_BUDGET = 30
AUDIENCE_MEMORY_BUDGET_MIB = 256
FIRST_FANOUT_BUDGET_SECONDS = 10.0
WORKER_CLAIM_BUDGET_SECONDS = 1.0


pytestmark = pytest.mark.django_db


def test_audience_filters_have_indexed_query_plans():
    """The two large insight filters must not regress to an unindexed scan."""

    now = timezone.now()
    customer = Customer.objects.create(
        ref="CAP-PLAN",
        first_name="Capacidade",
        phone="+5511999990000",
    )
    CustomerInsight.objects.create(
        customer=customer,
        last_order_at=now,
        rfm_segment="champion",
    )

    rfm_plan = CustomerInsight.objects.filter(
        rfm_segment="champion"
    ).values("customer_id").explain()
    purchase_plan = CustomerInsight.objects.filter(
        last_order_at__gte=now - timedelta(days=30)
    ).values("customer_id").explain()

    assert "customer_ins_rfm_seg_idx" in rfm_plan
    assert "customer_ins_last_order_idx" in purchase_plan


@pytest.mark.django_db(transaction=True)
def test_audience_index_migration_reverses_and_reapplies_cleanly():
    before = [("customer_insights", "0003_alter_customerinsight_rfm_segment")]
    after = [("customer_insights", "0004_customerinsight_audience_indexes")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    with connection.cursor() as cursor:
        indexes = connection.introspection.get_constraints(
            cursor,
            CustomerInsight._meta.db_table,
        )
    assert "customer_ins_last_order_idx" not in indexes

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    with connection.cursor() as cursor:
        indexes = connection.introspection.get_constraints(
            cursor,
            CustomerInsight._meta.db_table,
        )
    assert {
        "customer_ins_last_order_idx",
        "customer_ins_rfm_seg_idx",
        "customer_ins_churn_idx",
    } <= set(indexes)

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


@full_capacity
def test_audience_sustains_agreed_peak_with_2x_candidate_margin():
    """Resolve 100k eligible people inside a 200k-candidate local fixture."""

    _seed_audience_candidates(
        candidates=PEAK_CANDIDATES_2X,
        eligible=MAX_AUDIENCE,
    )
    gc.collect()

    # Warm indexes/caches before measuring the p95 contract.
    warm = audience.resolve({"rfm_segments": ["champion"]})
    assert warm.total == MAX_AUDIENCE
    del warm
    gc.collect()

    samples = []
    query_counts = []
    resolved_total = 0
    for _sample in range(5):
        started = time.perf_counter()
        with CaptureQueriesContext(connection) as queries:
            result = audience.resolve({"rfm_segments": ["champion"]})
        samples.append(time.perf_counter() - started)
        query_counts.append(len(queries))
        resolved_total = result.total
        del result
        gc.collect()

    tracemalloc.start()
    memory_result = audience.resolve({"rfm_segments": ["champion"]})
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert memory_result.total == MAX_AUDIENCE
    del memory_result

    p95_seconds = _nearest_rank_p95(samples)
    peak_mib = peak_bytes / (1024 * 1024)
    evidence = {
        "fixture": {
            "candidates": PEAK_CANDIDATES_2X,
            "eligible": MAX_AUDIENCE,
            "margin": "2x candidates",
        },
        "latency_seconds": {
            "samples": [round(value, 4) for value in samples],
            "p95": round(p95_seconds, 4),
            "budget": AUDIENCE_P95_SECONDS,
        },
        "queries": {
            "samples": query_counts,
            "max": max(query_counts),
            "budget": AUDIENCE_QUERY_BUDGET,
        },
        "peak_memory_mib": round(peak_mib, 2),
        "peak_memory_budget_mib": AUDIENCE_MEMORY_BUDGET_MIB,
    }
    print("MARKETING_CAPACITY_AUDIENCE=" + json.dumps(evidence, sort_keys=True))

    assert resolved_total == MAX_AUDIENCE
    assert max(query_counts) <= AUDIENCE_QUERY_BUDGET
    assert p95_seconds <= AUDIENCE_P95_SECONDS
    assert peak_mib <= AUDIENCE_MEMORY_BUDGET_MIB


@full_capacity
def test_fanout_and_two_workers_sustain_20k_targets_without_cap_bypass():
    """Use four legal 5k lanes; never raise the per-command safety cap."""

    assert MAX_TARGETS_PER_COMMAND == 5_000
    queue_started = time.perf_counter()
    lane_results = []
    for lane_index in range(PEAK_TARGETS_2X // TARGETS_PER_COMMAND):
        outbox, member_ids = _seed_worker_lane(lane_index, TARGETS_PER_COMMAND)
        first_started = time.perf_counter()
        reports = []
        while True:
            report = fanout_in_chunks(
                outbox.ref,
                member_ids=member_ids,
                chunk_size=DEFAULT_FANOUT_CHUNK_SIZE,
            )
            reports.append(report)
            if report.complete:
                break
        first_fanout_seconds = time.perf_counter() - first_started
        DeliveryTarget.objects.filter(outbox=outbox).update(
            state=DeliveryTarget.State.QUEUED,
            next_attempt_at=timezone.now(),
        )
        lane_results.append(
            {
                "lane": lane_index,
                "targets": reports[-1].requested,
                "calls": len(reports),
                "chunks": sum(item.chunks_committed for item in reports),
                "fanout_seconds": round(first_fanout_seconds, 4),
            }
        )
    queue_seconds = time.perf_counter() - queue_started

    claims = []
    for worker_id in ("capacity-worker-one", "capacity-worker-two"):
        started = time.perf_counter()
        with CaptureQueriesContext(connection) as queries:
            report = claim_due_targets(
                worker_id=worker_id,
                limit=DEFAULT_CLAIM_LIMIT,
            )
        claims.append(
            {
                "worker": worker_id,
                "report": report,
                "seconds": time.perf_counter() - started,
                "queries": len(queries),
            }
        )

    claimed_refs = [
        {target.ref for target in measurement["report"].targets}
        for measurement in claims
    ]
    evidence = {
        "fixture": {
            "targets": PEAK_TARGETS_2X,
            "commands": len(lane_results),
            "targets_per_command": TARGETS_PER_COMMAND,
            "runtime_cap_changed": False,
        },
        "queue_seconds": round(queue_seconds, 4),
        "lanes": lane_results,
        "claims": [
            {
                "worker": item["worker"],
                "targets": len(item["report"].targets),
                "seconds": round(item["seconds"], 4),
                "queries": item["queries"],
            }
            for item in claims
        ],
    }
    print("MARKETING_CAPACITY_WORKERS=" + json.dumps(evidence, sort_keys=True))

    assert DeliveryTarget.objects.count() == PEAK_TARGETS_2X
    assert all(item["targets"] == TARGETS_PER_COMMAND for item in lane_results)
    assert all(item["calls"] == 5 for item in lane_results)
    assert all(item["chunks"] == 50 for item in lane_results)
    assert all(
        item["fanout_seconds"] <= FIRST_FANOUT_BUDGET_SECONDS
        for item in lane_results
    )
    assert all(len(refs) == DEFAULT_CLAIM_LIMIT for refs in claimed_refs)
    assert claimed_refs[0].isdisjoint(claimed_refs[1])
    assert all(item["queries"] <= 10 for item in claims)
    assert all(item["seconds"] <= WORKER_CLAIM_BUDGET_SECONDS for item in claims)


def _seed_audience_candidates(*, candidates: int, eligible: int) -> None:
    now = timezone.now()
    for start in range(0, candidates, SEED_BATCH_SIZE):
        stop = min(start + SEED_BATCH_SIZE, candidates)
        customers = [
            Customer(
                ref=f"CAP-AUD-{index:06d}",
                first_name="Pessoa sintética",
                phone=f"+5511{index:011d}",
            )
            for index in range(start, stop)
        ]
        Customer.objects.bulk_create(customers, batch_size=SEED_BATCH_SIZE)
        CustomerInsight.objects.bulk_create(
            [
                CustomerInsight(
                    customer=customer,
                    rfm_segment="champion" if index < eligible else "regular",
                    last_order_at=now - timedelta(days=index % 365),
                )
                for index, customer in zip(range(start, stop), customers, strict=True)
            ],
            batch_size=SEED_BATCH_SIZE,
        )
        opted_in = [
            CommunicationConsent(
                customer=customer,
                channel="whatsapp",
                purpose=ConsentPurpose.MARKETING_GENERAL,
                status=ConsentStatus.OPTED_IN,
                proof_status=ConsentProofStatus.VERIFIED,
                source="synthetic-capacity-gate",
            )
            for index, customer in zip(range(start, stop), customers, strict=True)
            if index < eligible
        ]
        CommunicationConsent.objects.bulk_create(
            opted_in,
            batch_size=SEED_BATCH_SIZE,
        )


def _seed_worker_lane(lane_index: int, count: int):
    outbox, _empty = _graph(
        platform="whatsapp",
        suffix=f"capacity-{lane_index}",
        target_keys=(),
    )
    customers = [
        Customer(
            ref=f"CAP-W{lane_index}-{index:05d}",
            first_name="Pessoa sintética",
            phone=f"+552{lane_index}{index:016d}",
        )
        for index in range(count)
    ]
    Customer.objects.bulk_create(customers, batch_size=SEED_BATCH_SIZE)
    members = [
        AudienceSnapshotMember(
            snapshot=outbox.snapshot,
            customer=customer,
            target_key=f"{lane_index:04x}{index:060x}",
            reasons=["consent"],
        )
        for index, customer in enumerate(customers)
    ]
    AudienceSnapshotMember.objects.bulk_create(
        members,
        batch_size=SEED_BATCH_SIZE,
    )
    CommunicationConsent.objects.bulk_create(
        [
            CommunicationConsent(
                customer=customer,
                channel="whatsapp",
                purpose=ConsentPurpose.MARKETING_GENERAL,
                status=ConsentStatus.OPTED_IN,
                proof_status=ConsentProofStatus.VERIFIED,
                source="synthetic-capacity-gate",
            )
            for customer in customers
        ],
        batch_size=SEED_BATCH_SIZE,
    )
    return outbox, [member.pk for member in members]


def _nearest_rank_p95(samples: list[float]) -> float:
    return sorted(samples)[max(0, int(len(samples) * 0.95 + 0.9999) - 1)]
