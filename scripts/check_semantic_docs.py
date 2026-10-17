#!/usr/bin/env python3
"""Guard the package semantic map and Constitution section references."""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_MAP = Path("docs/reference/semantic-map.md")
CONSTITUTIONS = {
    Path("docs/constitution.md"),
    Path("docs/_archive/constitution-v1.md"),
}

PACKAGE_ENTRY_RE = re.compile(
    r"^\*\*Diretório físico:\*\* `packages/([a-z][a-z0-9_]*)/`\s*$", re.MULTILINE
)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
REFERENCE_DEFINITION_RE = re.compile(r"^\s*\[([^\]]+)\]:\s*(\S+)", re.MULTILINE)
REFERENCE_LINK_RE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
SHORTCUT_REFERENCE_RE = re.compile(r"(?<![!\[])\[([^\]]+)\](?![\[(])")
SECTION_SUFFIX_RE = re.compile(
    r"^\s*(?:[-—:,]\s*)?(?:(?:vigente|atual|canonica|canonical)\s*)?"
    r"(?:§\s*`?\d|c\s*`?\d|(?:secao|section|clausula|clause|item)\s*`?c?\s*\d)"
)
BARE_CONSTITUTION_SECTION_RE = re.compile(
    r"(?:"
    r"(?:\bconstituicao|\bconstitution)(?:\s+v\d+)?\b"
    r"(?:\s+(?:vigente|atual|canonica|canonical))?"
    r"\s*`?\s*(?:[-—:,]\s*)?"
    r"(?:§\s*`?\d|c\s*`?\d|(?:secao|section|clausula|clause|item)\s*`?c?\s*\d)|"
    r"(?:docs/)?constitution(?:-v\d+)?\.md`?"
    r"(?:\s+(?:vigente|atual|canonica|canonical))?"
    r"\s*(?:[-—:,]\s*)?"
    r"(?:§\s*`?\d|c\s*`?\d|(?:secao|section|clausula|clause|item)\s*`?c?\s*\d)"
    r")",
)
UNFRAGMENTED_SECTION_RE = re.compile(
    r"\]\([^)]*(?:constitution|constituicao)[^)]*\.md\)"
    r"\s*(?:[-—:,]\s*)?(?:(?:vigente|atual|canonica|canonical)\s*)?"
    r"(?:§\s*`?\d|c\s*`?\d|(?:secao|section|clausula|clause|item)\s*`?c?\s*\d)",
    re.IGNORECASE,
)
REQUIRED_FIELDS = ("Pergunta canônica", "Verbos", "Estados e sinais", "Eventos")


def _plain(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )


