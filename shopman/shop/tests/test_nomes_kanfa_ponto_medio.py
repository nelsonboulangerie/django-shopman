"""Nomes de produto separam a embalagem com ponto médio, não com travessão.

Decisão do dono (03/10/2026): "Chalosofia Kãnfa · Lata 50g". O seed nasce assim, e a
migração ``shop.0087`` leva o mesmo texto ao banco vivo sem tocar o que foi editado à
mão. O hint do defeito "Contaminado" sai do travessão pela pontuação do sentido.

A trava geral de copy (``shopman/backstage/tests/test_copy_sem_travessao.py``) não lê
``management/commands/`` (a saída do comando vai para o terminal); por isso a tabela de
produtos do seed tem a trava dela aqui.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest
from django.apps import apps
from shopman.buyman.models import Material
from shopman.offerman.models import Product

from shopman.shop.models import QualityDefect

REPO = Path(__file__).resolve().parents[3]
CATALOG_SOURCES = (
    "config/management/commands/seed.py",
    "config/management/commands/apply_grocery_catalog.py",
)
SKU = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")

migration = importlib.import_module("shopman.shop.migrations.0087_nomes_kanfa_com_ponto_medio")


def _product_names(source: str) -> list[tuple[str, str]]:
    """(sku, nome) das tabelas de catálogo: tupla ``("SKU", "Nome", ...)`` e ``GroceryItem("SKU", "Nome", ...)``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Tuple):
            items = node.elts
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "GroceryItem":
            items = node.args
        else:
            continue
        if len(items) >= 2 and all(isinstance(i, ast.Constant) and isinstance(i.value, str) for i in items[:2]):
            sku, name = items[0].value, items[1].value
            if SKU.match(sku) and " " in name:
                found.append((sku, name))
    return found


@pytest.mark.parametrize("relative", CATALOG_SOURCES)
def test_catalog_names_use_middle_dot_not_em_dash(relative: str) -> None:
    names = _product_names((REPO / relative).read_text(encoding="utf-8"))
    assert len(names) > 10, f"{relative}: a leitura achou só {len(names)} nomes"
    assert [entry for entry in names if "—" in entry[1]] == []


def test_seed_names_are_what_the_migration_writes() -> None:
    seeded = dict(
        entry
        for relative in CATALOG_SOURCES
        for entry in _product_names((REPO / relative).read_text(encoding="utf-8"))
    )
    for sku, (_old, new) in migration.NAMES.items():
        assert seeded.get(sku) == new, sku


def test_seed_defect_hint_is_what_the_migration_writes() -> None:
    from config.management.commands.seed import QUALITY_DEFECTS

    hints = {ref: hint for ref, _label, hint, *_ in QUALITY_DEFECTS}
    assert all("—" not in hint for hint in hints.values())
    for ref, (_old, new) in migration.HINTS.items():
        assert hints[ref] == new


@pytest.mark.django_db
def test_migration_renames_only_the_exact_seed_text() -> None:
    seeded = Product.objects.create(sku="CHA-CHALOSOFIA-KANFA-L50", name="Chalosofia Kãnfa — Lata 50g", base_price_q=7300)
    edited = Product.objects.create(sku="CHA-MAMA-KANFA-P50", name="Mama Chai (pouch)", base_price_q=6000)
    other = Product.objects.create(sku="JB", name="Jambon — Beurre", base_price_q=1800)
    material = Material.objects.create(sku="CHA-CHALOSOFIA-KANFA-L50", name="Chalosofia Kãnfa — Lata 50g", unit="un")
    # As migrações de catálogo (shop.0013/0018) já semeiam os defeitos no banco de teste.
    defect, _ = QualityDefect.objects.update_or_create(
        ref="contaminated", defaults={"label": "Contaminado", "hint": "Matéria estranha — não vende"}
    )
    edited_defect, _ = QualityDefect.objects.update_or_create(
        ref="misshapen", defaults={"label": "Deformado", "hint": "Torto — colado"}
    )

    migration.forwards(apps, None)

    for row in (seeded, edited, other, material, defect, edited_defect):
        row.refresh_from_db()
    assert seeded.name == "Chalosofia Kãnfa · Lata 50g"
    assert material.name == "Chalosofia Kãnfa · Lata 50g"
    assert edited.name == "Mama Chai (pouch)"
    assert other.name == "Jambon — Beurre"
    assert defect.hint == "Matéria estranha: não vende"
    assert edited_defect.hint == "Torto — colado"

    migration.backwards(apps, None)

    seeded.refresh_from_db()
    material.refresh_from_db()
    defect.refresh_from_db()
    edited.refresh_from_db()
    assert seeded.name == "Chalosofia Kãnfa — Lata 50g"
    assert material.name == "Chalosofia Kãnfa — Lata 50g"
    assert defect.hint == "Matéria estranha — não vende"
    assert edited.name == "Mama Chai (pouch)"


@pytest.mark.django_db
def test_migration_runs_on_an_empty_database() -> None:
    QualityDefect.objects.all().delete()
    migration.forwards(apps, None)
    migration.backwards(apps, None)
    assert not Product.objects.exists()
