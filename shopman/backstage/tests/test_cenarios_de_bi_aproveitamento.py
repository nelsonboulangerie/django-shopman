"""Cenários salvos do B.I. com a métrica de aproveitamento falam "aproveitamento".

O UX-PROD-AF2 (PR #1439) renomeou a métrica ``yield_percent`` para "Aproveitamento". A
migração ``backstage.0082`` leva o vocabulário novo aos cenários que os gestores já
salvaram, sem tocar cenário de outra métrica nem apagar o que colide.
"""

from __future__ import annotations

import importlib

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

# O ``BIView`` saiu na ``backstage.0090`` (os cenários viraram ``SavedView``): a 0082 é
# exercitada no estado em que rodou, o da 0089.
BEFORE_SAVED_VIEWS = [("backstage", "0089_alerta_responder_ate")]

migration = importlib.import_module(
    "shopman.backstage.migrations.0082_cenarios_de_bi_falam_aproveitamento"
)

YIELD = {"metric": "yield_percent", "by": "recipe", "by2": "", "window": {}}
LOSS = {"metric": "loss", "by": "recipe", "by2": "", "window": {}}


def test_bi_nuxt_example_already_speaks_aproveitamento() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    source = (root / "surfaces/bi-nuxt/app/presentation/bi.ts").read_text(encoding="utf-8")
    assert '"Aproveitamento por receita", config: { metric: "yield_percent"' in source
    assert "Rendimento" not in source


def test_word_swap_preserves_initial_case_and_whole_word() -> None:
    assert migration.FORWARDS("Rendimento por receita") == "Aproveitamento por receita"
    assert migration.FORWARDS("Forno 2: rendimento semanal") == "Forno 2: aproveitamento semanal"
    assert migration.FORWARDS("Rendimentos do mês") == "Aproveitamentos do mês"
    assert migration.FORWARDS("Rendimentograma") == "Rendimentograma"
    assert migration.BACKWARDS("Aproveitamento por receita") == "Rendimento por receita"


@pytest.fixture
def bi_view_apps():
    """O banco no estado da 0089 (com o ``BIView``), devolvido à folha no fim."""
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE_SAVED_VIEWS)
    yield executor.loader.project_state(BEFORE_SAVED_VIEWS).apps
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_migration_renames_only_yield_scenarios_and_reverts(bi_view_apps) -> None:
    apps = bi_view_apps
    BIView = apps.get_model("backstage", "BIView")
    ana = User.objects.create(username="ana")
    bia = User.objects.create(username="bia")
    by_recipe = BIView.objects.create(owner_id=ana.pk, name="Rendimento por receita", config=YIELD)
    lowercase = BIView.objects.create(owner_id=ana.pk, name="Forno 2: rendimento", config=YIELD)
    other_metric = BIView.objects.create(owner_id=ana.pk, name="Perda e rendimento", config=LOSS)
    untouched = BIView.objects.create(owner_id=ana.pk, name="Por dia", config=YIELD)
    # Bia já salvou o nome novo: renomear o antigo apagaria um dos dois.
    BIView.objects.create(owner_id=bia.pk, name="Aproveitamento por receita", config=YIELD)
    collides = BIView.objects.create(owner_id=bia.pk, name="Rendimento por receita", config=YIELD)
    too_long = BIView.objects.create(owner_id=bia.pk, name="Rendimento " + "x" * 69, config=YIELD)

    migration.forwards(apps, None)

    rows = (by_recipe, lowercase, other_metric, untouched, collides, too_long)
    for row in rows:
        row.refresh_from_db()
    assert by_recipe.name == "Aproveitamento por receita"
    assert lowercase.name == "Forno 2: aproveitamento"
    assert other_metric.name == "Perda e rendimento"
    assert untouched.name == "Por dia"
    assert collides.name == "Rendimento por receita"
    assert too_long.name == "Rendimento " + "x" * 69

    migration.backwards(apps, None)

    for row in rows:
        row.refresh_from_db()
    assert by_recipe.name == "Rendimento por receita"
    assert lowercase.name == "Forno 2: rendimento"
    assert other_metric.name == "Perda e rendimento"


@pytest.mark.django_db(transaction=True)
def test_migration_runs_on_empty_database(bi_view_apps) -> None:
    apps = bi_view_apps
    BIView = apps.get_model("backstage", "BIView")
    migration.forwards(apps, None)
    migration.backwards(apps, None)
    assert not BIView.objects.exists()
