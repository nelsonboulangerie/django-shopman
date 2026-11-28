"""Quem decide "pode pedir" fora do carrinho pergunta à promessa do Stockman.

Caracterização em matriz, no estilo do dual-run da F2 (#2263): cada leitura é
montada pela aritmética real do Stockman (``_build_availability_dict`` /
``_zero_availability_dict``), e cada ponto do shop e do backstage que responde
"dá para pedir este SKU?" tem de responder o mesmo que
``decision_from_availability`` (o miolo de ``promise_for_sku``).

A matriz cruza as três políticas (``stock_only``, ``planned_ok``,
``demand_ok``) com: pronto na prateleira, esgotado, fornada planejada com vaga,
fornada planejada já toda reservada, pausado e SKU sem ledger.

"Pode pedir alguma coisa" é ``orderable_ceiling is None or > 0`` (o teto da
própria promessa); para o substituto, que pergunta por uma quantidade, é
``approved`` da promessa naquela quantidade.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from shopman.stockman.services.availability import (
    _build_availability_dict,
    _zero_availability_dict,
    decision_from_availability,
)

from shopman.shop.projections import catalog_context

POLICIES = ("stock_only", "planned_ok", "demand_ok")
Z = Decimal("0")


def _reading(policy: str, state: str) -> dict:
    if state == "paused":
        return _zero_availability_dict("SKU", policy, 0, is_paused=True, is_tracked=True)
    if state == "untracked":
        return _zero_availability_dict("SKU", policy, 0, is_paused=False, is_tracked=False)
    # (pronto, planejado, planejado já reservado, is_planned)
    ready, planned, held_planned, is_planned = {
        "ready": (Decimal("5"), Z, Z, False),
        "sold_out": (Z, Z, Z, False),
        "planned_open": (Z, Decimal("10"), Decimal("3"), True),
        "planned_full": (Z, Decimal("10"), Decimal("10"), True),
    }[state]
    return _build_availability_dict(
        sku="SKU",
        availability_policy=policy,
        ready=ready,
        in_production=Z,
        planned=planned,
        held_ready=Z,
        held_production=Z,
        held_planned=held_planned,
        safety_margin=0,
        is_planned=is_planned,
        positions_data=[],
    )


STATES = ("ready", "sold_out", "planned_open", "planned_full", "paused", "untracked")
MATRIX = [(p, s) for p in POLICIES for s in STATES]


def _promise_can_order(reading: dict) -> bool:
    ceiling = decision_from_availability("SKU", Decimal("1"), reading).orderable_ceiling
    return ceiling is None or ceiling > 0


@pytest.mark.parametrize(("policy", "state"), MATRIX)
def test_storefront_can_order_e_a_promessa(policy, state):
    reading = _reading(policy, state)
    got = catalog_context.storefront_availability(reading, is_sellable=True)["can_order"]
    assert got is _promise_can_order(reading)


@pytest.mark.parametrize(("policy", "state"), MATRIX)
def test_selo_do_cardapio_abre_o_carrinho_como_a_promessa(policy, state):
    reading = _reading(policy, state)
    got = catalog_context.basic_availability(
        reading, is_sellable=True, low_stock_threshold=Decimal("2")
    ).can_add_to_cart
    assert got is _promise_can_order(reading)


@pytest.mark.parametrize(("policy", "state"), MATRIX)
def test_teto_do_stepper_e_o_teto_da_promessa(policy, state):
    reading = _reading(policy, state)
    decision = decision_from_availability("SKU", Decimal("1"), reading)
    got = catalog_context.orderable_ceiling(reading, can_add=True)
    if decision.is_paused or decision.orderable_ceiling is None:
        assert got is None
    else:
        assert got == int(decision.orderable_ceiling)


@pytest.mark.parametrize("qty", [Decimal("1"), Decimal("7")])
@pytest.mark.parametrize(("policy", "state"), MATRIX)
def test_substituto_pergunta_a_promessa(policy, state, qty):
    from shopman.shop.services.substitutes import _resolve_availability

    reading = _reading(policy, state)
    product = SimpleNamespace(sku="SKU", is_sellable=True)
    can_order, _qty = _resolve_availability(reading, product, qty)
    assert can_order is decision_from_availability("SKU", qty, reading).approved


@pytest.mark.parametrize(("policy", "state"), MATRIX)
def test_post_social_espera_estoque_como_a_promessa(policy, state):
    from shopman.shop.services.social_publish_rules import _has_promisable_stock

    reading = _reading(policy, state)
    with mock.patch.object(catalog_context, "availability_for_sku", return_value=reading):
        got = _has_promisable_stock("SKU", "instagram")
    assert got is _promise_can_order(reading)


@pytest.mark.parametrize(("policy", "state"), MATRIX)
def test_anuncio_do_marketing_recusa_como_a_promessa(policy, state):
    from shopman.shop.services import marketing_facts
    from shopman.shop.services.marketing_facts import MarketingContractError

    reading = _reading(policy, state)
    product = SimpleNamespace(sku="SKU")
    with mock.patch.object(catalog_context, "availability_for_sku", return_value=reading):
        try:
            payload = marketing_facts._availability(product)
        except MarketingContractError as exc:
            assert exc.code == "marketing_product_unavailable"
            got = False
        else:
            got = True
    assert got is _promise_can_order(reading)
    if got:
        ceiling = decision_from_availability("SKU", Decimal("1"), reading).orderable_ceiling
        assert payload["available_qty"] == (None if ceiling is None else int(ceiling))


@pytest.mark.django_db
@pytest.mark.parametrize(("policy", "state"), MATRIX)
def test_falta_na_prateleira_abre_como_a_promessa(policy, state):
    from shopman.backstage.models import OutageReason
    from shopman.backstage.services.shelf_outages import _reason_from

    reading = _reading(policy, state)
    got = _reason_from(reading)
    if state == "paused":
        assert got == OutageReason.PAUSED
    else:
        assert (got == "") is _promise_can_order(reading)