def _heading_slug(title: str) -> str:
    title = re.sub(r"\s+#+\s*$", "", title.strip().lower())
    title = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE)
    return re.sub(r"[ ]+", "-", title)


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    occurrences: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if not match:
            continue
        base = _heading_slug(match.group(1))
        count = occurrences.get(base, 0)
        occurrences[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def check_package_bijection(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    package_root = root / "packages"
    semantic_map = root / SEMANTIC_MAP
    if not semantic_map.is_file():
        return [f"missing semantic map: {SEMANTIC_MAP}"]
    actual = {path.name for path in package_root.iterdir() if path.is_dir() and not path.name.startswith(".")}
    entries = PACKAGE_ENTRY_RE.findall(semantic_map.read_text(encoding="utf-8"))
    documented = set(entries)
    duplicates = sorted({name for name in entries if entries.count(name) > 1})
    if duplicates:
        errors.append(f"semantic map has duplicate package entries: {duplicates}")
    missing = sorted(actual - documented)
    unknown = sorted(documented - actual)
    if missing:
        errors.append(f"semantic map is missing physical packages: {missing}")
    if unknown:
        errors.append(f"semantic map names nonexistent packages: {unknown}")

    text = semantic_map.read_text(encoding="utf-8")
    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
    by_name = {section.splitlines()[0].strip(): section for section in sections}
    for name in sorted(documented):
        section = by_name.get(name, "")
        for field in REQUIRED_FIELDS:
            if f"**{field}:**" not in section:
                errors.append(f"semantic map package {name!r} is missing field {field!r}")
    return errors


def _iter_markdown(root: Path):
    for path in sorted(root.rglob("*.md")):
        if any(part in {".git", ".venv", "node_modules"} for part in path.parts):
            continue
        yield path


def check_constitution_references(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    for source in _iter_markdown(root):
        text = source.read_text(encoding="utf-8")
        relative_source = source.relative_to(root)

        def check_target(
            label: str,
            raw_target: str,
            *,
            source: Path = source,
            relative_source: Path = relative_source,
        ) -> None:
            target = raw_target.strip().strip("<>")
            path_part, separator, fragment = target.partition("#")
            resolved = (source.parent / unquote(path_part)).resolve()
            try:
                relative_target = resolved.relative_to(root)
            except ValueError:
                return
            if relative_target not in CONSTITUTIONS:
                return
            if relative_target == Path("docs/_archive/constitution-v1.md") and "histor" not in _plain(label):
                errors.append(
                    f"{relative_source}: archived Constitution link must say historical: {label!r}"
                )
            if not separator:
                return
            if not resolved.is_file():
                errors.append(f"{relative_source}: Constitution link target is missing: {raw_target}")
                return
            anchors = anchor_cache.setdefault(resolved, markdown_anchors(resolved))
            decoded = unquote(fragment).lower()
            if decoded not in anchors:
                errors.append(
                    f"{relative_source}: nonexistent Constitution anchor #{fragment} in {relative_target}"
                )

        definitions = {
            reference.strip().lower(): raw_target
            for reference, raw_target in REFERENCE_DEFINITION_RE.findall(text)
        }
        reference_uses = [
            (match.group(1), (match.group(2) or match.group(1)).strip().lower(), match.end())
            for match in REFERENCE_LINK_RE.finditer(text)
        ]
        without_definitions = REFERENCE_DEFINITION_RE.sub("", text)
        reference_uses.extend(
            (match.group(1), match.group(1).strip().lower(), None)
            for match in SHORTCUT_REFERENCE_RE.finditer(without_definitions)
            if match.group(1).strip().lower() in definitions
        )
        for label, reference, end in reference_uses:
            raw_target = definitions.get(reference)
            if raw_target:
                path_part, separator, _fragment = raw_target.strip().strip("<>").partition("#")
                resolved = (source.parent / unquote(path_part)).resolve()
                try:
                    relative_target = resolved.relative_to(root)
                except ValueError:
                    relative_target = None
                trailing_section = end is not None and SECTION_SUFFIX_RE.match(_plain(text[end:]))
                if (
                    relative_target in CONSTITUTIONS
                    and not separator
                    and (
                        BARE_CONSTITUTION_SECTION_RE.search(_plain(label))
                        or trailing_section
                    )
                ):
                    errors.append(
                        f"{relative_source}: Constitution section follows a link without an anchor"
                    )
                check_target(label, raw_target)

        for label, raw_target in MARKDOWN_LINK_RE.findall(text):
            check_target(label, raw_target)

        without_links = MARKDOWN_LINK_RE.sub("", text)
        without_links = REFERENCE_LINK_RE.sub("", without_links)
        without_links = REFERENCE_DEFINITION_RE.sub("", without_links)
        for label, reference, end in reference_uses:
            if end is None and reference in definitions:
                without_links = without_links.replace(f"[{label}]", "")
        normalized = _plain(without_links)
        if BARE_CONSTITUTION_SECTION_RE.search(normalized):
            errors.append(
                f"{relative_source}: bare Constitution section citation; use a verified Markdown anchor"
            )
        if UNFRAGMENTED_SECTION_RE.search(_plain(text)):
            errors.append(
                f"{relative_source}: Constitution section follows a link without an anchor"
            )
    return errors


def check_repository(root: Path = ROOT) -> list[str]:
    return check_package_bijection(root) + check_constitution_references(root)


def main() -> int:
    errors = check_repository()
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        print(f"semantic docs drift: {len(errors)} failure(s)", file=sys.stderr)
        return 1
    print("[OK] semantic map matches physical packages")
    print("[OK] Constitution references use existing anchors")
    print("semantic docs: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
