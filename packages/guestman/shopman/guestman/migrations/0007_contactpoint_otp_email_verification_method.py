from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("guestman", "0006_customer_price_tiers_advantage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contactpoint",
            name="verification_method",
            field=models.CharField(
                choices=[
                    ("unverified", "Não verificado"),
                    ("channel_asserted", "Verificado pelo canal"),
                    ("otp_whatsapp", "OTP via WhatsApp"),
                    ("otp_sms", "OTP via SMS"),
                    ("otp_email", "OTP via email"),
                    ("email_link", "Link por email"),
                    ("manual", "Manual (equipe)"),
                ],
                default="unverified",
                max_length=20,
                verbose_name="método de verificação",
            ),
        ),
    ]
