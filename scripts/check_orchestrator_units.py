#!/usr/bin/env python3
"""Validate the reviewed Shop orchestrator inventory without importing Django."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHOP_ROOT = ROOT / "shopman" / "shop"
INVENTORY_PATH = ROOT / "docs" / "architecture" / "orchestrator-inventory.json"
MANIFEST_PATH = ROOT / "docs" / "architecture" / "orchestrator-units.json"
SCHEMA_PATH = ROOT / "docs" / "architecture" / "orchestrator-unit.schema.json"
INSTANCE_DEBT_PATH = ROOT / "docs" / "architecture" / "orchestrator-instance-debt.json"

RESPONSIBILITIES = {
    "decisão",
    "composição",
    "leitura",
    "contrato",
    "configuração",
    "infraestrutura",
}
TOUCHPOINTS = {
    "service",
    "adapter",
    "handler",
    "projection",
    "API",
    "admin",
    "model",
    "lifecycle",
    "middleware",
    "outro",
}
KERNELS = {
    "buyman",
    "cashman",
    "craftsman",
    "doorman",
    "fiscalman",
    "guestman",
    "offerman",
    "orderman",
    "payman",
    "stockman",
}
POLICY_SUFFIXES = ("Policy", "Rule")
CAPABILITY_OWNER = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*)+")
DECISION_NAME = re.compile(
    r"(^_?(?:should|requires?|can_|allows?|allowed|eligible|is_eligible))"
    r"|(?:^|_)(?:policy|refusal|allowed|eligible|required)(?:_|$)",
    re.I,
)


@dataclass(frozen=True)
class SourceFacts:
    path: str
    module: str
    tree: ast.Module
    doc: str
    symbols: tuple[str, ...]
    public_symbols: tuple[str, ...]
    imports: tuple[str, ...]
    domains: tuple[str, ...]
    ports: tuple[str, ...]
    config_surface: tuple[str, ...]


def _defined_names(tree: ast.Module) -> tuple[str, ...]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in {"__all__"}:
                    names.append(target.id)
    return tuple(dict.fromkeys(names))


class GateError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise GateError(code, message)


def production_sources(root: Path = ROOT) -> list[Path]:
    shop_root = root / "shopman" / "shop"
    return sorted(
        path
        for path in shop_root.rglob("*.py")
        if "tests" not in path.parts and "migrations" not in path.parts and "__pycache__" not in path.parts
    )


def _absolute_imports(tree: ast.AST) -> tuple[str, ...]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            result.add(node.module)
    return tuple(sorted(result))


def _facts(path: Path, root: Path = ROOT) -> SourceFacts:
    rel = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(), filename=rel)
    module = ".".join(path.relative_to(root).with_suffix("").parts)
    definitions = _defined_names(tree)
    imports = _absolute_imports(tree)
    domains = tuple(
        sorted(
            {
                parts[1]
                for item in imports
                if (parts := item.split(".")) and len(parts) >= 2 and parts[0] == "shopman" and parts[1] in KERNELS
            }
        )
    )
    ports = tuple(
        sorted(
            item
            for item in imports
            if any(
                item == f"shopman.{domain}.{boundary}" or item.startswith(f"shopman.{domain}.{boundary}.")
                for domain in KERNELS
                for boundary in ("protocols", "contracts", "adapters")
            )
        )
    )
    strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    config_surface = tuple(sorted(value for value in strings if value.startswith("SHOPMAN_")))
    return SourceFacts(
        path=rel,
        module=module,
        tree=tree,
        doc=(ast.get_docstring(tree) or "").strip(),
        symbols=definitions,
        public_symbols=tuple(name for name in definitions if not name.startswith("_")),
        imports=imports,
        domains=domains,
        ports=ports,
        config_surface=config_surface,
    )


def _definition_nodes(facts: SourceFacts) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in facts.tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in facts.symbols:
                    result[target.id] = node
    return result


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _terminates_runtime_block(node: ast.stmt) -> bool:
    if isinstance(node, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
        return True
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and _dotted_name(node.value.func) in {"pytest.skip", "pytest.xfail"}
    )


def _always_terminates(node: ast.stmt) -> bool:
    if _terminates_runtime_block(node):
        return True
    if isinstance(node, ast.If):
        if isinstance(node.test, ast.Constant):
            selected = node.body if bool(node.test.value) else node.orelse
            return bool(selected) and _always_terminates(selected[-1])
        return (
            bool(node.body and node.orelse)
            and _always_terminates(node.body[-1])
            and _always_terminates(node.orelse[-1])
        )
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return bool(node.body) and _always_terminates(node.body[-1])
    return False


def _runtime_walk(node: ast.AST):
    """Walk potentially executed syntax, excluding dead/deferred branches."""

    deferred = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)

    def walk_block(statements: list[ast.stmt]):
        for statement in statements:
            yield from walk_node(statement)
            if _always_terminates(statement):
                break

    def walk_node(current: ast.AST):
        yield current
        if isinstance(current, deferred):
            return
        if isinstance(current, ast.If) and isinstance(current.test, ast.Constant):
            yield from walk_node(current.test)
            branch = current.body if bool(current.test.value) else current.orelse
            yield from walk_block(branch)
            return
        for _field, value in ast.iter_fields(current):
            if isinstance(value, ast.AST):
                yield from walk_node(value)
            elif isinstance(value, list):
                children = [child for child in value if isinstance(child, ast.AST)]
                if children and all(isinstance(child, ast.stmt) for child in children):
                    yield from walk_block(children)
                else:
                    for child in children:
                        yield from walk_node(child)

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from walk_block(node.body)
    else:
        for child in ast.iter_child_nodes(node):
            yield from walk_node(child)


def _import_bindings(facts: SourceFacts) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in facts.tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                result[alias.asname or alias.name] = node.module
    return result


def _expanded_observation_symbols(
    facts: SourceFacts,
    symbols: list[str],
    facts_by_path: dict[str, SourceFacts] | None = None,
    helper_symbols: set[str] | None = None,
) -> set[str]:
    nodes = _definition_nodes(facts)
    observed_symbols = set(symbols)
    if symbols and facts_by_path is not None:
        facts_by_module = {item.module: item for item in facts_by_path.values()}
        pending = list(symbols)
        while pending:
            symbol = pending.pop()
            for dependency in _qualified_dependencies(facts, symbol, facts_by_module):
                module, separator, target = dependency.partition(":")
                target_root = target.partition(".")[0]
                if (
                    separator
                    and module == facts.module
                    and target_root in nodes
                    and target_root not in observed_symbols
                    and helper_symbols is not None
                    and target_root in helper_symbols
                ):
                    observed_symbols.add(target_root)
                    pending.append(target_root)
    return observed_symbols


def _observation_walk(node: ast.AST):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from _runtime_walk(node)
        return
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            yield child
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from _runtime_walk(child)
            elif not isinstance(child, ast.ClassDef):
                yield from ast.walk(child)
        return
    yield from ast.walk(node)


def _scoped_observations(
    facts: SourceFacts,
    symbols: list[str],
    facts_by_path: dict[str, SourceFacts] | None = None,
    helper_symbols: set[str] | None = None,
    support_references: set[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    nodes = _definition_nodes(facts)
    bindings = _import_bindings(facts)
    observed_symbols = _expanded_observation_symbols(facts, symbols, facts_by_path, helper_symbols)
    selected = [nodes[name] for name in observed_symbols if name in nodes]
    if not selected:
        used_imports = set(facts.imports)
        walked: list[ast.AST] = [facts.tree]
    else:
        loaded = {
            node.id
            for selected_node in selected
            for node in _observation_walk(selected_node)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        used_imports = {module for name, module in bindings.items() if name in loaded}
        walked = selected
    # Imports inside functions and methods are part of that semantic unit too.
    # Looking only at module bindings made cross-kernel calls disappear from the
    # gate precisely where import cycles had forced a local import.
    for selected_node in walked:
        for node in _observation_walk(selected_node):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    used_imports.add(alias.name)
                    bindings[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                used_imports.add(node.module)
                for alias in node.names:
                    bindings[alias.asname or alias.name] = node.module
    domains = {
        parts[1]
        for item in used_imports
        if (parts := item.split(".")) and len(parts) >= 2 and parts[0] == "shopman" and parts[1] in KERNELS
    }
    ports = {
        item
        for item in used_imports
        if any(
            item == f"shopman.{domain}.{boundary}" or item.startswith(f"shopman.{domain}.{boundary}.")
            for domain in KERNELS
            for boundary in ("protocols", "contracts", "adapters")
        )
    }
    # Shop adapters are runtime seams even though they are selected by a
    # registry rather than imported from a kernel ``protocols`` package.
    for selected_node in walked:
        for node in _observation_walk(selected_node):
            if not isinstance(node, ast.Call):
                continue
            callable_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if callable_name != "get_adapter":
                continue
            adapter_origin = bindings.get("get_adapter")
            if (
                adapter_origin == "shopman.shop.adapters"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                ports.add(f"adapter:{node.args[0].value}")
            elif adapter_origin:
                ports.add(f"{adapter_origin}:get_adapter")
    strings = {
        node.value
        for selected_node in walked
        for node in _observation_walk(selected_node)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    config_surface = {value for value in strings if value.startswith("SHOPMAN_")}
    # Configuration is not limited to SHOPMAN_* string literals.  Django's
    # canonical settings seam is also used through ``settings.NAME`` and
    # ``getattr(settings, "NAME", default)``; both forms must participate in
    # symbol-scoped drift detection, including imports local to the function.
    if bindings.get("settings") == "django.conf":
        for selected_node in walked:
            for node in _observation_walk(selected_node):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "settings"
                    and node.attr.isupper()
                ):
                    config_surface.add(node.attr)
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "settings"
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                    and node.args[1].value.isupper()
                ):
                    config_surface.add(node.args[1].value)
    event_aliases = {
        name: module for name, module in bindings.items() if module.endswith(".signals") or ".signals." in module
    }
    directive_aliases = {
        name: module
        for name, module in bindings.items()
        if name.isupper() and (module.endswith(".directives") or ".directives." in module)
    }
    local_directive_names: set[str] = set()
    module_definitions = _definition_nodes(facts)
    for selected_node in walked:
        for node in _observation_walk(selected_node):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if not any(isinstance(target, ast.Name) and target.id == "topic" for target in targets):
                continue
            if isinstance(value, ast.Name) and value.id in module_definitions:
                definition = module_definitions[value.id]
                if (
                    isinstance(definition, (ast.Assign, ast.AnnAssign))
                    and isinstance(definition.value, ast.Constant)
                    and isinstance(definition.value.value, str)
                ):
                    local_directive_names.add(value.id)
    loaded_names = {
        node.id
        for selected_node in walked
        for node in _observation_walk(selected_node)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    result = {
        "domains": tuple(sorted(domains)),
        "ports": tuple(sorted(ports)),
        "events": tuple(sorted(name for name in event_aliases if name in loaded_names)),
        "directives": tuple(
            sorted({name for name in directive_aliases if name in loaded_names} | local_directive_names)
        ),
        "config_surface": tuple(sorted(config_surface)),
    }
    if facts_by_path is None or support_references is None:
        return result

    # A semantic entrypoint may delegate mechanical work to support living in
    # another Shop module.  Those helpers are part of the unit's observable
    # boundary, but another semantic unit is not: ownership is the traversal
    # stop.  Same-module support was already expanded above.
    facts_by_module = {item.module: item for item in facts_by_path.values()}
    pending = [
        dependency
        for symbol in observed_symbols
        for dependency in _qualified_dependencies(facts, symbol, facts_by_module)
    ]
    seen: set[str] = set()
    while pending:
        reference = pending.pop()
        if reference in seen:
            continue
        seen.add(reference)
        module, separator, symbol = reference.partition(":")
        root_reference = f"{module}:{symbol.partition('.')[0]}"
        if not separator or root_reference not in support_references or module == facts.module:
            continue
        target_facts = facts_by_module.get(module)
        if target_facts is None or _resolve_symbol_node(target_facts, symbol) is None:
            continue
        observed = _scoped_observations(target_facts, [symbol])
        for key, values in observed.items():
            result[key] = tuple(sorted(set(result[key]) | set(values)))
        pending.extend(_qualified_dependencies(target_facts, symbol, facts_by_module) - seen)
    return result


@lru_cache(maxsize=4)
def collect_facts(root: Path = ROOT) -> dict[str, SourceFacts]:
    result: dict[str, SourceFacts] = {}
    for path in production_sources(root):
        facts = _facts(path, root)
        result[facts.path] = facts
    return result


def _runtime_strings(tree: ast.Module) -> set[str]:
    """String literals that execute; comments and every Python docstring are excluded."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    }


