#!/usr/bin/env python3
"""Hook ``PreToolUse`` (Bash): ``gh pr merge`` só com preflight verde do HEAD.

DEV-2026-098. Regra do dono (23/11/2026): "auto só com o local verde". Até aqui
ela era texto; este hook a põe no ponto de promoção, para toda sessão do Claude
Code neste repositório (registrado em ``.claude/settings.json``). Codex e
humanos seguem pelo ``make ready pr=<N>``, que faz a mesma conferência.

A conferência é pelo CONTEÚDO: o hash da árvore do commit que o PR aponta
agora (``gh api .../commits/<sha>``) tem de ter evidência ``preflight``/``full``
verde em ``~/Library/Caches/shopman-local-ci/evidence/<tree>.json`` — gravada
por QUALQUER worktree desta máquina. Por isso a coordenação, que enfileira PR
de outra sessão, passa quando aquela sessão rodou o preflight.

Saídas declaradas, nunca silenciosas:

* ``SHOPMAN_SEM_PREFLIGHT="motivo" gh pr merge ...`` — urgência, agente sem
  ambiente local, PR só de documentação; o motivo vai para
  ``overrides.jsonl`` ao lado das evidências;
* ``SHOPMAN_PREFLIGHT_GUARD=off`` no ambiente da sessão — desliga o hook
  (rollback sem commit).

Falha de infraestrutura (sem ``gh``, sem rede, PR não encontrado) deixa
passar: a CI continua sendo a autoridade, e o hook não pode travar a esteira.
``--disable-auto`` e merge de outro repositório passam direto.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO = "nelsonboulangerie/django-shopman"
PROMOTABLE = {"preflight", "full"}
MERGE = re.compile(r"(^|[\s;&|(])gh\s+pr\s+merge\b")


def state_dir() -> Path:
    return Path(os.environ.get("SHOPMAN_LOCAL_CI_HOME") or Path.home() / "Library/Caches/shopman-local-ci")


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, timeout=20).stdout.strip()


def pr_from_command(cmd: str) -> str | None:
    """O número (ou URL) logo depois de ``gh pr merge``; None = PR do branch atual."""
    tail = MERGE.split(cmd, maxsplit=1)[-1]
    try:
        tokens = shlex.split(tail)
    except ValueError:
        tokens = tail.split()
    for tok in tokens:
        if tok in {"&&", "||", ";", "|"}:
            break
        if re.fullmatch(r"\d+", tok) or re.search(r"/pull/\d+", tok):
            return tok
        if not tok.startswith("-") and re.fullmatch(r"[\w./-]+", tok) and "/" not in tok:
            return tok  # nome do branch
    return None


def decide(cmd: str, cwd: str | None = None) -> tuple[bool, str]:
    if not MERGE.search(cmd):
        return True, ""
    if "--disable-auto" in cmd:
        return True, ""
    repo_flag = re.search(r"(?:-R|--repo)[\s=]+(\S+)", cmd)
    if repo_flag and repo_flag.group(1).strip("'\"") != REPO:
        return True, ""
    override = re.search(r"SHOPMAN_SEM_PREFLIGHT=(\"[^\"]+\"|'[^']+'|\S+)", cmd)
    pr = pr_from_command(cmd)
    if override and override.group(1).strip("'\""):
        state_dir().mkdir(parents=True, exist_ok=True)
        with open(state_dir() / "overrides.jsonl", "a") as fh:
            fh.write(json.dumps({
                "pr": pr, "reason": override.group(1).strip("'\""), "via": "hook",
                "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "cwd": cwd,
            }, ensure_ascii=False) + "\n")
        return True, ""
    try:
        args = ["pr", "view", *([pr] if pr else []), "-R", REPO, "--json", "number,headRefOid,isDraft"]
        info = json.loads(gh(*args))
        tree = gh("api", f"repos/{REPO}/commits/{info['headRefOid']}", "-q", ".commit.tree.sha")
    except Exception:  # noqa: BLE001 — infraestrutura: a CI decide
        return True, ""
    path = state_dir() / "evidence" / f"{tree}.json"
    evidence = json.loads(path.read_text()) if path.exists() else None
    if evidence and evidence.get("status") == "pass" and evidence.get("level") in PROMOTABLE:
        return True, ""
    n = info["number"]
    found = f"a evidência dela é {evidence['level']}/{evidence['status']}" if evidence else "não há evidência para ela nesta máquina"
    return False, (
        f"⛔ PR #{n}: o HEAD {info['headRefOid'][:9]} (árvore {tree[:12]}) não tem preflight verde — {found}.\n"
        "Regra do dono (23/11): auto só com o local verde. Na worktree do PR:\n"
        f"  make preflight && make ready pr={n}\n"
        "Sem ambiente local, urgência ou PR só de docs: declare o motivo no mesmo comando,\n"
        f"  SHOPMAN_SEM_PREFLIGHT=\"<motivo>\" gh pr merge {n} --auto\n"
        "(docs/plans/CI-DX-LOCAL-FIRST-PLAN.md)"
    )


def main() -> int:
    if os.environ.get("SHOPMAN_PREFLIGHT_GUARD", "").lower() in {"off", "0", "false"}:
        return 0
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    ok, message = decide(cmd, payload.get("cwd"))
    if ok:
        return 0
    print(message, file=sys.stderr)
    return 2  # PreToolUse: 2 bloqueia e devolve o stderr ao agente


if __name__ == "__main__":
    raise SystemExit(main())
