"""Tests for MergeService — customer deduplication."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    ConsentChannel,
    ConsentStatus,
    LegalBasis,
)
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.loyalty.models import (
    LoyaltyAccount,
    LoyaltyTier,
    LoyaltyTransaction,
    TransactionType,
)
from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus
from shopman.guestman.contrib.merge.service import MergeResult, MergeService
from shopman.guestman.contrib.preferences.models import CustomerPreference, PreferenceType
from shopman.guestman.contrib.timeline.models import EventType, TimelineEvent
from shopman.guestman.exceptions import CustomerError
from shopman.guestman.gates import GateError
from shopman.guestman.models import (
    ContactPoint,
    Customer,
    CustomerAddress,
    ExternalIdentity,
    PriceTier,
)

pytestmark = pytest.mark.django_db


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def tier(db):
    return PriceTier.objects.create(
        ref="regular",
        name="Regular",
        is_default=True,
        priority=0,
    )


@pytest.fixture
def source(tier):
    return Customer.objects.create(
        ref="SRC-001",
        first_name="Maria",
        last_name="Souza",
        phone="+5543911111111",
        email="maria@example.com",
        price_tier=tier,
    )


@pytest.fixture
def target(tier):
    return Customer.objects.create(
        ref="TGT-001",
        first_name="Maria",
        last_name="Silva",
        phone="+5543922222222",
        email="maria.silva@example.com",
        price_tier=tier,
    )


@pytest.fixture
def evidence():
    return {"staff_override": True}


# ======================================================================
# Gate validation
# ======================================================================


class TestMergeGateValidation:
    """Test G6 gate enforcement."""

    def test_merge_requires_evidence(self, source, target):
        with pytest.raises(GateError):
            MergeService.merge(source, target, evidence={}, actor="test")

    def test_merge_rejects_invalid_evidence(self, source, target):
        with pytest.raises(GateError):
            MergeService.merge(
                source, target, evidence={"random_key": True}, actor="test"
            )

    def test_merge_rejects_same_customer(self, source):
        with pytest.raises(GateError, match="Cannot merge customer into itself"):
            MergeService.merge(
                source, source, evidence={"staff_override": True}, actor="test"
            )

    def test_merge_rejects_inactive_source(self, source, target, evidence):
        source.is_active = False
        source.save(update_fields=["is_active"])

        with pytest.raises(CustomerError):
            MergeService.merge(source, target, evidence, actor="test")

    def test_merge_rejects_inactive_target(self, source, target, evidence):
        target.is_active = False
        target.save(update_fields=["is_active"])

        with pytest.raises(CustomerError):
            MergeService.merge(source, target, evidence, actor="test")

    def test_merge_accepts_staff_override(self, source, target):
        result = MergeService.merge(
            source, target, evidence={"staff_override": True}, actor="test"
        )
        assert isinstance(result, MergeResult)

    def test_merge_accepts_same_verified_phone(self, source, target):
        result = MergeService.merge(
            source, target, evidence={"same_verified_phone": True}, actor="test"
        )
        assert result.source_ref == "SRC-001"

    def test_merge_accepts_same_verified_email(self, source, target):
        result = MergeService.merge(
            source, target, evidence={"same_verified_email": True}, actor="test"
        )
        assert result.target_ref == "TGT-001"


# ======================================================================
# Contact points migration
# ======================================================================


class TestMergeContactPoints:

    def test_migrates_unique_contact_points(self, source, target, evidence):
        # Source has an Instagram CP that target doesn't
        cp = ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@maria_ig",
            is_primary=True,
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.migrated_contact_points >= 1
        cp.refresh_from_db()
        assert cp.customer == target

    def test_skips_duplicate_contact_points(self, source, target, evidence):
        # Source has a WhatsApp CP; target already has same value
        # Since (type, value_normalized) is globally unique, we create it on target first
        # then create a *different* value on source, and also test the scenario where
        # source's CP value already exists on target via the global constraint.
        ContactPoint.objects.create(
            customer=target,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized="+5543933333333",
            is_primary=True,
        )

        # Source has a different WhatsApp CP
        source_cp = ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized="+5543944444444",
            is_primary=True,
        )

        MergeService.merge(source, target, evidence, actor="test")

        # Source's CP should be migrated (different value), but demoted
        source_cp.refresh_from_db()
        assert source_cp.customer == target
        assert source_cp.is_primary is False

    def test_demotes_primary_on_conflict(self, source, target, evidence):
        # Source has a primary Instagram CP, target also has a primary Instagram CP
        # Source's should be demoted when migrated
        source_cp = ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@maria_source",
            is_primary=True,
        )
        target_cp = ContactPoint.objects.create(
            customer=target,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@maria_target",
            is_primary=True,
        )

        MergeService.merge(source, target, evidence, actor="test")

        # Source's CP should have been moved to target with is_primary=False
        source_cp.refresh_from_db()
        assert source_cp.customer == target
        assert source_cp.is_primary is False

        # Target's primary should still be primary
        target_cp.refresh_from_db()
        assert target_cp.is_primary is True


# ======================================================================
# External identities migration
# ======================================================================


class TestMergeExternalIdentities:

    def test_migrates_external_identities(self, source, target, evidence):
        eid = ExternalIdentity.objects.create(
            customer=source,
            provider=ExternalIdentity.Provider.MANYCHAT,
            provider_uid="mc_12345",
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.migrated_external_identities == 1
        eid.refresh_from_db()
        assert eid.customer == target

    def test_skips_when_target_already_has_provider(self, source, target, evidence):
        # Source has a Manychat identity; target has the same provider with different uid
        # Both should coexist (different uid = different record, no conflict)
        ExternalIdentity.objects.create(
            customer=source,
            provider=ExternalIdentity.Provider.MANYCHAT,
            provider_uid="mc_source_111",
        )
        ExternalIdentity.objects.create(
            customer=target,
            provider=ExternalIdentity.Provider.MANYCHAT,
            provider_uid="mc_target_222",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        # Source's identity should be migrated (different uid)
        assert result.migrated_external_identities == 1


# ======================================================================
# Order history migration
# ======================================================================


class TestMergeOrders:

    def test_migrates_order_identity_to_target_customer(self, source, target, evidence):
        from django.apps import apps

        # Order migration is an optional merge integration; this test exercises
        # the real path and needs the orderman app + tables. When guestman runs
        # standalone (no orderman installed) the merge skips orders gracefully,
        # so there is nothing to assert here.
        if not apps.is_installed("shopman.orderman"):
            pytest.skip("requires the orderman app (optional merge integration)")

        from shopman.orderman.models import Order

        order = Order.objects.create(
            ref="ORD-MERGE-001",
            channel_ref="web",
            session_key="sess-merge-001",
            handle_type="phone",
            handle_ref=source.phone,
            status=Order.Status.ACCEPTED,
            total_q=3900,
            data={
                "customer_ref": source.ref,
                "customer": {
                    "ref": source.ref,
                    "uuid": str(source.uuid),
                    "name": source.name,
                    "phone": source.phone,
                },
            },
        )

        original_data = order.data
        unrelated = Order.objects.create(
            ref="ORD-MERGE-OTHER",
            channel_ref="web",
            session_key="sess-merge-other",
            handle_type="phone",
            handle_ref=target.phone,
            status=Order.Status.ACCEPTED,
            total_q=1000,
            data={"customer_ref": target.ref},
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        order.refresh_from_db()
        assert result.migrated_orders == 1
        assert order.data["customer_ref"] == target.ref
        assert order.data["customer"]["ref"] == target.ref
        assert order.data["customer"]["uuid"] == str(target.uuid)
        assert order.data["customer"]["phone"] == target.phone
        assert order.handle_ref == target.phone
        # This order matches several identity predicates, but must be migrated
        # and recorded exactly once. Orders of another identity stay untouched.
        audit = MergeAudit.objects.get(pk=result.audit_id)
        assert [entry["pk"] for entry in audit.snapshot["orders"]] == [order.pk]
        unrelated.refresh_from_db()
        assert unrelated.data == {"customer_ref": target.ref}
        assert unrelated.handle_ref == target.phone

        MergeService.undo(result.audit_id, actor="test")
        order.refresh_from_db()
        assert order.data == original_data
        assert order.handle_ref == source.phone
        unrelated.refresh_from_db()
        assert unrelated.data == {"customer_ref": target.ref}


# ======================================================================
# Identifiers migration
# ======================================================================


class TestMergeIdentifiers:

    def test_migrates_identifiers(self, source, target, evidence):
        ident = CustomerIdentifier.objects.create(
            customer=source,
            identifier_type=IdentifierType.INSTAGRAM,
            identifier_value="@maria_ig",
            is_primary=True,
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.migrated_identifiers == 1
        ident.refresh_from_db()
        assert ident.customer == target

    def test_skips_identifier_when_globally_taken(self, source, target, evidence):
        """Source identifier's value already exists on target — should be deleted, not migrated."""
        # Create identifier on target first
        CustomerIdentifier.objects.create(
            customer=target,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="shared@example.com",
        )
        # Source has same type but different value (global unique allows this)
        ident = CustomerIdentifier.objects.create(
            customer=source,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="source-only@example.com",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        # Source's different-value identifier should migrate
        assert result.migrated_identifiers == 1
        ident.refresh_from_db()
        assert ident.customer == target

    def test_demotes_primary_identifier_on_conflict(self, source, target, evidence):
        CustomerIdentifier.objects.create(
            customer=source,
            identifier_type=IdentifierType.PHONE,
            identifier_value="+5543955555555",
            is_primary=True,
        )
        CustomerIdentifier.objects.create(
            customer=target,
            identifier_type=IdentifierType.PHONE,
            identifier_value="+5543966666666",
            is_primary=True,
        )

        MergeService.merge(source, target, evidence, actor="test")

        source_moved = CustomerIdentifier.objects.filter(
            customer=target,
            identifier_value="+5543955555555",
        ).first()
        assert source_moved is not None
        assert source_moved.is_primary is False


# ======================================================================
# Addresses migration
# ======================================================================


class TestMergeAddresses:

    def test_migrates_addresses(self, source, target, evidence):
        addr = CustomerAddress.objects.create(
            customer=source,
            label="home",
            formatted_address="Rua Source, 100",
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.migrated_addresses == 1
        addr.refresh_from_db()
        assert addr.customer == target

    def test_demotes_default_address_on_conflict(self, source, target, evidence):
        CustomerAddress.objects.create(
            customer=source,
            label="home",
            formatted_address="Rua Source, 100",
            is_default=True,
        )
        CustomerAddress.objects.create(
            customer=target,
            label="work",
            formatted_address="Rua Target, 200",
            is_default=True,
        )

        MergeService.merge(source, target, evidence, actor="test")

        # Source's address should be migrated but not default
        source_addr = CustomerAddress.objects.get(
            customer=target,
            formatted_address="Rua Source, 100",
        )
        assert source_addr.is_default is False

        # Target's default should remain
        target_addr = CustomerAddress.objects.get(
            customer=target,
            formatted_address="Rua Target, 200",
        )
        assert target_addr.is_default is True


# ======================================================================
# Preferences migration
# ======================================================================


class TestMergePreferences:

    def test_migrates_non_conflicting_preferences(self, source, target, evidence):
        pref = CustomerPreference.objects.create(
            customer=source,
            category="dietary",
            key="vegan",
            value=True,
            preference_type=PreferenceType.RESTRICTION,
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.migrated_preferences == 1
        pref.refresh_from_db()
        assert pref.customer == target

    def test_target_wins_on_preference_conflict(self, source, target, evidence):
        CustomerPreference.objects.create(
            customer=source,
            category="dietary",
            key="lactose_free",
            value=False,
            preference_type=PreferenceType.EXPLICIT,
        )
        target_pref = CustomerPreference.objects.create(
            customer=target,
            category="dietary",
            key="lactose_free",
            value=True,
            preference_type=PreferenceType.RESTRICTION,
        )

        MergeService.merge(source, target, evidence, actor="test")

        # Target's preference should be unchanged
        target_pref.refresh_from_db()
        assert target_pref.value is True

        # Source's preference should be deleted
        assert not CustomerPreference.objects.filter(
            customer=source, category="dietary", key="lactose_free"
        ).exists()


# ======================================================================
# Consents migration
# ======================================================================


class TestMergeConsents:

    def test_migrates_non_conflicting_consents(self, source, target, evidence):
        CommunicationConsent.objects.create(
            customer=source,
            channel=ConsentChannel.SMS,
            status=ConsentStatus.OPTED_IN,
            legal_basis=LegalBasis.CONSENT,
            consented_at=timezone.now(),
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.migrated_consents == 1
        assert CommunicationConsent.objects.filter(
            customer=target,
            channel=ConsentChannel.SMS,
        ).exists()

    def test_more_restrictive_consent_wins(self, source, target, evidence):
        """If source is opted_out but target is opted_in, result should be opted_out."""
        now = timezone.now()
        CommunicationConsent.objects.create(
            customer=source,
            channel=ConsentChannel.WHATSAPP,
            status=ConsentStatus.OPTED_OUT,
            legal_basis=LegalBasis.CONSENT,
            revoked_at=now,
        )
        target_consent = CommunicationConsent.objects.create(
            customer=target,
            channel=ConsentChannel.WHATSAPP,
            status=ConsentStatus.OPTED_IN,
            legal_basis=LegalBasis.CONSENT,
            consented_at=now,
        )

        MergeService.merge(source, target, evidence, actor="test")

        target_consent.refresh_from_db()
        assert target_consent.status == ConsentStatus.OPTED_OUT

    def test_less_restrictive_source_does_not_override(self, source, target, evidence):
        """If source is opted_in but target is opted_out, target stays opted_out."""
        now = timezone.now()
        CommunicationConsent.objects.create(
            customer=source,
            channel=ConsentChannel.EMAIL,
            status=ConsentStatus.OPTED_IN,
            legal_basis=LegalBasis.CONSENT,
            consented_at=now,
        )
        target_consent = CommunicationConsent.objects.create(
            customer=target,
            channel=ConsentChannel.EMAIL,
            status=ConsentStatus.OPTED_OUT,
            legal_basis=LegalBasis.CONSENT,
            revoked_at=now,
        )

        MergeService.merge(source, target, evidence, actor="test")

        target_consent.refresh_from_db()
        assert target_consent.status == ConsentStatus.OPTED_OUT


# ======================================================================
# Timeline events migration
# ======================================================================


class TestMergeTimelineEvents:

    def test_migrates_timeline_events(self, source, target, evidence):
        TimelineEvent.objects.create(
            customer=source,
            event_type=EventType.ORDER,
            title="Pedido #100",
        )
        TimelineEvent.objects.create(
            customer=source,
            event_type=EventType.CONTACT,
            title="WhatsApp recebido",
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.migrated_timeline_events == 2
        assert TimelineEvent.objects.filter(customer=target).count() >= 2

    def test_creates_merge_audit_event(self, source, target, evidence):
        MergeService.merge(source, target, evidence, actor="admin:pablo")

        merge_event = TimelineEvent.objects.filter(
            customer=target,
            event_type=EventType.SYSTEM,
            reference=f"merge:{source.ref}",
        ).first()
        assert merge_event is not None
        assert "SRC-001" in merge_event.title
        assert merge_event.created_by == "admin:pablo"


# ======================================================================
# Loyalty migration
# ======================================================================


class TestMergeLoyalty:

    def test_merges_loyalty_points(self, source, target, evidence):
        source_acct = LoyaltyAccount.objects.create(
            customer=source,
            points_balance=500,
            lifetime_points=1000,
            tier=LoyaltyTier.SILVER,
        )
        target_acct = LoyaltyAccount.objects.create(
            customer=target,
            points_balance=300,
            lifetime_points=600,
            tier=LoyaltyTier.BRONZE,
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.loyalty_merged is True
        target_acct.refresh_from_db()
        assert target_acct.points_balance == 800
        assert target_acct.lifetime_points == 1600
        # Higher tier wins
        assert target_acct.tier == LoyaltyTier.SILVER

        # Source account should be deactivated
        source_acct.refresh_from_db()
        assert source_acct.is_active is False

    def test_merges_loyalty_stamps(self, source, target, evidence):
        LoyaltyAccount.objects.create(
            customer=source,
            stamps_current=3,
            stamps_completed=1,
        )
        target_acct = LoyaltyAccount.objects.create(
            customer=target,
            stamps_current=5,
            stamps_completed=2,
        )

        MergeService.merge(source, target, evidence, actor="test")

        target_acct.refresh_from_db()
        assert target_acct.stamps_current == 8
        assert target_acct.stamps_completed == 3

    def test_creates_target_account_if_missing(self, source, target, evidence):
        LoyaltyAccount.objects.create(
            customer=source,
            points_balance=200,
            lifetime_points=200,
            tier=LoyaltyTier.BRONZE,
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        assert result.loyalty_merged is True
        target_acct = LoyaltyAccount.objects.get(customer=target)
        assert target_acct.points_balance == 200

    def test_no_loyalty_merge_if_no_source_account(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")
        assert result.loyalty_merged is False

    def test_reassigns_loyalty_transactions(self, source, target, evidence):
        source_acct = LoyaltyAccount.objects.create(
            customer=source,
            points_balance=100,
            lifetime_points=100,
        )
        LoyaltyTransaction.objects.create(
            account=source_acct,
            transaction_type=TransactionType.EARN,
            points=100,
            balance_after=100,
            description="First purchase",
        )
        target_acct = LoyaltyAccount.objects.create(
            customer=target,
            points_balance=50,
            lifetime_points=50,
        )

        MergeService.merge(source, target, evidence, actor="test")

        # Source's transaction should now belong to target's account
        assert LoyaltyTransaction.objects.filter(account=target_acct).count() >= 1
        # Plus the merge adjustment transaction
        merge_tx = LoyaltyTransaction.objects.filter(
            account=target_acct,
            transaction_type=TransactionType.ADJUST,
            reference=f"merge:{source.ref}",
        )
        assert merge_tx.exists()

    def test_keeps_higher_tier(self, source, target, evidence):
        LoyaltyAccount.objects.create(
            customer=source,
            points_balance=0,
            lifetime_points=0,
            tier=LoyaltyTier.GOLD,
        )
        target_acct = LoyaltyAccount.objects.create(
            customer=target,
            points_balance=0,
            lifetime_points=0,
            tier=LoyaltyTier.PLATINUM,
        )

        MergeService.merge(source, target, evidence, actor="test")

        target_acct.refresh_from_db()
        assert target_acct.tier == LoyaltyTier.PLATINUM


# ======================================================================
# Source deactivation and audit
# ======================================================================


class TestMergeSourceDeactivation:

    def test_deactivates_source(self, source, target, evidence):
        MergeService.merge(source, target, evidence, actor="test")

        source.refresh_from_db()
        assert source.is_active is False

    def test_adds_merge_note_to_source(self, source, target, evidence):
        MergeService.merge(source, target, evidence, actor="admin:pablo")

        source.refresh_from_db()
        assert "[MERGED]" in source.notes
        assert target.ref in source.notes

    def test_returns_merge_result(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")

        assert isinstance(result, MergeResult)
        assert result.source_ref == "SRC-001"
        assert result.target_ref == "TGT-001"


# ======================================================================
# Transactional safety (rollback)
# ======================================================================


class TestMergeTransactionalSafety:

    def test_rollback_on_failure(self, source, target, evidence, monkeypatch):
        """If an error occurs mid-merge, everything should roll back."""
        # Make _migrate_preferences raise to simulate a mid-merge failure
        def boom(*args, **kwargs):
            raise RuntimeError("Simulated failure")

        monkeypatch.setattr(MergeService, "_migrate_preferences", boom)

        with pytest.raises(RuntimeError, match="Simulated failure"):
            MergeService.merge(source, target, evidence, actor="test")

        # Source should still be active (rollback)
        source.refresh_from_db()
        assert source.is_active is True

        # No timeline events should have been created
        assert not TimelineEvent.objects.filter(
            reference=f"merge:{source.ref}",
        ).exists()

        # No audit record should exist
        assert not MergeAudit.objects.filter(source_ref=source.ref).exists()


# ======================================================================
# MergeAudit
# ======================================================================


class TestMergeAudit:

    def test_creates_audit_record(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="admin:pablo")

        assert result.audit_id
        audit = MergeAudit.objects.get(pk=result.audit_id)
        assert audit.source_ref == "SRC-001"
        assert audit.target_ref == "TGT-001"
        assert audit.actor == "admin:pablo"
        assert audit.status == MergeStatus.COMPLETED
        assert audit.evidence == {"staff_override": True}

    def test_audit_snapshot_tracks_migrated_pks(self, source, target, evidence):
        cp = ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@audit_test",
            is_primary=True,
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        audit = MergeAudit.objects.get(pk=result.audit_id)
        assert str(cp.pk) in audit.snapshot.get("contact_points", [])

    def test_audit_can_undo_within_window(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")
        audit = MergeAudit.objects.get(pk=result.audit_id)
        assert audit.can_undo is True

    def test_audit_cannot_undo_after_window(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")
        audit = MergeAudit.objects.get(pk=result.audit_id)
        # Simulate expired window
        audit.merged_at = timezone.now() - timedelta(hours=25)
        audit.save(update_fields=["merged_at"])
        assert audit.can_undo is False

    def test_audit_counts_match_result(self, source, target, evidence):
        ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@counts_test",
        )
        CustomerAddress.objects.create(
            customer=source,
            label="home",
            formatted_address="Rua Counts, 1",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        audit = MergeAudit.objects.get(pk=result.audit_id)

        assert audit.migrated_contact_points == result.migrated_contact_points
        assert audit.migrated_addresses == result.migrated_addresses
        assert audit.loyalty_merged == result.loyalty_merged


# ======================================================================
# Undo / Revert
# ======================================================================


class TestMergeUndo:

    def test_undo_reactivates_source(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")

        MergeService.undo(result.audit_id, actor="admin:pablo")

        source.refresh_from_db()
        assert source.is_active is True

    def test_undo_moves_contact_points_back(self, source, target, evidence):
        cp = ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@undo_cp_test",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        cp.refresh_from_db()
        assert cp.customer == target

        MergeService.undo(result.audit_id, actor="test")
        cp.refresh_from_db()
        assert cp.customer == source

    def test_undo_moves_addresses_back(self, source, target, evidence):
        addr = CustomerAddress.objects.create(
            customer=source,
            label="home",
            formatted_address="Rua Undo, 42",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        addr.refresh_from_db()
        assert addr.customer == target

        MergeService.undo(result.audit_id, actor="test")
        addr.refresh_from_db()
        assert addr.customer == source

    def test_undo_moves_identifiers_back(self, source, target, evidence):
        ident = CustomerIdentifier.objects.create(
            customer=source,
            identifier_type=IdentifierType.INSTAGRAM,
            identifier_value="@undo_ident",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        ident.refresh_from_db()
        assert ident.customer == target

        MergeService.undo(result.audit_id, actor="test")
        ident.refresh_from_db()
        assert ident.customer == source

    def test_undo_moves_preferences_back(self, source, target, evidence):
        pref = CustomerPreference.objects.create(
            customer=source,
            category="flavor",
            key="undo_test",
            value="chocolate",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        pref.refresh_from_db()
        assert pref.customer == target

        MergeService.undo(result.audit_id, actor="test")
        pref.refresh_from_db()
        assert pref.customer == source

    def test_undo_moves_timeline_events_back(self, source, target, evidence):
        evt = TimelineEvent.objects.create(
            customer=source,
            event_type=EventType.NOTE,
            title="Undo test event",
        )

        result = MergeService.merge(source, target, evidence, actor="test")
        evt.refresh_from_db()
        assert evt.customer == target

        MergeService.undo(result.audit_id, actor="test")
        evt.refresh_from_db()
        assert evt.customer == source

    def test_undo_marks_audit_reverted(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")

        MergeService.undo(result.audit_id, actor="admin:pablo")

        audit = MergeAudit.objects.get(pk=result.audit_id)
        assert audit.status == MergeStatus.REVERTED
        assert audit.reverted_by == "admin:pablo"
        assert audit.reverted_at is not None

    def test_undo_rejects_already_reverted(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")
        MergeService.undo(result.audit_id, actor="test")

        with pytest.raises(CustomerError, match="already reverted"):
            MergeService.undo(result.audit_id, actor="test")

    def test_undo_rejects_expired_window(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")
        audit = MergeAudit.objects.get(pk=result.audit_id)
        audit.merged_at = timezone.now() - timedelta(hours=25)
        audit.save(update_fields=["merged_at"])

        with pytest.raises(CustomerError, match="window expired"):
            MergeService.undo(result.audit_id, actor="test")

    def test_undo_rejects_invalid_audit_id(self):
        with pytest.raises(CustomerError, match="not found"):
            MergeService.undo("00000000-0000-0000-0000-000000000000", actor="test")

    def test_undo_creates_timeline_event(self, source, target, evidence):
        result = MergeService.merge(source, target, evidence, actor="test")
        MergeService.undo(result.audit_id, actor="admin:pablo")

        undo_event = TimelineEvent.objects.filter(
            customer=target,
            event_type=EventType.SYSTEM,
            reference=f"undo-merge:{source.ref}",
        ).first()
        assert undo_event is not None
        assert "reverted" in undo_event.title.lower()


# ======================================================================
# Full integration — everything together
# ======================================================================


class TestMergeIntegration:

    def test_full_merge_scenario(self, source, target, evidence):
        """End-to-end merge with data in all related models."""
        now = timezone.now()

        # Contact points
        ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@maria_bakery",
            is_primary=True,
        )

        # External identity
        ExternalIdentity.objects.create(
            customer=source,
            provider=ExternalIdentity.Provider.MANYCHAT,
            provider_uid="mc_99999",
        )

        # Identifier
        CustomerIdentifier.objects.create(
            customer=source,
            identifier_type=IdentifierType.INSTAGRAM,
            identifier_value="@maria_bakery",
        )

        # Address
        CustomerAddress.objects.create(
            customer=source,
            label="home",
            formatted_address="Rua das Flores, 42",
        )

        # Preference
        CustomerPreference.objects.create(
            customer=source,
            category="flavor",
            key="favorite_bread",
            value="sourdough",
        )

        # Consent
        CommunicationConsent.objects.create(
            customer=source,
            channel=ConsentChannel.PUSH,
            status=ConsentStatus.OPTED_IN,
            consented_at=now,
        )

        # Timeline
        TimelineEvent.objects.create(
            customer=source,
            event_type=EventType.ORDER,
            title="Pedido #42",
        )

        # Loyalty
        LoyaltyAccount.objects.create(
            customer=source,
            points_balance=250,
            lifetime_points=500,
            tier=LoyaltyTier.SILVER,
        )

        # --- Execute merge ---
        result = MergeService.merge(source, target, evidence, actor="admin:pablo")

        # --- Verify everything migrated ---
        assert result.migrated_contact_points >= 1
        assert result.migrated_external_identities == 1
        assert result.migrated_identifiers == 1
        assert result.migrated_addresses == 1
        assert result.migrated_preferences == 1
        assert result.migrated_consents == 1
        assert result.migrated_timeline_events == 1
        assert result.loyalty_merged is True
        assert result.audit_id  # Audit record created

        # Source deactivated
        source.refresh_from_db()
        assert source.is_active is False

        # Audit event exists
        assert TimelineEvent.objects.filter(
            customer=target,
            event_type=EventType.SYSTEM,
            reference=f"merge:{source.ref}",
        ).exists()

        # All source data now belongs to target
        assert ContactPoint.objects.filter(customer=source).count() == 0
        assert ExternalIdentity.objects.filter(customer=source).count() == 0
        assert CustomerIdentifier.objects.filter(customer=source).count() == 0
        assert CustomerAddress.objects.filter(customer=source).count() == 0
        assert CustomerPreference.objects.filter(customer=source).count() == 0
        assert TimelineEvent.objects.filter(customer=source).count() == 0

        # Audit record has full snapshot
        audit = MergeAudit.objects.get(pk=result.audit_id)
        assert len(audit.snapshot.get("contact_points", [])) >= 1
        assert len(audit.snapshot.get("addresses", [])) == 1
        assert audit.snapshot.get("loyalty", {}).get("source_points") == 250

    def test_full_merge_then_undo(self, source, target, evidence):
        """E2E: merge with multiple data types, then undo."""
        cp = ContactPoint.objects.create(
            customer=source,
            type=ContactPoint.Type.INSTAGRAM,
            value_normalized="@undo_e2e",
        )
        addr = CustomerAddress.objects.create(
            customer=source,
            label="home",
            formatted_address="Rua E2E, 1",
        )
        ident = CustomerIdentifier.objects.create(
            customer=source,
            identifier_type=IdentifierType.INSTAGRAM,
            identifier_value="@undo_e2e_ident",
        )
        pref = CustomerPreference.objects.create(
            customer=source,
            category="test",
            key="e2e_undo",
            value="yes",
        )

        result = MergeService.merge(source, target, evidence, actor="test")

        # Verify merge happened
        source.refresh_from_db()
        assert source.is_active is False

        # Undo
        MergeService.undo(result.audit_id, actor="admin:undo")

        # Verify revert
        source.refresh_from_db()
        assert source.is_active is True

        cp.refresh_from_db()
        assert cp.customer == source

        addr.refresh_from_db()
        assert addr.customer == source

        ident.refresh_from_db()
        assert ident.customer == source

        pref.refresh_from_db()
        assert pref.customer == source


# ======================================================================
# O fantasma encontra o dono
# ======================================================================


class TestMergeFillsIdentityGaps:
    """O cadastro largado só com um dado, quando reencontra a pessoa.

    Ele vai existir — nasce toda vez que alguém pede a nota no balcão e o CPF
    não é de ninguém conhecido. É um documento sem rosto. O dia em que o rosto
    aparece, unificar tem de entregar o documento a ele: mover contato e pedido
    e deixar o CPF para trás, na ficha que a própria unificação desativa, é
    unificar pela metade — e é a metade que o operador estava tentando cadastrar.
    """

    @pytest.fixture
    def fantasma(self, tier):
        """Só um CPF. Sem nome, sem telefone, sem e-mail."""
        return Customer.objects.create(
            ref="GHOST-001", first_name="", last_name="", document="11144477735",
            price_tier=tier,
        )

    def test_documento_do_fantasma_chega_no_sobrevivente(self, fantasma, target, evidence):
        MergeService.merge(fantasma, target, evidence=evidence, actor="pdv")

        target.refresh_from_db()
        assert target.document == "11144477735"

    def test_documento_sai_do_doador(self, fantasma, target, evidence):
        """UM dono por dado. Dois cadastros dizendo "este CPF é meu" é
        exatamente a pergunta que o conflito do PDV faz — e ela tem uma resposta
        só."""
        MergeService.merge(fantasma, target, evidence=evidence, actor="pdv")

        fantasma.refresh_from_db()
        assert fantasma.document == ""

    def test_email_solto_chega_no_cache_do_sobrevivente(self, tier, evidence):
        """O `email` do Customer é cache do ContactPoint principal.

        O ContactPoint já migrava; o cache ficava vazio, e é ele que a tela lê.
        Quem preenche NÃO é este service copiando o campo — é o Core, quando o
        contato que chegou assume o posto de principal (`set_as_primary`).
        """
        sem_email = Customer.objects.create(
            ref="TGT-SEM-EMAIL", first_name="Maria", last_name="Silva", price_tier=tier,
        )
        fantasma = Customer.objects.create(
            ref="GHOST-002", first_name="", last_name="",
            email="fantasma@example.com", price_tier=tier,
        )

        MergeService.merge(fantasma, sem_email, evidence=evidence, actor="pdv")

        sem_email.refresh_from_db()
        assert sem_email.email == "fantasma@example.com"

    def test_contato_ja_existente_no_sobrevivente_MANDA(self, tier, source, target, evidence):
        """Com principal próprio, quem governa o cache é ele — não o que chegou.

        É a regra do Core, e é por isso que o cache não se copia à mão aqui: o
        ContactPoint que chega é demovido antes de mudar de dono, e um preencher
        manual passaria por cima do principal que o sobrevivente já tinha.
        """
        MergeService.merge(source, target, evidence=evidence, actor="pdv")

        target.refresh_from_db()
        assert target.email == "maria.silva@example.com"
        assert target.phone == "+5543922222222"

    def test_telefone_solto_troca_de_dono_sem_violar_o_unique(self, tier, evidence):
        """`unique_customer_phone` é GLOBAL e não olha `is_active`: o número tem
        de sair do doador ANTES de entrar no sobrevivente, ou os dois o têm por
        um instante e o banco recusa."""
        sem_telefone = Customer.objects.create(
            ref="TGT-SEM-TEL", first_name="Maria", last_name="Silva", price_tier=tier,
        )
        fantasma = Customer.objects.create(
            ref="GHOST-003", first_name="", last_name="",
            phone="+5543933333333", price_tier=tier,
        )

        MergeService.merge(fantasma, sem_telefone, evidence=evidence, actor="pdv")

        sem_telefone.refresh_from_db()
        fantasma.refresh_from_db()
        assert sem_telefone.phone == "+5543933333333"
        assert fantasma.phone == ""

    def test_quem_sobrevive_nunca_e_sobrescrito(self, tier, target, evidence):
        """Só LACUNA. O sobrevivente está na comanda e é dele que o operador
        acabou de falar com o cliente: um merge que troca o CPF de quem fica não
        unifica, adultera."""
        doador = Customer.objects.create(
            ref="SRC-DOC", first_name="Maria", last_name="Souza",
            document="52998224725", price_tier=tier,
        )
        target.document = "11144477735"
        target.save(update_fields=["document"])

        MergeService.merge(doador, target, evidence=evidence, actor="pdv")

        target.refresh_from_db()
        assert target.document == "11144477735"

    def test_o_nome_anda_inteiro_ou_nao_anda(self, tier, evidence):
        """Emprestar só o sobrenome constrói uma pessoa que não existe."""
        doador = Customer.objects.create(
            ref="SRC-NOME", first_name="Ana", last_name="Souza", price_tier=tier,
        )
        sem_sobrenome = Customer.objects.create(
            ref="TGT-NOME", first_name="Ana", last_name="", price_tier=tier,
        )

        MergeService.merge(doador, sem_sobrenome, evidence=evidence, actor="pdv")

        sem_sobrenome.refresh_from_db()
        assert sem_sobrenome.last_name == ""
        assert sem_sobrenome.name == "Ana"

    def test_fantasma_como_alvo_ganha_o_nome_do_doador(self, tier, fantasma, evidence):
        """A direção inversa (possível pelo Admin): quem fica é o sem rosto."""
        com_nome = Customer.objects.create(
            ref="SRC-ROSTO", first_name="Ana", last_name="Souza", price_tier=tier,
        )

        MergeService.merge(com_nome, fantasma, evidence=evidence, actor="admin")

        fantasma.refresh_from_db()
        assert fantasma.name == "Ana Souza"

    def test_undo_devolve_o_documento_ao_doador(self, fantasma, target, evidence):
        result = MergeService.merge(fantasma, target, evidence=evidence, actor="pdv")

        MergeService.undo(result.audit_id, actor="gerente")

        target.refresh_from_db()
        fantasma.refresh_from_db()
        assert target.document == ""
        assert fantasma.document == "11144477735"

    def test_undo_nao_pisa_em_correcao_feita_depois(self, fantasma, target, evidence):
        """Entre a unificação e o desfazer cabem 24h de balcão. Se alguém
        corrigiu o CPF nesse meio-tempo, o valor que está lá é decisão de
        alguém — e "desfazer" não pode apagá-la calado."""
        result = MergeService.merge(fantasma, target, evidence=evidence, actor="pdv")
        target.refresh_from_db()
        target.document = "52998224725"
        target.save(update_fields=["document"])

        MergeService.undo(result.audit_id, actor="gerente")

        target.refresh_from_db()
        assert target.document == "52998224725"
