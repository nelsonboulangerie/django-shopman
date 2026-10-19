#!/usr/bin/env python3
"""Validate live documentation links, historical debt and the plan inventory.

The checker is intentionally stdlib-only: documentation governance must run before
the application environment is installed.  Live documentation is held to zero debt;
archived material is held to a checked-in list of known broken links, LINK BY LINK:
fixing an old link never pays for a new broken one, and the list only shrinks.
Every Markdown file of the repository is scanned (not only ``docs/``); outside the
historical directories of ``docs/`` everything is live.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

HISTORICAL_PARTS = {"_archive", "_quarantine", "completed", "coordination", "reports"}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
LINE_FRAGMENT_RE = re.compile(r"L\d+(?:-L\d+)?", re.IGNORECASE)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
BASELINE_FILE = Path("docs/governance/docs-link-debt.json")
PLAN_INDEX = Path("docs/plans/INDEX.md")
PLAN_README = Path("docs/plans/README.md")
SKIPPED_PARTS = {
    ".git", ".venv", "node_modules", ".nuxt", ".output", ".claude", ".codex",
    "__pycache__", ".pytest_cache", "dist", "coverage", "playwright-report", "test-results",
}


@dataclass(frozen=True)
class Debt:
    source: Path
    line: int
    destination: str
    kind: str

    def render(self, root: Path) -> str:
        source = self.source.relative_to(root)
        return f"{source}:{self.line}: {self.kind}: {self.destination}"

    def key(self, root: Path) -> tuple[str, str, str]:
        """Identidade do link sem o número da linha: editar o arquivo não mexe nela."""
        return (self.source.relative_to(root).as_posix(), self.destination, self.kind)


def _is_historical(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root / "docs").parts
    except ValueError:
        return False
    return bool(set(parts) & HISTORICAL_PARTS)


def _markdown_lines(path: Path, *, strip_inline_code: bool = True) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    fence: str | None = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        marker = FENCE_RE.match(raw)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            continue
        if fence is None:
            lines.append((number, INLINE_CODE_RE.sub("", raw) if strip_inline_code else raw))
    return lines


def _links(path: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in _markdown_lines(path):
        for match in LINK_RE.finditer(line):
            found.append((number, match.group(1) or match.group(2)))
    return found


def _slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = INLINE_CODE_RE.sub(lambda match: match.group(0).strip("`"), text)
    text = unicodedata.normalize("NFC", text).casefold()
    text = "".join(char for char in text if char.isalnum() or char in " _-")
    return text.replace(" ", "-").strip("-")


def _anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: Counter[str] = Counter()
    for _, line in _markdown_lines(path, strip_inline_code=False):
        match = HEADING_RE.match(line)
        if match is None:
            continue
        base = _slug(match.group(1))
        if not base:
            continue
        occurrence = seen[base]
        seen[base] += 1
        anchors.add(base if occurrence == 0 else f"{base}-{occurrence}")
    return anchors


def _resolve(source: Path, destination: str, root: Path) -> tuple[Path | None, str]:
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc:
        return None, ""
    raw_path = unquote(parsed.path)
    if not raw_path:
        return source, unquote(parsed.fragment)
    target = Path(raw_path) if raw_path.startswith("/") else source.parent / raw_path
    return target.resolve(), unquote(parsed.fragment)


def link_debt(root: Path) -> tuple[list[Debt], list[Debt]]:
    root = root.resolve()
    live: list[Debt] = []
    historical: list[Debt] = []
    for source in _markdown_sources(root):
        bucket = historical if _is_historical(source, root) else live
        for line, destination in _links(source):
            target, fragment = _resolve(source, destination, root)
            if target is None:
                continue
            try:
                target.relative_to(root)
            except ValueError:
                bucket.append(Debt(source, line, destination, "outside_repo"))
                continue
            if not target.exists():
                bucket.append(Debt(source, line, destination, "missing_target"))
                continue
            if fragment and target.is_file() and target.suffix.lower() == ".md":
                if LINE_FRAGMENT_RE.fullmatch(fragment):
                    continue
                if fragment.casefold() not in _anchors(target):
                    bucket.append(Debt(source, line, destination, "missing_anchor"))
    return live, historical


def _markdown_sources(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not set(path.relative_to(root).parts[:-1]) & SKIPPED_PARTS
    )


def _historical_baseline(root: Path) -> Counter[tuple[str, str, str]]:
    path = root / BASELINE_FILE
    if not path.is_file():
        raise ValueError(f"{BASELINE_FILE}: baseline ausente")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Counter(
        (str(item["source"]), str(item["destination"]), str(item["kind"]))
        for item in data["historical_links"]
    )


def write_baseline(root: Path) -> int:
    """Regrava o baseline com a dívida histórica atual (uso: depois de PAGAR dívida)."""
    root = root.resolve()
    _live, historical = link_debt(root)
    links = sorted(debt.key(root) for debt in historical)
    data = {
        "scope": (
            "Links quebrados conhecidos em diretórios históricos de docs/, um por um. "
            "Dívida viva tem teto zero; esta lista só encolhe."
        ),
        "historical_links": [
            {"source": source, "destination": destination, "kind": kind}
            for source, destination, kind in links
        ],
    }
    (root / BASELINE_FILE).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(links)


def _live_plans(root: Path) -> set[Path]:
    plans = root / "docs" / "plans"
    return {
        path.relative_to(plans)
        for path in plans.rglob("*.md")
        if path.name not in {"README.md", "INDEX.md"} and not _is_historical(path, root)
    }


def _indexed_plans(root: Path) -> set[Path]:
    index = root / PLAN_INDEX
    if not index.is_file():
        return set()
    indexed: set[Path] = set()
    for _, destination in _links(index):
        target, _ = _resolve(index, destination, root)
        if target is None:
            continue
        try:
            indexed.add(target.relative_to(root / "docs" / "plans"))
        except ValueError:
            pass
    return indexed


def _active_archive_rows(root: Path) -> list[str]:
    path = root / PLAN_README
    if not path.is_file():
        return [f"{PLAN_README}: arquivo ausente"]
    prefix = path.read_text(encoding="utf-8").split("## Concluídos Recentemente", 1)[0]
    violations: list[str] = []
    for line_number, line in enumerate(prefix.splitlines(), 1):
        if not line.startswith("|"):
            continue
        match = LINK_RE.search(line)
        if match is None:
            continue
        destination = match.group(1) or match.group(2)
        target, _ = _resolve(path, destination, root)
        if target is not None and _is_historical(target, root):
            violations.append(f"{PLAN_README}:{line_number}: plano ativo aponta para arquivo histórico: {destination}")
    return violations


def check(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    live, historical = link_debt(root)
    errors.extend(debt.render(root) for debt in live)

    try:
        baseline = _historical_baseline(root)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        baseline = Counter()
    actual = Counter(debt.key(root) for debt in historical)
    rendered = {debt.key(root): debt.render(root) for debt in historical}
    for key in sorted(actual - baseline):
        errors.append(f"dívida histórica nova (fora do baseline): {rendered[key]}")
    for source, destination, kind in sorted(baseline - actual):
        errors.append(
            f"{BASELINE_FILE}: o link não está mais quebrado, apague a entrada: "
            f"{source}: {kind}: {destination}"
        )

    live_plans = _live_plans(root)
    indexed_plans = _indexed_plans(root)
    for path in sorted(live_plans - indexed_plans):
        errors.append(f"{PLAN_INDEX}: plano vivo não indexado: {path}")
    errors.extend(_active_archive_rows(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="regrava o baseline com a dívida histórica atual (depois de consertar links)",
    )
    args = parser.parse_args()
    if args.write_baseline:
        print(f"[OK] baseline regravado: {write_baseline(args.root)} links históricos")
        return 0
    errors = check(args.root)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    live, historical = link_debt(args.root.resolve())
    counts = Counter(debt.kind for debt in historical)
    summary = ", ".join(f"{kind}={counts[kind]}" for kind in sorted(counts)) or "zero"
    print(
        f"[OK] governança documental: dívida viva={len(live)}; "
        f"dívida histórica = baseline, link a link ({summary}); planos vivos indexados={len(_live_plans(args.root.resolve()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
