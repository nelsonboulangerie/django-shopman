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

    assert len(live) == 95
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


def _workflow(contract, workflow_id):
    return next(w for w in contract["workflows"] if w["id"] == workflow_id)


def _group_of(contract, model):
    return next(g for g in contract["admin_model_groups"] if model in g["models"])


def test_promotion_is_rare_in_admin_because_its_routine_lives_in_marketing() -> None:
    """A11-1: as duas classificações agora se citam, e o gate confere uma contra a outra."""
    contract = _contract()
    workflow = _workflow(contract, "marketing-offer-crud")

    assert "shop.promotion" in workflow["admin_models"]
    assert workflow["frequency"] == "daily"
    assert _group_of(contract, "shop.promotion")["frequency"] == "rare"
    assert gate.validate_contract(contract) == []


def test_routine_model_cannot_also_be_routine_in_admin() -> None:
    contract = _contract()
    group = _group_of(contract, "shop.promotion")
    group["frequency"] = "daily"

    errors = gate.validate_contract(contract)

    assert any(
        "marketing-offer-crud" in error and "shop.promotion is routine on the surface" in error
        for error in errors
    ), errors


def test_routine_admin_group_needs_a_routine_workflow_that_declares_it() -> None:
    contract = _contract()
    group = _group_of(contract, "shop.ruleconfig")
    group["frequency"] = "daily"

    errors = gate.validate_contract(contract)

    assert any("shop.ruleconfig is routine in the Admin" in error for error in errors), errors


def test_workflow_admin_models_must_be_classified_and_claimed_once() -> None:
    contract = _contract()
    _workflow(contract, "catalog-crud")["admin_models"].append("shop.nao_existe")
    _workflow(contract, "customer-crud")["admin_models"].append("offerman.product")
    del _workflow(contract, "recipe-crud")["admin_models"]

    errors = gate.validate_contract(contract)

    assert "workflow 'catalog-crud': admin_models names an unclassified ModelAdmin 'shop.nao_existe'" in errors
    assert "ModelAdmin claimed by more than one workflow: offerman.product" in errors
    assert (
        "workflow 'recipe-crud': admin_models must be a list (empty when no ModelAdmin backs it)" in errors
    )


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
