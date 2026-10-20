"""O modo de produção das fichas do seed, e o que ele decide na cozinha (ADR-040).

Irmã de ``test_massa_de_cada_peca.py``. Toda ficha do seed é a VIGENTE do SKU
(``is_active`` é só vigente × arquivada). O modo de produção diz o resto: "Na
hora" (montagem e bebida) nunca é planejado, vai à estação de preparo e a venda
baixa os insumos; "Em lote" é planejado, sai por ordem de produção e, na venda,
é separação. As derivas são silenciosas (café que não baixa grão, croque que
entra no plano, pão pronto que toca o KDS no balcão), por isso a lista é fechada
aqui, pelo ref da ficha, e o roteamento é provado com o seed inteiro.

⚠️ Roda o seed inteiro de propósito: ler a tabela do seed provaria que a tabela
concorda consigo mesma.
"""

from __future__ import annotations

import importlib

import pytest
from django.core.management import call_command
from shopman.craftsman.models import ProductionMode, Recipe

pytestmark = pytest.mark.django_db

#: FONTE ÚNICA: a lista mora na migração que leva o modo ao banco já semeado
#: (``shop.0104``); o seed que montar outra coisa na venda reprova aqui.
NA_HORA = set(importlib.import_module("shopman.shop.migrations.0104_fichas_na_hora_vigentes").MADE_TO_ORDER_RECIPE_REFS)


def _fire(session_key: str, skus: list[str], *, prep_only: bool) -> dict[str, list[str]]:
    from shopman.shop.adapters import get_adapter
    from shopman.shop.adapters import kds as kds_adapter
    from shopman.shop.services.kds import _fire_lines_locked

    lines = [
        {"line_id": f"L{index}", "sku": sku, "name": sku, "qty": 1, "notes": "", "meta": {}}
        for index, sku in enumerate(skus)
    ]
    tickets = _fire_lines_locked(
        session_key=session_key, lines=lines, get_adapter=get_adapter, kds_adapter=kds_adapter, prep_only=prep_only,
    )
    return {str(ticket.kds_instance.name): sorted(item["sku"] for item in ticket.items) for ticket in tickets}


def test_modo_de_producao_do_seed_e_o_roteamento_da_cozinha(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Feita-Na-Hora-2026!")
    call_command("seed", verbosity=0)

    # 1. Toda ficha do seed é vigente; nada fica desligado para sair do plano.
    arquivadas = sorted(Recipe.objects.filter(is_active=False).values_list("ref", flat=True))
    assert not arquivadas, f"ficha arquivada no seed (o modo de produção é que tira do plano): {arquivadas}"

    # 2. "Na hora" é exatamente a montagem e a bebida.
    na_hora = set(Recipe.objects.filter(production_mode=ProductionMode.MADE_TO_ORDER).values_list("ref", flat=True))
    assert na_hora == NA_HORA

    # 3. Nenhuma marca antiga sobrou.
    assert not [r.ref for r in Recipe.objects.all() if {"made_to_order", "made_to_order_marked_by"} & set(r.meta or {})]

    # 4. Todo SKU "Na hora" tem estação de preparo: senão a cozinha nunca o vê.
    from shopman.backstage.models import KDSInstance
    from shopman.shop.services.kds import kitchen_routes_for_skus

    skus = sorted(Recipe.objects.filter(production_mode=ProductionMode.MADE_TO_ORDER).values_list("output_sku", flat=True))
    routes = kitchen_routes_for_skus(skus)
    prep_stations = set(KDSInstance.objects.filter(type="prep", is_active=True).values_list("name", flat=True))
    sem_preparo = sorted(sku for sku in skus if (routes.get(sku) or {}).get("station") not in prep_stations)
    assert not sem_preparo, f"feito na hora sem estação de preparo: {sem_preparo}"

    # 5. O defeito medido em 20/10/2026, fechado: no balcão presencial o café e
    #    o croque viravam NADA e o pão pronto virava ticket em Encomendas.
    balcao = _fire("SEED-BALCAO", ["SP", "CQMO", "BAT", "HOD", "AGUA-MINERAL-PRATA-310", "SDLA"], prep_only=True)
    assert balcao == {"Cafés": ["SP"], "Lanches": ["CQMO"]}

    # 6. No pedido remoto, o que se separa vai à Separação (Encomendas), sempre
    #    do mesmo tipo: em lote e revenda nunca caem em estação de preparo.
    remoto = _fire("SEED-REMOTO", ["SP", "CQMO", "BAT", "HOD", "AGUA-MINERAL-PRATA-310"], prep_only=False)
    assert remoto == {
        "Cafés": ["SP"],
        "Lanches": ["CQMO"],
        "Encomendas": ["AGUA-MINERAL-PRATA-310", "BAT", "HOD"],
    }
