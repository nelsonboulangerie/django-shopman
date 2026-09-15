"""PostgreSQL proof that a queued print job has only one physical claimant."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection, connections
from django.utils import timezone
from shopman.cashman.models import Terminal

from shopman.backstage.models import PrintAgentCredential, PrintAttempt, PrintJob
from shopman.backstage.services import print_jobs

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="SELECT FOR UPDATE SKIP LOCKED requires PostgreSQL",
)


@pytest.mark.django_db(transaction=True)
@requires_postgres
def test_two_relays_claim_one_print_job_exactly_once():
    terminal = Terminal.objects.create(ref="print-race", label="Impressora da preparação")
    credentials = [PrintAgentCredential.issue(terminal=terminal, label=f"relay-{slot}")[0] for slot in (1, 2)]
    payload = b"one physical label"
    job = PrintJob.objects.create(
        kind=PrintJob.Kind.PRODUCTION_WEIGHING,
        transport=PrintJob.Transport.RELAY,
        status=PrintJob.Status.QUEUED,
        target_terminal=terminal,
        requested_by_ref="postgresql-proof",
        requested_station_ref="prep-tablet",
        source_revision="sha256:1111111111111111:weighing:2026-09-14:user:1:signature",
        document={"contract_version": 2, "tickets": [{"blind_code": "Q4"}]},
        document_sha256=hashlib.sha256(b"document").hexdigest(),
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        payload_size=len(payload),
        label_count=1,
        expires_at=timezone.now() + print_jobs.JOB_LIFETIME,
    )
    barrier = Barrier(2, timeout=10)

    def claim(credential_pk: int):
        try:
            credential = PrintAgentCredential.objects.get(pk=credential_pk)
            barrier.wait()
            claimed = print_jobs.claim_next_job(
                credential=credential,
                telemetry={"build": f"race-{credential_pk}", "health": "ready"},
            )
            return None if claimed is None else (claimed[0].pk, claimed[1].pk)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, [credential.pk for credential in credentials]))

    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert winners[0][0] == job.pk
    assert PrintAttempt.objects.filter(job=job, status=PrintAttempt.Status.LEASED).count() == 1
    job.refresh_from_db()
    assert job.status == PrintJob.Status.LEASED
