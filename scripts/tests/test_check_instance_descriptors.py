from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_instance_descriptors", ROOT / "scripts/check_instance_descriptors.py")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def _nelson():
    return json.loads((ROOT / "config/instances/nelson.json").read_text(encoding="utf-8"))


def test_canonical_descriptors_are_valid():
    paths = gate.validate_directory()
    schema = json.loads((ROOT / "config/instances/schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for path in paths:
        validator.validate(json.loads(path.read_text(encoding="utf-8")))
    assert [path.stem for path in paths] == ["counter-minimal", "nelson"]


def test_rejects_ownership_overlap():
    descriptor = _nelson()
    descriptor["ownership"]["deploy"].append("SECRET_KEY")
    with pytest.raises(gate.DescriptorError, match="pertence a"):
        gate.validate_descriptor(descriptor)


def test_rejects_secret_material_inside_bootstrap():
    descriptor = _nelson()
    descriptor["bootstrap"]["channels"][0]["config"] = {"api_token": "never-version-this"}
    with pytest.raises(gate.DescriptorError, match="segredo proibido"):
        gate.validate_descriptor(descriptor)


def test_rejects_secret_pattern_inside_an_innocent_value():
    descriptor = _nelson()
    descriptor["bootstrap"]["channels"][0]["config"] = {
        "endpoint": "postgresql://operator:password@db.internal/shopman"
    }
    with pytest.raises(gate.DescriptorError, match="valor com padrão de segredo"):
        gate.validate_descriptor(descriptor)


def test_rejects_operational_state_inside_bootstrap():
    descriptor = _nelson()
    descriptor["bootstrap"]["channels"][0]["config"] = {"orders": []}
    with pytest.raises(gate.DescriptorError, match="estado operacional proibido"):
        gate.validate_descriptor(descriptor)


def test_rejects_missing_database_owned_section():
    descriptor = _nelson()
    descriptor["ownership"]["instance_db"].remove("templates")
    with pytest.raises(gate.DescriptorError, match="instance_db precisa possuir"):
        gate.validate_descriptor(descriptor)


def test_rejects_persona_ref_that_does_not_match_its_name():
    descriptor = _nelson()
    descriptor["bootstrap"]["rbac_personas"][0]["ref"] = "wrong-name"
    with pytest.raises(gate.DescriptorError, match="não corresponde ao nome"):
        gate.validate_descriptor(descriptor)


@pytest.mark.parametrize(
    "overrides",
    [
        {"activation": {"by": "operador", "reason": "forno parado"}},
        {"display": {"paused_skus": ["PAO-01"]}},
    ],
    ids=["activation", "paused_skus"],
)
def test_rejects_channel_operational_state(overrides):
    descriptor = _nelson()
    descriptor["bootstrap"]["channels"][0]["config"]["overrides"].update(overrides)
    with pytest.raises(gate.DescriptorError, match="estado operacional proibido"):
        gate.validate_descriptor(descriptor)


@pytest.mark.parametrize(
    "key",
    ["pix_key", "chave_pix", "webhook_hmac", "authorization", "signing", "senha", "certificado_a1"],
)
def test_rejects_secret_names_the_old_denylist_let_through(key):
    descriptor = _nelson()
    descriptor["bootstrap"]["channels"][0]["config"]["overrides"][key] = "x"
    with pytest.raises(gate.DescriptorError, match="segredo proibido"):
        gate.validate_descriptor(descriptor)
