from __future__ import annotations

import ast
import copy
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).with_name("fixtures") / "orchestrator_units"
SPEC = importlib.util.spec_from_file_location("check_orchestrator_units", ROOT / "scripts/check_orchestrator_units.py")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def _canonical():
    return (
        json.loads((ROOT / "docs/architecture/orchestrator-inventory.json").read_text()),
        json.loads((ROOT / "docs/architecture/orchestrator-units.json").read_text()),
    )


def _instance_debt():
    return json.loads((ROOT / "docs/architecture/orchestrator-instance-debt.json").read_text())


def _unit(manifests, unit_id):
    return next(unit for unit in manifests["units"] if unit["id"] == unit_id)


def test_canonical_inventory_is_valid():
    inventory, manifests = _canonical()
    counts = gate.validate(inventory, manifests, root=ROOT)
    expected_responsibilities = Counter(
        responsibility for source in inventory["sources"] for responsibility in source["responsibilities"]
    )
    assert counts["physical_responsibilities"] == expected_responsibilities
    assert counts["coverage"]["sources"] == len(inventory["sources"])
    assert counts["instance_debt"]["pending"] > 0


def test_policy_namespace_rejects_a_non_policy_unit():
    inventory, manifests = _canonical()
    unit = _unit(manifests, "promotion.minimum-order-eligibility")
    unit["policy"] = False

    with pytest.raises(gate.GateError) as caught:
        gate.validate(inventory, manifests, root=ROOT)

    assert caught.value.code == "policy-namespace"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [("stale", "instance-debt-stale"), ("untriaged", "instance-debt-untriaged")],
)
def test_instance_debt_negative_cases(mutation, expected):
    inventory, manifests = _canonical()
    debt = _instance_debt()
    if mutation == "stale":
        debt["findings"][0]["evidence"] = "evidence-that-does-not-exist"
    else:
        debt["findings"] = [
            finding for finding in debt["findings"] if finding["source"] != "shopman/shop/adapters/_sms.py"
        ]
    with pytest.raises(gate.GateError) as caught:
        gate.validate(inventory, manifests, root=ROOT, instance_debt=debt)
    assert caught.value.code == expected


def _qualified_test_fixture(tmp_path, test_body):
    source = tmp_path / "shopman/shop/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("def decide():\n    return True\n")
    test = tmp_path / "shopman/shop/tests/test_example.py"
    test.parent.mkdir(parents=True)
    test.write_text(test_body)
    unit = {
        "sources": [{"path": "shopman/shop/example.py", "symbols": ["decide"]}],
        "authoritative_symbols": ["shopman.shop.example:decide"],
    }
    return unit


def test_test_evidence_accepts_a_qualified_call(tmp_path):
    unit = _qualified_test_fixture(
        tmp_path,
        "from shopman.shop.example import decide\n\ndef test_decision():\n    assert decide()\n",
    )

    assert gate._test_references_unit("shopman/shop/tests/test_example.py::test_decision", unit, tmp_path)


def test_test_evidence_rejects_an_unqualified_homonym(tmp_path):
    unit = _qualified_test_fixture(
        tmp_path,
        "def decide():\n    return True\n\ndef test_decision():\n    assert decide()\n",
    )

    assert not gate._test_references_unit("shopman/shop/tests/test_example.py::test_decision", unit, tmp_path)


@pytest.mark.parametrize(
    "body",
    [
        "from shopman.shop.example import decide\n\ndef test_decision():\n    assert decide is not None\n",
        "import shopman.shop.example as example\n\ndef test_decision():\n    assert example.decide is not None\n",
    ],
)
def test_test_evidence_rejects_qualified_load_without_call(tmp_path, body):
    unit = _qualified_test_fixture(tmp_path, body)

    assert not gate._test_references_unit("shopman/shop/tests/test_example.py::test_decision", unit, tmp_path)


def test_test_evidence_rejects_called_helper_that_does_not_reach_authority(tmp_path):
    unit = _qualified_test_fixture(
        tmp_path,
        "from shopman.shop.example import helper\n\ndef test_decision():\n    assert helper() == 1\n",
    )
    source = tmp_path / "shopman/shop/example.py"
    source.write_text("def decide():\n    return True\n\ndef helper():\n    return 1\n")
    unit["sources"][0]["symbols"].append("helper")
    gate.collect_facts.cache_clear()

    assert not gate._test_references_unit("shopman/shop/tests/test_example.py::test_decision", unit, tmp_path)


