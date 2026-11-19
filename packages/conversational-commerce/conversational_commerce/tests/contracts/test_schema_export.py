"""O JSON Schema versionado é o gerado: deriva reprova (decisão 2a)."""

from __future__ import annotations

import json
import shutil

from conversational_commerce.contracts import CONTRACTS, ObservationRecord
from conversational_commerce.contracts.schema_export import SCHEMAS_DIR, drift, expected_files, main


def test_no_drift_between_dataclasses_and_versioned_schema():
    assert drift() == []


def test_check_command_passes(capsys):
    assert main(["--check"]) == 0
    assert "sem deriva" in capsys.readouterr().out


def test_one_schema_per_contract():
    names = {path.name for path in SCHEMAS_DIR.glob("*.schema.json")}
    assert names == {f"{contract.SCHEMA}.schema.json" for contract in CONTRACTS}


def test_drift_is_detected(tmp_path):
    for name in expected_files():
        shutil.copy(SCHEMAS_DIR / name, tmp_path / name)
    assert drift(tmp_path) == []
    target = tmp_path / "cc.terms_document.schema.json"
    schema = json.loads(target.read_text(encoding="utf-8"))
    schema["properties"].pop("total")
    target.write_text(json.dumps(schema), encoding="utf-8")
    (tmp_path / "cc.orphan.schema.json").write_text("{}", encoding="utf-8")
    (tmp_path / "cc.need.schema.json").unlink()
    problems = drift(tmp_path)
    assert "cc.terms_document.schema.json difere do gerado" in problems
    assert "falta cc.need.schema.json" in problems
    assert "cc.orphan.schema.json não corresponde a contrato nenhum" in problems


def test_schema_states_strictness_and_has_no_number_type():
    for contract in CONTRACTS:
        text = (SCHEMAS_DIR / f"{contract.SCHEMA}.schema.json").read_text(encoding="utf-8")
        schema = json.loads(text)
        assert schema["additionalProperties"] is issubclass(contract, ObservationRecord)
        assert schema["properties"]["schema"] == {"const": contract.SCHEMA}
        assert '"number"' not in text, "esquema não admite número de ponto flutuante"
        assert {"schema", "kind", "schema_version"} <= set(schema["required"])
        if contract.HASH_FIELD:
            assert contract.HASH_FIELD in schema["required"]
