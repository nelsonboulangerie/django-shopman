import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("guestman", "0004_alter_customer_ref"),
        ("shop", "0022_shoppurchase"),
    ]

    operations = [
        migrations.CreateModel(
            name="AudienceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ref", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("summary", models.JSONField(default=dict)),
                ("rule_summary", models.JSONField(default=dict)),
                ("rule_hash", models.CharField(max_length=64)),
                ("cohort_hash", models.CharField(max_length=64)),
                ("policy_version", models.CharField(max_length=64)),
                ("calculated_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("sealed_at", models.DateTimeField(auto_now_add=True)),
                ("retention_until", models.DateTimeField()),
                ("announcement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audience_snapshots", to="shop.announcement")),
            ],
            options={
                "ordering": ["-sealed_at"],
                "constraints": [models.UniqueConstraint(condition=models.Q(("announcement__isnull", False)), fields=("announcement", "version"), name="shop_audience_snapshot_announcement_version_uq")],
            },
        ),
        migrations.CreateModel(
            name="AudienceSnapshotMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subscription_ref", models.UUIDField(blank=True, null=True)),
                ("target_key", models.CharField(max_length=64)),
                ("reasons", models.JSONField(default=list)),
                ("is_vip", models.BooleanField(default=False)),
                ("preferred_hour", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marketing_audience_memberships", to="guestman.customer")),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="members", to="shop.audiencesnapshot")),
            ],
            options={
                "indexes": [models.Index(fields=["snapshot", "customer"], name="shop_audien_snapsho_003822_idx")],
                "constraints": [models.UniqueConstraint(fields=("snapshot", "target_key"), name="shop_audience_snapshot_member_target_uq"), models.CheckConstraint(condition=models.Q(("customer__isnull", False), ("subscription_ref__isnull", False), _connector="OR"), name="shop_audience_snapshot_member_has_identity")],
            },
        ),
    ]
