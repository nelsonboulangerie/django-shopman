"""A migração ``shop.0104`` põe as fichas montadas na venda vigentes e "Na hora" (ADR-040).

No banco já semeado (o alpha) elas estavam INATIVAS com a marca
``meta["made_to_order"]``. A migração: dá o modo "Na hora" às fichas da lista,
devolve a vigência às que estavam arquivadas só por isso (sem violar uma vigente
por SKU), limpa a marca antiga de toda ficha, roda duas vezes sem efeito e
reverte ao estado da ``shop.0102``.
"""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from django.apps import apps
from shopman.craftsman.models import ProductionMode, Recipe

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.shop.migrations.0104_fichas_na_hora_vigentes")


def _ficha(ref: str, *, is_active: bool = False, meta: dict | None = None, sku: str = "") -> Recipe:
    recipe = Recipe(
        ref=ref, name=ref, output_sku=sku or ref.upper(), batch_size=Decimal("1"), is_active=is_active,
        meta=meta if meta is not None else {"capacity_per_day": 40, "made_to_order": True},
    )
    # Grava sem o ``clean`` de hoje: é o dado como o alpha o tem.
    Recipe.objects.bulk_create([recipe])
    return Recipe.objects.get(ref=ref)


def _recipe(ref: str) -> Recipe:
    return Recipe.objects.get(ref=ref)


def test_a_lista_tem_as_21_fichas_sem_repeticao():
    assert len(migration.MADE_TO_ORDER_RECIPE_REFS) == 21
    assert len(set(migration.MADE_TO_ORDER_RECIPE_REFS)) == 21


def test_aplica_vigente_na_hora_e_limpa_a_marca(capsys):
    _ficha("espresso", meta={"capacity_per_day": 40, "made_to_order": True, "made_to_order_marked_by": "x"})
    _ficha("croque-monsieur")
    _ficha("pao-de-campagne", is_active=True, meta={"made_to_order": True, "output_unit": "kg"})  # fora da lista

    result = migration.forward(apps, None)

    assert sorted(result["activated"]) == ["croque-monsieur", "espresso"]
    espresso = _recipe("espresso")
    assert espresso.is_active is True
    assert espresso.production_mode == ProductionMode.MADE_TO_ORDER
    assert espresso.meta == {"capacity_per_day": 40}
    pao = _recipe("pao-de-campagne")
    assert pao.production_mode == ProductionMode.BATCH
    assert pao.meta == {"output_unit": "kg"}
    assert "2 fichas Na hora (2 voltaram a vigentes)" in capsys.readouterr().out


def test_sku_com_outra_vigente_fica_arquivado_e_o_log_diz_qual(capsys):
    _ficha("espresso-novo", is_active=True, meta={}, sku="SP")
    _ficha("espresso", sku="SP")

    result = migration.forward(apps, None)

    assert result["activated"] == []
    assert result["kept_archived"] == ["espresso (SP já tem espresso-novo)"]
    assert _recipe("espresso").is_active is False
    assert _recipe("espresso").production_mode == ProductionMode.MADE_TO_ORDER
    assert "espresso (SP já tem espresso-novo)" in capsys.readouterr().out


def test_roda_duas_vezes_sem_efeito():
    _ficha("mocha")

    migration.forward(apps, None)
    first = _recipe("mocha")
    second_result = migration.forward(apps, None)
    again = _recipe("mocha")

    assert second_result["activated"] == []
    assert second_result["cleaned"] == 0
    assert (again.is_active, again.production_mode, again.meta) == (first.is_active, first.production_mode, first.meta)


def test_reverte_ao_estado_da_0102():
    _ficha("cha-bleu")

    migration.forward(apps, None)
    migration.backward(apps, None)

    recipe = _recipe("cha-bleu")
    assert recipe.is_active is False
    assert recipe.production_mode == ProductionMode.BATCH
    assert recipe.meta["made_to_order"] is True


def test_banco_vazio_nao_falha():
    assert migration.forward(apps, None)["activated"] == []
    migration.backward(apps, None)


def test_lanches_passa_a_receber_doces_uma_vez_so(capsys):
    from shopman.offerman.models import Collection

    from shopman.backstage.models import KDSInstance

    lanches = KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep")
    doces = Collection.objects.create(ref="doces", name="Doces")

    migration.forward(apps, None)
    migration.forward(apps, None)

    assert list(lanches.collections.all()) == [doces]
    out = capsys.readouterr().out
    assert "Lanches passou a receber Doces" in out
    assert "Lanches já tinha Doces" in out
