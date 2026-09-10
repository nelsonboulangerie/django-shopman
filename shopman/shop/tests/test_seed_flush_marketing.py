"""O reset canônico remove o ledger de Marketing antes das identidades protegidas."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import AudienceSnapshot, AudienceSnapshotMember
from shopman.shop.services import audience, audience_snapshot

pytestmark = pytest.mark.django_db


def test_seed_flush_removes_a_sealed_audience_before_its_customer() -> None:
    """Regressão: SET_NULL violava a identidade mínima antes de apagar o snapshot."""
    customer = Customer.objects.create(
        ref="QA-SEED-FLUSH-MARKETING",
        first_name="Cliente sintético",
        phone="+5543999002998",
    )
    now = timezone.now()
    snapshot = audience_snapshot.create_snapshot(
        audience.AudienceResult(
            general=(
                audience.Recipient(
                    phone=customer.phone,
                    customer_ref=customer.ref,
                ),
            ),
            calculated_at=now,
            expires_at=now + timedelta(minutes=15),
            cohort_hash="a" * 64,
        ),
        rules={"customer_refs": [customer.ref]},
        now=now,
    )
    assert snapshot.members.filter(customer=customer).exists()

    from config.management.commands.seed import Command

    command = Command()
    command.stdout = StringIO()
    command._flush()

    assert not AudienceSnapshot.objects.exists()
    assert not AudienceSnapshotMember.objects.exists()
    assert not Customer.objects.filter(pk=customer.pk).exists()
