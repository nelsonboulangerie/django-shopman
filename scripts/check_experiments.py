#!/usr/bin/env python3
"""Experimento vencido reprova a CI (R4 do WP-RELEASE-01, OC-20).

Versão paralela permanente é dívida (WP-RELEASE-01, invariante 14; ADR-043): todo
experimento nasce com ``remove_after`` e, vencido o prazo, o código da versão que
perdeu tem de sair. O resolvedor já devolve o padrão a todo mundo quando o prazo
passa (``shopman/shop/services/experience.py``); esta trava impede que o código e a
configuração fiquem para trás em silêncio.

O que reprova:

- **anotação de código** nas superfícies (``surfaces/**``): a linha
  ``// EXPERIMENT(<ref>) remove_after AAAA-MM-DD`` com a data já passada, ou
  malformada (sem ``remove_after``, data ilegível, ref fora do formato). Vale para
  qualquer marcador de comentário (``//``, ``<!-- -->``, ``/* */``). O molde literal
  ``EXPERIMENT(<ref>) remove_after AAAA-MM-DD``, que documenta a convenção, passa;
- **configuração semeada**: ``RuleConfig`` de ``ExperienceRule`` (ou qualquer objeto
  com ``variants`` e ``remove_after``) com data literal já passada, no ``seed`` e nos
  módulos de ``config/``, nos comandos de gestão de ``shopman/``, nos descritores de
  instância (``config/instances/*.json``) e em qualquer pasta ``fixtures``.

Data calculada (``timezone.localdate() + timedelta(...)``) não vence por construção
e não é lida. Stdlib só, sem importar Django.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPERIENCE_RULE_SUFFIX = "experience.ExperienceRule"
SURFACE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".mjs", ".cjs", ".vue", ".css", ".html"})
SKIP_PARTS = frozenset({
    "node_modules",
    ".nuxt",
    ".output",
    ".output-e2e",
    ".data",
    "dist",
    "coverage",
    "test-results",
    "playwright-report",
    "__pycache__",
    ".venv",
    "site-packages",
})

_MARKER = "EXPERIMENT("
_ANNOTATION = re.compile(
    r"EXPERIMENT\((?P<ref>[^)]*)\)\s+remove_after\s+(?P<date>\S+?)(?:\s|-->|\*/|$)"
)
_REF = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
# O molde da convenção, escrito para ensinar (``useExperience.ts``), não é anotação:
# ``<ref>`` e ``AAAA-MM-DD`` assim, literais. Qualquer outra coisa é conferida.
_TEMPLATE = ("<ref>", "AAAA-MM-DD")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _walk(base: Path, suffixes: Iterable[str]) -> Iterator[Path]:
    """Arquivos com o sufixo pedido, podando as pastas geradas sem entrar nelas."""
    wanted = set(suffixes)
    if not base.exists():
        return
    for current, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_PARTS)
        for name in sorted(files):
            path = Path(current) / name
            if path.suffix in wanted:
                yield path


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ── anotações de código nas superfícies ──────────────────────────────


def check_annotation_text(text: str, rel: str, today: date) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _MARKER not in line:
            continue
        match = _ANNOTATION.search(line)
        if match is None:
            findings.append(Finding(
                rel, number,
                "anotação de experimento malformada; o formato é "
                "'// EXPERIMENT(<ref>) remove_after AAAA-MM-DD'",
            ))
            continue
        ref = match.group("ref").strip()
        if (ref, match.group("date")) == _TEMPLATE:
            continue
        if not _REF.match(ref):
            findings.append(Finding(rel, number, f"ref de experimento inválido: {ref!r}"))
            continue
        when = _parse_date(match.group("date"))
        if when is None:
            findings.append(Finding(
                rel, number, f"EXPERIMENT({ref}): remove_after ilegível {match.group('date')!r}"
            ))
        elif when < today:
            findings.append(Finding(
                rel, number,
                f"EXPERIMENT({ref}) venceu em {when.isoformat()}: apague a versão que perdeu "
                "e a anotação",
            ))
    return findings


def check_surfaces(root: Path, today: date) -> list[Finding]:
    findings: list[Finding] = []
    for path in _walk(root / "surfaces", SURFACE_SUFFIXES):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _MARKER in text:
            findings.extend(check_annotation_text(text, _rel(path, root), today))
    return findings


# ── configuração semeada ─────────────────────────────────────────────


def _expired_params(params: dict, today: date) -> tuple[str, str] | None:
    """``(ref, data)`` se ``params`` é de experimento e o prazo literal passou."""
    value = params.get("remove_after")
    if not isinstance(value, str):
        return None
    when = _parse_date(value)
    if when is None:
        return (str(params.get("ref") or "?"), f"ilegível {value!r}")
    if when < today:
        return (str(params.get("ref") or "?"), when.isoformat())
    return None


def _is_experiment_params(obj: dict) -> bool:
    return "remove_after" in obj and "variants" in obj


def _json_objects(value) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_objects(child)


def check_json_text(text: str, rel: str, today: date) -> list[Finding]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    findings: list[Finding] = []
    seen: set[int] = set()
    for obj in _json_objects(data):
        candidates: list[dict] = []
        if str(obj.get("rule_path", "")).endswith(EXPERIENCE_RULE_SUFFIX):
            for holder in (obj, obj.get("config"), obj.get("fields")):
                if isinstance(holder, dict) and isinstance(holder.get("params"), dict):
                    candidates.append(holder["params"])
        if _is_experiment_params(obj):
            candidates.append(obj)
        for params in candidates:
            if id(params) in seen:
                continue
            seen.add(id(params))
            expired = _expired_params(params, today)
            if expired:
                findings.append(Finding(
                    rel, 1, f"experimento '{expired[0]}' semeado com remove_after vencido ({expired[1]})"
                ))
    return findings


def _literal_dict(node: ast.Dict) -> dict:
    """As chaves e valores constantes de um dict literal (o resto vira ``None``)."""
    out: dict = {}
    for key, value in zip(node.keys, node.values, strict=False):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            out[key.value] = value.value if isinstance(value, ast.Constant) else ...
    return out


def check_python_text(text: str, rel: str, today: date) -> list[Finding]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        literal = _literal_dict(node)
        if not _is_experiment_params(literal):
            continue
        expired = _expired_params(literal, today)
        if expired:
            findings.append(Finding(
                rel, node.lineno,
                f"experimento '{expired[0]}' semeado com remove_after vencido ({expired[1]})",
            ))
    return findings


def _seed_files(root: Path) -> Iterator[Path]:
    config = root / "config"
    for path in _walk(config, {".py"}):
        if "tests" in path.relative_to(config).parts:
            continue
        yield path
    yield from _walk(config / "instances", {".json"})
    for base in ("shopman", "packages"):
        for path in _walk(root / base, {".py"}):
            parts = path.parts
            if "management" in parts and "commands" in parts and "tests" not in parts:
                yield path
    for base in ("shopman", "packages", "config"):
        for path in _walk(root / base, {".py", ".json"}):
            if "fixtures" in path.parts:
                yield path


def check_seeds(root: Path, today: date) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[Path] = set()
    for path in _seed_files(root):
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "remove_after" not in text:
            continue
        rel = _rel(path, root)
        if path.suffix == ".json":
            findings.extend(check_json_text(text, rel, today))
        else:
            findings.extend(check_python_text(text, rel, today))
    return findings


def run(root: Path, today: date) -> list[Finding]:
    return check_surfaces(root, today) + check_seeds(root, today)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)

    findings = run(args.root, args.today)
    if findings:
        print("Experimento vencido ou malformado (R4 do release):", file=sys.stderr)
        for finding in findings:
            print(f"  {finding.render()}", file=sys.stderr)
        return 1
    print(f"Experimentos em dia ({args.today.isoformat()}): nenhuma anotação nem configuração vencida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
