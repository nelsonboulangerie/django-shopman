#!/usr/bin/env python
"""Todo PR declara o que deixou de fora, e cada item tem uma issue com dono.

Por que existe (dono, 12/11/2026): "Você decide não fazer, por algum motivo, e
fica por isso mesmo... COMO saberei o que ficou para trás?" O agente fecha o PR
com um parágrafo "Ficou de fora: X, Y" no relatório, o relatório some no chat, e
X e Y dormem para sempre. A esteira (commit → push → PR → fila) cuidava do que
foi FEITO; nada cuidava do que foi ADIADO. Regra sem trava é lembrete.

A trava: o corpo do PR tem a seção ``## Ficou de fora`` e ela diz, literalmente,
``nada``, ou lista itens em que cada linha cita uma issue (``#N``) com o label
``ficou-de-fora``. A issue aparece em ``gh issue list``, no ``make inflight`` e
no lembrete diário; o parágrafo no chat não aparece em lugar nenhum.

Isento: PR de robô (Dependabot), PR em draft (o WIP ainda não terminou de
decidir), PR aberto antes da trava nascer, e o evento ``merge_group`` (o corpo
já foi conferido no PR).

Uso:
    python scripts/check_ficou_de_fora.py                      # no CI (GITHUB_EVENT_PATH)
    python scripts/check_ficou_de_fora.py --pr 2298            # local, pelo gh
    python scripts/check_ficou_de_fora.py --body-file corpo.md # só o texto, sem rede
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LABEL = "ficou-de-fora"
SECTION = "Ficou de fora"
#: PR aberto antes disto não tinha como conhecer a regra.
CUTOFF = "2026-11-12T13:00:00Z"
BOT_LOGINS = {"dependabot", "app/dependabot", "github-actions", "app/github-actions"}

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_ISSUE_REF = re.compile(r"(?<![\w/&])#(\d+)\b")
_NOTHING = re.compile(r"^[-*\s]*nada[.!\s]*$", re.I)
_LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+")

HOW_TO = f"""\
Como resolver:
  1. Para cada coisa que este PR decidiu NÃO fazer, abra uma issue:
       gh issue create --label {LABEL} --title "<o que falta>" \\
         --body "Deixado de fora por #<este PR>. Motivo: <por quê>. Pronto quando: <critério>."
  2. No corpo do PR, a seção:
       ## {SECTION}
       - <o que falta> (#<issue>)
     ou, se nada ficou de fora:
       ## {SECTION}
       nada
  3. Edite o corpo (gh pr edit <N> --body-file ...). O check roda de novo sozinho."""


def section(body: str) -> str | None:
    """O texto da seção ``## Ficou de fora``, sem comentários HTML; None se não existe."""
    out: list[str] | None = None
    for line in _COMMENT.sub("", body or "").splitlines():
        m = _HEADING.match(line)
        if m:
            if out is not None:
                break
            if m.group(1).strip().rstrip(":").lower() == SECTION.lower():
                out = []
            continue
        if out is not None:
            out.append(line)
    return None if out is None else "\n".join(out).strip()


def problems_in_text(body: str) -> tuple[list[str], list[int]]:
    """(erros de forma, issues citadas). Sem rede: só o texto."""
    text = section(body)
    if text is None:
        return [f"o corpo não tem a seção '## {SECTION}'"], []
    if not text:
        return [f"a seção '## {SECTION}' está vazia (escreva 'nada' ou liste os itens com #issue)"], []
    lines = [raw.strip() for raw in text.splitlines() if raw.strip()]
    # Item é linha de lista. Prosa depois da lista (a assinatura do PR, uma nota)
    # não é item; mas seção só de prosa não declara nada e reprova abaixo.
    items = [line for line in lines if _LIST_ITEM.match(line)]
    if not items:
        if _NOTHING.match(lines[0]):
            return [], []
        return [f"a seção '## {SECTION}' não diz 'nada' nem lista itens ('- <o que falta> (#issue)')"], []
    errors: list[str] = []
    refs: list[int] = []
    for line in items:
        found = [int(n) for n in _ISSUE_REF.findall(line)]
        if not found:
            if _NOTHING.match(line):
                continue
            errors.append(f"item sem issue: {line!r}")
        refs.extend(found)
    return errors, refs


def _gh_json(args: list[str]) -> dict:
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def problems_in_issues(repo: str, refs: list[int], fetch=None) -> list[str]:
    fetch = fetch or (lambda n: _gh_json(["api", f"repos/{repo}/issues/{n}"]))
    errors = []
    for number in dict.fromkeys(refs):
        try:
            issue = fetch(number)
        except subprocess.CalledProcessError:
            errors.append(f"#{number} não existe")
            continue
        if "pull_request" in issue:
            errors.append(f"#{number} é um PR, não uma issue: o que ficou de fora precisa de issue própria")
            continue
        labels = {lbl.get("name") for lbl in issue.get("labels", [])}
        if LABEL not in labels:
            errors.append(f"a issue #{number} não tem o label '{LABEL}' (gh issue edit {number} --add-label {LABEL})")
    return errors


def exemption(pr: dict) -> str | None:
    author = pr.get("author") or ""
    if author in BOT_LOGINS or author.endswith("[bot]"):
        return f"é de robô ({author})"
    if pr.get("isDraft"):
        return "é draft: confere quando sair do draft"
    created = pr.get("createdAt") or ""
    if created and created < CUTOFF:
        return f"é anterior à trava ({created})"
    return None


def _pr_from_event() -> dict | None:
    if os.environ.get("GITHUB_EVENT_NAME") == "merge_group":
        return None
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        return None
    pr = json.loads(Path(path).read_text()).get("pull_request") or {}
    return {
        "body": pr.get("body") or "",
        "author": (pr.get("user") or {}).get("login", ""),
        "createdAt": pr.get("created_at", ""),
        "isDraft": bool(pr.get("draft")),
        "number": pr.get("number"),
    }


def _pr_from_gh(number: int) -> dict:
    data = _gh_json(["pr", "view", str(number), "--json", "body,author,createdAt,isDraft,number"])
    data["author"] = (data.get("author") or {}).get("login", "")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Todo PR declara o que deixou de fora.")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--body-file")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "nelsonboulangerie/django-shopman"))
    args = parser.parse_args(argv)

    if args.body_file:
        errors, _ = problems_in_text(Path(args.body_file).read_text())
        return _report(errors, "corpo")

    pr = _pr_from_gh(args.pr) if args.pr else _pr_from_event()
    if pr is None:
        print("ficou-de-fora: fora de PR (merge_group ou sem evento): nada a conferir.")
        return 0
    label = f"PR #{pr.get('number')}"
    why = exemption(pr)
    if why:
        print(f"ficou-de-fora: {label} {why}: isento.")
        return 0

    errors, refs = problems_in_text(pr["body"])
    if not errors and refs:
        errors = problems_in_issues(args.repo, refs)
    return _report(errors, label)


def _report(errors: list[str], label: str) -> int:
    if not errors:
        print(f"ficou-de-fora: {label} declara o que ficou de fora. ✓")
        return 0
    print(f"ficou-de-fora: {label} não declara direito o que ficou de fora:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    print(file=sys.stderr)
    print(HOW_TO, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
