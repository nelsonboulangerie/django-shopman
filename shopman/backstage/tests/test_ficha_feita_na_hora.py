"""Quais fichas baixam insumo na VENDA: a marca explícita, travada (ADR-040).

Irmã de ``test_massa_de_cada_peca.py``. A venda do item feito na hora baixa o
insumo da ficha marcada ``Recipe.meta["made_to_order"] = true``. Ficha inativa
sem a marca é ficha DESLIGADA e não baixa nada; ficha marcada e ativa entraria
no plano de forno (``craft.suggest`` olha toda ficha ativa). As duas derivas são
silenciosas: a primeira deixa o café em grão sem descer, a segunda põe croque
na fornada. Por isso a lista é fechada aqui, pelo ref da ficha.

⚠️ Roda o seed inteiro de propósito: ler a tabela do seed provaria que a tabela
concorda consigo mesma.
"""

from __future__ import annotations

import importlib

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe

pytestmark = pytest.mark.django_db

#: Montagem (croques, sanduíches, pain perdu) e bebida: o que se faz quando o
#: cliente pede. A seção 2b do seed. FONTE ÚNICA: a lista mora na migração que
#: marca o banco já semeado (``shop.0102``); o seed que marcar outra coisa reprova
#: aqui, e a migração nunca anda descolada do seed.
FEITAS_NA_HORA = set(
    importlib.import_module("shopman.shop.migrations.0102_fichas_feitas_na_hora").MADE_TO_ORDER_RECIPE_REFS
)


def test_so_as_fichas_de_montagem_e_bebida_baixam_na_venda(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Feita-Na-Hora-2026!")
    call_command("seed", verbosity=0)

    marcadas = {
        recipe.ref: recipe
        for recipe in Recipe.objects.all()
        if (recipe.meta or {}).get("made_to_order") is True
    }
    assert set(marcadas) == FEITAS_NA_HORA

    ativas = sorted(ref for ref, recipe in marcadas.items() if recipe.is_active)
    assert not ativas, f"ficha feita na hora entraria no plano de forno: {ativas}"

    desligadas = sorted(
        recipe.ref for recipe in Recipe.objects.filter(is_active=False) if recipe.ref not in marcadas
    )
    assert not desligadas, f"ficha inativa sem a marca (desligada ou esquecida?): {desligadas}"

    # Um nível só e uma ficha por produto: a baixa não escolhe entre duas.
    por_produto: dict[str, list[str]] = {}
    for ref, recipe in marcadas.items():
        por_produto.setdefault(recipe.output_sku, []).append(ref)
    duplicadas = {sku: refs for sku, refs in por_produto.items() if len(refs) > 1}
    assert not duplicadas, duplicadas

    # O banco semeado ANTES do ADR-040 (o alpha) não tem a marca: a migração
    # ``shop.0102`` a escreve nas mesmas 21 fichas, todas presentes e inativas.
    from django.apps import apps

    migration = importlib.import_module("shopman.shop.migrations.0102_fichas_feitas_na_hora")
    for recipe in marcadas.values():
        recipe.meta = {k: v for k, v in recipe.meta.items() if k != "made_to_order"}
        recipe.save(update_fields=["meta"])
    assert sorted(migration.mark(apps, None)) == sorted(FEITAS_NA_HORA)
