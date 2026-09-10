from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps
from django.utils import timezone
from shopman.orderman.models import Order, Session
from shopman.stockman.models import Hold, HoldStatus

from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db

migration = import_module("shopman.shop.migrations.0042_freeze_active_hold_quality_policy")


def _hold(reference: str, *, purpose: str = "") -> Hold:
    metadata = {"reference": reference}
    if purpose:
        metadata["purpose"] = purpose
    return Hold.objects.create(
        sku="CUTOVER-SKU",
        quant=None,
        quantity=1,
        target_date=timezone.localdate(),
        status=HoldStatus.PENDING,
        metadata=metadata,
    )


def test_forward_freezes_policy_from_order_session_and_workorder_owner():
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        config={"stock": {"sells_nonconforming": True}},
    )
    Order.objects.create(ref="CUT-WEB", channel_ref="web", status="new", total_q=100)
    Session.objects.create(session_key="CUT-PDV", channel_ref="pdv")
    web = _hold("order:CUT-WEB")
    pdv = _hold("CUT-PDV")
    workorder = _hold("workorder:WO-1", purpose="workorder")

    migration.forwards(apps, None)

    web.refresh_from_db()
    pdv.refresh_from_db()
    workorder.refresh_from_db()
    assert web.metadata[migration.VERSION_KEY] == migration.POLICY_VERSION
    assert web.metadata[migration.ALLOWLIST_KEY] == ["excellent", "standard"]
    assert migration.ALLOWLIST_KEY not in pdv.metadata
    assert migration.ALLOWLIST_KEY not in workorder.metadata
    assert pdv.metadata[migration.BACKFILL_MARKER] == "shop.0042"

    migration.backwards(apps, None)
    for hold in (web, pdv, workorder):
        hold.refresh_from_db()
        assert migration.VERSION_KEY not in hold.metadata
        assert migration.ALLOWLIST_KEY not in hold.metadata
        assert migration.BACKFILL_MARKER not in hold.metadata


def test_forward_refuses_an_active_hold_whose_channel_cannot_be_proven():
    hold = _hold("owner-that-no-longer-exists")

    with pytest.raises(RuntimeError, match="sem canal identificável"):
        migration.forwards(apps, None)

    hold.refresh_from_db()
    assert migration.VERSION_KEY not in hold.metadata


def test_forward_ignores_an_expired_hold_whose_owner_no_longer_exists():
    hold = _hold("owner-that-no-longer-exists")
    hold.expires_at = timezone.now() - timedelta(seconds=1)
    hold.save(update_fields=["expires_at"])

    migration.forwards(apps, None)
    migration.backwards(apps, None)

    hold.refresh_from_db()
    assert migration.VERSION_KEY not in hold.metadata
    assert migration.ALLOWLIST_KEY not in hold.metadata
    assert migration.BACKFILL_MARKER not in hold.metadata
