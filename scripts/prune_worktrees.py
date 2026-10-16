#!/usr/bin/env python
"""Remove worktrees mortas — e recusa tocar na que tem sessão viva dentro.

O critério óbvio ("o branch já está no main e a árvore está limpa, logo não há
nada a perder") é verdadeiro sobre o GIT e falso sobre o AGENTE: uma sessão que
ainda está de pé perde o diretório de trabalho debaixo dela, junto com tudo que
é gitignored e não volta num `git worktree add` — ``.env``, ``node_modules``,
``.nuxt``, ``.output``, venv. Aconteceu em 15/10/2026: 185 worktrees foram
removidas com o critério só-git e duas sessões Claude vivas ficaram sem chão.

Esta ferramenta acrescenta a única checagem que faltava: **antes de remover,
pergunta se alguma sessão viva está (ou esteve) trabalhando ali.** Ela só
remove automaticamente worktrees sob ``<checkout principal>/.claude/worktrees``.
Worktrees geridas por Codex, DeepSeek ou outra ferramenta ficam fora do escopo:
sem conhecer o registro de sessões desses agentes, ausência de processo Claude
não é prova de abandono.

Como identifica sessão viva:

1. Processos ``claude`` com ``--resume=<session-id>``: o id mapeia para o
   transcript em ``~/.claude/projects/<slug>/<session-id>.jsonl``, e o transcript
   guarda o ``cwd`` da sessão. É a prova mais forte — o processo está rodando
   AGORA.
2. Opcionalmente (``--recent-hours``), transcripts cujo ``cwd`` é a worktree e
   cuja última atividade é recente. Pega a sessão que está entre turnos e não tem
   processo filho no instante da medição.

Sem ``--apply`` a ferramenta só relata: é o modo para revisar antes de apagar.

Uso:
    python3 scripts/prune_worktrees.py                 # relatório (dry-run)
    python3 scripts/prune_worktrees.py --apply         # remove as seguras
    python3 scripts/prune_worktrees.py --recent-hours 24
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
_RESUME_RE = re.compile(r"--resume=([0-9a-fA-F-]{8,})")


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou: {result.stderr.strip()}")
    return result.stdout


@dataclass
class Session:
    """Uma sessão de agente conhecida por transcript."""

    session_id: str
    cwd: str
    last_activity: float
    live: bool = False


def _read_cwd(transcript: Path) -> str:
    try:
        with transcript.open() as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("cwd"):
                    return str(data["cwd"])
    except OSError:
        pass
    return ""


def live_session_ids() -> set[str]:
    """Ids de sessão com processo ``claude --resume=<id>`` rodando agora."""
    try:
        listing = subprocess.run(["pgrep", "-fl", "claude"], capture_output=True, text=True).stdout
    except OSError:
        return set()
    return {m.group(1) for m in (_RESUME_RE.search(line) for line in listing.splitlines()) if m}


def known_sessions() -> list[Session]:
    live = live_session_ids()
    sessions: list[Session] = []
    if not CLAUDE_PROJECTS.exists():
        return sessions
    for transcript in CLAUDE_PROJECTS.glob("*/*.jsonl"):
        cwd = _read_cwd(transcript)
        if not cwd:
            continue
        try:
            mtime = transcript.stat().st_mtime
        except OSError:
            continue
        sessions.append(
            Session(
                session_id=transcript.stem,
                cwd=cwd,
                last_activity=mtime,
                live=transcript.stem in live,
            )
        )
    return sessions


@dataclass
class Worktree:
    path: Path
    branch: str
    dirty: int
    merged: bool
    sessions: list[Session] = field(default_factory=list)
    managed: bool = True

    @property
    def safe(self) -> bool:
        return self.managed and self.merged and self.dirty == 0 and not self.sessions


def inspect(recent_hours: float) -> tuple[list[Worktree], Path]:
    """Analisa os worktrees do repositório.

    A árvore principal é a PRIMEIRA entrada de ``git worktree list`` — não o
    diretório do script. A diferença importa: rodando de dentro de um worktree,
    ``Path(__file__).parents[1]`` aponta para ele mesmo, e a árvore principal
    (que é justamente a que não pode ser removida) entraria na lista como
    candidata.
    """
    out = _git("worktree", "list", "--porcelain")
    paths = [Path(line.split(" ", 1)[1]) for line in out.splitlines() if line.startswith("worktree ")]
    if not paths:
        return [], Path.cwd()
    main_checkout = paths[0]
    managed_root = main_checkout / ".claude" / "worktrees"

    sessions = known_sessions()
    cutoff = time.time() - recent_hours * 3600 if recent_hours > 0 else None

    worktrees: list[Worktree] = []
    for path in paths:
        if path == main_checkout or not path.is_dir():
            continue
        try:
            branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=path).strip()
        except RuntimeError:
            continue
        dirty = sum(1 for line in _git("status", "--porcelain", cwd=path).splitlines() if line)
        merged = False
        if branch not in {"HEAD", ""}:
            merged = (
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", branch, "origin/main"],
                    cwd=str(path),
                    capture_output=True,
                ).returncode
                == 0
            )
        # Comparação exata de caminho, em texto: `Path.resolve()` colapsa um
        # caminho inexistente e faria o worktree `~/.codex/worktrees/<nome>/django-shopman`
        # casar com qualquer sessão de mesmo basename.
        target = str(path)
        related = [session for session in sessions if session.cwd == target]
        if cutoff is not None:
            related = [s for s in related if s.live or s.last_activity >= cutoff]
        worktrees.append(
            Worktree(
                path=path,
                branch=branch,
                dirty=dirty,
                merged=merged,
                sessions=related,
                managed=path.is_relative_to(managed_root),
            )
        )
    return worktrees, main_checkout


def _human_age(seconds: float) -> str:
    minutes = int((time.time() - seconds) // 60)
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes // 60
    return f"{hours}h" if hours < 48 else f"{hours // 24}d"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove worktrees mortas sem derrubar sessao viva.")
    parser.add_argument("--apply", action="store_true", help="Remove as worktrees seguras.")
    parser.add_argument(
        "--recent-hours",
        type=float,
        default=0.0,
        help=(
            "Também protege a worktree cuja sessão teve atividade nas últimas N horas, "
            "mesmo sem processo vivo (default: 0 = só processo vivo)."
        ),
    )
    args = parser.parse_args(argv)

    worktrees, main_checkout = inspect(args.recent_hours)

    protected = [w for w in worktrees if w.sessions]
    foreign = [w for w in worktrees if not w.managed and not w.sessions]
    dirty = [w for w in worktrees if w.managed and w.dirty and not w.sessions]
    unmerged = [w for w in worktrees if w.managed and not w.merged and not w.dirty and not w.sessions]
    safe = [w for w in worktrees if w.safe]

    print(f"worktrees analisadas: {len(worktrees)}")
    print(f"  protegidas (tem sessao):  {len(protected)}")
    print(f"  fora do escopo do Claude: {len(foreign)}")
    print(f"  sujas:                    {len(dirty)}")
    print(f"  branch fora do main:      {len(unmerged)}")
    print(f"  seguras para remover:     {len(safe)}")

    if protected:
        print("\nPROTEGIDAS (uma sessao trabalha ou trabalhou aqui):")
        for worktree in protected:
            marks = ", ".join(
                f"{s.session_id[:8]}{' VIVA' if s.live else ''} ({_human_age(s.last_activity)})"
                for s in worktree.sessions
            )
            print(f"  {worktree.path.name}  [{worktree.branch}]  {marks}")

    if safe:
        print("\nSEGURAS PARA REMOVER (Claude, sem sessao, limpas e no main):")
        for worktree in safe:
            print(f"  {worktree.path.name}  [{worktree.branch}]")

    if not args.apply:
        print("\n(dry-run: nada foi removido. Use --apply para remover as seguras.)")
        return 0

    removed = 0
    for worktree in safe:
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree.path)],
            cwd=str(main_checkout),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            removed += 1
            print(f"removida: {worktree.path.name} [{worktree.branch}]")
        else:
            print(f"FALHOU {worktree.path.name}: {result.stderr.strip()}", file=sys.stderr)
    subprocess.run(["git", "worktree", "prune"], cwd=str(main_checkout), capture_output=True)
    print(f"\nremovidas: {removed} | preservadas: {len(worktrees) - removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
