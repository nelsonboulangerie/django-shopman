"""``ActionReceipt`` só aceita as quatro combinações de estado × efeito (v2 4.7)."""

from __future__ import annotations

import itertools

import pytest

from conversational_commerce.contracts import VALID_COMBINATIONS, ActionReceipt, ContractError

from .examples import action_receipt

STATUSES = ("success", "failure", "pending", "unknown")
EFFECTS = ("applied", "not_applied", "unknown")


def _receipt(status: str, effect: str) -> dict:
    document = action_receipt()
    document.update(status=status, effect=effect)
    if status == "failure":
        document["error"] = {"code": "terms_changed", "retry": "never"}
        document.pop("domain_refs")
    if status in ("pending", "unknown"):
        document["reconciliation"] = {"deadline": "2026-11-18T14:15:00.000000Z", "owner": "core"}
        document.pop("domain_refs")
    return document


def test_the_four_combinations_are_the_table():
    assert VALID_COMBINATIONS == {
        ("success", "applied"),
        ("failure", "not_applied"),
        ("pending", "unknown"),
        ("unknown", "unknown"),
    }


@pytest.mark.parametrize(("status", "effect"), list(itertools.product(STATUSES, EFFECTS)))
def test_only_four_of_twelve_combinations_exist(status, effect):
    document = _receipt(status, effect)
    if (status, effect) in VALID_COMBINATIONS:
        record = ActionReceipt.from_document(document)
        assert (record.status, record.effect) == (status, effect)
    else:
        with pytest.raises(ContractError) as caught:
            ActionReceipt.from_document(document)
        assert caught.value.code == "invalid_content"
        assert caught.value.dotted_path == "effect"


def test_success_needs_proof_and_no_error():
    document = _receipt("success", "applied")
    document.pop("domain_refs")
    with pytest.raises(ContractError, match="domain_refs"):
        ActionReceipt.from_document(document)
    document = _receipt("success", "applied")
    document["error"] = {"code": "terms_changed", "retry": "never"}
    with pytest.raises(ContractError, match="error"):
        ActionReceipt.from_document(document)


def test_failure_is_definitive():
    document = _receipt("failure", "not_applied")
    document.pop("error")
    with pytest.raises(ContractError, match="error"):
        ActionReceipt.from_document(document)
    document = _receipt("failure", "not_applied")
    document["error"]["retry"] = "same_key"
    with pytest.raises(ContractError, match="retry"):
        ActionReceipt.from_document(document)


@pytest.mark.parametrize("status", ["pending", "unknown"])
def test_open_effect_has_reconciliation_and_never_a_new_key(status):
    document = _receipt(status, "unknown")
    document.pop("reconciliation")
    with pytest.raises(ContractError, match="reconciliation"):
        ActionReceipt.from_document(document)
    document = _receipt(status, "unknown")
    document["error"] = {"code": "provider_unavailable", "retry": "never"}
    with pytest.raises(ContractError, match="retry"):
        ActionReceipt.from_document(document)
    document["error"]["retry"] = "same_key"
    assert ActionReceipt.from_document(document).error.retry == "same_key"


def test_terminal_receipt_has_no_reconciliation():
    document = _receipt("success", "applied")
    document["reconciliation"] = {"deadline": "2026-11-18T14:15:00.000000Z", "owner": "core"}
    with pytest.raises(ContractError, match="reconciliation"):
        ActionReceipt.from_document(document)


def test_error_code_is_the_stable_enum():
    document = _receipt("failure", "not_applied")
    document["error"]["code"] = "something_went_wrong"
    with pytest.raises(ContractError) as caught:
        ActionReceipt.from_document(document)
    assert caught.value.dotted_path == "error.code"