HHMM_RE = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d$")
RGB_CHANNELS_RE = re.compile(r"^\d{1,3} \d{1,3} \d{1,3}$")
#: A palette is a mapping of at least this many 'R G B' strings.
PALETTE_MIN_ENTRIES = 5


def _literal_strings(node: ast.AST) -> list[str]:
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _structural_instance_defaults(tree: ast.Module) -> set[str]:
    """Names that carry an instance's policy as code, without naming the instance.

    - ``DEFAULT_*`` (module or class level) that IS a clock time (``"17:30"``) or a
      mapping of clock times, or a ``*_PARAMS`` mapping: a house's window or rule
      params frozen as product code. A clock nested in records (a list of slots)
      is a catalog default, not a policy constant, and is not matched here;
    - ``params.get("<key>", DEFAULT_*)``: a rule param silently completed by code;
    - a module-level mapping of ``'R G B'`` strings: a brand palette.
    """
    found: set[str] = set()
    scopes: list[list[ast.stmt]] = [tree.body]
    scopes.extend(node.body for node in tree.body if isinstance(node, ast.ClassDef))
    for body in scopes:
        for node in body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            strings = _literal_strings(node.value)
            direct = [node.value] if not isinstance(node.value, ast.Dict) else list(node.value.values)
            clocks = [
                value.value
                for value in direct
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and HHMM_RE.match(value.value)
            ]
            for name in names:
                bare = name.lstrip("_")
                if bare.startswith("DEFAULT_") and (bare.endswith("_PARAMS") or clocks):
                    found.add(name)
                if (
                    body is tree.body
                    and isinstance(node.value, ast.Dict)
                    and sum(bool(RGB_CHANNELS_RE.match(value)) for value in strings) >= PALETTE_MIN_ENTRIES
                ):
                    found.add(name)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "params"
            and len(node.args) == 2
            and isinstance(node.args[1], ast.Name)
            and node.args[1].id.lstrip("_").startswith("DEFAULT_")
        ):
            found.add(node.args[1].id)
    return found


def _derived_touchpoints(facts: SourceFacts) -> set[str]:
    parts = Path(facts.path).parts
    points = {
        value
        for directory, value in {
            "services": "service",
            "adapters": "adapter",
            "handlers": "handler",
            "projections": "projection",
            "admin": "admin",
            "models": "model",
        }.items()
        if directory in parts
    }
    filename = parts[-1]
    if filename in {"lifecycle.py", "production_lifecycle.py"}:
        points.add("lifecycle")
    if filename == "middleware.py":
        points.add("middleware")
    if filename in {"api_errors.py", "api_throttles.py", "fiscal_urls.py", "menuboard_urls.py"}:
        points.add("API")
    if (
        "views" in parts
        or "webhooks" in parts
        or any(item.startswith(("django.http", "rest_framework")) for item in facts.imports)
    ):
        points.add("API")
    return points or {"outro"}


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _fail(code, f"{path}: {exc}")
    if not isinstance(value, dict):
        _fail(code, f"{path}: top level must be an object")
    return value


