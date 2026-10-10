"""Posto de trabalho desacoplado do caixa (UX-POSTO1).

Cria o modelo e um posto por ``Terminal`` que já existe, com o MESMO ref: a confiança
dos dispositivos já provisionados (``doorman.TrustedDevice.subject_id``) continua
apontando para um posto, e nenhum tablet precisa ser provisionado de novo.

O terminal declarado autônomo (o painel da Produção) vira Sala da Produção; os
demais, Caixa. O gestor renomeia e reclassifica depois, no cadastro de Postos.

A arrumação das colunas do Gestor (``Terminal.metadata["gestor_board"]``) muda para
``Workstation.metadata["gestor_board"]``, e sai do terminal.
"""

import django.db.models.deletion
from django.db import migrations, models

BOARD_KEY = "gestor_board"


def forward(apps, schema_editor):
    Terminal = apps.get_model("cashman", "Terminal")
    Workstation = apps.get_model("backstage", "Workstation")
    for terminal in Terminal.objects.all().order_by("ref"):
        metadata = dict(terminal.metadata) if isinstance(terminal.metadata, dict) else {}
        station = metadata.get("station") if isinstance(metadata.get("station"), dict) else {}
        autonomous = str(station.get("mode") or "").strip().lower() == "autonomous"
        preferences = {}
        if BOARD_KEY in metadata:
            preferences[BOARD_KEY] = metadata.pop(BOARD_KEY)
            terminal.metadata = metadata
            terminal.save(update_fields=["metadata"])
        Workstation.objects.update_or_create(
            ref=terminal.ref,
            defaults={
                "label": (terminal.label or terminal.ref)[:80],
                "kind": "production_room" if autonomous else "cash_desk",
                "terminal": terminal,
                "metadata": preferences,
                "is_active": terminal.is_active,
            },
        )


def backward(apps, schema_editor):
    Workstation = apps.get_model("backstage", "Workstation")
    for workstation in Workstation.objects.exclude(terminal=None).select_related("terminal"):
        board = (workstation.metadata or {}).get(BOARD_KEY)
        if board is None:
            continue
        terminal = workstation.terminal
        metadata = dict(terminal.metadata) if isinstance(terminal.metadata, dict) else {}
        metadata[BOARD_KEY] = board
        terminal.metadata = metadata
        terminal.save(update_fields=["metadata"])


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0080_recipe_rating"),
        ("cashman", "0006_alter_terminal_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="Workstation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ref",
                    models.SlugField(max_length=80, unique=True, verbose_name="ref"),
                ),
                ("label", models.CharField(max_length=80, verbose_name="nome")),
                ("kind", models.CharField(max_length=32, verbose_name="tipo")),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Preferências do posto (ex.: gestor_board). Schema em docs/reference/data-schemas.md.",
                        verbose_name="preferências",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "terminal",
                    models.OneToOneField(
                        blank=True,
                        help_text="Só o posto Caixa tem gaveta e turno.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workstation",
                        to="cashman.terminal",
                        verbose_name="caixa",
                    ),
                ),
            ],
            options={
                "verbose_name": "posto de trabalho",
                "verbose_name_plural": "postos de trabalho",
                "ordering": ["label", "ref"],
            },
        ),
        migrations.RunPython(forward, backward),
    ]
