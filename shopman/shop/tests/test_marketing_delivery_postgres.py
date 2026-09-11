"""PostgreSQL regressions for the protected Marketing delivery ledger."""

from __future__ import annotations

import pytest
from django.db import connection
from django.utils import timezone

from shopman.shop.services.marketing_delivery_worker import (
    claim_due_targets,
    fanout_in_chunks,
    queue_materialized_targets,
)
from shopman.shop.tests.test_marketing_delivery_ledger import _graph

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_public_target_claim_does_not_lock_nullable_member_join():
    """A public publication has no member, so PostgreSQL sees an OUTER JOIN.

    A broad ``FOR UPDATE`` tries to lock that nullable side and PostgreSQL rejects
    the query.  The claim only mutates ``DeliveryTarget`` and must lock that table
    explicitly.
    """

    assert connection.vendor == "postgresql"
    outbox, _members = _graph(
        platform="instagram",
        suffix="postgres-public-claim",
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref)
    assert queue_materialized_targets(outbox.ref) == 1

    report = claim_due_targets(
        worker_id="postgres-public-claim",
        now=timezone.now(),
        limit=1,
        platforms=("instagram",),
        outbox_refs=(str(outbox.ref),),
    )

    assert len(report.targets) == 1
    assert report.targets[0].member_id is None
    assert report.targets[0].lease_owner == "postgres-public-claim"
