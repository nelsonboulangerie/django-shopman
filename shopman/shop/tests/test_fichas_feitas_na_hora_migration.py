"""A migração ``shop.0102`` marca as fichas feitas na hora no banco já semeado (ADR-040).

Marca só a lista do seed, pelo ``ref``; não mexe em mais nada; ficha ausente ou
ATIVA fica de fora sem erro; roda duas vezes sem efeito; o reverse desmarca só
o que ela marcou. A lista é a do seed: ``backstage/tests/test_ficha_feita_na_hora.py``.
"""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from django.apps import apps
from shopman.craftsman.models import Recipe

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.shop.migrations.0102_fichas_feitas_na_hora")


def _ficha(ref: str, *, is_active: bool = False, meta: dict | None = None) -> Recipe:
    return Recipe.objects.create(
        ref=ref, name=ref, output_sku=ref.upper(), batch_size=Decimal("1"), is_active=is_active,
        meta=meta if meta is not None else {"capacity_per_day": 40},
    )


def _meta(ref: str) -> dict:
    return Recipe.objects.get(ref=ref).meta


def test_a_lista_tem_as_21_fichas_sem_repeticao():
    assert len(migration.MADE_TO_ORDER_RECIPE_REFS) == 21
    assert len(set(migration.MADE_TO_ORDER_RECIPE_REFS)) == 21


def test_marca_so_as_fichas_da_lista_sem_tocar_no_resto(capsys):
    _ficha("espresso")
    _ficha("croque-monsieur")
    _ficha("pao-de-campagne")  # fora da lista

    marked = migration.mark(apps, None)

    assert sorted(marked) == ["croque-monsieur", "espresso"]
    assert _meta("espresso") == {
        "capacity_per_day": 40,
        "made_to_order": True,
        "made_to_order_marked_by": migration.MIGRATION_NAME,
    }
    assert _meta("pao-de-campagne") == {"capacity_per_day": 40}
    assert Recipe.objects.get(ref="espresso").is_active is False
    # Registra quantas marcou (19 da lista não existem neste banco).
    assert "2 fichas marcadas" in capsys.readouterr().out


def test_ficha_ativa_fica_de_fora():
    _ficha("cappuccino", is_active=True)

    assert migration.mark(apps, None) == []
    assert "made_to_order" not in _meta("cappuccino")


def test_roda_duas_vezes_sem_efeito():
    _ficha("mocha")

    assert migration.mark(apps, None) == ["mocha"]
    first = _meta("mocha")
    assert migration.mark(apps, None) == []
    assert _meta("mocha") == first


def test_reverse_desmarca_so_o_que_ela_marcou():
    _ficha("cha-bleu")
    _ficha("cha-rouge", meta={"made_to_order": True})  # marca do seed ou do Admin

    migration.mark(apps, None)
    migration.unmark(apps, None)

    assert _meta("cha-bleu") == {"capacity_per_day": 40}
    assert _meta("cha-rouge") == {"made_to_order": True}


def test_banco_vazio_nao_falha():
    assert migration.mark(apps, None) == []
    migration.unmark(apps, None)