@pytest.mark.parametrize(
    "body",
    [
        (
            "from shopman.shop.example import decide\n\n"
            "def test_decision():\n"
            "    if False:\n"
            "        decide()\n"
            "    assert True\n"
        ),
        (
            "import pytest\n"
            "from shopman.shop.example import decide\n\n"
            "def test_decision():\n"
            "    pytest.skip('not executed')\n"
            "    decide()\n"
        ),
        ("from shopman.shop.example import decide\n\ndef test_decision():\n    return\n    decide()\n"),
        ("from shopman.shop.example import decide\n\ndef test_decision():\n    raise RuntimeError\n    decide()\n"),
    ],
)
def test_test_evidence_rejects_calls_in_statically_unexecuted_flow(tmp_path, body):
    unit = _qualified_test_fixture(tmp_path, body)

    assert not gate._test_references_unit("shopman/shop/tests/test_example.py::test_decision", unit, tmp_path)


def test_test_evidence_does_not_treat_a_parameter_name_as_a_called_helper(tmp_path):
    unit = _qualified_test_fixture(
        tmp_path,
        "import pytest\n"
        "from shopman.shop.example import decide\n\n"
        "def authority_helper():\n"
        "    return decide()\n\n"
        "@pytest.mark.parametrize('authority_helper', [True])\n"
        "def test_decision(authority_helper):\n"
        "    assert authority_helper\n",
    )

    assert not gate._test_references_unit("shopman/shop/tests/test_example.py::test_decision", unit, tmp_path)


def test_test_reference_must_be_pytest_collectable_and_not_statically_skipped(tmp_path):
    _qualified_test_fixture(
        tmp_path,
        "import pytest\n"
        "from shopman.shop.example import decide\n\n"
        "def evidence_only():\n"
        "    assert decide()\n\n"
        "@pytest.mark.skip(reason='disabled')\n"
        "def test_disabled():\n"
        "    assert decide()\n\n"
        "class EvidenceClass:\n"
        "    def test_decision(self):\n"
        "        assert decide()\n\n"
        "class TestWithInit:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "    def test_decision(self):\n"
        "        assert decide()\n\n"
        "class LegacyTests(TestCase):\n"
        "    def test_decision(self):\n"
        "        assert decide()\n",
    )

    assert not gate._resolve_test("shopman/shop/tests/test_example.py::evidence_only", tmp_path)
    assert not gate._resolve_test("shopman/shop/tests/test_example.py::test_disabled", tmp_path)
    assert not gate._resolve_test("shopman/shop/tests/test_example.py::EvidenceClass::test_decision", tmp_path)
    assert not gate._resolve_test("shopman/shop/tests/test_example.py::TestWithInit::test_decision", tmp_path)
    assert gate._resolve_test("shopman/shop/tests/test_example.py::LegacyTests::test_decision", tmp_path)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (
            "shopman/shop/tests/evidence.py",
            "from shopman.shop.example import decide\n\ndef test_decision():\n    assert decide()\n",
        ),
        (
            "shopman/shop/tests/test_example.py",
            "import pytest\n"
            "from shopman.shop.example import decide\n"
            "pytestmark = pytest.mark.skip(reason='disabled module')\n\n"
            "def test_decision():\n    assert decide()\n",
        ),
    ],
)
def test_test_reference_rejects_non_collected_file_or_skipped_module(tmp_path, path, body):
    unit = _qualified_test_fixture(tmp_path, body)
    original = tmp_path / "shopman/shop/tests/test_example.py"
    target = tmp_path / path
    if target != original:
        original.replace(target)

    assert not gate._resolve_test(f"{path}::test_decision", tmp_path)
    assert not gate._test_references_unit(f"{path}::test_decision", unit, tmp_path)


def test_test_evidence_covers_multiple_authorities_collectively(tmp_path):
    source = tmp_path / "shopman/shop/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("def first():\n    return 1\n\ndef second():\n    return 2\n")
    test = tmp_path / "shopman/shop/tests/test_example.py"
    test.parent.mkdir(parents=True)
    test.write_text(
        "from shopman.shop.example import first, second\n\n"
        "def test_first():\n    assert first() == 1\n\n"
        "def test_second():\n    assert second() == 2\n"
    )
    unit = {
        "sources": [{"path": "shopman/shop/example.py", "symbols": ["first", "second"]}],
        "authoritative_symbols": ["shopman.shop.example:first", "shopman.shop.example:second"],
    }
    gate.collect_facts.cache_clear()

    first = gate._test_reached_authorities("shopman/shop/tests/test_example.py::test_first", unit, tmp_path)
    second = gate._test_reached_authorities("shopman/shop/tests/test_example.py::test_second", unit, tmp_path)

    assert first == {"shopman.shop.example:first"}
    assert second == {"shopman.shop.example:second"}
    assert first | second == set(unit["authoritative_symbols"])


