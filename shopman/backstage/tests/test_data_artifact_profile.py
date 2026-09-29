from __future__ import annotations

import json
import sqlite3

import pytest
from django.core.management import CommandError, call_command

from shopman.backstage.data_readiness import ArtifactProfileError, profile_artifact


def test_csv_profile_is_sanitized_and_measures_keys_dates_and_nulls(tmp_path):
    source = tmp_path / "private" / "catalog.csv"
    source.parent.mkdir()
    source.write_text(
        "sku;price;as_of;owner_phone\n"
        "PAO-1;1290;2026-09-01;+5543999990000\n"
        "PAO-1;1390;2026-09-02;+5543999990001\n"
        "PAO-2;;2026-09-03;+5543999990002\n"
        ";1990;;+5543999990003\n",
        encoding="utf-8",
    )

    manifest = profile_artifact(
        source,
        source="catalogo_nelson_consolidado",
        purpose="catalog_candidate",
        key_fields=("sku",),
        date_fields=("as_of",),
    )

    table = manifest["profile"]["tables"][0]
    assert table["rows_raw"] == 4
    assert table["rows_valid"] == 4
    assert table["distinct_keys"] == 2
    assert table["duplicate_keys"] == 1
    assert table["null_counts"] == {"as_of": 1, "sku": 1}
    assert table["date_ranges"]["as_of"] == {"min": "2026-09-01", "max": "2026-09-03"}
    rendered = json.dumps(manifest)
    assert str(source.parent) not in rendered
    assert "+5543" not in rendered
    assert "PAO-1" not in rendered


def test_xlsx_profile_scopes_composite_keys_without_exposing_values(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "catalog.xlsx"
    workbook = openpyxl.Workbook()
    products = workbook.active
    products.title = "Produtos"
    products.append(("sku", "channel", "price"))
    products.append(("A", "loja", 10))
    products.append(("A", "loja", 11))
    products.append(("A", "ifood", 12))
    empty = workbook.create_sheet("Vazia")
    empty.append(("sku",))
    workbook.save(source)

    manifest = profile_artifact(
        source,
        source="catalogo_nelson_consolidado",
        purpose="catalog_candidate",
        key_fields=("Produtos:sku", "Produtos:channel"),
    )
    products_profile = manifest["profile"]["tables"][0]
    assert products_profile["distinct_keys"] == 2
    assert products_profile["duplicate_keys"] == 1
    assert "ifood" not in json.dumps(manifest)


def test_xml_profile_rejects_entities_and_never_outputs_text(tmp_path):
    source = tmp_path / "nfe.xml"
    source.write_text("<!DOCTYPE x [<!ENTITY pii 'secret-value'>]><root><item>&pii;</item></root>")
    with pytest.raises(ArtifactProfileError, match="XML inseguro"):
        profile_artifact(source, source="nfe", purpose="historical_fiscal")


def test_sqlite_is_opened_read_only_and_only_schema_counts_are_reported(tmp_path):
    source = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE product (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    connection.execute("INSERT INTO product(name) VALUES ('segredo comercial')")
    connection.commit()
    connection.close()

    manifest = profile_artifact(source, source="legacy_snapshot", purpose="catalog_evidence")
    assert manifest["profile"]["tables"] == [
        {
            "name": "product",
            "columns": [
                {"name": "id", "type": "INTEGER", "not_null": False, "primary_key": True},
                {"name": "name", "type": "TEXT", "not_null": True, "primary_key": False},
            ],
            "rows_raw": 1,
        }
    ]
    assert "segredo comercial" not in json.dumps(manifest)


def test_command_refuses_to_overwrite_report(tmp_path):
    source = tmp_path / "catalog.csv"
    source.write_text("sku\nA\n")
    output = tmp_path / "manifest.json"
    call_command(
        "profile_data_artifact",
        "--file",
        source,
        "--source",
        "catalog",
        "--purpose",
        "candidate",
        "--output",
        output,
    )
    with pytest.raises(CommandError, match="já existe"):
        call_command(
            "profile_data_artifact",
            "--file",
            source,
            "--source",
            "catalog",
            "--purpose",
            "candidate",
            "--output",
            output,
        )


def test_identity_fields_cannot_smuggle_paths_or_free_text(tmp_path):
    source = tmp_path / "catalog.csv"
    source.write_text("sku\nA\n")
    with pytest.raises(ArtifactProfileError, match="tokens seguros"):
        profile_artifact(source, source="nome de pessoa", purpose="candidate")
    with pytest.raises(ArtifactProfileError, match="nunca um caminho"):
        profile_artifact(source, source="catalog", purpose="candidate", logical_name="/Users/alguem/catalog.csv")
