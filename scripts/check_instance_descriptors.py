#!/usr/bin/env python3
"""Validate versioned instance descriptors without Django or a database."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTANCE_DIR = ROOT / "config" / "instances"
OWNERS = ("instance_db", "deploy", "secret", "structural")
BOOTSTRAP_SECTIONS = (
    "channels", "fiscal_profiles", "pipelines", "pricing_policies",
    "rbac_personas", "rule_configs", "templates", "units",
)
REF_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PERMISSION_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
SECRET_KEY_RE = re.compile(r"(?:secret|password|passwd|token|credential|api[_-]?key|private[_-]?key)", re.I)
SECRET_VALUE_RES = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\b(?:postgres(?:ql)?|redis)://[^\s/@:]+:[^\s/@]+@", re.I),
)
OPERATIONAL_KEYS = {"orders", "payments", "ledger_entries", "stock_balances", "sessions", "audit_events"}


class DescriptorError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DescriptorError(message)


def _walk_mapping(value, path: str = "bootstrap"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield path, key
            yield from _walk_mapping(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_mapping(child, f"{path}[{index}]")


def _walk_strings(value, path: str = "bootstrap"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def validate_descriptor(data: dict, *, filename: str = "<memory>") -> None:
    _require(isinstance(data, dict), f"{filename}: raiz precisa ser objeto")
    _require(set(data) == {"schema_version", "instance", "ownership", "bootstrap"}, f"{filename}: campos de topo divergiram do schema v1")
    _require(data["schema_version"] == 1, f"{filename}: schema_version precisa ser 1")
    instance = data["instance"]
    _require(isinstance(instance, dict) and set(instance) == {"ref", "display_name"}, f"{filename}: instance inválida")
    ref = instance["ref"]
    _require(isinstance(ref, str) and REF_RE.fullmatch(ref) is not None, f"{filename}: instance.ref inválido")
    _require(filename == "<memory>" or Path(filename).stem == ref, f"{filename}: nome não concorda com instance.ref")
    _require(isinstance(instance["display_name"], str) and instance["display_name"].strip(), f"{filename}: display_name vazio")

    bootstrap = data["bootstrap"]
    _require(isinstance(bootstrap, dict) and set(bootstrap) == set(BOOTSTRAP_SECTIONS), f"{filename}: seções bootstrap incompletas")
    ownership = data["ownership"]
    _require(isinstance(ownership, dict) and set(ownership) == set(OWNERS), f"{filename}: ownership incompleto")
    seen: dict[str, str] = {}
    for owner in OWNERS:
        names = ownership[owner]
        _require(isinstance(names, list) and all(isinstance(item, str) for item in names), f"{filename}: ownership.{owner} inválido")
        _require(len(names) == len(set(names)), f"{filename}: ownership.{owner} contém duplicata")
        for name in names:
            previous = seen.setdefault(name, owner)
            _require(previous == owner, f"{filename}: {name!r} pertence a {previous} e {owner}")
    _require(set(ownership["instance_db"]) == set(BOOTSTRAP_SECTIONS), f"{filename}: instance_db precisa possuir exatamente as seções materializadas no DB")
    for owner in ("deploy", "secret", "structural"):
        _require(ownership[owner] and all(ENV_RE.fullmatch(name) for name in ownership[owner]), f"{filename}: ownership.{owner} exige nomes de configuração")

    for section, items in bootstrap.items():
        _require(isinstance(items, list), f"{filename}: bootstrap.{section} precisa ser lista")
        refs: list[str] = []
        for item in items:
            _require(isinstance(item, dict), f"{filename}: item de {section} precisa ser objeto")
            item_ref = item.get("ref")
            _require(isinstance(item_ref, str) and REF_RE.fullmatch(item_ref), f"{filename}: ref inválida em {section}")
            refs.append(item_ref)
            if section == "rbac_personas":
                _require(set(item) == {"ref", "permissions"}, f"{filename}: persona tem campos inválidos")
                permissions = item["permissions"]
                _require(isinstance(permissions, list) and len(permissions) == len(set(permissions)) and all(isinstance(p, str) and PERMISSION_RE.fullmatch(p) for p in permissions), f"{filename}: permissions inválidas em {item_ref}")
            elif section == "units":
                _require(set(item) == {"ref", "symbol"}, f"{filename}: unidade tem campos inválidos")
                _require(isinstance(item["symbol"], str) and 0 < len(item["symbol"]) <= 12, f"{filename}: símbolo inválido em {item_ref}")
            else:
                _require(set(item) <= {"ref", "enabled", "config"}, f"{filename}: item de {section} tem campos inválidos")
                _require("enabled" not in item or isinstance(item["enabled"], bool), f"{filename}: enabled inválido em {item_ref}")
                _require("config" not in item or isinstance(item["config"], dict), f"{filename}: config inválida em {item_ref}")
        _require(len(refs) == len(set(refs)), f"{filename}: refs duplicadas em {section}")

    for path, key in _walk_mapping(bootstrap):
        _require(key not in OPERATIONAL_KEYS, f"{filename}: estado operacional proibido em {path}.{key}")
        _require(not SECRET_KEY_RE.search(key), f"{filename}: segredo proibido em {path}.{key}")
    for path, value in _walk_strings(bootstrap):
        _require(
            not any(pattern.search(value) for pattern in SECRET_VALUE_RES),
            f"{filename}: valor com padrão de segredo proibido em {path}",
        )


def validate_directory(instance_dir: Path = INSTANCE_DIR) -> list[Path]:
    schema = json.loads((instance_dir / "schema.json").read_text(encoding="utf-8"))
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema.json: draft canônico ausente")
    _require(schema.get("properties", {}).get("schema_version", {}).get("const") == 1, "schema.json: versão divergente")
    paths = sorted(path for path in instance_dir.glob("*.json") if path.name != "schema.json")
    _require(paths, "nenhum descritor de instância")
    refs: list[str] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_descriptor(data, filename=path.name)
        refs.append(data["instance"]["ref"])
    _require(len(refs) == len(set(refs)), "refs de instância duplicadas")
    _require("nelson" in refs, "descritor nelson ausente")
    _require(any(ref != "nelson" for ref in refs), "uma segunda instância é obrigatória")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=INSTANCE_DIR)
    args = parser.parse_args(argv)
    try:
        paths = validate_directory(args.directory)
    except (DescriptorError, json.JSONDecodeError, OSError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print(f"✓ descritores de instância: {', '.join(path.stem for path in paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
