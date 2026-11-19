"""Vetores de termos e concessões: o que outra implementação tem que reproduzir.

O hash esperado é conferido de duas formas: pelo código do pacote e por
``hashlib`` direto sobre a forma canônica gravada no vetor, para que um erro no
código não se confirme a si mesmo.
"""

from __future__ import annotations

import hashlib

import pytest

from conversational_commerce.contracts import (
    AuthorizationGrant,
    ContractError,
    TermsDocument,
    canonical_text,
    compute_hash,
)
from conversational_commerce.contracts.validate import hash_input
from conversational_commerce.vectors import load

TERMS = load("terms")
GRANTS = load("grants")
CONTRACT_BY_FILE = {"cc.terms_document": TermsDocument, "cc.authorization_grant": AuthorizationGrant}


def _cases(payload, result):
    return [pytest.param(case, id=case["name"]) for case in payload["cases"] if case["expect"]["result"] == result]


def test_vector_files_have_both_kinds():
    for payload in (TERMS, GRANTS):
        assert payload["format"] == "cc.vectors/1"
        results = {case["expect"]["result"] for case in payload["cases"]}
        assert results == {"valid", "rejected"}
        names = [case["name"] for case in payload["cases"]]
        assert len(names) == len(set(names))


@pytest.mark.parametrize("case", _cases(TERMS, "valid"))
def test_terms_vector_reproduces_canonical_form_and_hash(case):
    record = TermsDocument.from_document(case["document"])
    expected = case["expect"]
    assert canonical_text(hash_input(record)) == expected["canonical"]
    independent = "sha256:" + hashlib.sha256(expected["canonical"].encode("utf-8")).hexdigest()
    assert independent == expected["hash"]
    assert compute_hash(record) == expected["hash"]
    assert record.hash == expected["hash"]


@pytest.mark.parametrize("case", _cases(TERMS, "valid") + _cases(GRANTS, "valid"))
def test_valid_vector_round_trips_to_the_same_document(case):
    contract = CONTRACT_BY_FILE[case["document"]["schema"]]
    record = contract.from_document(case["document"])
    assert canonical_text(record.to_document()) == canonical_text(case["document"])
    assert contract.from_document(record.to_document()) == record


@pytest.mark.parametrize("case", _cases(TERMS, "rejected") + _cases(GRANTS, "rejected"))
def test_rejected_vector_fails_with_the_stated_code_and_path(case):
    contract = CONTRACT_BY_FILE[case["document"]["schema"]]
    with pytest.raises(ContractError) as caught:
        contract.from_document(case["document"])
    assert caught.value.code.value == case["expect"]["code"]
    assert caught.value.dotted_path == case["expect"]["path"]


def test_recorded_at_stays_out_of_the_hash():
    by_name = {case["name"]: case for case in TERMS["cases"]}
    basic, recorded = by_name["terms-basic"], by_name["terms-basic-recorded"]
    assert "recorded_at" in recorded["document"]
    assert recorded["expect"]["hash"] == basic["expect"]["hash"]


def test_grant_vector_is_bound_to_the_terms_vector_hash():
    terms_hash = {case["name"]: case["expect"].get("hash") for case in TERMS["cases"]}
    bound = [case for case in GRANTS["cases"] if "binds_to" in case]
    assert bound
    for case in bound:
        assert case["document"]["terms_hash"] == terms_hash[case["binds_to"]]


def test_any_material_change_changes_the_hash():
    """Propriedade 2 do contrato de efeito: mudança material é outro documento, com outro hash."""
    base = next(case for case in TERMS["cases"] if case["name"] == "terms-rich")["document"]
    original = TermsDocument.from_document(base)
    changes = {
        "quantity": lambda d: d["items"][1]["quantity"].__setitem__("value", "0.36"),
        "recipient": lambda d: d["recipient"].__setitem__("subject_ref", "customer-0002"),
        "fulfillment": lambda d: d["fulfillment"].__setitem__("mode", "pickup"),
        "condition": lambda d: d["conditions"][0].__setitem__("value", False),
        "validity": lambda d: d.__setitem__("valid_until", "2026-11-18T14:31:00.000000Z"),
    }
    import copy

    for name, change in changes.items():
        document = copy.deepcopy(base)
        change(document)
        document.pop("hash")
        draft = TermsDocument(**{k: v for k, v in document.items() if k not in ("schema", "kind")})
        assert compute_hash(draft) != original.hash, name
