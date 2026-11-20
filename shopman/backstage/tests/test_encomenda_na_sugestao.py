"""A encomenda e o plano da Produção, sem hora de corte (#2755).

O dono, 19/11/2026: "precisamos disso? a diferença é se vai compor a sugestão no
planejamento OU consumir/compromissar o já planejado. fora isso, não vejo motivo
concreto para cortar arbitrariamente." Esta suíte prova as duas metades com a
fiação real (a encomenda nasce do ``close_sale`` do PDV, o lote do Craftsman):

- encomenda para uma data SEM lote compõe a sugestão de produção dessa data
  (``production.suggest_for``, a mesma da tela da Produção e do
  ``suggest_production``), inclusive para o produto que ainda não tem histórico
  de vendas;
- encomenda para uma data COM lote planejado se ancora no lote e o compromete: a
  reserva fica no saldo planejado, e o plano não desce abaixo do prometido.
"""

# ruff: noqa: F811 (os testes recebem as fixtures importadas acima)

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.protocols.demand import DailyDemand
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product

from shopman.backstage.tests.test_iniciar_lote_leva_a_reserva import (
    DAY,
    SKU,
    _encomenda_do_pdv,
    _hoje,
    _onde,
    _planejar,
    _reserva,
)
from shopman.backstage.tests.test_iniciar_lote_leva_a_reserva import (  # noqa: F401 (a casa e o balcão da #2709)
    balcao as balcao,
)
from shopman.backstage.tests.test_iniciar_lote_leva_a_reserva import (
    ficha as ficha,
)
from shopman.shop.adapters.demand import LedgerAwareDemandBackend
from shopman.shop.services.production import suggest_for

pytestmark = pytest.mark.django_db


def _rastreado(ficha) -> None:
    """O produto já passou pelo estoque (um lote de hoje), como todo produto da loja.

    Sem nenhum saldo na vida, o SKU é "não rastreado" e a encomenda nem reserva:
    é o produto de teste nascido do nada, não a loja.
    """
    _planejar(ficha, 10, _hoje())


def _basis(sugestao, key: str) -> Decimal:
    return Decimal(str(sugestao.basis[key]))


def _sugestao(day: date):
    return next((item for item in suggest_for(day, output_skus=[SKU]) if item.recipe.output_sku == SKU), None)


def test_encomenda_sem_lote_compoe_a_sugestao_da_data(ficha, balcao, monkeypatch, django_capture_on_commit_callbacks):
    """Com histórico, o prometido entra na sugestão por cima da média."""
    day = _hoje() + 3 * DAY
    # O histórico não é a pergunta: um dia de 10 vendidos, sem sobra.
    monkeypatch.setattr(
        LedgerAwareDemandBackend, "history",
        lambda self, *args, **kwargs: [DailyDemand(date=day - 7 * DAY, sold=Decimal("10"), wasted=Decimal("0"))],
    )
    _rastreado(ficha)
    sem_encomenda = _sugestao(day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _encomenda_do_pdv(balcao, 4, day=day)

    # A encomenda reservou sem lote nenhum: a demanda da data, sem saldo por trás.
    assert _onde(order) == "sem_saldo"
    assert _reserva(order).target_date == day
    com_encomenda = _sugestao(day)
    assert _basis(sem_encomenda, "committed") == Decimal("0")
    assert _basis(com_encomenda, "committed") == Decimal("4")
    assert com_encomenda.quantity > sem_encomenda.quantity


def test_encomenda_de_produto_sem_historico_tambem_compoe_a_sugestao(ficha, balcao, django_capture_on_commit_callbacks):
    """Produto novo, sem venda nenhuma: a sugestão existe pelo prometido."""
    day = _hoje() + 3 * DAY
    _rastreado(ficha)
    assert _sugestao(day) is None  # sem histórico e sem encomenda, nada a sugerir

    with django_capture_on_commit_callbacks(execute=True):
        _encomenda_do_pdv(balcao, 4, day=day)

    sugestao = _sugestao(day)
    assert sugestao is not None
    assert _basis(sugestao, "committed") == Decimal("4")
    assert (sugestao.basis["sample_size"], sugestao.basis["confidence"]) == (0, "")
    assert _basis(sugestao, "avg_demand") == Decimal("0")
    # O prometido mais a margem da casa, nunca menos que o prometido.
    assert sugestao.quantity >= Decimal("4")


def test_encomenda_para_data_planejada_compromete_o_lote(ficha, balcao, django_capture_on_commit_callbacks):
    day = _hoje() + 3 * DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _encomenda_do_pdv(balcao, 4, day=day)

    # A reserva se ancora no saldo planejado do lote da data.
    assert _onde(order) == "planejado"
    assert _reserva(order).quant.target_date == day
    # E o plano não desce abaixo do que já foi prometido.
    lote.refresh_from_db()
    with pytest.raises(CraftError):
        craft.adjust(lote, quantity=Decimal("3"), expected_rev=lote.rev)
    lote.refresh_from_db()
    craft.adjust(lote, quantity=Decimal("4"), expected_rev=lote.rev)


def test_produto_fora_da_ficha_nao_ganha_sugestao(ficha, balcao, django_capture_on_commit_callbacks):
    """O feito na hora nunca é planejado, com ou sem encomenda."""
    from shopman.craftsman.models import ProductionMode

    ficha.production_mode = ProductionMode.MADE_TO_ORDER
    ficha.save(update_fields=["production_mode"])
    Product.objects.filter(sku=SKU).update(availability_policy="demand_ok")
    day = _hoje() + 3 * DAY
    with django_capture_on_commit_callbacks(execute=True):
        _encomenda_do_pdv(balcao, 4, day=day)
    assert _sugestao(day) is None
