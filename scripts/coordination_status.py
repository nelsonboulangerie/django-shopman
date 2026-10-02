#!/usr/bin/env python3
"""Leitura de coordenação: o que está em voo, medido no remoto, sem prosa no meio.

Sessão nova roda isto ANTES de ler o HANDOFF ou o BOARD. A prosa é escrita por outra
sessão e pode estar errada; o remoto não.

Funciona só com `git` (ls-remote, merge-base, rev-list). O `gh` é atalho para o título
real e o estado dos PRs quando existe e está autenticado, nunca dependência.

    python3 scripts/coordination_status.py            # busca o remoto e imprime
    python3 scripts/coordination_status.py --no-fetch # usa o que já está local
    python3 scripts/coordination_status.py --no-gh    # força o caminho só-git
    python3 scripts/coordination_status.py --strict   # sai 1 quando o resumo é ATENÇÃO

Como o "aberto" é medido sem `gh`: o GitHub apaga `refs/pull/<n>/merge` quando o PR
fecha (medido em 02/10: 5 refs de merge, 5 PRs abertos, um deles em conflito). PR aberto
que NASCEU em conflito pode não ter esse ref ainda; com `gh` essa lacuna some.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = REPO_ROOT / "docs" / "coordination" / "BOARD.md"

OPEN_PR_LIMIT = 15
ACTIVITY_WINDOW = timedelta(hours=24)
ORPHAN_CLAIM_AGE = timedelta(hours=12)
QUEUE_STUCK_AGE = timedelta(hours=1)

# Snapshots de resgate de 10 a 17/09 (`rescue/*`): guardam de propósito o que estava
# solto em worktrees. Aparecem contados, sem disparar ATENÇÃO (senão o resumo ficaria
# em ATENÇÃO para sempre e ninguém mais leria); a triagem deles é frente do BOARD.
SNAPSHOT_PREFIXES = ("rescue/",)
IGNORED_BRANCH_PREFIXES = ("gh-readonly-queue/",)


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def missing_objects(shas: set[str]) -> set[str]:
    """Os SHAs sem objeto local, numa chamada (`cat-file --batch-check`)."""
    if not shas:
        return set()
    result = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname)"],
        input="\n".join(sorted(shas)) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.split()[0] for line in result.stdout.splitlines() if line.endswith(" missing")}


_MISSING: set[str] = set()


def has_object(sha: str) -> bool:
    return sha not in _MISSING


def main_history(main: str) -> set[str]:
    """Todos os ancestrais do main, numa chamada: `sha in history` é o is-ancestor."""
    return set(git("rev-list", main).split())


def commit_infos(shas: set[str]) -> dict[str, tuple[datetime, str]]:
    """Data e assunto de vários commits numa chamada (só dos que existem localmente)."""
    present = sorted(s for s in shas if has_object(s))
    infos: dict[str, tuple[datetime, str]] = {}
    for i in range(0, len(present), 200):
        out = git("log", "--no-walk=unsorted", "--format=%H%x00%cI%x00%s", *present[i : i + 200])
        for line in out.splitlines():
            sha, when, subject = line.split("\x00", 2)
            infos[sha] = (datetime.fromisoformat(when).astimezone(UTC), subject)
    return infos


def ahead_of(sha: str, main: str) -> int:
    return int(git("rev-list", "--count", f"{main}..{sha}").strip() or 0)


def content_already_in_main(sha: str, main: str) -> bool:
    """O branch não acrescenta nada: todo commit tem equivalente no main (`git cherry`),
    ou mesclar no main dá a árvore do main."""
    cherry = git("cherry", main, sha, check=False).split()
    if cherry and all(mark == "-" for mark in cherry[::2]):
        return True
    result = subprocess.run(
        ["git", "merge-tree", "--write-tree", main, sha],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # conflito, ou git < 2.38
        return False
    main_tree = git("rev-parse", f"{main}^{{tree}}").strip()
    return result.stdout.split("\n", 1)[0].strip() == main_tree


def ls_remote(remote: str, *patterns: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for line in git("ls-remote", remote, *patterns).splitlines():
        sha, _, ref = line.partition("\t")
        if ref:
            refs[ref] = sha
    return refs


def fetch_missing(remote: str, shas: set[str]) -> None:
    missing = sorted(missing_objects(shas))
    for i in range(0, len(missing), 50):
        git("fetch", "--quiet", "--no-tags", remote, *missing[i : i + 50], check=False)
    _MISSING.clear()
    _MISSING.update(missing_objects(shas))


@dataclass
class OpenPR:
    number: int
    sha: str
    title: str
    note: str = ""


def gh_open_prs() -> list[OpenPR] | None:
    if not shutil.which("gh"):
        return None
    try:
        if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
            return None
        out = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--limit",
                "200",
                "--json",
                "number,title,headRefOid,isDraft,mergeable,autoMergeRequest",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    prs = []
    for item in json.loads(out):
        notes = []
        if item.get("isDraft"):
            notes.append("draft")
        if item.get("mergeable") == "CONFLICTING":
            notes.append("CONFLITO")
        if item.get("autoMergeRequest"):
            notes.append("auto-merge")
        prs.append(OpenPR(item["number"], item["headRefOid"], item["title"], ", ".join(notes)))
    return prs


def parse_board_time(text: str, now: datetime) -> datetime | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})", text)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime(y, mo, d, h, mi, tzinfo=UTC)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s+(\d{1,2})[:h](\d{2})\b", text)
    if m:
        d, mo, y, h, mi = m.groups()
        when = datetime(int(y or now.year), int(mo), int(d), int(h), int(mi), tzinfo=UTC)
        if not y and when > now + timedelta(days=1):
            when = when.replace(year=now.year - 1)
        return when
    return None


def orphan_claims(board: Path, now: datetime) -> tuple[list[str], list[str]]:
    """Linhas `EM_EXECUCAO` com hora mais velha que 12 h, e as que não têm hora legível."""
    if not board.exists():
        return [], []
    orphans, unreadable = [], []
    header: list[str] | None = None
    for line in board.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if not any("EM_EXECUCAO" in c for c in cells):
            continue
        since_cols = [i for i, h in enumerate(header) if "desde" in h or "hora" in h]
        source = " ".join(cells[i] for i in since_cols if i < len(cells)) or line
        when = parse_board_time(source, now)
        label = " | ".join(cells[:2])
        if when is None:
            unreadable.append(label)
        elif now - when > ORPHAN_CLAIM_AGE:
            hours = int((now - when).total_seconds() // 3600)
            orphans.append(f"{label}  (há {hours} h)")
    return orphans, unreadable


def fmt_age(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 120:
        return f"{minutes} min"
    hours = minutes // 60
    return f"{hours} h" if hours < 48 else f"{hours // 24} d"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--main", default="main")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--no-gh", action="store_true")
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--strict", action="store_true", help="sai 1 quando o resumo é ATENÇÃO")
    parser.add_argument("--now", help="ISO 8601; só para teste")
    args = parser.parse_args(argv)

    now = datetime.fromisoformat(args.now).astimezone(UTC) if args.now else datetime.now(UTC)
    remote = args.remote
    if not args.no_fetch:
        git("fetch", "--quiet", "--no-tags", remote, check=False)

    heads = ls_remote(remote, "refs/heads/*")
    pulls = ls_remote(remote, "refs/pull/*/head", "refs/pull/*/merge")
    main_sha = heads.get(f"refs/heads/{args.main}")
    if not main_sha:
        print(f"ERRO: {remote} não tem refs/heads/{args.main}")
        return 2

    pr_heads: dict[int, str] = {}
    pr_has_merge: set[int] = set()
    for ref, sha in pulls.items():
        m = re.fullmatch(r"refs/pull/(\d+)/(head|merge)", ref)
        if not m:
            continue
        if m.group(2) == "head":
            pr_heads[int(m.group(1))] = sha
        else:
            pr_has_merge.add(int(m.group(1)))

    branches = {ref.removeprefix("refs/heads/"): sha for ref, sha in heads.items() if ref != f"refs/heads/{args.main}"}
    queue = {b: s for b, s in branches.items() if b.startswith("gh-readonly-queue/")}
    live_branches = {b: s for b, s in branches.items() if not b.startswith(IGNORED_BRANCH_PREFIXES)}

    open_heads = {pr_heads[n] for n in pr_has_merge if n in pr_heads}
    wanted = {main_sha, *queue.values(), *live_branches.values(), *open_heads}
    fetch_missing(remote, wanted)
    if not has_object(main_sha):
        print(f"ERRO: não consegui o objeto do {args.main} ({main_sha[:9]})")
        return 2
    history = main_history(main_sha)
    infos = commit_infos(wanted)

    def commit_info(sha: str) -> tuple[datetime, str]:
        return infos[sha]

    def is_ancestor(sha: str, _main: str) -> bool:
        return sha in history

    attention: list[str] = []

    # 1. main
    when, subject = commit_info(main_sha)
    print(f"== {remote}/{args.main}")
    print(f"   {main_sha[:9]}  {when:%Y-%m-%d %H:%M} UTC  {subject}")

    # 2. fila de merge
    print("\n== Fila de merge (gh-readonly-queue)")
    if not queue:
        print("   (vazia)")
    for b, s in sorted(queue.items()):
        age = ""
        if has_object(s):
            q_when, _ = commit_info(s)
            age = fmt_age(now - q_when)
            if now - q_when > QUEUE_STUCK_AGE:
                attention.append(f"fila parada há {age}: {b}")
        print(f"   {b}  {s[:9]}  {age}")

    # 3. PRs abertos
    gh_prs = None if args.no_gh else gh_open_prs()
    print(
        f"\n== PRs abertos (os {OPEN_PR_LIMIT} mais novos)"
        + ("  [fonte: gh]" if gh_prs is not None else "  [fonte: git, ref de merge]")
    )
    if gh_prs is None:
        open_prs = []
        for n in sorted(pr_has_merge, reverse=True):
            sha = pr_heads.get(n)
            if not sha or (has_object(sha) and is_ancestor(sha, main_sha)):
                continue
            title = commit_info(sha)[1] if has_object(sha) else "(objeto ausente)"
            open_prs.append(OpenPR(n, sha, title, "título = último commit"))
    else:
        open_prs = sorted(gh_prs, key=lambda p: p.number, reverse=True)
    if not open_prs:
        print("   (nenhum)")
    for pr in open_prs[:OPEN_PR_LIMIT]:
        note = f"  [{pr.note}]" if pr.note else ""
        print(f"   #{pr.number}  {pr.sha[:9]}  {pr.title}{note}")
    if len(open_prs) > OPEN_PR_LIMIT:
        print(f"   … e mais {len(open_prs) - OPEN_PR_LIMIT}")

    # 4. atividade nas últimas 24 h
    print("\n== Branches com commit nas últimas 24 h (commits à frente do main)")
    recent = []
    for b, s in live_branches.items():
        if not has_object(s):
            continue
        b_when, _ = commit_info(s)
        if now - b_when <= ACTIVITY_WINDOW:
            recent.append((b_when, b, s))
    if not recent:
        print("   (nenhum)")
    for b_when, b, s in sorted(recent, reverse=True):
        print(f"   {b_when:%m-%d %H:%M}  +{ahead_of(s, main_sha):<3} {b}")

    # 5. branches sem PR
    print("\n== Branches à frente do main SEM PR (trabalho invisível)")
    pr_shas = set(pr_heads.values())
    invisible, redundant, snapshots, unknown = [], [], [], []
    for b, s in sorted(live_branches.items()):
        if s in pr_shas:
            continue
        if not has_object(s):
            unknown.append(b)
            continue
        if is_ancestor(s, main_sha):
            continue
        if b.startswith(SNAPSHOT_PREFIXES):
            snapshots.append(b)
        elif content_already_in_main(s, main_sha):
            redundant.append(b)
        else:
            b_when, b_subject = commit_info(s)
            invisible.append(f"+{ahead_of(s, main_sha):<3} {b_when:%Y-%m-%d}  {b}  ({b_subject})")
    if not invisible:
        print("   (nenhum)")
    for line in invisible:
        print(f"   {line}")
        attention.append("branch sem PR")
    if redundant:
        print(
            f"   conteúdo já no main (sobrando; antes de apagar, veja se alguma worktree o usa): {' '.join(redundant)}"
        )
    if snapshots:
        print(f"   snapshots rescue/* (fora do resumo; triagem no BOARD): {len(snapshots)}")
    if unknown:
        print(f"   sem objeto local, não medi: {' '.join(unknown)}")

    # 6. reivindicações órfãs
    print(f"\n== Reivindicações órfãs (EM_EXECUCAO há mais de 12 h em {_rel(args.board)})")
    if not args.board.exists():
        print("   (sem BOARD)")
    else:
        orphans, unreadable = orphan_claims(args.board, now)
        if not orphans and not unreadable:
            print("   (nenhuma)")
        for line in orphans:
            print(f"   {line}")
            attention.append("reivindicação órfã")
        for line in unreadable:
            print(f"   sem hora legível: {line}")
            attention.append("reivindicação sem hora")

    # 7. resumo
    print()
    if attention:
        print("ATENÇÃO: " + "; ".join(dict.fromkeys(attention)))
        return 1 if args.strict else 0
    print("OK")
    return 0


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
