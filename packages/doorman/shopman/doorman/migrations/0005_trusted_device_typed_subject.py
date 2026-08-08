"""Confiança de dispositivo passa a ter sujeito TIPADO: cliente ou display.

`customer_id` (UUID) vira o par `subject_type` + `subject_id` (textual) — a forma
``handle_type`` + ``handle_ref`` que a constituição §3.1 nomeia como chave de
vínculo com ator/canal/contexto. Textual porque os sujeitos se identificam
diferente: cliente por UUID, display por ``ref`` de canal (`tv-cafe`).

Por que generalizar em vez de inventar credencial nova: confiança de dispositivo é
"este navegador já foi verificado para X, não verifique de novo", e o X não precisa
ser pessoa. Um quadro de menu na parede é um navegador autorizado a ler um quadro —
mesma forma, e de graça vêm revogação por dispositivo, expiração, e auditoria
(`label`, `ip_address`, `last_used_at`) que uma credencial nova não teria.

Zero prejuízo ao uso atual: `customer_id` **não era FK** (UUIDField puro, "same
decoupling pattern"), então não há relação a reescrever, e toda linha existente sai
daqui como `subject_type="customer"` com o mesmo valor.

Quatro operações em vez de um `AlterField` de UUID→varchar, de propósito: cast de
tipo depende do backend (SQLite local, PostgreSQL em staging) e um `USING` implícito
é justamente o lugar onde uma migração de Core silencia um erro. Copiar é
verificável.

`operator` NÃO entra: lembrar o terminal do PDV para não pedir PIN é feature
legítima e sem pedido (§8.3).

Refs constituição §3.1 e §4.7, ADR-004, ADR-018 §5.1.
"""

from __future__ import annotations

from django.db import migrations, models


def copy_customer_to_subject(apps, schema_editor):
    TrustedDevice = apps.get_model("doorman", "TrustedDevice")
    for device in TrustedDevice.objects.all().iterator():
        device.subject_type = "customer"
        device.subject_id = str(device.customer_id)
        device.save(update_fields=["subject_type", "subject_id"])


def copy_subject_to_customer(apps, schema_editor):
    """Só volta o que era cliente — display não tem para onde voltar."""
    import uuid as _uuid

    TrustedDevice = apps.get_model("doorman", "TrustedDevice")
    for device in TrustedDevice.objects.filter(subject_type="customer").iterator():
        try:
            device.customer_id = _uuid.UUID(device.subject_id)
        except (ValueError, AttributeError, TypeError):
            continue
        device.save(update_fields=["customer_id"])
    TrustedDevice.objects.exclude(subject_type="customer").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("doorman", "0004_pincredential_must_change"),
    ]

    operations = [
        # 1. Colunas novas, ainda vazias.
        migrations.AddField(
            model_name="trusteddevice",
            name="subject_type",
            field=models.CharField(
                choices=[("customer", "cliente"), ("display", "display")],
                db_index=True,
                default="customer",
                max_length=16,
                verbose_name="tipo de sujeito",
            ),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="subject_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="UUID do cliente no Guestman, ou ref do canal de exibição.",
                max_length=64,
                verbose_name="ID do sujeito",
            ),
        ),
        # 2. Copia o que existe (sem cast de tipo no banco).
        migrations.RunPython(copy_customer_to_subject, copy_subject_to_customer),
        # 3. O índice antigo sai junto com a coluna antiga.
        migrations.RemoveIndex(
            model_name="trusteddevice",
            name="doorman_tru_custome_57d429_idx",
        ),
        migrations.RemoveField(model_name="trusteddevice", name="customer_id"),
        # 4. Forma final do campo: o default/blank existiu só para o AddField poder
        #    rodar numa tabela com linhas.
        migrations.AlterField(
            model_name="trusteddevice",
            name="subject_id",
            field=models.CharField(
                db_index=True,
                help_text="UUID do cliente no Guestman, ou ref do canal de exibição.",
                max_length=64,
                verbose_name="ID do sujeito",
            ),
        ),
        # 5. Índice novo pelo par.
        migrations.AddIndex(
            model_name="trusteddevice",
            index=models.Index(
                fields=["subject_type", "subject_id", "is_active"],
                name="doorman_tru_subject_0f2086_idx",
            ),
        ),
    ]
