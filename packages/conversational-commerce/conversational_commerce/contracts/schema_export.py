"""Gera o JSON Schema de cada contrato a partir das dataclasses (Python é a fonte).

    python -m conversational_commerce.contracts.schema_export --write   # regrava schemas/
    python -m conversational_commerce.contracts.schema_export --check   # falha se houver deriva

O esquema é para quem lê de outra linguagem. Ele diz forma, tipo, enum e
formato; as regras que cruzam campos (as quatro combinações do recibo, total =
linhas + ajustes, hash que confere) moram no validador Python e estão escritas
no ``spec/01-contracts.md``. Um documento que passa no esquema ainda pode ser
recusado pelo validador; o contrário não acontece.

Um arquivo por contrato, ``schemas/<schema>.schema.json``, em JSON com chaves
ordenadas e indentação de dois espaços, terminado em nova linha.
"""

from __future__ import annotations

import argparse
import collections.abc
import json
import sys
import typing
from pathlib import Path
from typing import Any

from . import CONTRACTS
from .canonical import FrozenMap
from .common import ObservationRecord, Record, Rule, StrictRecord, Value
from .validate import PATTERNS, contract_fields, discriminator, is_nullable, split_annotated, union_args

SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

_JSON_VALUE_DEF = {
    "description": "Qualquer valor JSON, sem número de ponto flutuante.",
    "anyOf": [
        {"type": "null"},
        {"type": "boolean"},
        {"type": "string"},
        {"type": "integer", "minimum": -(2**53 - 1), "maximum": 2**53 - 1},
        {"type": "array", "items": {"$ref": "#/$defs/JsonValue"}},
        {"type": "object", "additionalProperties": {"$ref": "#/$defs/JsonValue"}},
    ],
}

_RULE_FRAGMENTS: dict[Rule, dict[str, Any]] = {
    Rule.IDENTIFIER: {"minLength": 1, "pattern": r"^\S+$"},
    Rule.TEXT: {"minLength": 1, "pattern": r"^\S(.*\S)?$"},
    Rule.NON_NEGATIVE: {"minimum": 0},
    Rule.POSITIVE: {"minimum": 1},
}


class _Builder:
    def __init__(self) -> None:
        self.defs: dict[str, Any] = {}

    def type_schema(self, tp: Any) -> dict[str, Any]:
        base, rules = split_annotated(tp)
        schema = self._base_schema(base)
        for rule in rules:
            if rule in PATTERNS:
                schema["pattern"] = PATTERNS[rule]
            elif rule is Rule.JSON:
                schema = {"$ref": "#/$defs/JsonValue"}
                self.defs["JsonValue"] = _JSON_VALUE_DEF
            elif rule is Rule.JSON_OBJECT:
                schema = {"type": "object", "additionalProperties": {"$ref": "#/$defs/JsonValue"}}
                self.defs["JsonValue"] = _JSON_VALUE_DEF
            else:
                schema.update(_RULE_FRAGMENTS.get(rule, {}))
        return schema

    def _base_schema(self, tp: Any) -> dict[str, Any]:
        args = union_args(tp)
        if args is not None:
            options = [arg for arg in args if arg is not type(None)]
            schemas = [self.type_schema(option) for option in options]
            if len(options) < len(args):
                schemas.append({"type": "null"})
            return schemas[0] if len(schemas) == 1 else {"oneOf": schemas}
        origin = typing.get_origin(tp)
        if origin is typing.Literal:
            return {"type": "string", "enum": list(typing.get_args(tp))}
        if origin is tuple:
            return {"type": "array", "items": self.type_schema(typing.get_args(tp)[0])}
        if origin is collections.abc.Mapping:
            return {
                "type": "object",
                "propertyNames": {"minLength": 1},
                "additionalProperties": self.type_schema(typing.get_args(tp)[1]),
            }
        if tp is str:
            return {"type": "string"}
        if tp is int:
            return {"type": "integer", "minimum": -(2**53 - 1), "maximum": 2**53 - 1}
        if tp is bool:
            return {"type": "boolean"}
        if tp is Any or tp is FrozenMap:
            return {}
        if isinstance(tp, type) and issubclass(tp, Value):
            name = tp.__name__
            if name not in self.defs:
                self.defs[name] = {}  # reserva, para recursão
                self.defs[name] = self.object_schema(tp, additional=False)
            return {"$ref": f"#/$defs/{name}"}
        raise TypeError(f"anotação sem esquema: {tp!r}")

    def object_schema(self, cls: type, *, additional: bool) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, tp, has_default in contract_fields(cls):
            if name == "extensions":
                continue
            properties[name] = self.type_schema(tp)
            if not has_default and not is_nullable(tp):
                required.append(name)
        if issubclass(cls, Value):
            try:
                key, tag = discriminator(cls)
            except TypeError:
                pass
            else:
                properties[key] = {"const": tag}
        doc = (cls.__doc__ or "").strip().split("\n\n")[0].replace("\n", " ")
        if doc.startswith(f"{cls.__name__}("):
            doc = ""  # docstring automática da dataclass: assinatura, não descrição
        schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": additional}
        if doc:
            schema["description"] = doc
        if required:
            schema["required"] = required
        return schema


