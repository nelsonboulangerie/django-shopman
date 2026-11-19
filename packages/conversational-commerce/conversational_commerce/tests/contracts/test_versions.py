"""Versão e tolerância (decisão 2b): cinco contratos estritos, doze de observação."""

from __future__ import annotations

import pytest

from conversational_commerce.contracts import (
    CONTRACTS,
    ActionCommand,
    ActionReceipt,
    AuthorizationGrant,
    ContextSnapshot,
    ContractError,
    DeploymentProfile,
    ObservationRecord,
    StrictRecord,
    TermsDocument,
    canonical_text,
    compute_hash,
    parse_document,
)

from .examples import example

STRICT = [contract for contract in CONTRACTS if issubclass(contract, StrictRecord)]
OBSERVATION = [contract for contract in CONTRACTS if issubclass(contract, ObservationRecord)]


def test_exactly_the_five_strict_contracts():
    assert set(STRICT) == {TermsDocument, AuthorizationGrant, ActionCommand, ActionReceipt, DeploymentProfile}
    assert len(OBSERVATION) == 12
    assert len(CONTRACTS) == 17
    assert len({contract.SCHEMA for contract in CONTRACTS}) == 17


@pytest.mark.parametrize("contract", STRICT, ids=lambda c: c.KIND)
def test_strict_refuses_unknown_field(contract):
    document = example(contract)
    document["unexpected"] = "x"
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "invalid_content"
    assert "unexpected" in caught.value.message


@pytest.mark.parametrize("contract", STRICT, ids=lambda c: c.KIND)
def test_strict_refuses_unknown_nested_field(contract):
    document = example(contract)
    document["producer"]["build"] = "x"
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.dotted_path == "producer"


@pytest.mark.parametrize("version", ["1.1", "2.0", "0.9", "1", "1.0.0", "v1.0", None])
@pytest.mark.parametrize("contract", STRICT, ids=lambda c: c.KIND)
def test_strict_refuses_unsupported_version(contract, version):
    document = example(contract)
    document["schema_version"] = version
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "unsupported_schema"


@pytest.mark.parametrize("contract", STRICT, ids=lambda c: c.KIND)
def test_strict_refuses_unsupported_version_at_construction(contract):
    record = contract.from_document(example(contract))
    import dataclasses

    with pytest.raises(ContractError) as caught:
        dataclasses.replace(record, schema_version="1.1")
    assert caught.value.code == "unsupported_schema"


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.KIND)
def test_wrong_schema_or_kind_is_refused(contract):
    document = example(contract)
    document["schema"] = "cc.something_else"
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "unsupported_schema"
    document = example(contract)
    document["kind"] = "Other"
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "invalid_content"


@pytest.mark.parametrize("contract", OBSERVATION, ids=lambda c: c.KIND)
def test_observation_keeps_minor_above_in_extensions(contract):
    document = example(contract)
    document["schema_version"] = "1.4"
    document["new_optional_field"] = {"nested": [1, "two"]}
    if contract.HASH_FIELD:
        # O produtor 1.4 calculou o hash com o campo novo; o leitor 1.0 confere igual.
        from conversational_commerce.contracts.canonical import sha256_hash

        body = {key: value for key, value in document.items() if key not in (contract.HASH_FIELD, "recorded_at")}
        document[contract.HASH_FIELD] = sha256_hash(body)
    record = contract.from_document(document)
    assert record.schema_version == "1.4"
    assert dict(record.extensions) == {"new_optional_field": {"nested": (1, "two")}}
    # Reescrito, o documento é o mesmo que chegou: o desconhecido volta ao nível de cima.
    assert canonical_text(record.to_document()) == canonical_text(document)
    if contract.HASH_FIELD:
        assert compute_hash(record) == document[contract.HASH_FIELD]


@pytest.mark.parametrize("contract", OBSERVATION, ids=lambda c: c.KIND)
def test_observation_refuses_unknown_field_without_minor_above(contract):
    document = example(contract)
    document["new_optional_field"] = 1
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "invalid_content"


@pytest.mark.parametrize("version", ["2.0", "0.1"])
@pytest.mark.parametrize("contract", OBSERVATION, ids=lambda c: c.KIND)
def test_observation_refuses_other_major(contract, version):
    document = example(contract)
    document["schema_version"] = version
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "unsupported_schema"


@pytest.mark.parametrize("contract", OBSERVATION, ids=lambda c: c.KIND)
def test_observation_minor_above_without_unknown_field_is_fine(contract):
    document = example(contract)
    document["schema_version"] = "1.2"
    if contract.HASH_FIELD:
        from conversational_commerce.contracts.canonical import sha256_hash

        body = {key: value for key, value in document.items() if key not in (contract.HASH_FIELD, "recorded_at")}
        document[contract.HASH_FIELD] = sha256_hash(body)
    assert contract.from_document(document).extensions == {}


def test_extensions_is_not_a_wire_field():
    document = example(ContextSnapshot)
    document["extensions"] = {}
    with pytest.raises(ContractError) as caught:
        ContextSnapshot.from_document(document)
    assert caught.value.dotted_path == "extensions"


def test_extension_cannot_shadow_a_field():
    record = ContextSnapshot.from_document(example(ContextSnapshot))
    import dataclasses

    with pytest.raises(ContractError):
        dataclasses.replace(record, schema_version="1.3", extensions={"tenant": "other"}, hash=None)


def test_strict_records_have_no_extensions():
    for contract in STRICT:
        assert not hasattr(contract.from_document(example(contract)), "extensions")


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.KIND)
def test_parse_document_dispatches_by_schema(contract):
    assert type(parse_document(example(contract))) is contract


def test_parse_document_refuses_unknown_schema_and_non_objects():
    with pytest.raises(ContractError) as caught:
        parse_document({"schema": "cc.nope"})
    assert caught.value.code == "unsupported_schema"
    with pytest.raises(ContractError) as caught:
        parse_document(["not", "an", "object"])
    assert caught.value.code == "invalid_content"
