from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_canonical_docs as guard


@pytest.fixture
def surface_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / guard.SURFACE_CONTRACT_FILE
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "surfaces": {
                    "storefront": {"dir": "storefront-nuxt", "kind": "customer"},
                    "kitchensink": {"dir": "kitchensink-nuxt", "kind": "internal"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)


def test_dynamic_quality_name_distinguishes_internal_preview(surface_contract: None):
    block = [
        f"    name: {guard.INTERNAL_PREVIEW_QUALITY_NAME}",
        "      matrix: ${{ fromJSON(needs.surface-contract.outputs.quality) }}",
    ]

    assert guard._job_check_names("app-quality", block) == {
        "storefront-nuxt",
        "Preview interno — kitchensink-nuxt",
    }


def test_dynamic_quality_name_rejects_an_unrecognized_kind_expression(surface_contract: None):
    block = [
        "    name: ${{ matrix.kind == 'internal' && format('Preview — {0}', matrix.dir) || matrix.dir }}",
        "      matrix: ${{ fromJSON(needs.surface-contract.outputs.quality) }}",
    ]

    with pytest.raises(ValueError, match="dynamic surface matrix must reference matrix.id or matrix.dir"):
        guard._job_check_names("app-quality", block)
