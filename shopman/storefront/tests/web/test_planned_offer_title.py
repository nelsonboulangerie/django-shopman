"""O próximo lote diz quando o item fica disponível (dono, 24/11/2026, KISS).

Quando o item acaba e há próximo lote, a folha da loja diz "Disponível a partir das
15h" (ou "Disponível amanhã, quarta, a partir das 7h") e oferece "Reservar". O
pedaço de quando sai da MESMA promessa do card e do produto; sem promessa, a frase
não inventa hora.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.storefront.api import surface
from shopman.storefront.presentation import promise as promise_module
from shopman.storefront.presentation.promise import KIND_BATCH, KIND_PREORDER, KIND_READY, PromiseProjection


def _exc(planned="2026-11-25"):
    return SimpleNamespace(sku="TABAT", planned_target_date=planned)


@pytest.fixture
def promise_is(monkeypatch):
    def install(value):
        monkeypatch.setattr("shopman.shop.projections.ready_promise.read_promise_facts", lambda skus, **kw: object())
        monkeypatch.setattr(promise_module, "promise_for", lambda sku, facts, **kw: value)
    return install


@pytest.mark.django_db
def test_hoje_mais_tarde_diz_a_hora(promise_is):
    promise_is(PromiseProjection(KIND_BATCH, "2026-11-24", "15:00", "hoje", "Disponível a partir das 15h"))
    assert surface._planned_offer_title(_exc()) == "Disponível a partir das 15h"


@pytest.mark.django_db
def test_outro_dia_diz_o_dia_e_a_hora(promise_is):
    promise_is(PromiseProjection(KIND_PREORDER, "2026-11-25", "07:30", "amanhã, quarta", "Disponível amanhã, quarta, a partir das 7h30"))
    assert surface._planned_offer_title(_exc()) == "Disponível amanhã, quarta, a partir das 7h30"


@pytest.mark.django_db
@pytest.mark.parametrize("value", [None, PromiseProjection(KIND_READY, "2026-11-24", "10:00", "hoje", "Disponível agora")])
def test_sem_promessa_de_lote_nao_inventa_hora(promise_is, value):
    promise_is(value)
    assert surface._planned_offer_title(_exc()) == "Disponível no próximo lote"


@pytest.mark.django_db
def test_a_frase_nunca_fala_de_prontidao(promise_is):
    promise_is(PromiseProjection(KIND_BATCH, "2026-11-24", "15:00", "hoje", "Disponível a partir das 15h"))
    assert "pront" not in surface._planned_offer_title(_exc()).lower()
