"""N14: snapshot e decisão (e todo registro) são imutáveis; correção é registro novo."""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.contracts import (
    CONTRACTS,
    ContextSnapshot,
    ContractError,
    DecisionRecord,
    FrozenMap,
    Money,
    compute_hash,
)

from .examples import example


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.KIND)
def test_record_fields_cannot_be_set_or_deleted(contract):
    record = contract.from_document(example(contract))
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.id = "other"
    with pytest.raises(dataclasses.FrozenInstanceError):
        del record.tenant
    assert not hasattr(record, "__dict__"), "slots: nenhum atributo novo cabe no registro"


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.KIND)
def test_no_mutable_container_inside_a_record(contract):
    record = contract.from_document(example(contract))

    def walk(value, path):
        assert not isinstance(value, list | dict | set), f"{contract.KIND}.{path} é mutável: {type(value).__name__}"
        if dataclasses.is_dataclass(value):
            for f in dataclasses.fields(value):
                walk(getattr(value, f.name), f"{path}.{f.name}")
        elif isinstance(value, FrozenMap):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, tuple):
            for index, item in enumerate(value):
                walk(item, f"{path}.{index}")

    walk(record, "")
    hash(record)  # imutável de verdade: o registro inteiro tem hash


def test_frozen_map_refuses_mutation():
    record = ContextSnapshot.from_document(example(ContextSnapshot))
    with pytest.raises(TypeError):
        record.dialogue_state["focus"] = "other"  # type: ignore[index]
    with pytest.raises(AttributeError):
        record.facts.update({})  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        record.facts._data = {}  # type: ignore[misc]


def test_list_given_to_constructor_becomes_tuple():
    record = DecisionRecord.from_document(example(DecisionRecord))
    corrected = dataclasses.replace(record, chosen=[0], id="rec-decision-2")
    assert corrected.chosen == (0,)
    assert isinstance(corrected.chosen, tuple)


def test_correction_is_a_new_record_and_the_old_one_is_untouched():
    old = ContextSnapshot.from_document(example(ContextSnapshot))
    new = dataclasses.replace(old, id="rec-snapshot-2", episode_version=5, hash=None)
    assert old.episode_version == 4
    assert compute_hash(new) != old.hash
    assert old.hash == compute_hash(old)


def test_replace_cannot_produce_an_invalid_record():
    old = ContextSnapshot.from_document(example(ContextSnapshot))
    with pytest.raises(ContractError, match="hash"):
        dataclasses.replace(old, episode_version=5)  # hash velho não confere
    with pytest.raises(ContractError):
        dataclasses.replace(Money(amount_minor=1, currency="BRL"), currency="real")
