from __future__ import annotations

import json

import pytest
from django.core.management import CommandError, call_command

from shopman.backstage.data_readiness.catalog import (
    CatalogAuditError,
    CatalogSnapshot,
    audit_catalog_candidate,
    read_catalog_candidate,
)


def _row(**overrides):
    row = {
        "sku": "BGG",
        "nome_consolidado": "Baguete Grande",
        "situacao_consolidado": "ativo",
        "preco_consolidado_brl": "18,00",
        "unidade_consolidado": "un",
        "peso_g_consolidado": "260",
        "ncm": "19059010",
        "cest": "",
        "gtin": "",
        "marca": "Nelson",
        "copy_curta": "Crocante por fora, macia por dentro.",
        "foto_consolidado": "https://cdn.example.test/bgg.jpg",
        "categoria_consolidado": "paes",
        "receita_consolidado": "sim",
        "origem": "producao propria",
    }
    row.update(overrides)
    return row


def _product(**overrides):
    product = {
        "name": "Baguete Grande",
        "short_description": "Crocante por fora, macia por dentro.",
        "unit": "un",
        "unit_weight_g": 260,
        "base_price_q": 1800,
        "is_published": True,
        "is_sellable": True,
        "image_url": "https://cdn.example.test/bgg.jpg",
        "ncm": "19059010",
        "cest": "",
        "brand": "Nelson",
        "gtin": "",
        "collections": ["paes"],
        "live_listing": True,
    }
    product.update(overrides)
    return product


def _snapshot(*, products=None, materials=None, recipes=("BGG",)):
    return CatalogSnapshot(
        products=products or {},
        materials=materials or {},
        active_recipe_skus=frozenset(recipes),
    )


def test_normalized_csv_contract_is_utf8_and_does_not_expose_local_path(tmp_path):
    source = tmp_path / "privado" / "catalogo.csv"
    source.parent.mkdir()
    source.write_text(
        "sku;nome_consolidado;situacao_consolidado;preco_consolidado_brl;unidade_consolidado\n"
        "BGG;Baguete Grande;ativo;18,00;un\n",
        encoding="utf-8",
    )
    rows, manifest = read_catalog_candidate(source)

    assert rows[0]["sku"] == "BGG"
    assert manifest["logical_name"] == "catalogo.csv"
    assert str(source.parent) not in json.dumps(manifest)


def test_normalized_csv_requires_the_explicit_day1_contract(tmp_path):
    source = tmp_path / "catalogo.csv"
    source.write_text("sku,nome_consolidado\nBGG,Baguete\n", encoding="utf-8")
    with pytest.raises(CatalogAuditError, match="Colunas obrigatórias ausentes"):
        read_catalog_candidate(source)


def test_existing_target_reports_authority_drift_without_changing_snapshot():
    original = _product(base_price_q=1700)
    snapshot = _snapshot(products={"BGG": original})

    report = audit_catalog_candidate(
        [_row()], snapshot, source={"sha256": "a" * 64, "logical_name": "catalogo.csv"}
    )

    issues = report["candidates"][0]["issues"]
    assert any(
        issue["code"] == "authority_drift"
        and issue["field"] == "base_price_q"
        and issue["expected"] == 1800
        and issue["observed"] == 1700
        for issue in issues
    )
    assert original["base_price_q"] == 1700
    assert report["mode"] == "read_only_dry_run"


def test_new_product_can_only_be_draft_and_missing_curation_blocks_publication():
    report = audit_catalog_candidate(
        [
            _row(
                sku="NOVO",
                situacao_consolidado="novo",
                peso_g_consolidado="",
                ncm="",
                marca="",
                copy_curta="",
                foto_consolidado="",
                receita_consolidado="",
                origem="revenda",
            )
        ],
        _snapshot(recipes=()),
        source={"sha256": "b" * 64, "logical_name": "catalogo.csv"},
    )

    candidate = report["candidates"][0]
    assert candidate["readiness"] == "draft_only"
    codes = {issue["code"] for issue in candidate["issues"]}
    assert {
        "new_product_draft_only",
        "missing_ncm",
        "missing_marca",
        "missing_copy_curta",
        "missing_foto_consolidado",
        "missing_unit_weight",
    } <= codes


def test_explicit_no_recipe_overrides_house_origin_and_invalid_cest_blocks():
    report = audit_catalog_candidate(
        [_row(receita_consolidado="não", cest="17.02")],
        _snapshot(products={"BGG": _product()}, recipes=()),
        source={"sha256": "d" * 64, "logical_name": "catalogo.csv"},
    )

    codes = {issue["code"] for issue in report["candidates"][0]["issues"]}
    assert "missing_active_recipe" not in codes
    assert "invalid_cest" in codes


def test_restrictive_live_sku_and_shared_material_unit_mismatch_need_explicit_resolution():
    report = audit_catalog_candidate(
        [_row(situacao_consolidado="despublicar", unidade_consolidado="kg")],
        _snapshot(products={"BGG": _product()}, materials={"BGG": {"unit": "un", "is_active": True}}),
        source={"sha256": "c" * 64, "logical_name": "catalogo.csv"},
    )

    issues = report["candidates"][0]["issues"]
    assert {issue["code"] for issue in issues} >= {
        "restrictive_status_still_commercial",
        "shared_sku_unit_mismatch",
    }
    assert report["candidates"][0]["readiness"] == "blocked"


def test_command_refuses_to_overwrite_audit_report(tmp_path, monkeypatch):
    source = tmp_path / "catalogo.csv"
    source.write_text(
        "sku,nome_consolidado,situacao_consolidado,preco_consolidado_brl,unidade_consolidado\n"
        "BGG,Baguete Grande,ativo,18.00,un\n",
        encoding="utf-8",
    )
    output = tmp_path / "audit.json"
    monkeypatch.setattr(
        "shopman.backstage.management.commands.audit_catalog_day1.database_catalog_snapshot",
        lambda: _snapshot(recipes=()),
    )

    call_command("audit_catalog_day1", "--file", source, "--output", output)
    with pytest.raises(CommandError, match="já existe"):
        call_command("audit_catalog_day1", "--file", source, "--output", output)