def contract_schema(contract: type[Record]) -> dict[str, Any]:
    builder = _Builder()
    observation = issubclass(contract, ObservationRecord)
    body = builder.object_schema(contract, additional=observation)
    body["properties"] = {
        "schema": {"const": contract.SCHEMA},
        "kind": {"const": contract.KIND},
        **body["properties"],
    }
    major = contract.VERSION.split(".")[0]
    if issubclass(contract, StrictRecord):
        body["properties"]["schema_version"] = {"enum": sorted(contract.SUPPORTED_VERSIONS)}
    else:
        body["properties"]["schema_version"] = {"type": "string", "pattern": f"^{major}\\.(0|[1-9][0-9]*)$"}
    if contract.HASH_FIELD is not None:
        body.setdefault("required", [])
        body["required"].append(contract.HASH_FIELD)
    body["required"] = ["schema", "kind", "schema_version", *body.get("required", [])]
    tolerance = (
        "Contrato de observação: campo desconhecido só com MENOR acima; o leitor o guarda em extensions."
        if observation
        else "Contrato estrito: campo desconhecido e versão não suportada são recusados."
    )
    document = {
        "$schema": DIALECT,
        "title": contract.KIND,
        "description": f"{body.pop('description', f'Contrato {contract.KIND}.')} {tolerance}",
        "x-contract-version": contract.VERSION,
        **body,
    }
    if builder.defs:
        document["$defs"] = dict(sorted(builder.defs.items()))
    return document


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def expected_files() -> dict[str, str]:
    return {f"{contract.SCHEMA}.schema.json": render(contract_schema(contract)) for contract in CONTRACTS}


def drift(directory: Path = SCHEMAS_DIR) -> list[str]:
    """Os problemas entre o esquema gerado e o versionado; vazio quando não há deriva."""
    problems = []
    expected = expected_files()
    present = {path.name for path in directory.glob("*.schema.json")}
    for name, text in expected.items():
        path = directory / name
        if not path.exists():
            problems.append(f"falta {name}")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"{name} difere do gerado")
    for name in sorted(present - set(expected)):
        problems.append(f"{name} não corresponde a contrato nenhum")
    return problems


def write(directory: Path = SCHEMAS_DIR) -> None:
    expected = expected_files()
    for path in directory.glob("*.schema.json"):
        if path.name not in expected:
            path.unlink()
    for name, text in expected.items():
        (directory / name).write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="falha se o esquema versionado diverge do gerado")
    group.add_argument("--write", action="store_true", help="regrava o esquema versionado")
    args = parser.parse_args(argv)
    if args.write:
        write()
        print(f"{len(CONTRACTS)} esquemas gravados em {SCHEMAS_DIR}")
        return 0
    problems = drift()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print("rode: python -m conversational_commerce.contracts.schema_export --write", file=sys.stderr)
        return 1
    print(f"{len(CONTRACTS)} esquemas sem deriva")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
