from types import SimpleNamespace

import pytest
from shopman.craftsman.contrib.stockman.handlers import _selected_ingredient_batches


def _work_order(items):
    return SimpleNamespace(meta={"_recipe_snapshot": {"items": items}})


def test_selected_ingredient_batch_preserves_the_weighed_lot():
    work_order = _work_order(
        [
            {
                "input_sku": "MASSA-VELHA-PAO-FRANCES",
                "meta": {"batch_ref": "MV-42-ABC"},
            },
            {"input_sku": "FARINHA", "meta": {}},
        ]
    )

    assert _selected_ingredient_batches(work_order) == {
        "MASSA-VELHA-PAO-FRANCES": "MV-42-ABC"
    }


def test_selected_ingredient_batch_leaves_ordinary_ingredients_on_fefo():
    work_order = _work_order([{"input_sku": "FARINHA", "meta": {}}])

    assert _selected_ingredient_batches(work_order) == {}


def test_selected_ingredient_batch_rejects_an_ambiguous_stock_lot():
    work_order = _work_order(
        [
            {"input_sku": "MASSA-VELHA", "meta": {"batch_ref": "MV-1"}},
            {"input_sku": "MASSA-VELHA", "meta": {"batch_ref": "MV-2"}},
        ]
    )

    with pytest.raises(ValueError, match="dois lotes diferentes"):
        _selected_ingredient_batches(work_order)
