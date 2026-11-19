"""Forma canônica e o veto a número de ponto flutuante (decisão 2c)."""

from __future__ import annotations

import copy
import math

import pytest

from conversational_commerce.contracts import (
    ContextSnapshot,
    ContractError,
    FrozenMap,
    Money,
    Quantity,
    TermsDocument,
    canonical_bytes,
    canonical_text,
    sha256_hash,
)
from conversational_commerce.contracts.canonical import MAX_SAFE_INTEGER

from .examples import context_snapshot, terms_document


def test_keys_sorted_no_spaces_utf8_raw():
    assert canonical_text({"b": 1, "a": {"d": [1, "é"], "c": None}}) == '{"a":{"c":null,"d":[1,"é"]},"b":1}'
    assert canonical_bytes({"x": "☕"}) == '{"x":"☕"}'.encode()


def test_only_mandatory_escapes():
    assert canonical_text({"t": 'a"b\\c\n\t\x01/'}) == '{"t":"a\\"b\\\\c\\n\\t\\u0001/"}'


def test_hash_format():
    value = sha256_hash({"a": 1})
    assert value.startswith("sha256:") and len(value) == len("sha256:") + 64
    assert value == sha256_hash(FrozenMap({"a": 1}))


@pytest.mark.parametrize("bad", [1.5, 1.0, math.nan, math.inf, {"a": [0.1]}])
def test_float_is_never_canonical(bad):
    with pytest.raises(ContractError) as caught:
        canonical_bytes(bad)
    assert caught.value.code == "invalid_content"
    with pytest.raises(ContractError):
        sha256_hash({"value": bad})


def test_integer_outside_safe_range_is_refused():
    canonical_bytes(MAX_SAFE_INTEGER)
    with pytest.raises(ContractError):
        canonical_bytes(MAX_SAFE_INTEGER + 1)
    with pytest.raises(ContractError):
        Money(amount_minor=-(MAX_SAFE_INTEGER + 1), currency="BRL")


def test_non_string_key_is_refused():
    with pytest.raises(ContractError):
        canonical_bytes({1: "a"})


def test_money_and_quantity_refuse_float():
    with pytest.raises(ContractError):
        Money(amount_minor=15.0, currency="BRL")
    with pytest.raises(ContractError):
        Quantity(value=0.35, unit="kg")
    with pytest.raises(ContractError):
        Quantity(value="0.350", unit="kg")
    with pytest.raises(ContractError):
        Quantity(value="-0", unit="kg")
    assert Quantity(value="-0.5", unit="kg").value == "-0.5"


@pytest.mark.parametrize(
    ("builder", "contract", "where"),
    [
        (terms_document, TermsDocument, lambda d: d["items"][0]["unit_price"].__setitem__("amount_minor", 750.0)),
        (terms_document, TermsDocument, lambda d: d["conditions"].append({"code": "c", "value": {"x": 0.5}})
         if "conditions" in d else d.__setitem__("conditions", [{"code": "c", "value": {"x": 0.5}}])),
        (context_snapshot, ContextSnapshot, lambda d: d["dialogue_state"].__setitem__("score", 0.9)),
        (context_snapshot, ContextSnapshot, lambda d: d.__setitem__("episode_version", 4.0)),
    ],
)
def test_float_in_a_hashed_document_is_refused(builder, contract, where):
    document = copy.deepcopy(builder())
    where(document)
    with pytest.raises(ContractError) as caught:
        contract.from_document(document)
    assert caught.value.code == "invalid_content"
    assert "ponto flutuante" in caught.value.message


def test_bool_is_not_an_integer():
    with pytest.raises(ContractError):
        Money(amount_minor=True, currency="BRL")