def test_callgraph_ignores_an_uninvoked_nested_definition(tmp_path):
    source = tmp_path / "shopman/shop/example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def decide():\n    return True\n\n"
        "def entry():\n    def never_called():\n        return decide()\n    return False\n"
    )
    gate.collect_facts.cache_clear()
    facts = gate.collect_facts(tmp_path)

    assert not gate._reachable_symbols("shopman.shop.example:entry", {"shopman.shop.example:decide"}, facts)


def test_callgraph_follows_a_simple_callable_alias(tmp_path):
    source = tmp_path / "shopman/shop/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("def decide():\n    return True\n\ndef entry():\n    selected = decide\n    return selected()\n")
    gate.collect_facts.cache_clear()
    facts = gate.collect_facts(tmp_path)

    assert gate._reachable_symbols("shopman.shop.example:entry", {"shopman.shop.example:decide"}, facts) == {
        "shopman.shop.example:decide"
    }


def test_callgraph_follows_safe_super_call_to_a_local_base(tmp_path):
    source = tmp_path / "shopman/shop/example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "class Base:\n    def decide(self):\n        return True\n\n"
        "class Child(Base):\n    def entry(self):\n        return super().decide()\n"
    )
    gate.collect_facts.cache_clear()
    facts = gate.collect_facts(tmp_path)

    assert gate._reachable_symbols("shopman.shop.example:Child.entry", {"shopman.shop.example:Base.decide"}, facts) == {
        "shopman.shop.example:Base.decide"
    }


def test_policy_shape_distinguishes_composition_modifier_from_policy():
    modifier = ast.parse("class BasketModifier:\n    pass\n").body[0]
    policy = ast.parse("class PurchasePolicy:\n    pass\n").body[0]

    assert not gate._is_policy_shaped("shopman/shop/modifiers.py", "BasketModifier", modifier)
    assert gate._is_policy_shaped("shopman/shop/example.py", "PurchasePolicy", policy)


@pytest.mark.parametrize(
    ("symbol", "source"),
    [
        ("_require_credentials", "def _require_credentials(config: dict) -> tuple[str, str]:\n    return ('a', 'b')\n"),
        (
            "_free_by_eligible_quant",
            "def _free_by_eligible_quant() -> dict[int, int]:\n    return {1: 2}\n",
        ),
        ("_allowed_prefixes", "def _allowed_prefixes() -> list[str]:\n    return ['shopman.shop.rules.']\n"),
        (
            "_require_decimal_or_none",
            "def _require_decimal_or_none(value) -> Decimal | None:\n"
            "    if value == 'bad':\n"
            "        raise ValueError\n"
            "    parsed = Decimal(value)\n"
            "    return parsed\n",
        ),
        ("BaseRule", "class BaseRule:\n    code = ''\n"),
    ],
)
def test_decision_shape_keeps_typed_contract_support_outside_policy(symbol, source):
    node = ast.parse(source).body[0]

    assert not gate._is_decision_shaped("shopman/shop/example.py", symbol, node)


@pytest.mark.parametrize(
    ("symbol", "source"),
    [
        ("_requires_conversion", "def _requires_conversion(item) -> bool:\n    return item.unit == 'CX'\n"),
        ("check_allowed_hosts", "def check_allowed_hosts():\n    return ['unsafe']\n"),
        ("_required_keys", "def _required_keys():\n    return ('payment', 'timing')\n"),
        ("_require_isolated_runtime", "def _require_isolated_runtime() -> None:\n    raise RuntimeError\n"),
        ("_canonical_allowed_host", "def _canonical_allowed_host() -> str:\n    return 'localhost'\n"),
        ("ConfiguredRule", "class ConfiguredRule:\n    def evaluate(self):\n        return True\n"),
    ],
)
def test_decision_shape_still_detects_nearby_behavioral_decisions(symbol, source):
    node = ast.parse(source).body[0]

    assert gate._is_decision_shaped("shopman/shop/example.py", symbol, node)


