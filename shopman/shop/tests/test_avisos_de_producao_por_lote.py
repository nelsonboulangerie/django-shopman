"""Avisos de produção ao operador falam de lote e aproveitamento.

O UX-PROD-AF (PR #1433) trocou no seed o texto de ``production_low_yield`` e
``production_forgotten``. A migração ``shop.0088`` leva o mesmo texto ao banco vivo sem
reseed e sem tocar o que o lojista editou no Admin.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps

from shopman.shop.models import NotificationTemplate

migration = importlib.import_module("shopman.shop.migrations.0088_avisos_de_producao_por_lote")


def test_seed_text_is_what_the_migration_writes() -> None:
    from config.management.commands.seed import NOTIFICATION_TEMPLATES

    for event, fields in migration.TEMPLATES.items():
        for field, (_old, new) in fields.items():
            assert NOTIFICATION_TEMPLATES[event][field] == new, (event, field)


def _old(event: str, field: str) -> str:
    return migration.TEMPLATES[event][field][0]


def _new(event: str, field: str) -> str:
    return migration.TEMPLATES[event][field][1]


@pytest.mark.django_db
def test_migration_rewrites_only_the_exact_seed_text() -> None:
    seeded = NotificationTemplate.objects.create(
        event="production_low_yield",
        subject=_old("production_low_yield", "subject"),
        body=_old("production_low_yield", "body"),
    )
    # Assunto ainda do seed, mensagem editada à mão: só o assunto muda.
    half_edited = NotificationTemplate.objects.create(
        event="production_forgotten",
        subject=_old("production_forgotten", "subject"),
        body="Ninguém abriu o {work_order_ref}. Liga pra cozinha.",
    )
    other = NotificationTemplate.objects.create(
        event="production_late",
        subject="Yield baixo na produção {work_order_ref}",
        body="Texto qualquer",
    )

    migration.forwards(apps, None)

    for row in (seeded, half_edited, other):
        row.refresh_from_db()
    assert seeded.subject == _new("production_low_yield", "subject")
    assert seeded.body == _new("production_low_yield", "body")
    assert seeded.version == 3
    assert half_edited.subject == _new("production_forgotten", "subject")
    assert half_edited.body == "Ninguém abriu o {work_order_ref}. Liga pra cozinha."
    assert half_edited.version == 2
    assert other.subject == "Yield baixo na produção {work_order_ref}"
    assert other.version == 1

    migration.backwards(apps, None)

    seeded.refresh_from_db()
    half_edited.refresh_from_db()
    assert seeded.subject == _old("production_low_yield", "subject")
    assert seeded.body == _old("production_low_yield", "body")
    assert half_edited.subject == _old("production_forgotten", "subject")
    assert half_edited.body == "Ninguém abriu o {work_order_ref}. Liga pra cozinha."


@pytest.mark.django_db
def test_migration_runs_on_an_empty_database() -> None:
    NotificationTemplate.objects.all().delete()
    migration.forwards(apps, None)
    migration.backwards(apps, None)
    assert not NotificationTemplate.objects.exists()