def _validate_schema_value(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Apply the JSON-Schema features used by the versioned unit schema."""
    declared_types = schema.get("type")
    if declared_types:
        names = [declared_types] if isinstance(declared_types, str) else declared_types
        checks = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "boolean": lambda item: isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "null": lambda item: item is None,
        }
        if not any(checks[name](value) for name in names):
            _fail("schema", f"{path}: expected type {names}")
    if "enum" in schema and value not in schema["enum"]:
        _fail("schema", f"{path}: value is outside enum")
    if "const" in schema and value != schema["const"]:
        _fail("schema", f"{path}: value must equal {schema['const']!r}")
    if "not" in schema and "const" in schema["not"] and value == schema["not"]["const"]:
        _fail("schema", f"{path}: forbidden value {value!r}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            _fail("schema", f"{path}: string is too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            _fail("schema", f"{path}: string does not match {schema['pattern']!r}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            _fail("schema", f"{path}: array is too short")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            _fail("schema", f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_schema_value(item, item_schema, f"{path}[{index}]")
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        if missing := required - set(value):
            _fail("schema", f"{path}: missing properties {sorted(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and (extra := set(value) - set(properties)):
            _fail("schema", f"{path}: additional properties {sorted(extra)}")
        for name, child in properties.items():
            if name in value:
                _validate_schema_value(value[name], child, f"{path}.{name}")


def _is_capability_owner(owner: object) -> bool:
    return isinstance(owner, str) and not owner.startswith("shopman.") and CAPABILITY_OWNER.fullmatch(owner) is not None


def _is_policy_shaped(path: str, symbol: str, node: ast.AST) -> bool:
    if symbol.endswith("Policy"):
        return isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    if symbol.endswith("Rule"):
        return isinstance(node, ast.ClassDef) and any(
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) for child in node.body
        )
    return False


def _annotation_root(annotation: ast.expr | None) -> str:
    while isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return "None"
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    return ""


def _is_decision_shaped(path: str, symbol: str, node: ast.AST) -> bool:
    """Recognize behavior, without turning typed support helpers into policies."""
    if symbol.endswith("Policy"):
        return isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    if symbol.endswith("Rule"):
        return isinstance(node, ast.ClassDef) and any(
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) for child in node.body
        )
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not DECISION_NAME.search(symbol):
        return False

    annotation_root = _annotation_root(node.returns)
    body_nodes = list(ast.walk(node))
    # Private collection materializers expose data assembled from collaborators;
    # the return annotation alone is not enough (public ``allowed_*`` selectors
    # remain decisions).  An explicit statement-level branch or raise is likewise
    # behavior rather than mechanical materialization.
    if (
        symbol.startswith("_")
        and annotation_root in {"dict", "list", "set", "tuple", "Mapping", "Sequence"}
        and not any(isinstance(child, (ast.If, ast.Raise)) for child in body_nodes)
    ):
        return False
    require_guard = re.match(r"^_?requires?", symbol, re.I)
    non_empty_returns = [
        child
        for child in body_nodes
        if isinstance(child, ast.Return)
        and child.value is not None
        and not (isinstance(child.value, ast.Constant) and child.value.value is None)
    ]
    # Contract parsers both reject malformed input and return its normalized
    # representation.  Pure guards that only raise, or selectors returning a
    # policy object, are not exempt merely because their name starts ``require``.
    if (
        require_guard
        and any(isinstance(child, ast.Raise) for child in body_nodes)
        and non_empty_returns
        and not any(
            isinstance(child.value, (ast.Compare, ast.BoolOp, ast.IfExp, ast.Attribute)) for child in non_empty_returns
        )
    ):
        return False
    return True


def _is_immutable_derived_property(parent: ast.ClassDef, node: ast.AST) -> bool:
    """Recognize a pure property that only exposes immutable instance state."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    decorators = {_dotted_name(item.func if isinstance(item, ast.Call) else item) for item in node.decorator_list}
    if "property" not in decorators or len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
        return False
    frozen_dataclass = any(
        isinstance(decorator, ast.Call)
        and _dotted_name(decorator.func).rpartition(".")[2] == "dataclass"
        and any(
            keyword.arg == "frozen" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            for keyword in decorator.keywords
        )
        for decorator in parent.decorator_list
    )
    if not frozen_dataclass:
        return False
    value = node.body[0].value
    allowed = (ast.BoolOp, ast.UnaryOp, ast.Attribute, ast.Name, ast.Load, ast.And, ast.Or, ast.Not, ast.Constant)
    return value is not None and all(
        isinstance(child, allowed)
        and not (isinstance(child, ast.Name) and child.id != "self")
        and not (
            isinstance(child, ast.Attribute) and not (isinstance(child.value, ast.Name) and child.value.id == "self")
        )
        and not (isinstance(child, ast.Constant) and child.value not in {True, False, None})
        for child in ast.walk(value)
    )


def _is_pure_attribute_accessor(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or len(node.body) != 1:
        return False
    statement = node.body[0]
    if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Attribute):
        return False
    root: ast.AST = statement.value
    while isinstance(root, ast.Attribute):
        root = root.value
    parameter_names = {argument.arg for argument in [*node.args.posonlyargs, *node.args.args]}
    return isinstance(root, ast.Name) and root.id in parameter_names


def _decision_nodes(symbol: str, node: ast.AST) -> list[tuple[str, ast.AST]]:
    candidates = [(symbol, node)]
    if isinstance(node, ast.ClassDef):
        candidates.extend(
            (f"{symbol}.{child.name}", child)
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not _is_immutable_derived_property(node, child)
            and not _is_pure_attribute_accessor(child)
        )
    return candidates


def _resolve_entrypoint(entrypoint: str, facts_by_path: dict[str, SourceFacts]) -> bool:
    module, _, symbol = entrypoint.partition(":")
    matches = [facts for facts in facts_by_path.values() if facts.module == module]
    return bool(matches and _resolve_symbol_node(matches[0], symbol))


def _resolve_symbol_node(facts: SourceFacts, symbol: str) -> ast.AST | None:
    """Resolve ``TopLevel`` or ``Class.method`` without importing application code."""
    top, dot, member = symbol.partition(".")
    node = _definition_nodes(facts).get(top)
    if node is None:
        return None
    if not dot:
        return node
    if not isinstance(node, ast.ClassDef) or "." in member:
        return None
    return next(
        (
            child
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == member
        ),
        None,
    )


def _absolute_from_module(facts: SourceFacts, node: ast.ImportFrom) -> str | None:
    if not node.level:
        return node.module
    package = facts.module.rpartition(".")[0]
    try:
        return importlib.util.resolve_name(
            "." * node.level + (node.module or ""),
            package,
        )
    except (ImportError, ValueError):
        return None


def _qualified_dependencies(
    facts: SourceFacts,
    symbol: str,
    facts_by_module: dict[str, SourceFacts],
) -> set[str]:
    """Return statically qualified Shop symbols referenced by one callable/symbol."""
    node = _resolve_symbol_node(facts, symbol)
    if node is None:
        return set()
    local = _definition_nodes(facts)
    direct: dict[str, str] = {}
    modules: dict[str, str] = {}
    for imported in _runtime_walk(node):
        if isinstance(imported, ast.Import):
            for alias in imported.names:
                modules[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(imported, ast.ImportFrom):
            origin = _absolute_from_module(facts, imported)
            if not origin:
                continue
            for alias in imported.names:
                local_name = alias.asname or alias.name
                imported_module = f"{origin}.{alias.name}"
                if imported_module in facts_by_module:
                    modules[local_name] = imported_module
                else:
                    direct[local_name] = f"{origin}:{alias.name}"
    # Module-level imports are visible inside every definition.
    for imported in facts.tree.body:
        if isinstance(imported, ast.Import):
            for alias in imported.names:
                modules.setdefault(alias.asname or alias.name.split(".")[0], alias.name)
        elif isinstance(imported, ast.ImportFrom):
            origin = _absolute_from_module(facts, imported)
            if not origin:
                continue
            for alias in imported.names:
                local_name = alias.asname or alias.name
                imported_module = f"{origin}.{alias.name}"
                if imported_module in facts_by_module:
                    modules.setdefault(local_name, imported_module)
                else:
                    direct.setdefault(local_name, f"{origin}:{alias.name}")

    result: set[str] = set()
    class_name = symbol.partition(".")[0] if "." in symbol else None
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        for child in ast.walk(node.value):
            if isinstance(child, ast.Name) and child.id in local:
                result.add(f"{facts.module}:{child.id}")
    aliases: dict[str, str] = {}

    def expression_reference(expression: ast.AST) -> str | None:
        if isinstance(expression, ast.Name):
            if expression.id in aliases:
                return aliases[expression.id]
            if expression.id in local:
                return f"{facts.module}:{expression.id}"
            return direct.get(expression.id)
        if isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
            if expression.value.id in modules:
                return f"{modules[expression.value.id]}:{expression.attr}"
            if expression.value.id in aliases:
                return f"{aliases[expression.value.id]}.{expression.attr}"
        return None

    for child in _runtime_walk(node):
        if not isinstance(child, (ast.Assign, ast.AnnAssign)):
            continue
        targets = child.targets if isinstance(child, ast.Assign) else [child.target]
        value = child.value.func if isinstance(child.value, ast.Call) else child.value
        if reference := expression_reference(value):
            for target in targets:
                if isinstance(target, ast.Name):
                    aliases[target.id] = reference

    for call in (child for child in _runtime_walk(node) if isinstance(child, ast.Call)):
        callee = call.func
        if isinstance(callee, ast.Name):
            if callee.id in local:
                result.add(f"{facts.module}:{callee.id}")
            if callee.id in direct:
                result.add(direct[callee.id])
            if callee.id in aliases:
                result.add(aliases[callee.id])
        elif isinstance(callee, ast.Attribute):
            if class_name and isinstance(callee.value, ast.Name) and callee.value.id in {"self", "cls"}:
                result.add(f"{facts.module}:{class_name}.{callee.attr}")
            elif isinstance(callee.value, ast.Name) and callee.value.id in modules:
                result.add(f"{modules[callee.value.id]}:{callee.attr}")
            elif isinstance(callee.value, ast.Name) and callee.value.id in local:
                target = local[callee.value.id]
                if isinstance(target, ast.ClassDef):
                    result.add(f"{facts.module}:{callee.value.id}")
                    result.add(f"{facts.module}:{callee.value.id}.{callee.attr}")
                elif isinstance(target, (ast.Assign, ast.AnnAssign)):
                    result.add(f"{facts.module}:{callee.value.id}")
            elif isinstance(callee.value, ast.Name) and callee.value.id in aliases:
                result.add(f"{aliases[callee.value.id]}.{callee.attr}")
            elif (
                class_name
                and isinstance(callee.value, ast.Call)
                and isinstance(callee.value.func, ast.Name)
                and callee.value.func.id == "super"
                and not callee.value.args
                and not callee.value.keywords
            ):
                class_node = local.get(class_name)
                if isinstance(class_node, ast.ClassDef):
                    for base in class_node.bases:
                        if isinstance(base, ast.Name) and isinstance(local.get(base.id), ast.ClassDef):
                            result.add(f"{facts.module}:{base.id}.{callee.attr}")
    return {reference for reference in result if reference.partition(":")[0] in facts_by_module}


def _reachable_symbols(
    entrypoint: str,
    authorities: set[str],
    facts_by_path: dict[str, SourceFacts],
) -> set[str]:
    """Walk the qualified static dependency graph from one canonical entrypoint."""
    facts_by_module = {facts.module: facts for facts in facts_by_path.values()}
    pending = [entrypoint]
    seen: set[str] = set()
    while pending:
        reference = pending.pop()
        if reference in seen:
            continue
        seen.add(reference)
        module, separator, symbol = reference.partition(":")
        facts = facts_by_module.get(module)
        if not separator or facts is None or _resolve_symbol_node(facts, symbol) is None:
            continue
        pending.extend(_qualified_dependencies(facts, symbol, facts_by_module) - seen)
    return {
        authority
        for authority in authorities
        if authority in seen or any(reference.startswith(f"{authority}.") for reference in seen)
    }


def _is_statically_skipped(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = _dotted_name(target)
        if name in {"pytest.mark.skip", "unittest.skip", "skip"}:
            return True
        if name in {"pytest.mark.skipif", "unittest.skipIf", "skipIf"} and isinstance(decorator, ast.Call):
            if decorator.args and isinstance(decorator.args[0], ast.Constant) and bool(decorator.args[0].value):
                return True
    return False


def _contains_static_skip_marker(node: ast.AST) -> bool:
    for child in ast.walk(node):
        target = child.func if isinstance(child, ast.Call) else child
        if _dotted_name(target) in {"pytest.mark.skip", "unittest.skip", "skip"}:
            return True
        if isinstance(child, ast.Call) and _dotted_name(child.func) in {
            "pytest.mark.skipif",
            "unittest.skipIf",
            "skipIf",
        }:
            if child.args and isinstance(child.args[0], ast.Constant) and bool(child.args[0].value):
                return True
    return False


def _module_is_statically_skipped(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in targets):
                if _contains_static_skip_marker(node.value):
                    return True
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and _dotted_name(node.value.func) == "pytest.skip"
            and any(
                keyword.arg == "allow_module_level"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.value.keywords
            )
        ):
            return True
    return False


def _collectable_test_node(
    reference: str, root: Path
) -> tuple[ast.Module, ast.FunctionDef | ast.AsyncFunctionDef] | None:
    parts = reference.split("::")
    if len(parts) not in {2, 3}:
        return None
    path = root / parts[0]
    filename = path.name
    if not path.is_file() or not (filename.startswith("test_") or filename.endswith("_test.py")):
        return None
    tree = ast.parse(path.read_text(), filename=parts[0])
    if _module_is_statically_skipped(tree):
        return None
    if len(parts) == 2:
        node = next(
            (
                item
                for item in tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == parts[1]
            ),
            None,
        )
        if node is None or not node.name.startswith("test_") or _is_statically_skipped(node):
            return None
        return tree, node
    parent = next(
        (item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == parts[1]),
        None,
    )
    unittest_style = bool(
        parent and any((_dotted_name(base) or "").rpartition(".")[2].endswith("TestCase") for base in parent.bases)
    )
    if (
        parent is None
        or (not parent.name.startswith("Test") and not unittest_style)
        or _is_statically_skipped(parent)
        or any(
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "__init__"
            for child in parent.body
        )
    ):
        return None
    node = next(
        (
            child
            for child in parent.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == parts[2]
        ),
        None,
    )
    if node is None or not node.name.startswith("test_") or _is_statically_skipped(node):
        return None
    return tree, node


def _resolve_test(reference: str, root: Path) -> bool:
    return _collectable_test_node(reference, root) is not None


def _test_nodes(reference: str, root: Path) -> tuple[ast.Module, list[ast.AST]] | None:
    parts = reference.split("::")
    collected = _collectable_test_node(reference, root)
    if collected is None:
        return None
    tree, test_node = collected
    nodes: list[ast.AST] = list(tree.body)
    class_definitions: dict[str, ast.AST] = {}
    if len(parts) == 3:
        parents = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == parts[1]]
        nodes = [child for node in parents for child in node.body]
        class_definitions = {
            child.name: child
            for node in parents
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
    for node in nodes:
        if node is test_node:
            definitions = {
                child.name: child for child in tree.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            definitions.update(class_definitions)
            selected: list[ast.AST] = []
            pending = [
                node,
                *(
                    class_definitions[name]
                    for name in ("setUp", "setup_method", "setUpClass", "setup_class")
                    if name in class_definitions
                ),
            ]
            seen: set[str] = set()
            while pending:
                current = pending.pop()
                name = getattr(current, "name", "")
                if name in seen:
                    continue
                seen.add(name)
                selected.append(current)
                called = {
                    child.func.id
                    for child in _runtime_walk(current)
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                }
                pending.extend(definitions[name] for name in called if name in definitions)
            return tree, selected
    return None


def _test_reached_authorities(reference: str, unit: dict[str, Any], root: Path) -> set[str]:
    """Return authorities reached by real qualified calls made by one test."""
    resolved = _test_nodes(reference, root)
    if resolved is None:
        return set()
    whole, scoped_nodes = resolved
    import_nodes = [
        node
        for candidate in [*whole.body, *(child for scoped in scoped_nodes for child in _runtime_walk(scoped))]
        for node in [candidate]
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    authorities = set(unit.get("authoritative_symbols", []))
    if not authorities:
        return set()
    facts_by_path = collect_facts(root)
    facts_by_module = {facts.module: facts for facts in facts_by_path.values()}
    direct_bindings: dict[str, str] = {}
    module_bindings: dict[str, str] = {}
    for node in import_nodes:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                imported_module = f"{node.module}.{alias.name}"
                if imported_module in facts_by_module:
                    module_bindings[local] = imported_module
                elif node.module in facts_by_module:
                    direct_bindings[local] = f"{node.module}:{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in facts_by_module:
                    module_bindings[alias.asname or alias.name.split(".")[0]] = alias.name

    candidates: set[str] = set()
    instance_bindings: dict[str, str] = {}
    default_modules: dict[str, str] = {}
    for scoped in scoped_nodes:
        if isinstance(scoped, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = [*scoped.args.posonlyargs, *scoped.args.args]
            defaults = (
                zip(positional[-len(scoped.args.defaults) :], scoped.args.defaults, strict=True)
                if scoped.args.defaults
                else ()
            )
            for argument, default in defaults:
                if isinstance(default, ast.Name) and default.id in module_bindings:
                    default_modules[argument.arg] = module_bindings[default.id]
            for argument, default in zip(scoped.args.kwonlyargs, scoped.args.kw_defaults, strict=True):
                if isinstance(default, ast.Name) and default.id in module_bindings:
                    default_modules[argument.arg] = module_bindings[default.id]
        runtime_nodes = list(_runtime_walk(scoped))
        for child in runtime_nodes:
            if isinstance(child, (ast.Assign, ast.AnnAssign)) and isinstance(child.value, ast.Call):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                if isinstance(child.value.func, ast.Name) and child.value.func.id in direct_bindings:
                    for target in targets:
                        if isinstance(target, ast.Name):
                            instance_bindings[target.id] = direct_bindings[child.value.func.id]
        for call in (child for child in runtime_nodes if isinstance(child, ast.Call)):
            callee = call.func
            if isinstance(callee, ast.Name) and callee.id in direct_bindings:
                candidates.add(direct_bindings[callee.id])
            elif isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
                base = callee.value.id
                if base in module_bindings:
                    candidates.add(f"{module_bindings[base]}:{callee.attr}")
                elif base in direct_bindings:
                    candidates.add(f"{direct_bindings[base]}.{callee.attr}")
                elif base in instance_bindings:
                    candidates.add(f"{instance_bindings[base]}.{callee.attr}")
                elif base in default_modules:
                    candidates.add(f"{default_modules[base]}:{callee.attr}")
            elif (
                isinstance(callee, ast.Attribute)
                and isinstance(callee.value, ast.Call)
                and isinstance(callee.value.func, ast.Name)
                and callee.value.func.id in direct_bindings
            ):
                candidates.add(f"{direct_bindings[callee.value.func.id]}.{callee.attr}")
    reached: set[str] = set()
    for candidate in candidates:
        reached.update(_reachable_symbols(candidate, authorities, facts_by_path))
    return reached


def _test_references_unit(reference: str, unit: dict[str, Any], root: Path) -> bool:
    return bool(_test_reached_authorities(reference, unit, root))


# ── Regras (a) e (c) como estrutura, não como nome ─────────────────────────────
#
# O manifesto prova que cada unidade tem UMA pergunta e UM entrypoint, mas isso é
# unicidade de string: uma segunda implementação da mesma decisão, escrita dentro
# de uma unidade que já existe, passava (laudo CORE-SOVEREIGNTY, A7-3). As três
# travas abaixo olham o CÓDIGO:
#
# 1. Campo possuído por política só é TESTADO (comparação, condição, operando
#    booleano) dentro do módulo da política. Uma comparação de ``min_order_q`` em
#    ``modifiers.py`` ou em ``services/cart.py`` é segunda implementação, tenha o
#    nome que tiver. Vale para ``shopman/shop``, ``storefront`` e ``backstage``.
# 2. Unidade de política nova nasce em ``shopman/shop/policies/``. As que já
#    viviam fora estão congeladas, símbolo a símbolo, em
#    ``policy-namespace-baseline.json``: a lista só encolhe.
# 3. Arquivo que acumulou unidades demais tem teto de linhas e de classes.

POLICY_SCAN_ROOTS = ("shopman/shop", "shopman/storefront", "shopman/backstage")
POLICY_NAMESPACE = "shopman/shop/policies/"
POLICY_NAMESPACE_BASELINE_PATH = ROOT / "docs" / "architecture" / "policy-namespace-baseline.json"


@dataclass(frozen=True)
class OwnedFields:
    """Campos cuja leitura em teste é decisão da política ``unit``.

    ``distinctive``: o nome só existe na entidade da política; qualquer receptor
    conta. ``generic``: o nome se repete em outras entidades (``skus``,
    ``fulfillment_types`` do canal); conta só quando o receptor se chama como a
    entidade (``receiver``).
    """

    unit: str
    module_path: str
    distinctive: frozenset[str]
    generic: frozenset[str]
    receiver: re.Pattern[str]


POLICY_OWNED_FIELDS = (
    OwnedFields(
        unit="promotion.eligibility",
        module_path="shopman/shop/policies/promotion.py",
        distinctive=frozenset({"min_order_q", "birthday_only", "customer_segments"}),
        generic=frozenset({"skus", "collections", "fulfillment_types"}),
        receiver=re.compile(r"promo|coupon", re.I),
    ),
)

# Leituras desses campos que NÃO decidem se a promoção vale, cada uma com o motivo.
# (path, símbolo de topo, campo). Entrada que deixa de casar reprova (lista só encolhe).
POLICY_FIELD_EXEMPTIONS: dict[tuple[str, str, str], str] = {
    ("shopman/shop/services/promotions.py", "_best_group_discount", "birthday_only"): (
        "escolhe QUAL promoção é a vantagem declarada do grupo, não se ela vale para a compra"
    ),
    ("shopman/shop/services/promotions.py", "_best_group_discount", "customer_segments"): (
        "escolhe QUAL promoção é a vantagem declarada do grupo, não se ela vale para a compra"
    ),
    ("shopman/shop/services/offers.py", "offer_skus", "skus"): (
        "lista os SKUs que a oferta nomeia para montar a sacola do anúncio; não decide se vale"
    ),
    ("shopman/shop/services/offers.py", "offer_skus", "collections"): (
        "lista os SKUs que a oferta nomeia para montar a sacola do anúncio; não decide se vale"
    ),
    ("shopman/shop/admin/price_tier.py", "PriceTierGroupDiscountForm", "fulfillment_types"): (
        "o editor do grupo mostra se a promoção do grupo foi salva como só-retirada"
    ),
    ("shopman/backstage/projections/customer_groups.py", "_project", "fulfillment_types"): (
        "a tela de grupos mostra se a promoção do grupo foi salva como só-retirada"
    ),
}

# Teto de tamanho: o arquivo não volta a crescer por acúmulo (A7-5). Baixar o teto
# quando o arquivo encolher; subir pede extrair uma unidade em vez disso.
SOURCE_BUDGETS: dict[str, dict[str, int]] = {
    "shopman/shop/modifiers.py": {"max_lines": 1880, "max_classes": 9},
}


def _receiver_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _receiver_name(node.func)
    return ""


def _delegation_walk(expression: ast.AST, delegates: frozenset[str]):
    """``ast.walk`` que não entra nos argumentos de uma chamada À política.

    Passar o campo para ``promotion_matches``/``promotion_minimum_eligible`` é
    delegar a decisão, não reimplementá-la.
    """
    pending = [expression]
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, ast.Call) and _receiver_name(node.func) in delegates:
            continue
        pending.extend(ast.iter_child_nodes(node))


def _is_empty_default(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return not node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"list", "tuple", "set", "dict", "frozenset"}
        and not node.args
        and not node.keywords
    )


def _policy_public_names(root: Path, owned: OwnedFields) -> frozenset[str]:
    path = root / owned.module_path
    if not path.exists():
        return frozenset()
    tree = ast.parse(path.read_text(), filename=owned.module_path)
    return frozenset(name for name in _defined_names(tree) if not name.startswith("_"))


def _owned_field_reads(
    expression: ast.AST,
    owned: OwnedFields,
    delegates: frozenset[str] = frozenset(),
    tainted: dict[str, set[str]] | None = None,
) -> set[str]:
    """Campos possuídos lidos dentro de uma expressão de teste.

    ``tainted`` mapeia variáveis locais que guardam um campo possuído
    (``segments = list(promo.customer_segments or [])``) para esse campo: testar a
    variável é testar o campo.
    """
    found: set[str] = set()
    for node in _delegation_walk(expression, delegates):
        if tainted and isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in tainted:
            found.update(tainted[node.id])
            continue
        field_name = ""
        receiver: ast.AST | None = None
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            field_name, receiver = node.attr, node.value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            field_name, receiver = node.args[1].value, node.args[0]
        if not field_name or receiver is None:
            continue
        if field_name in owned.distinctive:
            found.add(field_name)
        elif field_name in owned.generic and owned.receiver.search(_receiver_name(receiver)):
            found.add(field_name)
    return found


def _test_expressions(tree: ast.AST):
    """Toda expressão que DECIDE: condição, comparação ou operando booleano."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            yield node.test
        elif isinstance(node, ast.comprehension):
            yield from node.ifs
        elif isinstance(node, ast.Compare):
            yield node
        elif isinstance(node, ast.BoolOp):
            # ``promo.skus or []`` normaliza o vazio; não decide nada.
            if not (isinstance(node.op, ast.Or) and _is_empty_default(node.values[-1])):
                yield node
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            yield node.operand


def _tainted_locals(top: ast.AST, owned: OwnedFields, delegates: frozenset[str]) -> dict[str, set[str]]:
    """Variáveis atribuídas a partir de um campo possuído (duas passadas: cadeias curtas)."""
    tainted: dict[str, set[str]] = {}
    assignments = [node for node in ast.walk(top) if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))]
    for _ in range(2):
        for node in assignments:
            if node.value is None:
                continue
            fields = _owned_field_reads(node.value, owned, delegates, tainted)
            if not fields:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        tainted.setdefault(name.id, set()).update(fields)
    return tainted


def policy_field_scan_sources(root: Path = ROOT) -> list[Path]:
    result: list[Path] = []
    for scan_root in POLICY_SCAN_ROOTS:
        base = root / scan_root
        if not base.exists():
            continue
        result.extend(
            path
            for path in base.rglob("*.py")
            if "tests" not in path.parts and "migrations" not in path.parts and "__pycache__" not in path.parts
        )
    return sorted(result)


def policy_field_decisions(root: Path = ROOT) -> dict[str, set[tuple[str, str, str]]]:
    """Por política, os pontos (path, símbolo de topo, campo) que testam seus campos."""
    result: dict[str, set[tuple[str, str, str]]] = {owned.unit: set() for owned in POLICY_OWNED_FIELDS}
    delegates = {owned.unit: _policy_public_names(root, owned) for owned in POLICY_OWNED_FIELDS}
    for path in policy_field_scan_sources(root):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(), filename=rel)
        for top in tree.body:
            symbol = getattr(top, "name", "<module>")
            for owned in POLICY_OWNED_FIELDS:
                tainted = _tainted_locals(top, owned, delegates[owned.unit])
                for expression in _test_expressions(top):
                    for field_name in _owned_field_reads(expression, owned, delegates[owned.unit], tainted):
                        result[owned.unit].add((rel, symbol, field_name))
    return result


def check_policy_owned_fields(
    root: Path = ROOT,
    exemptions: dict[tuple[str, str, str], str] | None = None,
) -> dict[str, int]:
    """Reprova decisão de política reimplementada fora do módulo dela.

    Devolve, por política, quantos arquivos de produção implementam a decisão: a
    métrica de localidade do piloto (PROMOTION-PILOT.md), calculada e não declarada.
    """
    if exemptions is None:
        exemptions = POLICY_FIELD_EXEMPTIONS
    decisions = policy_field_decisions(root)
    used_exemptions: set[tuple[str, str, str]] = set()
    files_by_unit: dict[str, int] = {}
    for owned in POLICY_OWNED_FIELDS:
        violations = []
        files = set()
        for point in sorted(decisions[owned.unit]):
            if point[0] == owned.module_path:
                files.add(point[0])
            elif point in exemptions:
                used_exemptions.add(point)
            else:
                violations.append(point)
        if violations:
            _fail(
                "policy-reimplemented",
                f"{owned.unit}: campos da política testados fora de {owned.module_path} "
                f"(pergunte a ela em vez de comparar): {violations}",
            )
        files_by_unit[owned.unit] = len(files)
    stale = sorted(set(exemptions) - used_exemptions)
    if stale:
        _fail("policy-exemption-stale", f"exceções que não casam mais nada (apague-as): {stale}")
    return files_by_unit


def policy_units_outside_namespace(units: list[dict[str, Any]]) -> dict[str, list[str]]:
    outside: dict[str, list[str]] = {}
    for unit in units:
        if not unit.get("policy"):
            continue
        claims = sorted(
            f"{claim['path']}:{symbol}"
            for claim in unit["sources"]
            if not claim["path"].startswith(POLICY_NAMESPACE)
            for symbol in claim["symbols"]
        )
        if claims:
            outside[unit["id"]] = claims
    return outside


def check_policy_namespace(units: list[dict[str, Any]], baseline: dict[str, Any]) -> None:
    """Política nova nasce em ``policies/``; as antigas de fora não ganham símbolo."""
    if (
        not isinstance(baseline, dict)
        or baseline.get("schema_version") != 1
        or not isinstance(baseline.get("units"), dict)
    ):
        _fail("policy-baseline-schema", "baseline must contain schema_version=1 and units")
    frozen: dict[str, list[str]] = baseline["units"]
    outside = policy_units_outside_namespace(units)
    for uid, claims in sorted(outside.items()):
        if uid not in frozen:
            _fail(
                "policy-outside-namespace",
                f"{uid}: unidade de política nova nasce em {POLICY_NAMESPACE}: {claims}",
            )
        grown = sorted(set(claims) - set(frozen[uid]))
        if grown:
            _fail(
                "policy-outside-namespace",
                f"{uid}: política congelada fora de {POLICY_NAMESPACE} ganhou símbolos: {grown}",
            )
    stale = sorted(uid for uid, claims in frozen.items() if set(claims) != set(outside.get(uid, [])))
    if stale:
        _fail("policy-baseline-stale", f"baseline desatualizado (só encolhe; regrave-o): {stale}")


def check_source_budgets(root: Path = ROOT) -> None:
    for rel, budget in SOURCE_BUDGETS.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text()
        lines = text.count("\n")
        classes = sum(isinstance(node, ast.ClassDef) for node in ast.parse(text).body)
        if lines > budget["max_lines"] or classes > budget["max_classes"]:
            _fail(
                "source-budget",
                f"{rel}: {lines} linhas/{classes} classes, teto {budget['max_lines']}/{budget['max_classes']}; "
                "extraia uma unidade em vez de crescer o arquivo",
            )


def validate(
    inventory: dict[str, Any],
    manifests: dict[str, Any],
    *,
    root: Path = ROOT,
    instance_debt: dict[str, Any] | None = None,
    policy_namespace_baseline: dict[str, Any] | None = None,
    policy_field_exemptions: dict[tuple[str, str, str], str] | None = None,
) -> dict[str, Counter[str]]:
    if not isinstance(inventory, dict) or not isinstance(manifests, dict):
        _fail("schema", "inventory and manifests must be objects")
    if set(inventory) != {"schema_version", "sources"}:
        _fail("schema", "inventory top level must contain only schema_version and sources")
    if set(manifests) != {"schema_version", "units"}:
        _fail("schema", "manifest top level must contain only schema_version and units")
    schema = _load_json(root / SCHEMA_PATH.relative_to(ROOT), "schema-unreadable")
    if instance_debt is None:
        instance_debt = _load_json(root / INSTANCE_DEBT_PATH.relative_to(ROOT), "instance-debt-unreadable")
    schema_required = set(schema.get("required", []))
    schema_responsibilities = set(schema.get("properties", {}).get("responsibility", {}).get("enum", []))
    schema_touchpoints = set(schema.get("properties", {}).get("touchpoints", {}).get("items", {}).get("enum", []))
    schema_entrypoint_kinds = set(schema.get("properties", {}).get("entrypoint_kind", {}).get("enum", []))
    if (
        schema_required
        != {
            "id",
            "question",
            "owner",
            "responsibility",
            "public_entrypoint",
            "authoritative_symbols",
            "entrypoint_kind",
            "sources",
            "touchpoints",
            "domains",
            "ports",
            "events",
            "directives",
            "config_surface",
            "tests",
            "test_gap_reason",
            "policy",
            "out_of_extraction",
        }
        or schema_responsibilities != RESPONSIBILITIES
        or schema_touchpoints != TOUCHPOINTS
        or schema_entrypoint_kinds != {"symbol"}
    ):
        _fail("schema-drift", "JSON schema and executable vocabulary disagree")
    if inventory.get("schema_version") != 1 or manifests.get("schema_version") != 1:
        _fail("schema", "schema_version must be 1")
    sources = inventory.get("sources")
    units = manifests.get("units")
    if not isinstance(sources, list) or not isinstance(units, list):
        _fail("schema", "sources and units must be arrays")
    inventory_fields = {
        "path",
        "responsibilities",
        "support_claims",
        "touchpoints",
        "out_of_extraction",
        "unit_ids",
    }
    for item in sources:
        if not isinstance(item, dict) or set(item) != inventory_fields or not isinstance(item["path"], str):
            _fail("schema", "inventory sources must have the canonical shape and a string path")
        for field in ("responsibilities", "support_claims", "touchpoints", "unit_ids"):
            if not isinstance(item[field], list):
                _fail("schema", f"{item['path']}: {field} must be an array")
        if not isinstance(item["out_of_extraction"], bool):
            _fail("schema", f"{item['path']}: out_of_extraction must be boolean")
    for unit in units:
        _validate_schema_value(unit, schema)
    facts_by_path = collect_facts(root)
    if not isinstance(instance_debt, dict):
        _fail("instance-debt-schema", "instance debt must be an object")
    findings = instance_debt.get("findings")
    if instance_debt.get("schema_version") != 1 or not isinstance(findings, list):
        _fail("instance-debt-schema", "instance debt must contain schema_version=1 and findings")
    finding_keys: set[tuple[str, str, str]] = set()
    instance_markers = ("nelson", "boulangerie", "aliança francesa", "baguette de tradition")
    covered_markers: set[tuple[str, str]] = set()
    for finding in findings:
        required_finding = {"source", "symbol", "evidence", "risk", "target", "status"}
        if not isinstance(finding, dict) or set(finding) != required_finding:
            _fail("instance-debt-schema", "each finding must use the canonical fields")
        key = (finding["source"], finding["symbol"], finding["evidence"])
        if key in finding_keys:
            _fail("instance-debt-duplicate", f"duplicate instance debt: {key}")
        finding_keys.add(key)
        if finding["source"] not in facts_by_path or finding["status"] != "pending":
            _fail("instance-debt-schema", f"invalid pending finding: {key}")
        facts = facts_by_path[finding["source"]]
        if finding["symbol"] != "<module>" and finding["symbol"] not in facts.symbols:
            _fail("instance-debt-symbol", f"unresolved instance debt symbol: {key}")
        runtime_strings = _runtime_strings(facts.tree)
        structural_evidence = finding["evidence"] == finding["symbol"] or (
            finding["symbol"] == "<module>" and finding["evidence"] == "instance-brand-palette"
        )
        if not structural_evidence and not any(finding["evidence"] in value for value in runtime_strings):
            _fail("instance-debt-stale", f"evidence no longer exists: {key}")
        marker = finding["evidence"].lower()
        for candidate in instance_markers:
            if candidate in marker:
                covered_markers.add((finding["source"], candidate))
    # Known-instance proper names are never an allowlisted baseline: each source
    # occurrence must remain an explicit pending finding until a later WP removes it.
    for rel, facts in facts_by_path.items():
        runtime_values = {value.lower() for value in _runtime_strings(facts.tree)}
        for marker in instance_markers:
            if any(marker in value for value in runtime_values) and (rel, marker) not in covered_markers:
                _fail("instance-debt-untriaged", f"{rel}: untriaged instance marker {marker!r}")
    # Structural instance defaults do not need a proper name to be dangerous: a
    # house's hour, percentage, palette or rule params written as product code is
    # the same leak. Each detection must be a declared finding, and the canonical
    # registry declares none (CORE-SOVEREIGNTY A7-1/A7-2).
    declared_structural = {(finding["source"], finding["symbol"]) for finding in findings}
    untriaged_structural = sorted(
        (rel, symbol)
        for rel, facts in facts_by_path.items()
        for symbol in _structural_instance_defaults(facts.tree)
        if (rel, symbol) not in declared_structural
    )
    if untriaged_structural:
        _fail("instance-debt-untriaged", f"untriaged structural defaults: {untriaged_structural}")
    physical = set(facts_by_path)
    inventoried = [item.get("path") for item in sources if isinstance(item, dict)]
    if len(inventoried) != len(set(inventoried)):
        _fail("duplicate-source", "physical inventory contains duplicate source paths")
    missing = sorted(physical - set(inventoried))
    extra = sorted(set(inventoried) - physical)
    if missing or extra:
        _fail("coverage", f"physical inventory drift; missing={missing}, orphan={extra}")

    inventory_by_path: dict[str, dict[str, Any]] = {}
    physical_responsibilities: Counter[str] = Counter()
    physical_touchpoints: Counter[str] = Counter()
    for item in sources:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "responsibilities",
            "support_claims",
            "touchpoints",
            "out_of_extraction",
            "unit_ids",
        }:
            _fail(
                "schema",
                "inventory source must contain path, derived responsibilities, support claims, "
                "touchpoints, out_of_extraction and unit_ids",
            )
        path = item["path"]
        responsibilities_set = item["responsibilities"]
        support_claims = item["support_claims"]
        support_set = (
            [claim.get("responsibility") for claim in support_claims if isinstance(claim, dict)]
            if isinstance(support_claims, list)
            else []
        )
        if (
            not isinstance(responsibilities_set, list)
            or not responsibilities_set
            or responsibilities_set != sorted(set(responsibilities_set))
            or set(responsibilities_set) - RESPONSIBILITIES
            or not isinstance(support_claims, list)
            or set(support_set) - (RESPONSIBILITIES - {"decisão", "composição"})
            or support_set != sorted(set(support_set))
        ):
            _fail("schema", f"{path}: invalid physical responsibility sets")
        facts = facts_by_path[path]
        empty_support_claims = [
            claim for claim in support_claims if isinstance(claim, dict) and claim.get("symbols") == []
        ]
        if not facts.symbols:
            # An empty package is still a physical source and must remain visible
            # in the 100% inventory.  Its one empty claim describes the namespace,
            # never a semantic unit or imaginary symbol.  Projection package
            # initializers remain read-side namespaces; every other empty module is
            # infrastructure.
            source_path = Path(path)
            expected_empty_responsibility = (
                "leitura"
                if source_path.name == "__init__.py" and "projections" in source_path.parts
                else "infraestrutura"
            )
            if (
                len(support_claims) != 1
                or len(empty_support_claims) != 1
                or support_claims[0].get("responsibility") != expected_empty_responsibility
                or responsibilities_set != [expected_empty_responsibility]
                or item["unit_ids"]
            ):
                _fail(
                    "support-symbol",
                    f"{path}: empty source requires exactly one empty "
                    f"{expected_empty_responsibility} support claim and no units",
                )
        elif empty_support_claims:
            _fail("support-symbol", f"{path}: empty support claim is forbidden when symbols exist")
        seen_support_symbols: set[str] = set()
        for claim in support_claims:
            if not isinstance(claim, dict) or set(claim) != {"responsibility", "symbols"}:
                _fail("schema", f"{path}: invalid support claim")
            symbols = claim["symbols"]
            if not isinstance(symbols, list) or (not symbols and facts.symbols) or symbols != sorted(set(symbols)):
                _fail("schema", f"{path}: support symbols must be a sorted unique non-empty array")
            unknown = set(symbols) - set(facts.symbols)
            overlap = seen_support_symbols & set(symbols)
            if unknown or overlap:
                _fail("support-symbol", f"{path}: unknown={sorted(unknown)}, overlap={sorted(overlap)}")
            seen_support_symbols.update(symbols)
        if (
            not isinstance(item["touchpoints"], list)
            or not item["touchpoints"]
            or item["touchpoints"] != sorted(set(item["touchpoints"]))
            or set(item["touchpoints"]) - TOUCHPOINTS
        ):
            _fail("schema", f"{path}: invalid physical touchpoints")
        expected_touchpoints = _derived_touchpoints(facts_by_path[path])
        if set(item["touchpoints"]) != expected_touchpoints:
            _fail(
                "touchpoint-drift",
                f"{path}: declared={sorted(item['touchpoints'])}, AST/path={sorted(expected_touchpoints)}",
            )
        if (
            not isinstance(item["out_of_extraction"], bool)
            or not isinstance(item["unit_ids"], list)
            or item["unit_ids"] != sorted(set(item["unit_ids"]))
            or not all(isinstance(unit_id, str) and unit_id for unit_id in item["unit_ids"])
        ):
            _fail("schema", f"{path}: invalid physical inventory types")
        if "projections" in Path(path).parts and not (
            responsibilities_set == ["leitura"] and "projection" in item["touchpoints"] and item["out_of_extraction"]
        ):
            _fail("read-side", f"{path}: projection must be leitura/projection/out_of_extraction")
        if item["out_of_extraction"] != (responsibilities_set == ["leitura"]):
            _fail("read-side", f"{path}: source is out_of_extraction iff every responsibility is leitura")
        inventory_by_path[path] = item
        physical_responsibilities.update(responsibilities_set)
        physical_touchpoints.update(item["touchpoints"])

    ids = [unit.get("id") for unit in units if isinstance(unit, dict)]
    if len(ids) != len(set(ids)):
        _fail("duplicate-id", "unit ids must be unique")
    by_id = {unit["id"]: unit for unit in units if isinstance(unit, dict) and isinstance(unit.get("id"), str)}
    inventory_ids = {uid for item in sources for uid in item.get("unit_ids", [])}
    if inventory_ids - set(by_id):
        _fail("manifest-missing", f"inventory units without manifest: {sorted(inventory_ids - set(by_id))}")
    if set(by_id) - inventory_ids:
        _fail("manifest-orphan", f"manifest units absent from inventory: {sorted(set(by_id) - inventory_ids)}")
    for item in sources:
        semantic = {by_id[unit_id]["responsibility"] for unit_id in item["unit_ids"]}
        expected = semantic | {claim["responsibility"] for claim in item["support_claims"]}
        if set(item["responsibilities"]) & {"decisão", "composição"} and not item["unit_ids"]:
            _fail("semantic-unit-missing", f"{item['path']}: decision/composition source requires semantic units")
        if set(item["responsibilities"]) != expected:
            _fail(
                "inventory-responsibility-drift",
                f"{item['path']}: declared={item['responsibilities']}, derived={sorted(expected)}",
            )
        if item["path"].startswith("shopman/shop/policies/") and not item["path"].endswith(
            "/__init__.py"
        ):
            if item["support_claims"] or item["responsibilities"] != ["decisão"]:
                _fail(
                    "policy-namespace",
                    f"{item['path']}: policies/ only accepts manifested decision units",
                )
            non_policy_units = [unit_id for unit_id in item["unit_ids"] if not by_id[unit_id]["policy"]]
            if non_policy_units:
                _fail(
                    "policy-namespace",
                    f"{item['path']}: non-policy units in policies/: {non_policy_units}",
                )

    raw_questions = [unit.get("question") for unit in units if isinstance(unit, dict)]
    raw_entrypoints = [
        unit.get("public_entrypoint") for unit in units if isinstance(unit, dict) and unit.get("public_entrypoint")
    ]
    if len(raw_questions) != len(set(raw_questions)):
        _fail("duplicate-question", "unit questions must be unique")
    if len(raw_entrypoints) != len(set(raw_entrypoints)):
        _fail("duplicate-entrypoint", "public entrypoints must be unique")

    required = schema_required
    questions: list[str] = []
    entrypoints: list[str] = []
    symbol_claims: dict[tuple[str, str], str] = {}
    support_references: set[str] = set()
    for item in sources:
        for claim in item["support_claims"]:
            for symbol in claim["symbols"]:
                symbol_claims[(item["path"], symbol)] = f"support:{claim['responsibility']}"
                support_references.add(f"{facts_by_path[item['path']].module}:{symbol}")
    responsibilities: Counter[str] = Counter()
    touchpoints: Counter[str] = Counter()
    owner_prefixes: Counter[str] = Counter()
    test_gaps: Counter[str] = Counter()

    for unit in units:
        if not isinstance(unit, dict) or not required <= set(unit):
            _fail("schema", f"unit is missing fields: {sorted(required - set(unit if isinstance(unit, dict) else {}))}")
        uid = unit["id"]
        if uid.endswith("-unit") or "module-support" in uid:
            _fail("synthetic-unit", f"{uid}: generic module units are forbidden")
        for field in ("id", "question", "owner"):
            if not isinstance(unit[field], str) or not unit[field].strip():
                _fail("schema", f"{uid}: {field} must be a non-empty string")
        public_entrypoint = unit["public_entrypoint"]
        authoritative_symbols = unit["authoritative_symbols"]
        if not unit["question"].rstrip().endswith("?") or unit["question"].startswith(
            ("Como os participantes são coordenados para:", "Qual decisão canônica responde:", "Qual unidade realiza:")
        ):
            _fail("synthetic-question", f"{uid}: question must be factual and curated")
        if unit["responsibility"] not in RESPONSIBILITIES:
            _fail("schema", f"{uid}: invalid responsibility {unit['responsibility']!r}")
        if not isinstance(unit["touchpoints"], list) or not unit["touchpoints"]:
            _fail("schema", f"{uid}: touchpoints must be non-empty")
        if set(unit["touchpoints"]) - TOUCHPOINTS:
            _fail("schema", f"{uid}: invalid touchpoints")
        if unit["policy"] and unit["responsibility"] != "decisão":
            _fail("policy-responsibility", f"{uid}: policy must have decisão responsibility")
        if unit["out_of_extraction"] != (unit["responsibility"] == "leitura"):
            _fail("read-side", f"{uid}: leitura and out_of_extraction must be equivalent")
        observed_domains: set[str] = set()
        observed_ports: set[str] = set()
        observed_events: set[str] = set()
        observed_directives: set[str] = set()
        observed_config: set[str] = set()
        observed_touchpoints: set[str] = set()
        if not isinstance(unit["sources"], list) or not unit["sources"]:
            _fail("schema", f"{uid}: sources must be non-empty")
        source_modules: set[str] = set()
        for claim in unit["sources"]:
            if not isinstance(claim, dict) or set(claim) != {"path", "symbols"}:
                _fail("schema", f"{uid}: source claim must contain path and symbols")
            path = claim["path"]
            if path not in facts_by_path:
                _fail("source-orphan", f"{uid}: source does not exist: {path}")
            facts = facts_by_path[path]
            source_modules.add(facts.module)
            symbols = claim["symbols"]
            if not isinstance(symbols, list):
                _fail("schema", f"{uid}: symbols must be an array")
            if "*" in symbols:
                _fail("schema", f"{uid}: wildcard symbol coverage is forbidden")
            if not symbols and facts.symbols:
                _fail("schema", f"{uid}: a module with definitions cannot have empty symbols")
            expanded = symbols
            unknown = set(expanded) - set(facts.symbols)
            if unknown:
                _fail("symbol-unresolved", f"{uid}: unknown symbols in {path}: {sorted(unknown)}")
            for symbol in expanded:
                key = (path, symbol)
                if key in symbol_claims:
                    _fail("symbol-overlap", f"{path}:{symbol} claimed by {symbol_claims[key]} and {uid}")
                symbol_claims[key] = uid
            support_symbols = {
                symbol
                for support_claim in inventory_by_path[path]["support_claims"]
                for symbol in support_claim["symbols"]
            }
            observed_touchpoints.update(_derived_touchpoints(facts))
            observed = _scoped_observations(
                facts,
                expanded,
                facts_by_path,
                support_symbols,
                support_references,
            )
            observed_domains.update(observed["domains"])
            observed_ports.update(observed["ports"])
            observed_events.update(observed["events"])
            observed_directives.update(observed["directives"])
            observed_config.update(observed["config_surface"])
        if set(unit["touchpoints"]) != observed_touchpoints:
            _fail(
                "semantic-touchpoint-drift",
                f"{uid}: declared touchpoints={sorted(unit['touchpoints'])}, AST/path={sorted(observed_touchpoints)}",
            )
        owner = unit["owner"]
        if not _is_capability_owner(owner) or owner == public_entrypoint or owner in source_modules:
            _fail("owner-not-capability", f"{uid}: owner must name a capability, not a source path or symbol")
        if not _resolve_entrypoint(public_entrypoint, facts_by_path):
            _fail("entrypoint-unresolved", f"{uid}: unresolved entrypoint {public_entrypoint}")
        if set(unit["domains"]) != observed_domains:
            _fail(
                "domain-drift",
                f"{uid}: declared domains={sorted(unit['domains'])}, AST={sorted(observed_domains)}",
            )
        if set(unit["ports"]) != observed_ports:
            _fail("port-drift", f"{uid}: declared ports={sorted(unit['ports'])}, AST={sorted(observed_ports)}")
        if set(unit["events"]) != observed_events:
            _fail("event-drift", f"{uid}: declared events={sorted(unit['events'])}, AST={sorted(observed_events)}")
        if set(unit["directives"]) != observed_directives:
            _fail(
                "directive-drift",
                f"{uid}: declared directives={sorted(unit['directives'])}, AST={sorted(observed_directives)}",
            )
        if set(unit["config_surface"]) != observed_config:
            _fail(
                "config-drift",
                f"{uid}: declared config={sorted(unit['config_surface'])}, AST={sorted(observed_config)}",
            )
        claimed_references = {
            f"{facts_by_path[claim['path']].module}:{symbol}"
            for claim in unit["sources"]
            for symbol in claim["symbols"]
        }
        authority_roots: set[str] = set()
        for authority in authoritative_symbols:
            authority_module, _, authority_symbol = authority.partition(":")
            authority_root = authority_symbol.partition(".")[0]
            authority_claim = f"{authority_module}:{authority_root}"
            if not _resolve_entrypoint(authority, facts_by_path):
                _fail("authority-unresolved", f"{uid}: unresolved authority {authority}")
            if authority_claim not in claimed_references:
                _fail("authority-outside-unit", f"{uid}: authority is not claimed by the unit: {authority}")
            authority_roots.add(authority)
        reached = _reachable_symbols(public_entrypoint, authority_roots, facts_by_path)
        if reached != authority_roots:
            _fail(
                "authority-not-reachable",
                f"{uid}: entrypoint {public_entrypoint} does not reach {sorted(authority_roots - reached)}",
            )

        module, _, entry_symbol = public_entrypoint.partition(":")
        if unit["entrypoint_kind"] != "symbol":
            _fail("entrypoint-kind", f"{uid}: entrypoint_kind must be symbol")
        if entry_symbol:
            entry_leaf = entry_symbol.rpartition(".")[2]
            if entry_leaf.startswith("_") and entry_leaf != "__call__":
                _fail("entrypoint-private", f"{uid}: canonical entrypoint is private: {public_entrypoint}")
            entry_root = entry_symbol.partition(".")[0]
            claimed = {
                symbol
                for claim in unit["sources"]
                for symbol in claim["symbols"]
                if facts_by_path[claim["path"]].module == module
            }
            if entry_root not in claimed:
                _fail("entrypoint-outside-unit", f"{uid}: entrypoint is not one of its claimed symbols")
        if not isinstance(unit["tests"], list):
            _fail("schema", f"{uid}: tests must be an array")
        suite_reached: set[str] = set()
        for test in unit["tests"]:
            if not isinstance(test, str) or not _resolve_test(test, root):
                _fail("test-unresolved", f"{uid}: test does not resolve: {test!r}")
            reached_by_test = _test_reached_authorities(test, unit, root)
            if not reached_by_test:
                _fail("test-unrelated", f"{uid}: test does not use a qualified path to a claimed symbol: {test!r}")
            suite_reached.update(reached_by_test)
        if not unit["tests"]:
            _fail("test-gap", f"{uid}: every semantic unit requires direct test evidence")
        if suite_reached != authority_roots:
            _fail(
                "test-authority-coverage",
                f"{uid}: test suite does not reach {sorted(authority_roots - suite_reached)}",
            )
        if unit["test_gap_reason"] is not None:
            _fail("test-gap", f"{uid}: mergeable manifests cannot waive missing tests")
        questions.append(unit["question"])
        if public_entrypoint:
            entrypoints.append(public_entrypoint)
        responsibilities[unit["responsibility"]] += 1
        touchpoints.update(unit["touchpoints"])
        owner_prefixes[unit["owner"].partition(".")[0]] += 1

    uncovered_symbols = sorted(
        (path, symbol)
        for path in facts_by_path
        for symbol, node in _definition_nodes(facts_by_path[path]).items()
        if (path, symbol) not in symbol_claims
    )
    if uncovered_symbols:
        _fail("symbol-coverage", f"uncovered top-level symbols: {uncovered_symbols}")
    for (path, symbol), owner in symbol_claims.items():
        node = _definition_nodes(facts_by_path[path])[symbol]
        for decision_symbol, decision_node in _decision_nodes(symbol, node):
            if not _is_decision_shaped(path, decision_symbol.rpartition(".")[2], decision_node):
                continue
            if owner.startswith("support:"):
                _fail(
                    "decision-hidden-in-support",
                    f"{path}:{decision_symbol} is decision-shaped but classified as {owner}",
                )
            if by_id[owner]["responsibility"] != "decisão":
                _fail(
                    "decision-responsibility",
                    f"{path}:{decision_symbol} is decision-shaped but {owner} is {by_id[owner]['responsibility']}",
                )
    if len(questions) != len(set(questions)):
        _fail("duplicate-question", "unit questions must be unique")
    if len(entrypoints) != len(set(entrypoints)):
        _fail("duplicate-entrypoint", "public entrypoints must be unique")
    policy_owners = [unit["owner"] for unit in units if unit["policy"]]
    if len(policy_owners) != len(set(policy_owners)):
        _fail("duplicate-policy-owner", "policies with the same capability owner must be one unit")
    # Policy-shaped symbols cannot hide in a non-policy unit.
    for (path, symbol), uid in symbol_claims.items():
        node = _definition_nodes(facts_by_path[path])[symbol]
        policy_shaped = _is_policy_shaped(path, symbol, node)
        if policy_shaped and (uid.startswith("support:") or not by_id[uid]["policy"]):
            _fail("policy-without-manifest", f"{path}:{symbol} is policy-shaped but {uid} is not a policy unit")

    for item in sources:
        expected = sorted(
            uid for uid, unit in by_id.items() if any(claim["path"] == item["path"] for claim in unit["sources"])
        )
        if sorted(item.get("unit_ids", [])) != expected:
            _fail("inventory-drift", f"{item['path']}: unit_ids do not match manifests")
    if policy_namespace_baseline is None:
        policy_namespace_baseline = _load_json(
            root / POLICY_NAMESPACE_BASELINE_PATH.relative_to(ROOT), "policy-baseline-unreadable"
        )
    check_policy_namespace(units, policy_namespace_baseline)
    policy_decision_files = check_policy_owned_fields(root, policy_field_exemptions)
    check_source_budgets(root)
    return {
        "policy_decision_files": Counter(policy_decision_files),
        "responsibilities": responsibilities,
        "touchpoints": touchpoints,
        "owner_prefixes": owner_prefixes,
        "physical_responsibilities": physical_responsibilities,
        "physical_touchpoints": physical_touchpoints,
        "test_gaps": test_gaps,
        "instance_debt": Counter({"pending": len(findings)}),
        "coverage": Counter(
            {
                "sources": len(facts_by_path),
                "symbols": sum(len(_definition_nodes(facts)) for facts in facts_by_path.values()),
                "semantic_units": len(units),
            }
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)
    parser.add_argument("--manifests", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args(argv)
    try:
        inventory = _load_json(args.inventory, "inventory-unreadable")
        manifests = _load_json(args.manifests, "manifest-unreadable")
        counts = validate(inventory, manifests)
    except GateError as exc:
        print(f"[{exc.code}] {exc}", file=sys.stderr)
        return 1
    print(
        "orchestrator units: "
        f"sources={len(inventory['sources'])} units={len(manifests['units'])} "
        f"source_responsibilities={dict(sorted(counts['physical_responsibilities'].items()))} "
        f"source_touchpoints={dict(sorted(counts['physical_touchpoints'].items()))} "
        f"unit_responsibilities={dict(sorted(counts['responsibilities'].items()))} "
        f"unit_touchpoints={dict(sorted(counts['touchpoints'].items()))} "
        f"unit_owner_prefixes={dict(sorted(counts['owner_prefixes'].items()))} "
        f"test_gaps={dict(sorted(counts['test_gaps'].items()))} "
        f"instance_debt={counts['instance_debt']['pending']} "
        f"policy_decision_files={dict(sorted(counts['policy_decision_files'].items()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