@pytest.mark.parametrize(
    ("path", "symbol", "source"),
    [
        (
            "shopman/shop/projections/risk.py",
            "FraudPolicy",
            "class FraudPolicy:\n    def allows(self):\n        return False\n",
        ),
        (
            "shopman/shop/example.py",
            "allowed_channels",
            "def allowed_channels(order) -> list[str]:\n    return ['web'] if order.paid else []\n",
        ),
        (
            "shopman/shop/example.py",
            "_require_approval",
            "def _require_approval(order) -> Approval:\n"
            "    return Approval.YES if order.total > 100 else Approval.NO\n",
        ),
    ],
)
def test_decision_shape_does_not_fail_open_by_path_or_return_annotation(path, symbol, source):
    assert gate._is_decision_shaped(path, symbol, ast.parse(source).body[0])


def test_class_decision_members_distinguish_policy_from_immutable_accessor():
    limiter = ast.parse(
        "class ProbeRateLimiter:\n"
        "    def allow(self, key):\n"
        "        if key == 'blocked':\n"
        "            return False\n"
        "        return True\n"
    ).body[0]
    claim = ast.parse(
        "@dataclass(frozen=True)\n"
        "class WebhookClaim:\n"
        "    replayed: bool\n"
        "    in_progress: bool\n"
        "    @property\n"
        "    def can_process(self):\n"
        "        return not self.replayed and not self.in_progress\n"
    ).body[0]
    eligibility = ast.parse(
        "@dataclass(frozen=True)\n"
        "class Eligibility:\n"
        "    age: int\n"
        "    @property\n"
        "    def eligible(self):\n"
        "        return self.age >= 18\n"
    ).body[0]

    limiter_members = gate._decision_nodes("ProbeRateLimiter", limiter)
    claim_members = gate._decision_nodes("WebhookClaim", claim)
    eligibility_members = gate._decision_nodes("Eligibility", eligibility)

    assert any(
        name == "ProbeRateLimiter.allow" and gate._is_decision_shaped("example.py", name.rpartition(".")[2], node)
        for name, node in limiter_members
    )
    assert [name for name, _node in claim_members] == ["WebhookClaim"]
    assert any(name == "Eligibility.eligible" for name, _node in eligibility_members)


@pytest.mark.parametrize("owner", ["pricing.customer-groups", "fulfillment.order_flow"])
def test_owner_accepts_a_readable_capability_id(owner):
    assert gate._is_capability_owner(owner)


@pytest.mark.parametrize(
    "owner",
    ["x", "module", "shopman.shop.pricing", "shopman.payman.service", "Pricing.customer"],
)
def test_owner_rejects_generic_or_source_shaped_names(owner):
    assert not gate._is_capability_owner(owner)


def _hermetic_gate_case(tmp_path, *, symbol="decide", source_body=None, responsibility="decisão"):
    schema_source = ROOT / "docs/architecture/orchestrator-unit.schema.json"
    schema_target = tmp_path / "docs/architecture/orchestrator-unit.schema.json"
    schema_target.parent.mkdir(parents=True)
    schema_target.write_text(schema_source.read_text())
    source = tmp_path / "shopman/shop/example.py"
    source.parent.mkdir(parents=True)
    source.write_text(source_body or f"def {symbol}():\n    return True\n")
    test = tmp_path / "shopman/shop/tests/test_example.py"
    test.parent.mkdir(parents=True)
    test.write_text(f"from shopman.shop.example import {symbol}\n\ndef test_decision():\n    assert {symbol}()\n")
    unit_id = "example.decision"
    inventory = {
        "schema_version": 1,
        "sources": [
            {
                "path": "shopman/shop/example.py",
                "responsibilities": [responsibility],
                "support_claims": [],
                "touchpoints": ["outro"],
                "out_of_extraction": responsibility == "leitura",
                "unit_ids": [unit_id],
            }
        ],
    }
    manifests = {
        "schema_version": 1,
        "units": [
            {
                "id": unit_id,
                "question": "Qual comportamento canônico este exemplo oferece?",
                "owner": "example.decision",
                "responsibility": responsibility,
                "public_entrypoint": f"shopman.shop.example:{symbol}",
                "authoritative_symbols": [f"shopman.shop.example:{symbol}"],
                "entrypoint_kind": "symbol",
                "sources": [{"path": "shopman/shop/example.py", "symbols": [symbol]}],
                "touchpoints": ["outro"],
                "domains": [],
                "ports": [],
                "events": [],
                "directives": [],
                "config_surface": [],
                "tests": ["shopman/shop/tests/test_example.py::test_decision"],
                "test_gap_reason": None,
                "policy": False,
                "out_of_extraction": responsibility == "leitura",
            }
        ],
    }
    return inventory, manifests


