#!/usr/bin/env python3
"""Fail closed when the ADR address book drifts.

The file number, H1 number, canonical status and the unique index are one
contract.  This checker is stdlib-only so the merge gate can run it before the
Django environment is installed.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ADR_FILE_RE = re.compile(r"^adr-(\d{3})-[a-z0-9-]+\.md$")
TITLE_RE = re.compile(r"^# ADR-(\d{3})\s*[:—-]\s*(.+?)\s*$", re.MULTILINE)
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)
INDEX_ROW_RE = re.compile(
    r"^\| \[(\d{3})\]\((adr-(\d{3})-[^)]+\.md)\) "
    r"\| (.+?) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$"
)
STATUS_VALUE_RE = re.compile(
    r"^(?:Proposto|Aceito|Aceito; emendado por ADR-\d{3}|Substituído por ADR-\d{3})$"
)
STATUS_TARGET_RE = re.compile(r"(?:emendado por|Substituído por) ADR-(\d{3})$")


@dataclass(frozen=True)
class Adr:
    number: str
    path: Path
    title: str
    status: str
    governance_header: str


@dataclass(frozen=True)
class IndexEntry:
    number: str
    filename: str
    title: str
    status: str
    owner: str
    date: str
    theme: str


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _read_adrs(root: Path, errors: list[str]) -> list[Adr]:
    decisions = root / "docs" / "decisions"
    adrs: list[Adr] = []
    for path in sorted(decisions.glob("adr-*.md")):
        match = ADR_FILE_RE.fullmatch(path.name)
        if match is None:
            errors.append(f"{_relative(path, root)}: nome fora do padrão adr-NNN-slug.md")
            continue
        file_number = match.group(1)
        text = path.read_text(encoding="utf-8")
        title_match = TITLE_RE.search(text)
        status_match = STATUS_RE.search(text)
        if title_match is None:
            errors.append(f"{_relative(path, root)}: título '# ADR-NNN — ...' ausente")
            continue
        if title_match.group(1) != file_number:
            errors.append(
                f"{_relative(path, root)}: arquivo ADR-{file_number}, título ADR-{title_match.group(1)}"
            )
        if status_match is None:
            errors.append(f"{_relative(path, root)}: campo '**Status:**' ausente")
            status = ""
        else:
            status = status_match.group(1)
            if STATUS_VALUE_RE.fullmatch(status) is None:
                errors.append(f"{_relative(path, root)}: status não canônico: {status!r}")
        governance_header = re.split(r"^---\s*$", text, maxsplit=1, flags=re.MULTILINE)[0]
        adrs.append(Adr(file_number, path, title_match.group(2), status, governance_header))
    return adrs


def _read_index(root: Path, errors: list[str]) -> list[IndexEntry]:
    path = root / "docs" / "decisions" / "README.md"
    if not path.is_file():
        errors.append(f"{_relative(path, root)}: índice ausente")
        return []
    entries: list[IndexEntry] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = INDEX_ROW_RE.fullmatch(line)
        if match is None:
            continue
        number, filename, linked_number, title, status, owner, date, theme = match.groups()
        if number != linked_number:
            errors.append(f"{_relative(path, root)}:{line_number}: número e link divergem")
        if not all((title, status, owner, date, theme)):
            errors.append(f"{_relative(path, root)}:{line_number}: coluna vazia")
        entries.append(IndexEntry(number, filename, title, status, owner, date, theme))
    return entries


def check(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    adrs = _read_adrs(root, errors)
    entries = _read_index(root, errors)

    by_number: dict[str, list[Adr]] = {}
    for adr in adrs:
        by_number.setdefault(adr.number, []).append(adr)
    for number, duplicates in sorted(by_number.items()):
        if len(duplicates) > 1:
            names = ", ".join(adr.path.name for adr in duplicates)
            errors.append(f"ADR-{number}: número duplicado em {names}")

    index_by_number: dict[str, list[IndexEntry]] = {}
    for entry in entries:
        index_by_number.setdefault(entry.number, []).append(entry)
    for number, duplicates in sorted(index_by_number.items()):
        if len(duplicates) > 1:
            errors.append(f"docs/decisions/README.md: ADR-{number} aparece {len(duplicates)} vezes")

    unique_adrs = {number: values[0] for number, values in by_number.items() if len(values) == 1}
    unique_entries = {
        number: values[0] for number, values in index_by_number.items() if len(values) == 1
    }
    for number, adr in sorted(unique_adrs.items()):
        entry = unique_entries.get(number)
        if entry is None:
            errors.append(f"{_relative(adr.path, root)}: ADR-{number} sem entrada no índice")
            continue
        if entry.filename != adr.path.name:
            errors.append(
                f"docs/decisions/README.md: ADR-{number} aponta para {entry.filename}, "
                f"esperado {adr.path.name}"
            )
        if entry.title != adr.title:
            errors.append(f"docs/decisions/README.md: título da ADR-{number} diverge do arquivo")
        if entry.status != adr.status:
            errors.append(
                f"docs/decisions/README.md: status da ADR-{number} é {entry.status!r}, "
                f"arquivo diz {adr.status!r}"
            )
        target_match = STATUS_TARGET_RE.search(adr.status)
        if target_match:
            target = target_match.group(1)
            if target == number:
                errors.append(f"{_relative(adr.path, root)}: ADR não pode emendar/substituir a si própria")
            elif target not in unique_adrs:
                errors.append(f"{_relative(adr.path, root)}: alvo ADR-{target} não existe")
            else:
                successor = unique_adrs[target]
                if re.search(rf"\bADR-{re.escape(number)}\b", successor.governance_header) is None:
                    errors.append(
                        f"{_relative(successor.path, root)}: alvo ADR-{target} não referencia "
                        f"a predecessora ADR-{number} no cabeçalho de governança"
                    )

    for number in sorted(set(unique_entries) - set(unique_adrs)):
        errors.append(f"docs/decisions/README.md: ADR-{number} indexada sem arquivo")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = check(args.root)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    count = len(list((args.root / "docs" / "decisions").glob("adr-*.md")))
    print(f"[OK] governança de ADRs: {count} números únicos, status canônicos e índice completo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
