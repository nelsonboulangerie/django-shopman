import hashlib
import uuid

import django.db.models.deletion
from django.db import migrations, models


def import_legacy_consents(apps, schema_editor):
    Consent = apps.get_model("customer_consent", "CommunicationConsent")
    Event = apps.get_model("customer_consent", "CommunicationConsentEvent")

    for consent in Consent.objects.select_related("customer").iterator(chunk_size=500):
        occurred_at = (
            consent.revoked_at
            or consent.consented_at
            or consent.updated_at
            or consent.created_at
        )
        event_ref = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"shopman:legacy-consent:{consent.pk}",
        )
        customer_ref_hash = hashlib.sha256(
            str(consent.customer.ref).encode("utf-8")
        ).hexdigest()
        evidence_hash = hashlib.sha256(
            (
                f"legacy:{consent.pk}:{consent.channel}:{consent.status}:"
                f"{occurred_at.isoformat()}"
            ).encode()
        ).hexdigest()
        event_type = (
            "revoked" if consent.status == "opted_out" else "legacy_import"
        )
        Event.objects.create(
            ref=event_ref,
            customer=consent.customer,
            customer_ref_hash=customer_ref_hash,
            channel=consent.channel,
            purpose="marketing_general",
            event_type=event_type,
            resulting_status=consent.status,
            legal_basis=consent.legal_basis,
            source=consent.source or "legacy_import",
            disclosure_text="",
            disclosure_version="",
            disclosure_hash="",
            evidence_hash=evidence_hash,
            proof_status="legacy_unverified",
            locale="pt-BR",
            ip_address=consent.ip_address,
            actor_ref="migration:customer_consent:0002",
            occurred_at=occurred_at,
        )
        Consent.objects.filter(pk=consent.pk).update(
            purpose="marketing_general",
            policy_version="",
            disclosure_hash="",
            evidence_hash=evidence_hash,
            locale="pt-BR",
            proof_status="legacy_unverified",
            last_event_ref=event_ref,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("customer_consent", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="communicationconsent",
            name="disclosure_hash",
            field=models.CharField(blank=True, max_length=64, verbose_name="hash do texto"),
        ),
        migrations.AddField(
            model_name="communicationconsent",
            name="evidence_hash",
            field=models.CharField(blank=True, max_length=64, verbose_name="hash da evidência"),
        ),
        migrations.AddField(
            model_name="communicationconsent",
            name="last_event_ref",
            field=models.UUIDField(blank=True, editable=False, null=True, verbose_name="último evento"),
        ),
        migrations.AddField(
            model_name="communicationconsent",
            name="locale",
            field=models.CharField(default="pt-BR", max_length=16, verbose_name="idioma"),
        ),
        migrations.AddField(
            model_name="communicationconsent",
            name="policy_version",
            field=models.CharField(blank=True, max_length=64, verbose_name="versão da política"),
        ),
        migrations.AddField(
            model_name="communicationconsent",
            name="proof_status",
            field=models.CharField(
                choices=[
                    ("verified", "Verificado"),
                    ("legacy_unverified", "Legado sem prova completa"),
                ],
                default="legacy_unverified",
                max_length=24,
                verbose_name="situação da prova",
            ),
        ),
        migrations.AddField(
            model_name="communicationconsent",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("marketing_general", "Marketing geral"),
                    ("stock_availability", "Disponibilidade de produto"),
                    ("transactional_order", "Comunicação do pedido"),
                ],
                default="marketing_general",
                max_length=32,
                verbose_name="finalidade",
            ),
        ),
        migrations.CreateModel(
            name="CommunicationConsentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ref", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("customer_ref_hash", models.CharField(db_index=True, max_length=64, verbose_name="identificador protegido")),
                ("channel", models.CharField(choices=[("whatsapp", "WhatsApp"), ("email", "Email"), ("sms", "SMS"), ("push", "Push Notification")], max_length=20, verbose_name="canal")),
                ("purpose", models.CharField(choices=[("marketing_general", "Marketing geral"), ("stock_availability", "Disponibilidade de produto"), ("transactional_order", "Comunicação do pedido")], default="marketing_general", max_length=32, verbose_name="finalidade")),
                ("event_type", models.CharField(choices=[("granted", "Concedido"), ("revoked", "Revogado"), ("legacy_import", "Importado do legado")], max_length=24, verbose_name="evento")),
                ("resulting_status", models.CharField(choices=[("opted_in", "Opt-in"), ("opted_out", "Opt-out"), ("pending", "Pendente")], max_length=20, verbose_name="estado resultante")),
                ("legal_basis", models.CharField(choices=[("consent", "Consentimento"), ("legitimate_interest", "Interesse legítimo"), ("contract", "Execução de contrato"), ("legal_obligation", "Obrigação legal")], default="consent", max_length=30, verbose_name="base legal")),
                ("source", models.CharField(blank=True, max_length=100, verbose_name="origem")),
                ("disclosure_text", models.TextField(blank=True, verbose_name="texto apresentado")),
                ("disclosure_version", models.CharField(blank=True, max_length=64, verbose_name="versão do texto")),
                ("disclosure_hash", models.CharField(blank=True, max_length=64, verbose_name="hash do texto")),
                ("evidence_hash", models.CharField(max_length=64, unique=True, verbose_name="hash da evidência")),
                ("proof_status", models.CharField(choices=[("verified", "Verificado"), ("legacy_unverified", "Legado sem prova completa")], default="legacy_unverified", max_length=24, verbose_name="situação da prova")),
                ("locale", models.CharField(default="pt-BR", max_length=16, verbose_name="idioma")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True, verbose_name="endereço IP")),
                ("actor_ref", models.CharField(blank=True, max_length=128, verbose_name="responsável")),
                ("occurred_at", models.DateTimeField(verbose_name="ocorrido em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="registrado em")),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="consent_events", to="guestman.customer", verbose_name="cliente")),
            ],
            options={
                "verbose_name": "evento de consentimento",
                "verbose_name_plural": "eventos de consentimento",
                "ordering": ["occurred_at", "pk"],
                "indexes": [models.Index(fields=["customer", "channel", "purpose", "occurred_at"], name="customer_co_custome_db183b_idx")],
            },
        ),
        migrations.RunPython(import_legacy_consents, migrations.RunPython.noop),
    ]