def _validate_hermetic(tmp_path, inventory, manifests):
    gate.collect_facts.cache_clear()
    return gate.validate(
        inventory,
        manifests,
        root=tmp_path,
        instance_debt={"schema_version": 1, "findings": []},
    )


def _hermetic_negative_case(tmp_path, case):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    source = tmp_path / "shopman/shop/example.py"
    test = tmp_path / "shopman/shop/tests/test_example.py"
    unit = manifests["units"][0]

    def add_second_unit():
        other_source = tmp_path / "shopman/shop/other.py"
        other_source.write_text("def other():\n    return True\n")
        other_test = tmp_path / "shopman/shop/tests/test_other.py"
        other_test.write_text("from shopman.shop.other import other\n\ndef test_other():\n    assert other()\n")
        inventory["sources"].append(
            {
                "path": "shopman/shop/other.py",
                "responsibilities": ["decisão"],
                "support_claims": [],
                "touchpoints": ["outro"],
                "out_of_extraction": False,
                "unit_ids": ["example.other"],
            }
        )
        other = copy.deepcopy(unit)
        other.update(
            id="example.other",
            question="Qual outro comportamento canônico este exemplo oferece?",
            owner="example.other",
            public_entrypoint="shopman.shop.other:other",
            authoritative_symbols=["shopman.shop.other:other"],
            sources=[{"path": "shopman/shop/other.py", "symbols": ["other"]}],
            tests=["shopman/shop/tests/test_other.py::test_other"],
        )
        manifests["units"].append(other)
        return other

    def boundary_source(body, **declared):
        source.write_text(body)
        for field in ("domains", "ports", "events", "directives", "config_surface"):
            unit[field] = declared.get(field, [])

    if case == "schema":
        unit.pop("question")
    elif case == "duplicate-source":
        inventory["sources"].append(copy.deepcopy(inventory["sources"][0]))
    elif case == "coverage":
        inventory["sources"].clear()
    elif case in {"duplicate-question", "duplicate-entrypoint"}:
        other = add_second_unit()
        if case == "duplicate-question":
            other["question"] = unit["question"]
        else:
            other["public_entrypoint"] = unit["public_entrypoint"]
    elif case == "source-orphan":
        unit["sources"][0]["path"] = "shopman/shop/missing.py"
    elif case == "manifest-orphan":
        inventory["sources"][0]["unit_ids"] = []
    elif case == "manifest-missing":
        inventory["sources"][0]["unit_ids"].append("example.missing")
    elif case == "symbol-unresolved":
        unit["sources"][0]["symbols"].append("missing")
    elif case == "symbol-overlap":
        other = add_second_unit()
        other["sources"] = [{"path": "shopman/shop/example.py", "symbols": ["decide"]}]
    elif case in {"local-import-domain-drift", "event-drift", "directive-drift", "config-drift"}:
        boundary_source(
            "def decide():\n"
            "    from django.conf import settings\n"
            "    from shopman.stockman.directives import RESERVE\n"
            "    from shopman.stockman.protocols.inventory import InventoryPort\n"
            "    from shopman.stockman.signals import changed\n"
            "    return InventoryPort, changed, RESERVE, settings.SHOPMAN_EXAMPLE\n",
            domains=["stockman"],
            ports=["shopman.stockman.protocols.inventory"],
            events=["changed"],
            directives=["RESERVE"],
            config_surface=["SHOPMAN_EXAMPLE"],
        )
        field = {
            "local-import-domain-drift": "domains",
            "event-drift": "events",
            "directive-drift": "directives",
            "config-drift": "config_surface",
        }[case]
        unit[field] = []
    elif case == "adapter-port-drift":
        boundary_source(
            "from shopman.shop.adapters import get_adapter\n\ndef decide():\n    return get_adapter('stock')\n",
            ports=["adapter:stock"],
        )
        unit["ports"] = []
    elif case == "test-unresolved":
        unit["tests"] = ["shopman/shop/tests/missing.py::test_missing"]
    elif case == "policy-without-manifest":
        source.write_text("class PurchasePolicy:\n    pass\n")
        test.write_text(
            "from shopman.shop.example import PurchasePolicy\n\ndef test_decision():\n    assert PurchasePolicy()\n"
        )
        unit.update(
            public_entrypoint="shopman.shop.example:PurchasePolicy",
            authoritative_symbols=["shopman.shop.example:PurchasePolicy"],
            sources=[{"path": "shopman/shop/example.py", "symbols": ["PurchasePolicy"]}],
            policy=False,
        )
    elif case == "touchpoint-drift":
        inventory["sources"][0]["touchpoints"] = ["service"]
    elif case == "semantic-unit-missing":
        inventory["sources"][0]["unit_ids"] = []
        manifests["units"] = []
    elif case == "entrypoint-unresolved":
        unit["public_entrypoint"] = "shopman.shop.example:missing"
    elif case == "entrypoint-outside-unit":
        source.write_text("def decide():\n    return helper()\n\ndef helper():\n    return True\n")
        inventory["sources"][0].update(
            responsibilities=["decisão", "infraestrutura"],
            support_claims=[{"responsibility": "infraestrutura", "symbols": ["decide"]}],
        )
        unit.update(
            authoritative_symbols=["shopman.shop.example:helper"],
            sources=[{"path": "shopman/shop/example.py", "symbols": ["helper"]}],
        )
        test.write_text("from shopman.shop.example import helper\n\ndef test_decision():\n    assert helper()\n")
    elif case == "entrypoint-kind":
        unit["entrypoint_kind"] = "module"
    elif case == "entrypoint-private":
        source.write_text("def _decide():\n    return True\n")
        test.write_text("from shopman.shop.example import _decide\n\ndef test_decision():\n    assert _decide()\n")
        unit.update(
            public_entrypoint="shopman.shop.example:_decide",
            authoritative_symbols=["shopman.shop.example:_decide"],
            sources=[{"path": "shopman/shop/example.py", "symbols": ["_decide"]}],
        )
    elif case == "authority-not-reachable":
        source.write_text("def decide():\n    return True\n\ndef helper():\n    return True\n")
        unit["sources"][0]["symbols"] = ["decide", "helper"]
        unit["authoritative_symbols"] = ["shopman.shop.example:helper"]
        test.write_text("from shopman.shop.example import helper\n\ndef test_decision():\n    assert helper()\n")
    elif case == "authority-outside-unit":
        source.write_text("def decide():\n    return helper()\n\ndef helper():\n    return True\n")
        inventory["sources"][0].update(
            responsibilities=["decisão", "infraestrutura"],
            support_claims=[{"responsibility": "infraestrutura", "symbols": ["helper"]}],
        )
        unit["authoritative_symbols"] = ["shopman.shop.example:helper"]
    elif case == "authority-unresolved":
        unit["authoritative_symbols"] = ["shopman.shop.example:missing"]
    elif case == "owner-not-capability":
        unit["owner"] = "shopman.shop.example"
    elif case == "inventory-drift":
        add_second_unit()
        inventory["sources"][0]["unit_ids"].append("example.other")
        inventory["sources"][0]["unit_ids"].sort()
    elif case == "read-side":
        inventory["sources"][0]["out_of_extraction"] = True
    elif case == "semantic-read-side":
        unit["out_of_extraction"] = True
    elif case == "symbol-coverage":
        source.write_text("def decide():\n    return True\n\ndef helper():\n    return True\n")
    elif case == "test-unrelated":
        test.write_text("def test_decision():\n    assert True\n")
    elif case == "test-gap":
        unit["tests"] = []
    elif case == "additional-property":
        unit["legacy"] = True
    else:
        raise AssertionError(f"unknown fixture mutation: {case}")
    return inventory, manifests


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.json")), ids=lambda path: path.stem)
def test_negative_fixture_fails_with_its_specific_code(tmp_path, fixture):
    definition = json.loads(fixture.read_text())
    inventory, manifests = _hermetic_negative_case(tmp_path, definition["mutation"])
    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)
    assert caught.value.code == definition["expected_code"]


