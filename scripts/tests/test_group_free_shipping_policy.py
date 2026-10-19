"""Frete grátis de grupo: o menor mínimo vence e o pedido precisa alcançá-lo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.policies.group_advantage import (
    best_group_free_shipping,
    free_shipping_minimum_q,
    group_free_shipping_for_order,
)


def _adv(name: str, min_order_q=0):
    return SimpleNamespace(name=name, config={"min_order_q": min_order_q})


@pytest.mark.parametrize(
    ("minimum_q", "merchandise_q", "covers"),
    [
        (0, 0, True),
        (5_000, 4_999, False),
        (5_000, 5_000, True),
        (5_000, 9_000, True),
    ],
)
def test_group_free_shipping_truth_table(minimum_q: int, merchandise_q: int, covers: bool) -> None:
    found = group_free_shipping_for_order([_adv("alianca", minimum_q)], merchandise_q=merchandise_q)
    assert (found is not None) is covers
    assert group_free_shipping_for_order([], merchandise_q=merchandise_q) is None


def test_lowest_minimum_wins_and_order_breaks_ties() -> None:
    equipe, alianca, outro = _adv("equipe", 5_000), _adv("alianca", 2_000), _adv("outro", 2_000)
    assert best_group_free_shipping([equipe, alianca, outro]).name == "alianca"
    assert best_group_free_shipping([]) is None


@pytest.mark.parametrize(
    ("config", "expected"),
    [({"min_order_q": 3_000}, 3_000), ({}, 0), (None, 0), ({"min_order_q": "x"}, 0), ({"min_order_q": -5}, 0)],
)
def test_minimum_reads_the_config(config, expected: int) -> None:
    assert free_shipping_minimum_q(config) == expected
