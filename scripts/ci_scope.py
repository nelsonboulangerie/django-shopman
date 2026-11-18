#!/usr/bin/env python
"""Escopo da CI: o que um PR mexe decide o que roda NO PR.

Regra aprovada pelo dono em 17/11/2026: no ``pull_request`` roda só o leve
(lint, typecheck e os testes do que o PR mexe); as suítes pesadas rodam no
``merge_group``, que testa a árvore exata que pousa no ``main``. Nada chega ao
``main`` sem a suíte inteira: a fila continua sendo o portão.

Este script só CLASSIFICA. Recebe a lista de arquivos do PR (o
``dorny/paths-filter`` a entrega no job de escopo) e escreve, no formato do
``$GITHUB_OUTPUT``:

``full``      true quando não há como saber o alcance: evento que não é
              ``pull_request``, lista vazia, ou arquivo de infraestrutura
              (workflow, script, Makefile, Dockerfile, raiz de ``surfaces/``,
              qualquer pasta que esta tabela não conhece). Liga todo o leve.
``code``      algum arquivo que não é documentação.
``python``    algum arquivo das suítes Python (``packages/``, ``shopman/``,
              ``config/``, ``tools/``, ``manage.py``, ``locale/``).
``surfaces``  ``all`` ou a lista JSON de diretórios de ``surfaces/`` que o PR
              tocou, com o ``operator-kit`` sempre junto (os guardrails dele
              leem os apps irmãos).
``heavy``     true fora do ``pull_request``: a fila, o push e o disparo manual.

Desconhecido vira ``full``, nunca "pula": errar para o lado de rodar custa
minutos; errar para o lado de pular solta código sem teste.

    CI_EVENT=pull_request CI_FILES='["docs/a.md"]' python scripts/ci_scope.py
"""

from __future__ import annotations

import json
import os
import sys

#: Prefixos das suítes Python. Tudo que mora aqui liga Testes, Admin e CSP.
PYTHON_PREFIXES = ("packages/", "shopman/", "config/", "tools/", "locale/")
PYTHON_FILES = {"manage.py"}

#: Pastas que não são código nem infraestrutura: ninguém as importa nem as
#: empacota. Mudança só aqui é tratada como documentação.
DOC_PREFIXES = ("docs/", "evidence/", "prototypes/")


def is_doc(path: str) -> bool:
    return path.startswith(DOC_PREFIXES) or path.endswith(".md")


def classify(event: str, files: list[str]) -> dict[str, str]:
    heavy = event != "pull_request"
    full = heavy or not files
    python = False
    code = False
    surfaces: set[str] = set()

    for path in files:
        if is_doc(path):
            continue
        code = True
        if path.startswith(PYTHON_PREFIXES) or path in PYTHON_FILES:
            python = True
            continue
        parts = path.split("/")
        if parts[0] == "surfaces" and len(parts) > 2:
            surfaces.add(parts[1])
            continue
        # Workflow, script, Makefile, Dockerfile, constraints, `.do/`, a raiz
        # de `surfaces/` (registry, contratos, Dockerfile.surface) e qualquer
        # pasta nova: alcance desconhecido, roda todo o leve.
        full = True

    if surfaces:
        surfaces.add("operator-kit")

    def flag(value: bool) -> str:
        return "true" if value else "false"

    return {
        "full": flag(full),
        "heavy": flag(heavy),
        "code": flag(full or code),
        "python": flag(full or python),
        "surfaces": "all" if full else json.dumps(sorted(surfaces)),
    }


def main() -> int:
    event = os.environ.get("CI_EVENT", "")
    raw = os.environ.get("CI_FILES", "") or "[]"
    files = json.loads(raw)
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        print(f"CI_FILES não é lista JSON de caminhos: {raw[:200]}", file=sys.stderr)
        return 2
    scope = classify(event, files)
    for key, value in scope.items():
        print(f"{key}={value}")
    print(f"[ci-scope] {event}: {len(files)} arquivo(s) → {scope}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