def _hermetic_empty_source_case(tmp_path, *, path="shopman/shop/empty.py", responsibility="infraestrutura"):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    original = tmp_path / "shopman/shop/example.py"
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    original.replace(target)
    target.write_text('"""Intentional namespace with no executable symbols."""\n')
    inventory["sources"][0].update(
        path=path,
        responsibilities=[responsibility],
        support_claims=[{"responsibility": responsibility, "symbols": []}],
        touchpoints=["projection"] if "projections" in Path(path).parts else ["outro"],
        unit_ids=[],
        out_of_extraction=responsibility == "leitura",
    )
    manifests["units"] = []
    return inventory, manifests


@pytest.mark.parametrize(
    ("path", "responsibility"),
    [
        ("shopman/shop/empty.py", "infraestrutura"),
        ("shopman/shop/projections/__init__.py", "leitura"),
    ],
)
def test_validate_accepts_one_empty_support_claim_for_an_empty_source(tmp_path, path, responsibility):
    inventory, manifests = _hermetic_empty_source_case(
        tmp_path,
        path=path,
        responsibility=responsibility,
    )

    counts = _validate_hermetic(tmp_path, inventory, manifests)

    assert counts["coverage"]["sources"] == 1
    assert counts["physical_responsibilities"] == {responsibility: 1}


