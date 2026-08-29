"""O guardrail que nunca disparava no caminho real da tela.

Dá para reduzir o planejado abaixo do que já foi VENDIDO, em silêncio. É encomenda de
cliente que não vai existir.

⚠️ **A cobertura real deste guardrail era zero.** O único teste do assunto faz
`monkeypatch` do `apply_planned` inteiro e passa `position_ref` explícito — ele testa o
envelope de erro, nunca a lógica. Estes testes chamam o caminho de verdade, com o
`position_ref` que o board realmente manda: **nenhum**.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services import production as production_service
from shopman.backstage.services.production import ProductionOrderShortError

SKU = "PAO-FRANCES"


@pytest.fixture
def cenario(db):
    """Uma fornada planejada com encomenda amarrada, criada pelo ESCRITOR REAL.

    A fornada nasce de `apply_planned` com `position_ref=""` — exatamente como a tela
    faz — para que ela caia onde o escritor a coloca. Montá-la à mão poria a fornada
    onde o TESTE acha que ela vai, e era essa suposição que escondia o bug.
    """
    from django.utils import timezone

    Position.objects.filter(is_default=True).update(is_default=False)
    Position.objects.create(
        ref="massa", name="Massa", kind=PositionKind.PHYSICAL, is_saleable=False, is_default=True
    )
    receita = Recipe.objects.create(
        ref="pao-frances-v1", name="Pão francês", output_sku=SKU, batch_size=Decimal("100")
    )
    pedido = Order.objects.create(ref="ENC-1", channel_ref="web", total_q=5000)
    OrderItem.objects.create(
        order=pedido, line_id="1", sku=SKU, name="Pão", qty=Decimal("30"),
        unit_price_q=100, line_total_q=3000,
    )

    production_service.apply_planned(
        recipe_id=receita.pk, quantity=Decimal("50"), target_date_value=None,
        position_ref="", operator_ref="", force=False, actor="op",
    )
    fornada = WorkOrder.objects.filter(
        recipe=receita, target_date=timezone.localdate(), status=WorkOrder.Status.PLANNED
    ).first()
    assert fornada is not None, "o escritor não criou a fornada — o cenário não vale"
    fornada.meta = {**(fornada.meta or {}), "committed_order_refs": [pedido.ref]}
    fornada.save(update_fields=["meta"])
    return receita, fornada, pedido


@pytest.mark.django_db
def test_reduzir_abaixo_do_encomendado_e_recusado_SEM_filtro_de_posicao(cenario):
    """O caminho real da tela: `position_ref` vazio, que é o estado PADRÃO do board.

    O guardrail procurava `position_ref=""`; o escritor procurava a posição padrão
    (`"massa"` no seed vivo). Não se encontravam, o guardrail retornava cedo, e o
    planejado caía abaixo da encomenda sem checagem nenhuma.
    """
    receita, _fornada, _pedido = cenario

    with pytest.raises(ProductionOrderShortError):
        production_service.apply_planned(
            recipe_id=receita.pk,
            quantity=Decimal("10"),   # abaixo dos 30 encomendados
            target_date_value=None,
            position_ref="",          # ⬅ o que o board manda quando não há filtro
            operator_ref="",
            force=False,
            actor="op",
        )


@pytest.mark.django_db
def test_manter_acima_do_encomendado_passa(cenario):
    """Assert-positivo: o guardrail não pode virar uma porta fechada."""
    receita, fornada, _pedido = cenario

    production_service.apply_planned(
        recipe_id=receita.pk,
        quantity=Decimal("40"),   # acima dos 30 encomendados
        target_date_value=None,
        position_ref="",
        operator_ref="",
        force=False,
        actor="op",
    )

    fornada.refresh_from_db()
    assert fornada.planned_qty == Decimal("40")


@pytest.mark.django_db
def test_force_continua_passando_por_cima(cenario):
    """`force` é a saída deliberada — e continua sendo, com o guardrail funcionando."""
    receita, fornada, _pedido = cenario

    production_service.apply_planned(
        recipe_id=receita.pk,
        quantity=Decimal("10"),
        target_date_value=None,
        position_ref="",
        operator_ref="",
        force=True,
        actor="op",
    )

    fornada.refresh_from_db()
    assert fornada.planned_qty == Decimal("10")


@pytest.mark.django_db
def test_data_malformada_nao_cega_o_guardrail(cenario):
    """O escritor cai silenciosamente para HOJE em qualquer string não-ISO.

    O guardrail usava a string crua, então data malformada = guardrail cego E
    planejamento no dia errado. Agora os dois normalizam igual.
    """
    receita, _fornada, _pedido = cenario

    with pytest.raises(ProductionOrderShortError):
        production_service.apply_planned(
            recipe_id=receita.pk,
            quantity=Decimal("10"),
            target_date_value="amanhã",   # não-ISO: o escritor cai para hoje
            position_ref="",
            operator_ref="",
            force=False,
            actor="op",
        )
