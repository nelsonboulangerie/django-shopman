#!/usr/bin/env python
"""Decide QUAIS componentes o Deploy Images precisa publicar — e contra QUEM medir.

## O defeito que este arquivo existe para desarmar (medido em 17/09/2026)

Três merges entraram na fila em sequência. O do meio foi **cancelado antes de
rodar um único job**, e o componente que ele tocava não foi construído por run
nenhum — com tudo verde.

    #816  5d3b19cc7  run 35287867144  success    web, pos-nuxt, operator-floor
    #815  2ab8ec5d6  run 35288099333  CANCELLED  nenhum job (0 jobs)
    #814  6388d96b6  run 35288162047  success    só web

O commit `2ab8ec5d6` mexia em 11 arquivos de `surfaces/pos-nuxt/**`. O run do
`#814` comparou com `github.event.before` — que É `2ab8ec5d6` — e viu 2 arquivos.
A metade Django do conserto subiu (vai na imagem `web`, buildada do topo); a
metade Nuxt não existia em imagem alguma.

**A causa do cancelamento não é corrida, é o slot de espera da `concurrency`.**
O workflow declara `cancel-in-progress: false`, e isso protege o run EM
ANDAMENTO — não o run PENDENTE. O GitHub guarda **um** lugar na fila por grupo:
quando um run novo chega e já há um esperando, o que esperava é cancelado. Os
relógios provam: o run do `#814` nasceu 23:44:20Z e o do `#815` foi cancelado
23:44:21Z, um segundo depois, sem nunca ter começado. E o `#814` esperou de
23:44:20Z até 23:48:37Z para iniciar — porque o `#816` só terminou 23:48:33Z.
A serialização funcionava; era o assento único que atropelava.

Não é caso isolado: das 431 execuções deste workflow, **9 foram canceladas, todas
com zero jobs**, todas disparadas pela fila de merge.

## O conserto: a base não é o commit anterior, é o último deploy que DEU CERTO

Comparar com `github.event.before` assume que todo commit anterior teve deploy
bem-sucedido. Qualquer buraco — run cancelado, falho, pulado — faz componente
sumir em silêncio, e o silêncio é lido como "não mudou nada".

A base honesta é o `head_sha` do último run **de push, bem-sucedido, ancestral do
topo**. Se o do meio morreu, a base recua sozinha e a leva inteira volta para a
conta. No caso acima, o run do `#814` teria medido contra `5d3b19cc7` e visto os
11 arquivos de `pos-nuxt` mais os 2 de `guestman` — publicando `web`,
`pos-nuxt` e `operator-floor`.

A indução fecha: um run só conclui `success` depois que TODOS os componentes que
ele decidiu construir foram construídos (`build-push` reprovado reprova o run, e
o job do manifesto recusa componente sem digest). Então o sha de um run
bem-sucedido é base segura para o próximo.

⚠️ Só run de `push` serve de base. `workflow_dispatch` publica um subconjunto
escolhido à mão (`components=pos-nuxt,operator-floor`, que foi a remediação de
17/09) — tomá-lo por base declararia publicado o que ninguém publicou.

⚠️ Sem base utilizável (primeira execução, histórico reescrito, base que não é
ancestral) a saída é construir TUDO e dizer por quê. Errar para o lado de
publicar demais custa minutos de runner; errar para o lado de publicar de menos
foi o que deixou o PDV fora do ar.

Uso:

    python scripts/deploy_components.py --head <sha> --base <sha>
    python scripts/deploy_components.py --head <sha> --all
    python scripts/deploy_components.py --head <sha> --components "web,pos-nuxt"
    python scripts/deploy_components.py --head <sha> --base <sha> --per-app false

Escreve `matrix=<json>` e `any=<bool>` no stdout, no formato de `$GITHUB_OUTPUT`.
Os avisos vão para o stderr. Sai com 2 em erro de uso.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GROUPS_JSON = REPO_ROOT / "surfaces" / "operator-router" / "groups.json"

#: Caminhos que obrigam a imagem `web` (Django + pacotes) a rebuildar.
WEB_PATHS = (
    "packages/**",
    "shopman/**",
    "config/**",
    "tools/**",
    "manage.py",
    "pyproject.toml",
    "constraints.txt",
    "Dockerfile",
)

#: A layer compartilhada e a receita das surfaces. Mudou aqui, TODA surface
#: rebuilda — inclusive o storefront, que usa o mesmo `Dockerfile.surface`.
SURFACE_SHARED_PATHS = (
    "surfaces/operator-kit/**",
    "surfaces/Dockerfile.surface",
)

#: Infra do grupo de operador (ADR-030): roteador e receita do grupo.
GROUP_SHARED_PATHS = (
    "surfaces/operator-kit/**",
    "surfaces/operator-router/**",
    "surfaces/Dockerfile.operator-group",
)


def load_groups(groups_json: Path = GROUPS_JSON) -> dict[str, list[str]]:
    """Grupos de operador lidos de `groups.json` — a MESMA lista do launcher."""
    raw = json.loads(groups_json.read_text(encoding="utf-8"))
    return {
        name: [app["surface"] for app in group["apps"]] for name, group in raw.items()
    }


def component_paths(groups: dict[str, list[str]]) -> dict[str, tuple[str, ...]]:
    """Para cada componente, TUDO que obriga a publicá-lo de novo.

    Uma única tabela, usada tanto para decidir o que construir quanto para
    perguntar ao registry se o que está publicado é o que o `main` pede
    (`scripts/check_registry_drift.py`). Duas cópias divergiriam no primeiro dia
    em que alguém acrescentasse uma surface.
    """
    operator_surfaces = [s for members in groups.values() for s in members]
    surfaces = ["storefront-nuxt", *operator_surfaces]

    paths: dict[str, tuple[str, ...]] = {"web": WEB_PATHS}
    for surface in surfaces:
        paths[surface] = (f"surfaces/{surface}/**", *SURFACE_SHARED_PATHS)
    for group, members in groups.items():
        paths[group] = (
            *GROUP_SHARED_PATHS,
            *(f"surfaces/{member}/**" for member in members),
        )
    return paths


def matches(path: str, pattern: str) -> bool:
    """`x/**` casa qualquer coisa sob `x/`; o resto é literal.

    Deliberadamente simples: todo padrão desta casa é prefixo de diretório ou
    arquivo nomeado. Glob de verdade (`*.py`, `**/x`) casaria por acidente e
    esconderia a intenção — se um dia for preciso, que seja explícito.
    """
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return path == pattern


def components_for(
    changed: list[str], paths: dict[str, tuple[str, ...]]
) -> list[str]:
    """Ordem estável: `web`, depois as surfaces, depois os grupos."""
    return [
        name
        for name, patterns in paths.items()
        if any(matches(f, p) for f in changed for p in patterns)
    ]


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def is_ancestor(base: str, head: str, cwd: Path) -> bool:
    return _git("merge-base", "--is-ancestor", base, head, cwd=cwd).returncode == 0


def changed_files(base: str, head: str, cwd: Path) -> list[str]:
    """`git diff base head` — DOIS pontos, de propósito.

    Três pontos responderia "o que o head trouxe desde a bifurcação", que é
    outra pergunta. Aqui o `main` é linear e o que importa é literalmente quais
    arquivos diferem entre o que foi publicado e o que está no topo.
    """
    result = _git("diff", "--name-only", base, head, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"git diff {base} {head} falhou: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line]


def last_commit_touching(
    patterns: tuple[str, ...], ref: str, cwd: Path
) -> str | None:
    """Último commit em `ref` que tocou qualquer um dos caminhos.

    É o sha que o registry DEVERIA estar servindo para aquele componente.
    """
    pathspec = [p[:-3] if p.endswith("/**") else p for p in patterns]
    result = _git(
        "log", "-1", "--format=%H", ref, "--", *pathspec, cwd=cwd
    )
    if result.returncode != 0:
        raise RuntimeError(f"git log de {patterns} falhou: {result.stderr.strip()}")
    return result.stdout.strip() or None


def build_matrix(names: list[str], groups: dict[str, list[str]]) -> list[dict]:
    include: list[dict] = []
    for name in dict.fromkeys(names):
        if name == "web":
            include.append(
                {
                    "name": "web",
                    "dockerfile": "Dockerfile",
                    "surface": "",
                    "group": "",
                    "tag": "web",
                }
            )
        elif name in groups:
            include.append(
                {
                    "name": name,
                    "dockerfile": "surfaces/Dockerfile.operator-group",
                    "surface": "",
                    "group": name,
                    "tag": name,
                }
            )
        else:
            include.append(
                {
                    "name": name,
                    "dockerfile": "surfaces/Dockerfile.surface",
                    "surface": name,
                    "group": "",
                    "tag": name.removesuffix("-nuxt"),
                }
            )
    return include


def decide(
    *,
    head: str,
    base: str | None,
    asked: str,
    per_app: bool,
    repo: Path,
    groups: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    """Devolve (componentes, avisos). Avisos vão para o stderr, não somem."""
    paths = component_paths(groups)
    operator_surfaces = [s for members in groups.values() for s in members]
    everything = list(paths)
    warnings: list[str] = []

    if asked:
        names = (
            everything
            if asked == "all"
            else [c.strip() for c in asked.split(",") if c.strip()]
        )
        desconhecidos = [n for n in names if n not in paths]
        if desconhecidos:
            raise SystemExit(
                f"::error::componente inexistente: {desconhecidos}. "
                f"Conhecidos: {everything}"
            )
    elif not base:
        warnings.append(
            "sem base de deploy bem-sucedida para comparar — construindo TUDO. "
            "Publicar demais custa minutos; publicar de menos deixou o PDV fora "
            "do ar em 17/09/2026."
        )
        names = everything
    elif not is_ancestor(base, head, repo):
        warnings.append(
            f"a base {base} não é ancestral de {head} (histórico reescrito?) — "
            "construindo TUDO em vez de medir contra um passado que não existe."
        )
        names = everything
    else:
        changed = changed_files(base, head, repo)
        names = components_for(changed, paths)
        warnings.append(f"base={base} head={head} arquivos={len(changed)}")

    if not per_app:
        names = [n for n in names if n not in operator_surfaces]
    return names, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", required=True, help="sha do topo a publicar")
    parser.add_argument(
        "--base",
        default="",
        help="sha do último deploy de push bem-sucedido; vazio = construir tudo",
    )
    parser.add_argument("--components", default="", help="csv, ou 'all'")
    parser.add_argument("--all", action="store_true", help="atalho de --components all")
    parser.add_argument(
        "--per-app",
        default="auto",
        choices=["auto", "true", "false", ""],
        help="'auto' (ou vazio) segue OPERATOR_PER_APP_IMAGES do ambiente",
    )
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument("--groups-json", default=str(GROUPS_JSON))
    args = parser.parse_args(argv)

    groups = load_groups(Path(args.groups_json))
    # 'auto' segue a rede de rollback da ADR-030 declarada no workflow, para que
    # ligar/desligar as imagens por app seja UMA edição, não duas.
    escolha = args.per_app.strip() or "auto"
    if escolha == "auto":
        escolha = os.environ.get("OPERATOR_PER_APP_IMAGES", "true")
    per_app = escolha == "true"
    names, warnings = decide(
        head=args.head,
        base=args.base.strip() or None,
        asked="all" if args.all else args.components.strip(),
        per_app=per_app,
        repo=Path(args.repo),
        groups=groups,
    )
    for warning in warnings:
        print(f"::notice::{warning}", file=sys.stderr)

    include = build_matrix(names, groups)
    print("matrix=" + json.dumps({"include": include}))
    print("any=" + ("true" if include else "false"))
    # O confronto com o registry tem que cobrar exatamente o que ESTE run
    # decidiu publicar — inclusive a rede de rollback por app da ADR-030.
    print("per_app=" + ("true" if per_app else "false"))
    print(
        "componentes: " + (", ".join(c["name"] for c in include) or "nenhum"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
