import hashlib
import uuid
from datetime import timedelta

from django.db import migrations, models
from django.db.models import Q


def protect_legacy_subscriptions(apps, schema_editor):
    Subscription = apps.get_model("storefront", "StockAlertSubscription")
    seen: set[tuple[str, str, str, str]] = set()

    for sub in Subscription.objects.order_by("subscribed_at", "pk").iterator(chunk_size=500):
        identity = f"customer:{sub.customer_ref}" if sub.customer_ref else f"phone:{sub.contact_phone.strip()}"
        target_key = hashlib.sha256(identity.encode()).hexdigest()
        evidence_hash = hashlib.sha256(
            f"legacy-stock-alert:{sub.pk}:{sub.sku}:{sub.alert_type}:{target_key}".encode()
        ).hexdigest()
        subscription_ref = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"shopman:legacy-stock-alert:{sub.pk}",
        )
        expires_at = sub.subscribed_at + timedelta(days=30)
        key = (sub.sku, sub.alert_type, sub.channel_ref, target_key)
        duplicate = sub.notified_at is None and key in seen
        if sub.notified_at is None:
            seen.add(key)

        values = {
            "ref": subscription_ref,
            "delivery_channel": "whatsapp",
            "purpose": "stock_availability",
            "target_key": target_key,
            "disclosure_text": "",
            "disclosure_version": "",
            "disclosure_hash": "",
            "evidence_hash": evidence_hash,
            "proof_status": "legacy_unverified",
            "expires_at": expires_at,
        }
        if duplicate:
            values.update(
                revoked_at=sub.subscribed_at,
                revoke_reason="legacy_duplicate",
                revocation_evidence_hash=hashlib.sha256(
                    f"legacy-duplicate:{sub.pk}:{target_key}".encode()
                ).hexdigest(),
            )
        Subscription.objects.filter(pk=sub.pk).update(**values)


class Migration(migrations.Migration):
    dependencies = [
        ("storefront", "0002_rotulos_em_portugues"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockalertsubscription",
            name="ref",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="delivery_channel",
            field=models.CharField(default="whatsapp", max_length=20, verbose_name="canal de entrega"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="purpose",
            field=models.CharField(default="stock_availability", max_length=32, verbose_name="finalidade"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="target_key",
            field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name="identificador protegido"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="disclosure_text",
            field=models.TextField(blank=True, verbose_name="texto apresentado"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="disclosure_version",
            field=models.CharField(blank=True, max_length=64, verbose_name="versão do texto"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="disclosure_hash",
            field=models.CharField(blank=True, max_length=64, verbose_name="hash do texto"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="evidence_hash",
            field=models.CharField(blank=True, max_length=64, verbose_name="hash da evidência"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="proof_status",
            field=models.CharField(choices=[("verified", "verificada"), ("legacy_unverified", "legado sem prova completa")], default="legacy_unverified", max_length=24, verbose_name="situação da prova"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="expira em"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="revoked_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="cancelado em"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="revoke_reason",
            field=models.CharField(blank=True, max_length=100, verbose_name="motivo do cancelamento"),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="revocation_evidence_hash",
            field=models.CharField(blank=True, max_length=64, verbose_name="hash da revogação"),
        ),
        migrations.RunPython(protect_legacy_subscriptions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="stockalertsubscription",
            name="ref",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="stockalertsubscription",
            name="target_key",
            field=models.CharField(db_index=True, max_length=64, verbose_name="identificador protegido"),
        ),
        migrations.AlterField(
            model_name="stockalertsubscription",
            name="evidence_hash",
            field=models.CharField(max_length=64, unique=True, verbose_name="hash da evidência"),
        ),
        migrations.AddConstraint(
            model_name="stockalertsubscription",
            constraint=models.UniqueConstraint(
                condition=Q(notified_at__isnull=True, revoked_at__isnull=True),
                fields=("sku", "alert_type", "channel_ref", "target_key"),
                name="storefront_stock_alert_pending_target_uq",
            ),
        ),
    ]
