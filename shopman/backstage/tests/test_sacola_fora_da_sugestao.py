"""A sacola não é compromisso: ela não compõe a sugestão de produção (#3265).

A reserva da sacola numa fornada futura não tem prazo (o relógio só começa quando
o lote sai), e a sessão abandonada só é varrida em 48 h. Somada ao prometido, ela
fazia a Produção assar para ninguém e impedia o plano de descer até o que a casa
prometeu de verdade. O prometido da data é só o que é compromisso: o pedido (a
encomenda e a fila da fornada), a reserva manual do operador. A sacola entra
quando vira pedido.

Fiação real: a sacola reserva pelo ``availability.reserve`` da loja, o pedido pelo
``CommitService``, a sugestão pelo ``production.suggest_for`` da tela.
"""

# ruff: noqa: F811 (os testes recebem as fixtures importadas acima)

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.protocols.demand import DailyDemand
from shopman.stockman.models import Hold

from shopman.backstage.tests.test_iniciar_lote_leva_a_reserva import (
    DAY,
    SKU,
    _hoje,
    _pedido_da_loja,
    _planejar,
)
from shopman.backstage.tests.test_iniciar_lote_leva_a_reserva import (
    ficha as ficha,
)
from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.adapters.demand import LedgerAwareDemandBackend
from shopman.shop.services import availability
from shopman.shop.services.production import suggest_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def historico(monkeypatch):
    """Um dia de 10 vendidos: a sugestão existe, e a pergunta é só o prometido."""
    monkeypatch.setattr(
        LedgerAwareDemandBackend, "history",
        lambda self, *args, **kwargs: [DailyDemand(date=_hoje() - 7 * DAY, sold=Decimal("10"), wasted=Decimal("0"))],
    )


def _prometido(day) -> Decimal:
    [sugestao] = [item for item in suggest_for(day, output_skus=[SKU]) if item.recipe.output_sku == SKU]
    return Decimal(str(sugestao.basis["committed"]))


def _sacola(qty, day, *, key: str = "1") -> Hold:
    """A cliente põe o pão de amanhã na sacola da loja e vai embora."""
    result = availability.reserve(SKU, Decimal(str(qty)), session_key=f"S-WEB-{key}", channel_ref="web", target_date=day)
    assert result["ok"], result
    [hold_id] = result["hold_ids"]
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def test_sacola_abandonada_na_fornada_futura_nao_entra_no_prometido(ficha, historico):
    day = _hoje() + DAY
    _planejar(ficha, 10, day)
    sacola = _sacola(4, day)

    # O ponto de partida da #3265: a reserva da sacola na fornada futura não vence.
    assert sacola.expires_at is None
    assert sacola.metadata.get("planned") is True
    assert stock_adapter.is_held_by_a_cart(sacola)

    assert _prometido(day) == Decimal("0")


def test_a_sacola_vira_prometido_quando_vira_pedido(ficha, historico, django_capture_on_commit_callbacks):
    day = _hoje() + DAY
    _planejar(ficha, 10, day)
    _sacola(4, day, key="1")
    assert _prometido(day) == Decimal("0")

    # O checkout da mesma sessão adota a reserva da sacola: agora é pedido.
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(4, day=day, key="1")
    [entry] = order.data["hold_ids"]
    adotada = Hold.objects.get(pk=int(entry["hold_id"].split(":")[1]))
    assert adotada.metadata["reference"] == f"order:{order.ref}"

    assert _prometido(day) == Decimal("4")


def test_pedido_e_sacola_na_mesma_data_so_o_pedido_conta(ficha, historico, django_capture_on_commit_callbacks):
    day = _hoje() + DAY
    _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        _pedido_da_loja(3, day=day, key="pedido")
    _sacola(2, day, key="abandonada")

    assert _prometido(day) == Decimal("3")


def test_reserva_manual_do_operador_continua_prometido(ficha, historico):
    """Sem referência é decisão de gente, não sacola: segue contando."""
    day = _hoje() + DAY
    _planejar(ficha, 10, day)
    result = stock_adapter.create_hold(sku=SKU, qty=Decimal("2"), target_date=day)
    assert result["success"], result

    assert _prometido(day) == Decimal("2")


def test_a_sacola_nao_segura_o_plano(ficha):
    """O plano desce abaixo da sacola abandonada; só o pedido segura o plano."""
    from shopman.stockman.models import Quant

    from shopman.backstage.services import production

    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    sacola = _sacola(4, day)

    production.apply_planned(
        recipe_id=ficha.pk, quantity="3", target_date_value=day.isoformat(),
        actor="production:forneiro", expected_rev=lote.rev, idempotency_key="sacola-nao-segura",
    )
    lote.refresh_from_db()
    sacola.refresh_from_db()
    quant = Quant.objects.get(sku=SKU, target_date=day)
    assert (lote.quantity, quant.quantity) == (Decimal("3"), Decimal("3"))
    # A sacola não fica com mais do que o lote vai render: solta o que perdeu lastro.
    assert sacola.status == "released"


def test_plano_que_encolhe_solta_so_o_excesso_e_nunca_o_pedido(ficha, django_capture_on_commit_callbacks):
    """Pedido de 3 e sacola de 4 num lote de 10: o plano desce para 5, sai a sacola."""
    from shopman.backstage.services import production

    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(3, day=day, key="pedido")
    sacola = _sacola(4, day, key="abandonada")

    production.apply_planned(
        recipe_id=ficha.pk, quantity="5", target_date_value=day.isoformat(),
        actor="production:forneiro", expected_rev=lote.rev, idempotency_key="encolhe-com-pedido",
    )
    sacola.refresh_from_db()
    [entry] = order.data["hold_ids"]
    do_pedido = Hold.objects.get(pk=int(entry["hold_id"].split(":")[1]))
    assert sacola.status == "released"
    assert do_pedido.is_active and do_pedido.quantity == Decimal("3")


def test_plano_que_encolhe_com_folga_nao_mexe_na_sacola(ficha):
    from shopman.backstage.services import production

    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    sacola = _sacola(4, day)

    production.apply_planned(
        recipe_id=ficha.pk, quantity="6", target_date_value=day.isoformat(),
        actor="production:forneiro", expected_rev=lote.rev, idempotency_key="encolhe-com-folga",
    )
    sacola.refresh_from_db()
    assert sacola.is_active and sacola.quantity == Decimal("4")


def test_o_receiver_do_plano_solta_a_sacola_antes_do_pedido(ficha, django_capture_on_commit_callbacks):
    """O receiver direto: saldo planejado de 5 com pedido de 3 e sacolas de 2 e 4."""
    from shopman.stockman.models import Quant
    from shopman.stockman.services.movements import StockMovements

    from shopman.shop.handlers import _stock_receivers

    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(3, day=day, key="pedido")
    antiga = _sacola(2, day, key="antiga")
    nova = _sacola(4, day, key="nova")
    # O saldo desce sem passar pela tela: só o receiver decide quem sai.
    StockMovements.adjust(Quant.objects.get(sku=SKU, target_date=day), Decimal("5"), reason="teste")

    _stock_receivers.on_production_adjusted(sender=None, product_ref=SKU, date=day, action="adjusted", work_order=lote)

    antiga.refresh_from_db()
    nova.refresh_from_db()
    [entry] = order.data["hold_ids"]
    do_pedido = Hold.objects.get(pk=int(entry["hold_id"].split(":")[1]))
    # 3 + 2 + 4 = 9 num saldo de 5: sai a sacola mais nova, e o resto cabe.
    assert nova.status == "released"
    assert antiga.is_active and do_pedido.is_active
