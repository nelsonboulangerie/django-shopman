"""O porquê fica com o lote (WP-F17, P1-05).

Todo plano, manual ou como sugerido, grava a sugestão vigente e a conta dela em
``meta.formula_basis``, e o evento do plano a leva (``payload.attempt.planning_meta``):
o meta guarda o último porquê; os eventos, um por plano, são o histórico (append).
O B.I. aprende onde a casa discorda da conta só se a conta estiver gravada.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
from shopman.stockman.models import Position

from shopman.backstage.services import production
from shopman.shop.services import production as production_core

pytestmark = pytest.mark.django_db

AMANHA = (date.today() + timedelta(days=1)).isoformat()


@pytest.fixture
def receita(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Porquê")
    Position.objects.get_or_create(ref="forno", defaults={"name": "Forno", "is_default": True})
    return Recipe.objects.create(ref="croissant-porque", name="Croissant", output_sku="CRO-PQ", batch_size=Decimal("10"))


@pytest.fixture
def sugestao(monkeypatch, receita):
    """A sugestão de amanhã: 42 = 30 de média + 6 encomendas + 6 de margem.

    O ``basis`` vem como a fórmula o entrega: ``Decimal`` e ``date`` crus.
    """
    state = {"quantity": Decimal("42")}

    def suggest_for(target_date, output_skus=None):
        return [
            SimpleNamespace(
                recipe=receita,
                quantity=state["quantity"],
                basis={
                    "avg_demand": Decimal("29.6"),
                    "committed": Decimal("6"),
                    "confidence": "medium",
                    "sample_size": 4,
                    "date": target_date,
                },
            )
        ]

    monkeypatch.setattr(production_core, "suggest_for", suggest_for)
    return state


def _planned(receita) -> WorkOrder:
    return WorkOrder.objects.get(recipe=receita, status=WorkOrder.Status.PLANNED)


def _plan(receita, quantity, key, *, source_ref="production_matrix", expected_rev=None):
    return production.apply_planned(
        recipe_id=receita.pk,
        quantity=quantity,
        target_date_value=AMANHA,
        actor="production:cozinha",
        source_ref=source_ref,
        expected_rev=expected_rev,
        idempotency_key=key,
    )


def test_plano_manual_grava_a_sugestao_vigente_e_a_conta(receita, sugestao):
    _plan(receita, "36", "porque-manual")

    lote = _planned(receita)
    basis = lote.meta["formula_basis"]
    assert basis == {
        "date": AMANHA,
        "output_sku": "CRO-PQ",
        "recipe_ref": "croissant-porque",
        "planned_quantity": "36",
        "source": "manual",
        "suggested_quantity": "42",
        "projected": "30",
        "committed": "6",
        "margin": "6",
        "confidence": "medium",
        "sample_size": 4,
        "as_suggested": False,
    }
    evento = WorkOrderEvent.objects.get(work_order=lote, kind=WorkOrderEvent.Kind.PLANNED)
    assert evento.payload["attempt"]["planning_meta"]["formula_basis"] == basis


def test_como_sugerido_grava_a_origem_e_nada_cru(receita, sugestao):
    """O caminho ``suggested`` levava o ``basis`` cru (``Decimal``, ``date``) ao meta."""
    _plan(receita, "42", "porque-sugerido", source_ref="formula:suggestion")

    lote = _planned(receita)
    basis = lote.meta["formula_basis"]
    assert basis["source"] == "suggested"
    assert basis["as_suggested"] is True
    assert basis["suggested_quantity"] == basis["planned_quantity"] == "42"
    # Texto JSON de ponta a ponta: relido do banco, o meta volta igual.
    assert json.loads(json.dumps(lote.meta)) == lote.meta


def test_corrigir_um_produto_guarda_os_dois_planos(receita, sugestao):
    """A véspera (J-P2): como sugerido, depois corrigido. O meta diz o último; os eventos, os dois."""
    from shopman.backstage.projections.production import _build_wo_card

    _plan(receita, "42", "porque-j-p2-sugerido", source_ref="formula:suggestion")
    lote = _planned(receita)
    _plan(receita, "36", "porque-j-p2-corrigido", expected_rev=lote.rev)

    lote.refresh_from_db()
    assert lote.quantity == Decimal("36")
    assert lote.meta["formula_basis"]["planned_quantity"] == "36"
    assert lote.meta["formula_basis"]["source"] == "manual"
    gravados = [
        evento.payload["attempt"]["planning_meta"]["formula_basis"]
        for evento in WorkOrderEvent.objects.filter(work_order=lote).order_by("seq")
        if "attempt" in evento.payload
    ]
    assert [(b["suggested_quantity"], b["planned_quantity"], b["source"]) for b in gravados] == [
        ("42", "42", "suggested"),
        ("42", "36", "manual"),
    ]

    card = _build_wo_card(lote)
    assert (card.suggested_qty, card.planned_qty) == ("42", "36")


def test_repetir_a_tentativa_rele_o_porque_que_ela_gravou(receita, sugestao):
    """A sugestão mudou entre o envio e a repetição (resposta perdida): a mesma chave
    devolve o mesmo resultado, em vez de conflito por um porquê recalculado."""
    first = _plan(receita, "36", "porque-repeticao")
    sugestao["quantity"] = Decimal("50")

    assert _plan(receita, "36", "porque-repeticao") == first
    assert _planned(receita).meta["formula_basis"]["suggested_quantity"] == "42"


def test_sem_sugestao_grava_o_planejado_e_o_card_fica_vazio(receita, monkeypatch):
    from shopman.backstage.projections.production import _build_wo_card

    monkeypatch.setattr(production_core, "suggest_for", lambda target_date, output_skus=None: [])
    _plan(receita, "12", "porque-sem-sugestao")

    lote = _planned(receita)
    assert lote.meta["formula_basis"]["suggested_quantity"] == ""
    assert lote.meta["formula_basis"]["planned_quantity"] == "12"
    assert _build_wo_card(lote).suggested_qty == ""
