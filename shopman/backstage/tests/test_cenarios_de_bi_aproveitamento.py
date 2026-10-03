"""Cenários salvos do B.I. com a métrica de aproveitamento falam "aproveitamento".

O UX-PROD-AF2 (PR #1439) renomeou a métrica ``yield_percent`` para "Aproveitamento". A
migração ``backstage.0082`` leva o vocabulário novo aos cenários que os gestores já
salvaram, sem tocar cenário de outra métrica nem apagar o que colide.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import User

from shopman.backstage.models import BIView

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


@pytest.mark.django_db
def test_migration_renames_only_yield_scenarios_and_reverts() -> None:
    ana = User.objects.create(username="ana")
    bia = User.objects.create(username="bia")
    by_recipe = BIView.objects.create(owner=ana, name="Rendimento por receita", config=YIELD)
    lowercase = BIView.objects.create(owner=ana, name="Forno 2: rendimento", config=YIELD)
    other_metric = BIView.objects.create(owner=ana, name="Perda e rendimento", config=LOSS)
    untouched = BIView.objects.create(owner=ana, name="Por dia", config=YIELD)
    # Bia já salvou o nome novo: renomear o antigo apagaria um dos dois.
    BIView.objects.create(owner=bia, name="Aproveitamento por receita", config=YIELD)
    collides = BIView.objects.create(owner=bia, name="Rendimento por receita", config=YIELD)
    too_long = BIView.objects.create(owner=bia, name="Rendimento " + "x" * 69, config=YIELD)

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


@pytest.mark.django_db
def test_migration_runs_on_empty_database() -> None:
    migration.forwards(apps, None)
    migration.backwards(apps, None)
    assert not BIView.objects.exists()
