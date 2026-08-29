"""A pesagem tem de contar a MESMA história que o planejamento congelou.

⚠️ Peso errado de insumo na balança, em silêncio, é o hazard que o plano de domínio
nomeia: os **itens** vinham do snapshot da ficha (congelado no planejamento) e o
**coeficiente** saía do `batch_size` da receita VIVA. Editar o rendimento entre o
planejamento e a pesagem — a mesma manhã basta — dá quantidades congeladas sobre um
rendimento novo. Um `batch_size` de 10 para 20 corta todos os pesos pela metade, e a
etiqueta cega não dá pista nenhuma: o padeiro pesa 300 g onde a ficha manda 600 g.

Que era lapso e não decisão, os outros dois consumidores provam: `services/production`
e `craftsman/execution` já liam `snapshot["batch_size"]`. A pesagem era a única que
misturava.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem

from shopman.backstage.projections.production import (
    build_production_mise_en_place,
    build_production_weighing,
)

pytestmark = pytest.mark.django_db


def _planejar_e_editar_o_rendimento(*, de: str, para: str):
    """Planeja com um rendimento e o edita depois — o cenário exato do defeito."""
    receita = Recipe.objects.create(
        ref="brioche-cong", name="Brioche", output_sku="BRIOCHE-CONG",
        batch_size=Decimal(de),
    )
    RecipeItem.objects.create(recipe=receita, input_sku="FARINHA", quantity="6", unit="kg")
    craft.plan(receita, Decimal(de), date=date.today())

    # A edição da manhã. O snapshot no work order NÃO muda — é esse o ponto dele.
    receita.batch_size = Decimal(para)
    receita.save(update_fields=["batch_size"])
    return receita


def test_editar_o_rendimento_depois_do_plano_nao_mexe_na_balanca():
    """10 → 20 cortava todos os pesos pela metade, sem nada na etiqueta avisar."""
    _planejar_e_editar_o_rendimento(de="10", para="20")

    pesagem = build_production_weighing(selected_date=date.today())
    ticket = next(t for t in pesagem.tickets if t.recipe_ref == "brioche-cong")
    farinha = next(i for i in ticket.ingredients if i.sku == "FARINHA")

    # Planejado 10 sobre rendimento 10 = coeficiente 1 → os 6 kg da ficha, inteiros.
    # Com o rendimento vivo (20) o coeficiente virava 0,5 e saíam 3 kg.
    assert "6" in farinha.quantity_display, farinha.quantity_display
    assert "3 kg" not in farinha.quantity_display


def test_a_mise_en_place_conta_a_mesma_historia_da_pesagem():
    """Duas telas do mesmo dia não podem discordar sobre quanto pesar.

    A mise en place tinha a mesma origem de erro por outro caminho: itens VIVOS com
    rendimento VIVO — internamente coerente, e ainda assim divergente da pesagem, que
    lia o congelado.
    """
    _planejar_e_editar_o_rendimento(de="10", para="20")

    mise = build_production_mise_en_place(selected_date=date.today(), expand=False)
    linhas = [
        linha
        for grupo in mise.lines
        for linha in (grupo.breakdown or ())
        if grupo.sku == "FARINHA"
    ]
    assert linhas, "a farinha deveria aparecer no detalhamento"
    assert all("3 kg" not in linha.quantity_display for linha in linhas), [
        linha.quantity_display for linha in linhas
    ]


def test_ficha_sem_snapshot_continua_usando_o_rendimento_vivo():
    """Assert-positivo: work order antigo, sem snapshot, não pode quebrar.

    Antes de o planejamento congelar a ficha, o rendimento vivo era a única fonte. Ele
    segue sendo o fallback — melhor que dividir por zero.
    """
    receita = Recipe.objects.create(
        ref="sem-snap", name="Sem Snapshot", output_sku="SEM-SNAP", batch_size=Decimal("4")
    )
    RecipeItem.objects.create(recipe=receita, input_sku="FARINHA", quantity="2", unit="kg")
    ordem = craft.plan(receita, Decimal("4"), date=date.today())
    ordem.meta = {}
    ordem.save(update_fields=["meta"])

    pesagem = build_production_weighing(selected_date=date.today())
    ticket = next(t for t in pesagem.tickets if t.recipe_ref == "sem-snap")
    assert next(i for i in ticket.ingredients if i.sku == "FARINHA")
