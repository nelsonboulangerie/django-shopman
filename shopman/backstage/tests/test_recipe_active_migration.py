"""A troca para ``is_active`` preserva o sentido dos registros existentes."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def test_recipe_archive_flag_is_renamed_and_inverted() -> None:
    before = [("craftsman", "0017_abertura_fechamento_labels")]
    after = [("craftsman", "0018_recipeentry_is_active")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    old_recipe_entry = old_apps.get_model("craftsman", "RecipeEntry")
    active = old_recipe_entry.objects.create(ref="ativa", name="Ativa", is_archived=False)
    archived = old_recipe_entry.objects.create(ref="arquivada", name="Arquivada", is_archived=True)

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new_apps = executor.loader.project_state(after).apps
    recipe_entry = new_apps.get_model("craftsman", "RecipeEntry")

    assert recipe_entry.objects.get(pk=active.pk).is_active is True
    assert recipe_entry.objects.get(pk=archived.pk).is_active is False
    assert recipe_entry._meta.get_field("is_active").default is True
