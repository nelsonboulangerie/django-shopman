from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shop", "0055_catalog_snapshot_binding")]

    operations = [
        migrations.AlterModelOptions(
            name="conversation",
            options={
                "ordering": ("-last_inbound_at", "-id"),
                "permissions": [
                    ("review_conversation_observations", "Pode revisar observações da concierge")
                ],
                "verbose_name": "conversa do concierge",
                "verbose_name_plural": "conversas do concierge",
            },
        ),
        migrations.AddField(
            model_name="conversationmessage",
            name="automation_eligible",
            field=models.BooleanField(
                db_index=True,
                default=True,
                verbose_name="elegível para automação",
            ),
        ),
        migrations.AddField(
            model_name="conversationmessage",
            name="retention_until",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="reter até",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversationmessage",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("automation_eligible", True),
                    ("retention_until__isnull", False),
                    _connector="OR",
                ),
                name="shop_cmsg_observation_retention",
            ),
        ),
    ]
