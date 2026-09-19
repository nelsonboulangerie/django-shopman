#!/usr/bin/env python
"""Confronta o que ESTÁ publicado com o que o `main` PEDE — e grita o que faltou.

O irmão do `scripts/deploy_components.py`. Aquele decide o que construir; este
não confia na decisão e pergunta ao registry, que é onde a verdade mora: o App
Platform assina a tag MÓVEL (`web`, `pos`, `operator-floor`), então quem manda no
ambiente vivo é a imagem por trás dessa tag — não o que um run disse ter feito.

## A invariante

Para cada componente, o commit por trás da tag móvel tem que **conter** a última
mudança daquele componente: `último commit que tocou` deve ser ancestral-ou-igual
de `commit publicado`, que por sua vez é ancestral-ou-igual do topo.

⚠️ É contenção, não igualdade — e a diferença não é preciosismo. Não é "igual ao
topo do `main`": a maioria dos componentes fica legitimamente para trás do topo,
porque o push não os tocou. E também não é "igual ao último commit que os tocou":
uma imagem construída de um commit MAIS NOVO que não mexeu naquele componente
carrega o mesmo código dele, e é tão boa quanto. Foi assim que a remediação de
17/09 republicou o PDV — `gh workflow run ... --ref main`, do topo, não do commit
do conserto. Cobrar igualdade reprovaria justamente o conserto.

A correlação é possível porque o Deploy Images publica DUAS tags por
componente: a móvel (`pos`) e a imutável (`pos-<sha>`). As duas apontam para o
mesmo manifest digest, então o digest da tag móvel revela qual sha está no ar.

⚠️ "Qual sha" pode ser mais de um, e isso não é defeito do registry. Commit que
não altera o `.output` publica imagem byte a byte idêntica — o caso puro é
mudança só em arquivo de teste — e então várias imutáveis dividem um digest.
São nomes diferentes da MESMA imagem, então a invariante se satisfaz com
qualquer um deles. O que este script não faz mais é escolher um em silêncio.

⚠️ **Isto é um pré-requisito para o E4 do WP-DO-ECONOMIA** (retenção de tags +
garbage collection). A política proposta lá — guardar as 10 imutáveis mais
recentes por componente e nunca tocar nas móveis — é compatível por construção,
porque a irmã da tag móvel é sempre o build mais recente daquele componente. Mas
uma GC que apagasse a imutável apontada pela móvel cegaria este confronto: ele
passaria a dizer "impossível provar qual commit está no ar" para todo mundo. Se
o N da retenção virar 1, ou se a regra passar a ser por data, confira esta
invariante antes.

## Por que existir, se a decisão já foi consertada

Porque a decisão fecha a porta que já se viu abrir, e esta fecha a classe. Um
run cancelado, um run falho, um `workflow_dispatch` com o componente errado, uma
tag apagada à mão, um build que empurrou e o registry não guardou — tudo cai
aqui do mesmo jeito, sem precisar ter sido previsto. O buraco de 17/09/2026
custou o PDV fora do ar com tudo verde; o que não se mede volta.

## Como o `#815` apareceria aqui

`pos` serviria a imagem de `5d3b19cc7`, o `main` pediria `2ab8ec5d6`, e a saída
seria uma linha nomeando `pos-nuxt` e `operator-floor` com o comando que os
republica. Barulho no lugar de silêncio verde.

Uso:

    DO_TOKEN=... python scripts/check_registry_drift.py
    python scripts/check_registry_drift.py --registry-json tags.json  # offline

Ele também IMPRIME o que leu — digest da tag móvel e as imutáveis que o
dividem — em toda corrida. Sem isso, "a listagem serve estado anterior ao push"
e "li o digest certo e desempatei errado" produzem a mesma frase de erro, e a
única forma de distinguir era ter a credencial do registry na mão.

Saídas:
  0  tudo que o `main` pede está publicado
  1  DIVERGÊNCIA provada — há componente para trás, nomeado na saída
  2  não deu para PERGUNTAR (credencial, rede, resposta ilegível)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploy_components import (  # noqa: E402
    GROUPS_JSON,
    REPO_ROOT,
    build_matrix,
    component_paths,
    is_ancestor,
    last_commit_touching,
    load_groups,
)

API = "https://api.digitalocean.com/v2"

#: `pos-<40 hex>` → ("pos", sha). O sufixo imutável é o que permite dizer QUAL
#: commit está por trás de uma tag móvel.
IMMUTABLE = re.compile(r"^(?P<tag>.+)-(?P<sha>[0-9a-f]{40})$")


class NaoDeuParaPerguntar(RuntimeError):
    """Falta credencial, a rede caiu, ou a resposta não se parece com tags.

    Separado de divergência de propósito: "não consegui perguntar" e "perguntei
    e a resposta é ruim" pedem reações diferentes. Misturar os dois foi como o
    smoke pós-deploy passou a devolver verde sem medir nada, em 09/2026.
    """


def fetch_tags(registry: str, repository: str, token: str) -> list[dict]:
    tags: list[dict] = []
    url = f"{API}/registry/{registry}/repositories/{repository}/tags?per_page=200"
    while url:
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise NaoDeuParaPerguntar(f"GET {url}: {exc}") from exc
        if "tags" not in payload:
            raise NaoDeuParaPerguntar(f"resposta sem `tags`: {sorted(payload)}")
        tags.extend(payload["tags"])
        url = ((payload.get("links") or {}).get("pages") or {}).get("next") or ""
    return tags


def curto(digest: str) -> str:
    """`sha256:97057d40…` — o bastante para comparar duas leituras a olho."""
    return f"{digest[:19]}…" if len(digest) > 19 else digest


def digests_por_tag(tags: list[dict]) -> dict[str, set[str]]:
    """Todas as leituras de cada tag, SEM colapsar.

    ⚠️ Não é `{tag: digest}`, e a diferença é a causa de um vermelho que ninguém
    conseguia explicar em 18/09/2026. A listagem pode trazer a MESMA tag duas
    vezes — páginas distintas de uma lista que um push está mutando, ou entrada
    remanescente. Num dict simples a última escrita vence em silêncio, e nada
    garante que a última seja a mais nova: a guarda passa a responder o digest
    anterior a um push que o log do build prova ter acontecido. Guardar o
    conjunto faz a ambiguidade APARECER em vez de virar resposta errada.
    """
    leituras: dict[str, set[str]] = {}
    for t in tags:
        tag = t.get("tag")
        digest = t.get("manifest_digest")
        if tag and digest:
            leituras.setdefault(tag, set()).add(digest)
    return leituras


def published_shas(
    tags: list[dict], moving_tag: str
) -> tuple[str, tuple[str, ...], str]:
    """(digest lido na móvel, shas que dividem esse digest, motivo se não deu).

    ⚠️ Devolve TODOS os shas, não um. Dois commits publicam a mesma imagem
    sempre que a mudança não altera o `.output` — `Dockerfile.surface` copia a
    surface inteira no estágio de build e só o `.output` no final, então commit
    que mexe apenas em teste produz imagem byte a byte idêntica, e o cache a
    reproduz. Medido em 18/09/2026: `210f2164c` e `15cd468f3` publicaram
    `sha256:97057d40…`, o mesmo digest.

    Escolher UM deles seria arbitrário — a versão anterior devolvia o primeiro
    da ordem do dict, que é a ordem em que o registry listou, e nada ali prefere
    o mais novo. Mas escolher também é desnecessário: as tags nomeiam a MESMA
    imagem, então qualquer uma delas é um nome honesto do que está no ar, e quem
    decide é a invariante — basta que UM dos candidatos a satisfaça.
    """
    leituras = digests_por_tag(tags)
    digests = leituras.get(moving_tag) or set()
    if not digests:
        return "", (), f"a tag `{moving_tag}` não existe no registry"
    if len(digests) > 1:
        vistos = ", ".join(curto(d) for d in sorted(digests))
        return (
            "",
            (),
            f"a listagem trouxe `{moving_tag}` com {len(digests)} digests "
            f"diferentes ({vistos}) — leitura ambígua do registry, não dá para "
            "dizer o que está no ar",
        )
    digest = next(iter(digests))
    shas = tuple(
        sorted(
            match["sha"]
            for tag, outros in leituras.items()
            if (match := IMMUTABLE.match(tag))
            and match["tag"] == moving_tag
            and digest in outros
        )
    )
    if not shas:
        return (
            digest,
            (),
            f"a tag `{moving_tag}` aponta para {curto(digest)}, e nenhuma tag "
            f"`{moving_tag}-<sha>` aponta para o mesmo digest — impossível "
            "provar qual commit está no ar",
        )
    return digest, shas, ""


def audit(
    tags: list[dict],
    *,
    ref: str,
    per_app: bool,
    repo: Path,
    groups: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    """(linhas de divergência, linhas do que foi LIDO no registry).

    A segunda lista não é decoração. A guarda era a única peça da cadeia que
    inferia um commit e escondia a medida de onde inferiu — dizia "publicado
    2842ed54b" sem dizer qual digest tinha lido, e três hipóteses diferentes
    produziam exatamente a mesma frase. Declarar o que se leu é o mesmo
    movimento do #573, quando o Deploy Images passou a declarar o que publicou.
    """
    paths = component_paths(groups)
    operator_surfaces = [s for members in groups.values() for s in members]
    tag_de = {c["name"]: c["tag"] for c in build_matrix(list(paths), groups)}

    problemas: list[str] = []
    lido: list[str] = []
    for name, patterns in paths.items():
        # ⚠️ Com OPERATOR_PER_APP_IMAGES desligado, as imagens por app param de
        # ser publicadas de propósito (rede de rollback da ADR-030 vencida).
        # Cobrar delas aí seria gate vermelho por decisão da casa.
        if not per_app and name in operator_surfaces:
            continue
        esperado = last_commit_touching(patterns, ref, repo)
        if esperado is None:
            continue  # nada no histórico tocou esse componente; nada a cobrar
        digest, shas, motivo = published_shas(tags, tag_de[name])
        if not shas:
            lido.append(f"{name}: {motivo}")
            problemas.append(f"{name}: {motivo} (o `main` pede {esperado[:9]})")
            continue

        nomes = ", ".join(sha[:9] for sha in shas)
        divididas = (
            "" if len(shas) == 1 else f" ({len(shas)} tags dividem esse digest)"
        )
        lido.append(f"{name}: móvel em {curto(digest)} = {nomes}{divididas}")

        contem = [sha for sha in shas if is_ancestor(esperado, sha, repo)]
        if not contem:
            problemas.append(
                f"{name}: publicado {nomes}, que NÃO contém "
                f"{esperado[:9]} — a última mudança deste componente não está "
                f"no ar (móvel em {curto(digest)})"
            )
        elif not any(is_ancestor(sha, ref, repo) for sha in contem):
            problemas.append(
                f"{name}: publicado {nomes}, que não é ancestral do "
                f"topo — o ambiente vivo está servindo algo que não veio do "
                f"`main` (móvel em {curto(digest)})"
            )
    return problemas, lido


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="ref que é a verdade")
    parser.add_argument("--registry", default="nelsonboulangerie")
    parser.add_argument("--repository", default="shopman")
    parser.add_argument("--per-app", default=os.environ.get("PER_APP", "true"))
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument("--groups-json", default=str(GROUPS_JSON))
    parser.add_argument(
        "--registry-json",
        default="",
        help="lê as tags de um arquivo em vez da API (teste offline)",
    )
    args = parser.parse_args(argv)

    try:
        if args.registry_json:
            payload = json.loads(Path(args.registry_json).read_text(encoding="utf-8"))
            tags = payload["tags"] if isinstance(payload, dict) else payload
        else:
            token = os.environ.get("DO_TOKEN", "").strip()
            if not token:
                raise NaoDeuParaPerguntar("DO_TOKEN ausente")
            tags = fetch_tags(args.registry, args.repository, token)
    except (NaoDeuParaPerguntar, KeyError, ValueError, OSError) as exc:
        print(f"::warning::não deu para perguntar ao registry: {exc}", file=sys.stderr)
        return 2

    problemas, lido = audit(
        tags,
        ref=args.ref,
        per_app=args.per_app == "true",
        repo=Path(args.repo),
        groups=load_groups(Path(args.groups_json)),
    )
    # Sai SEMPRE, verde ou vermelho: é o que permite distinguir "li o digest
    # novo e desempatei errado" de "li o digest anterior ao push" sem precisar
    # de credencial para reproduzir. Uma corrida vermelha passa a responder
    # sozinha qual das duas aconteceu.
    print("o que o registry respondeu:")
    for linha in lido:
        print(f"  {linha}")
    if not problemas:
        print("registry bate com o `main`: nenhum componente ficou para trás.")
        return 0

    for linha in problemas:
        print(f"::error::{linha}")
    atrasados = ",".join(linha.split(":")[0] for linha in problemas)
    print(
        "::error::COMPONENTE PARA TRÁS. Republique com: "
        f'gh workflow run deploy-images.yml --ref main -f components="{atrasados}"'
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
