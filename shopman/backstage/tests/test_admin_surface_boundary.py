"""Executable contract for the Admin/Unfold × operator-surface boundary."""

from __future__ import annotations

from copy import deepcopy

from scripts import check_admin_surface_boundary as gate


def _contract():
    return gate.load_json(gate.CONTRACT_PATH)


def test_repository_boundary_contract_matches_live_admin_registry() -> None:
    contract = _contract()
    live = gate.registered_model_admins()
    custom_pages = gate.registered_custom_admin_pages()

    assert len(live) == 96
    assert len(custom_pages) == 7
    assert gate.validate_contract(
        contract,
        runtime_models=live,
        runtime_custom_pages=custom_pages,
    ) == []


def test_boundary_contract_rejects_unclassified_and_duplicate_modeladmins() -> None:
    contract = _contract()
    first = contract["admin_model_groups"][0]
    duplicate = first["models"][0]
    first["models"].remove(duplicate)
    contract["admin_model_groups"][1]["models"].extend([duplicate, duplicate])

    errors = gate.validate_contract(contract, runtime_models=gate.registered_model_admins())

    assert f"ModelAdmin classified more than once: {duplicate}" in errors


def test_boundary_contract_forbids_admin_only_routine_work() -> None:
    contract = _contract()
    workflow = contract["workflows"][0]
    workflow["admin_only"] = True

    errors = gate.validate_contract(contract, runtime_models=gate.registered_model_admins())

    assert f"workflow {workflow['id']!r}: routine work cannot be admin_only" in errors


def test_boundary_contract_requires_machine_readable_admin_fit() -> None:
    contract = _contract()
    group = contract["admin_model_groups"][0]
    group.pop("admin_fit")

    errors = gate.validate_contract(contract, runtime_models=gate.registered_model_admins())

    assert f"admin_model_group {group['id']!r}: invalid or missing admin_fit=None" in errors


def test_boundary_contract_requires_registered_surface_page_api_and_test(tmp_path) -> None:
    contract = deepcopy(_contract())
    workflow = contract["workflows"][0]
    workflow["surface"] = "not-registered"
    workflow["pages"] = ["missing/page.vue"]
    workflow["api"] = [{"path": "missing/api.py", "contains": "route"}]
    workflow["tests"] = ["missing/spec.ts"]

    errors = gate.validate_contract(
        contract,
        root=tmp_path,
        runtime_models=None,
        surface_registry={"surfaces": {}},
    )

    assert any("is not a registered operator surface" in error for error in errors)
    assert any("missing page evidence" in error for error in errors)
    assert any("missing API evidence" in error for error in errors)
    assert any("invalid test evidence" in error for error in errors)


def test_boundary_contract_locks_named_wp11_decisions_exactly_once() -> None:
    contract = _contract()
    assigned = [lock for workflow in contract["workflows"] for lock in workflow.get("locks", [])]

    assert set(assigned) == set(contract["required_locks"])
    assert len(assigned) == len(set(assigned))


def test_two_factor_routes_are_explicit_security_interstitials_not_custom_pages() -> None:
    contract = _contract()
    interstitials = {entry["route"]: entry for entry in contract["admin_auth_interstitials"]}
    custom_ids = {page["id"] for page in contract["custom_admin_pages"]}

    assert set(interstitials) == {"admin_2fa_verify", "admin_2fa_enroll"}
    assert {entry["admin_fit"] for entry in interstitials.values()} == {"secret"}
    assert not custom_ids.intersection({"admin-2fa-verify", "admin-2fa-enroll"})