def test_validate_rejects_an_empty_support_claim_when_the_source_has_a_symbol(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    inventory["sources"][0].update(
        responsibilities=["infraestrutura"],
        support_claims=[{"responsibility": "infraestrutura", "symbols": []}],
        unit_ids=[],
    )
    manifests["units"] = []

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "support-symbol"


def test_validate_rejects_multiple_empty_support_claims_for_an_empty_source(tmp_path):
    inventory, manifests = _hermetic_empty_source_case(tmp_path)
    inventory["sources"][0].update(
        responsibilities=["contrato", "infraestrutura"],
        support_claims=[
            {"responsibility": "contrato", "symbols": []},
            {"responsibility": "infraestrutura", "symbols": []},
        ],
    )

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "support-symbol"


def test_validate_rejects_units_on_an_empty_source(tmp_path):
    inventory, manifests = _hermetic_empty_source_case(tmp_path)
    inventory["sources"][0]["unit_ids"] = ["imaginary.unit"]

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "support-symbol"


def test_inventory_top_level_is_fail_closed(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    inventory["legacy"] = True

    with pytest.raises(gate.GateError, match="inventory top level") as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "schema"


def test_inventory_source_shape_is_checked_before_coverage(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    inventory["sources"] = [[]]

    with pytest.raises(gate.GateError, match="canonical shape") as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "schema"


def test_validate_rejects_a_non_capability_owner(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    manifests["units"][0]["owner"] = "shopman.payman.service"

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "owner-not-capability"


def test_validate_accepts_a_composition_modifier(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        symbol="BasketModifier",
        source_body="class BasketModifier:\n    pass\n",
        responsibility="composição",
    )

    assert _validate_hermetic(tmp_path, inventory, manifests)["responsibilities"] == {"composição": 1}


def test_validate_rejects_policy_shaped_symbol_in_non_policy_unit(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        symbol="PurchasePolicy",
        source_body="class PurchasePolicy:\n    pass\n",
    )

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "policy-without-manifest"


def test_validate_requires_collective_test_coverage_of_all_authorities(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        symbol="entry",
        source_body=(
            "def first():\n    return True\n\n"
            "def second():\n    return True\n\n"
            "def entry():\n    return first() and second()\n"
        ),
    )
    source_claim = manifests["units"][0]["sources"][0]
    source_claim["symbols"] = ["entry", "first", "second"]
    manifests["units"][0]["authoritative_symbols"] = [
        "shopman.shop.example:first",
        "shopman.shop.example:second",
    ]
    test = tmp_path / "shopman/shop/tests/test_example.py"
    test.write_text(
        "from shopman.shop.example import first, second\n\n"
        "def test_first():\n    assert first()\n\n"
        "def test_second():\n    assert second()\n"
    )
    manifests["units"][0]["tests"] = ["shopman/shop/tests/test_example.py::test_first"]

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "test-authority-coverage"

    manifests["units"][0]["tests"].append("shopman/shop/tests/test_example.py::test_second")
    assert _validate_hermetic(tmp_path, inventory, manifests)["responsibilities"] == {"decisão": 1}


def test_validate_rejects_decision_hidden_in_support(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        symbol="should_allow",
        source_body="def should_allow():\n    return True\n",
    )
    inventory["sources"][0].update(
        responsibilities=["contrato"],
        support_claims=[{"responsibility": "contrato", "symbols": ["should_allow"]}],
        unit_ids=[],
    )
    manifests["units"] = []

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "decision-hidden-in-support"


def test_validate_rejects_decision_method_hidden_in_support(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        symbol="AdmissionGate",
        source_body=("class AdmissionGate:\n    def allow(self, key):\n        return key != 'blocked'\n"),
    )
    inventory["sources"][0].update(
        responsibilities=["infraestrutura"],
        support_claims=[{"responsibility": "infraestrutura", "symbols": ["AdmissionGate"]}],
        unit_ids=[],
    )
    manifests["units"] = []

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "decision-hidden-in-support"


def test_validate_accepts_immutable_derived_property_as_support(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        symbol="WebhookClaim",
        source_body=(
            "from dataclasses import dataclass\n\n"
            "@dataclass(frozen=True)\n"
            "class WebhookClaim:\n"
            "    replayed: bool\n"
            "    in_progress: bool\n"
            "    @property\n"
            "    def can_process(self):\n"
            "        return not self.replayed and not self.in_progress\n"
        ),
    )
    inventory["sources"][0].update(
        responsibilities=["infraestrutura"],
        support_claims=[{"responsibility": "infraestrutura", "symbols": ["WebhookClaim"]}],
        unit_ids=[],
    )
    manifests["units"] = []

    assert _validate_hermetic(tmp_path, inventory, manifests)["coverage"]["semantic_units"] == 0


def test_validate_requires_decision_responsibility_for_decision_shaped_symbol(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        symbol="should_allow",
        source_body="def should_allow():\n    return True\n",
        responsibility="composição",
    )

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "decision-responsibility"


def test_validate_observes_transitive_boundary_in_called_support_helper(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        source_body=(
            "def decide():\n    return _helper()\n\n"
            "def _helper():\n"
            "    from shopman.stockman.protocols.inventory import InventoryPort\n"
            "    def never_called():\n"
            "        from shopman.payman.protocols.payments import PaymentPort\n"
            "        return PaymentPort\n"
            "    return InventoryPort\n"
        ),
    )
    inventory["sources"][0].update(
        responsibilities=["decisão", "infraestrutura"],
        support_claims=[{"responsibility": "infraestrutura", "symbols": ["_helper"]}],
    )

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "domain-drift"
    manifests["units"][0]["domains"] = ["stockman"]
    manifests["units"][0]["ports"] = ["shopman.stockman.protocols.inventory"]
    assert _validate_hermetic(tmp_path, inventory, manifests)["responsibilities"] == {"decisão": 1}


def test_validate_observes_transitive_boundary_in_inter_module_support_helper(tmp_path):
    inventory, manifests = _hermetic_gate_case(
        tmp_path,
        source_body="from shopman.shop import helper\n\ndef decide():\n    return helper.load()\n",
    )
    helper = tmp_path / "shopman/shop/helper.py"
    helper.write_text(
        "def load():\n    from shopman.stockman.protocols.inventory import InventoryPort\n    return InventoryPort\n"
    )
    inventory["sources"].append(
        {
            "path": "shopman/shop/helper.py",
            "responsibilities": ["infraestrutura"],
            "support_claims": [{"responsibility": "infraestrutura", "symbols": ["load"]}],
            "touchpoints": ["outro"],
            "out_of_extraction": False,
            "unit_ids": [],
        }
    )

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "domain-drift"
    manifests["units"][0]["domains"] = ["stockman"]
    manifests["units"][0]["ports"] = ["shopman.stockman.protocols.inventory"]
    assert _validate_hermetic(tmp_path, inventory, manifests)["responsibilities"] == {"decisão": 1}


def test_validate_rejects_semantic_touchpoint_drift(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    manifests["units"][0]["touchpoints"] = ["adapter"]

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "semantic-touchpoint-drift"


def test_validate_rejects_duplicate_unit_id(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    manifests["units"].append(copy.deepcopy(manifests["units"][0]))

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "duplicate-id"


def test_validate_rejects_policy_with_composition_responsibility(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path, responsibility="composição")
    manifests["units"][0]["policy"] = True

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "policy-responsibility"


def test_validate_rejects_synthetic_question(tmp_path):
    inventory, manifests = _hermetic_gate_case(tmp_path)
    manifests["units"][0]["question"] = "Qual unidade realiza: exemplo?"

    with pytest.raises(gate.GateError) as caught:
        _validate_hermetic(tmp_path, inventory, manifests)

    assert caught.value.code == "synthetic-question"
