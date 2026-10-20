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

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe

pytestmark = pytest.mark.django_db

#: Montagem (croques, sanduíches, pain perdu) e bebida: o que se faz quando o
#: cliente pede. A seção 2b do seed.
FEITAS_NA_HORA = {
    "queijo-quente", "croque-monsieur", "croque-madame", "croque-complet",
    "jambon-beurre", "pain-perdu",
    "espresso", "espresso-macchiato", "cappuccino", "mochaccino", "mocha",
    "caffe-latte", "chocolate-quente",
    "cha-camille", "cha-rouge", "cha-sophie", "cha-bleu", "cha-hibisco",
    "soft-chai-citrico", "vienna-gelado", "cha-tonica-frutas-vermelhas",
}


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
