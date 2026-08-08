"""Rename: BroadcastRule→Campaign, BroadcastPost→Announcement, PostTemplate→AnnouncementTemplate.

`broadcast` nomeia o transporte, e descrevia mal metade do que a feature faz: uma
onda de WhatsApp é broadcast, um `localPost` de Google Business é colocação e um
banner na TV é sinalização — e o mesmo registro dirige os três. `Campaign` nomeia
o compromisso (levar esta oferta a este público nesta janela) e `Announcement`
nomeia o fato (o que foi dito, a quem, com que resultado). "Post" era palavra do
Instagram para uma linha que também manda SMS.

Escrita à mão de propósito: o autodetector pede confirmação interativa para
rename de model, e aqui as opções e o `related_name` mudam junto.

O rename de ContentType é injetado automaticamente pelo app `contenttypes`
(post-migrate). As **permissões** não: elas são renomeadas na 0030, que roda
depois, para preservar os IDs e portanto as concessões a grupos e usuários
(a armadilha que a ADR-011 §Negativas registrou).

Refs ADR-020 §1, plano F2.
"""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0028_marketing_consent_single_owner"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. Os três modelos ────────────────────────────────────────
        migrations.RenameModel(old_name="PostTemplate", new_name="AnnouncementTemplate"),
        migrations.RenameModel(old_name="BroadcastRule", new_name="Campaign"),
        migrations.RenameModel(old_name="BroadcastPost", new_name="Announcement"),
        # ── 2. Opções (rótulos PT + a permissão renomeada) ────────────
        migrations.AlterModelOptions(
            name="announcementtemplate",
            options={
                "ordering": ["name"],
                "verbose_name": "modelo de anúncio",
                "verbose_name_plural": "modelos de anúncio",
            },
        ),
        migrations.AlterModelOptions(
            name="campaign",
            options={
                "ordering": ["name"],
                "permissions": [("manage_campaigns", "Pode revisar e publicar campanhas")],
                "verbose_name": "campanha",
                "verbose_name_plural": "campanhas",
            },
        ),
        migrations.AlterModelOptions(
            name="announcement",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "anúncio",
                "verbose_name_plural": "anúncios",
            },
        ),
        # ── 3. related_name do aprovador ─────────────────────────────
        migrations.AlterField(
            model_name="announcement",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_announcements",
                to=settings.AUTH_USER_MODEL,
                verbose_name="aprovado por",
            ),
        ),
    ]
