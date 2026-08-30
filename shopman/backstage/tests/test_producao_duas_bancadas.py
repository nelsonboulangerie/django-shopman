"""Duas bancadas na mesma fornada é o dia normal da padaria.

⚠️ O core tem concorrência otimista — `WorkOrder.rev` e o compare-and-swap atômico de
`_check_rev` — e `adjust`, `start`, `finish` e `void` todos aceitam `expected_rev`.
Nenhum caller do backstage passava: o parâmetro nem estava nas assinaturas das duas
camadas de serviço. Resultado: a bancada A ajusta o planejado para 40 enquanto a B
ajusta para 25 sobre um quadro de sessenta segundos de idade. **O último POST vence,
sem 409 e sem aviso** — e ninguém fica sabendo que o outro número existiu.

A tradução para 409 já existia (`STALE_REVISION` → `ProductionConflict`). O que faltava
era o número atravessar a borda, e o card publicar a revisão que ele leu.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman.models import Position

from shopman.backstage.services import production
from shopman.backstage.services.exceptions import ProductionConflict
from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db


@pytest.fixture
def forneiro(db):
    """Superfície MAIS colunas — ver `production_grants`."""
    user = User.objects.create_user("forneiro-rev", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def fornada(db):
    """A fornada nasce pelo MESMO caminho da tela.

    ⚠️ Criar por `craft.plan` direto produz um `position_ref` que a matriz não
    reconhece — ela filtra pela posição padrão —, e aí o "ajuste" da segunda chamada
    criaria uma fornada nova em vez de disputar a primeira. O teste mediria outra coisa.
    """
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Rev")
    Position.objects.get_or_create(ref="forno", defaults={"name": "Forno", "is_default": True})
    receita = Recipe.objects.create(
        ref="pao-rev", name="Pão Rev", output_sku="PAO-REV", batch_size=Decimal("10")
    )
    production.apply_planned(
        recipe_id=receita.pk,
        quantity="10",
        target_date_value=date.today().isoformat(),
        actor="setup",
    )
    return receita, WorkOrder.objects.get(recipe=receita, status=WorkOrder.Status.PLANNED)


def test_a_segunda_bancada_e_recusada_em_vez_de_vencer(forneiro, fornada):
    """O caso concreto: A ajusta para 40, B ajusta para 25 sobre o quadro velho."""
    receita, ordem = fornada
    rev_que_as_duas_leram = ordem.rev

    production.apply_planned(
        recipe_id=receita.pk,
        quantity="40",
        target_date_value=date.today().isoformat(),
        actor="bancada-a",
        expected_rev=rev_que_as_duas_leram,
    )

    with pytest.raises(ProductionConflict):
        production.apply_planned(
            recipe_id=receita.pk,
            quantity="25",
            target_date_value=date.today().isoformat(),
            actor="bancada-b",
            expected_rev=rev_que_as_duas_leram,
        )

    ordem.refresh_from_db()
    assert ordem.quantity == Decimal("40"), "o primeiro número tem de sobreviver"


def test_sem_rev_o_contrato_antigo_continua_valendo(forneiro, fornada):
    """Assert-positivo: `expected_rev=None` mantém o last-write-wins.

    É o contrato documentado do craftsman para uso standalone, e tornar obrigatório
    quebraria todo chamador que não tem quadro para ler.
    """
    receita, ordem = fornada

    production.apply_planned(
        recipe_id=receita.pk,
        quantity="40",
        target_date_value=date.today().isoformat(),
        actor="bancada-a",
    )
    production.apply_planned(
        recipe_id=receita.pk,
        quantity="25",
        target_date_value=date.today().isoformat(),
        actor="bancada-b",
    )

    ordem.refresh_from_db()
    assert ordem.quantity == Decimal("25")


def test_o_card_publica_a_revisao_que_ele_leu(forneiro, fornada):
    """Sem `rev` no card, o cliente não tem o que devolver — o parâmetro seria inerte."""
    from shopman.backstage.projections.production import build_production_board

    board = build_production_board(selected_date=date.today())
    cards = [c for coluna in (board.planned_queue, board.started_queue) for c in coluna]
    assert cards, "a fornada do dia deveria aparecer no quadro"
    assert all(isinstance(c.rev, int) for c in cards)


def test_rev_ilegivel_nao_derruba_o_gesto_do_forneiro(forneiro, fornada):
    """⚠️ `None` não é zero, e ilegível não é 400.

    Zero é revisão legítima (fornada recém-criada): confundir os dois faria toda
    mutação sem `rev` recusar exatamente as fornadas novas. E derrubar o gesto do
    forneiro por um campo que a tela dele talvez nem mande trocaria uma corrida rara
    por uma parede diária.
    """
    from shopman.backstage.api.operations import _expected_rev

    class _Req:
        def __init__(self, data):
            self.data = data

    assert _expected_rev(_Req({})) is None
    assert _expected_rev(_Req({"expected_rev": "abacaxi"})) is None
    assert _expected_rev(_Req({"expected_rev": True})) is None
    assert _expected_rev(_Req({"expected_rev": 0})) == 0
    assert _expected_rev(_Req({"expected_rev": "3"})) == 3


def test_o_estorno_tambem_confere(forneiro, fornada):
    """Estornar a fornada que o colega acabou de fechar é a mesma corrida."""
    _receita, ordem = fornada
    rev_velha = ordem.rev
    WorkOrder.objects.filter(pk=ordem.pk).update(rev=rev_velha + 5)

    with pytest.raises(ProductionConflict):
        production.apply_void(ordem.pk, actor="bancada-b", expected_rev=rev_velha)
