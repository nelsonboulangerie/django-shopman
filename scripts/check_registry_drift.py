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

## A guarda declara a MEDIDA, não só a conclusão

Até 18/09/2026 esta guarda dizia qual commit ela INFERIU e escondia de onde
inferiu. Quando ficou vermelha três corridas seguidas acusando um componente
para trás, não havia como decidir, sem credencial, se a listagem tinha servido
estado anterior ao push, se duas imutáveis dividiam o digest, ou se
`digest_por_tag` estava colapsando a mesma tag vinda em duas páginas.

Então toda linha de erro carrega agora: o **digest** que foi lido na tag móvel,
**quantas entradas da listagem** trazem aquele nome de tag (mais de uma = a
listagem repetiu a tag, e o dicionário colapsou), e **quantas imutáveis dividem
esse digest** (mais de uma = dois commits publicaram a MESMA imagem). É o mesmo
movimento do `#573`, quando o Deploy Images passou a DECLARAR o que publicou: o
conserto não foi adivinhar melhor, foi obrigar o passo a dizer o que viu.

Uso:

    DO_TOKEN=... python scripts/check_registry_drift.py
    python scripts/check_registry_drift.py --registry-json tags.json  # offline

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
from typing import NamedTuple

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
    """Todas as tags do repositório — e diz em QUANTAS páginas elas vieram.

    A contagem não é enfeite. `read_published` colapsa nome de tag repetido, e
    uma listagem que muda no meio da paginação pode devolver a MESMA tag em duas
    páginas com digests diferentes. Se tudo couber numa página só, esse
    mecanismo está descartado sem ninguém precisar discuti-lo — e ninguém tinha
    contado as tags até 18/09/2026.
    """
    tags: list[dict] = []
    paginas = 0
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
        paginas += 1
        tags.extend(payload["tags"])
        url = ((payload.get("links") or {}).get("pages") or {}).get("next") or ""
    print(
        f"::notice::registry: {len(tags)} tags lidas em {paginas} página(s)",
        file=sys.stderr,
    )
    return tags


class Leitura(NamedTuple):
    """O que a listagem disse sobre uma tag móvel — a MEDIDA, não só a conclusão.

    `shas` vazio = não deu para provar, e `motivo` diz por quê. Mais de um sha =
    várias imutáveis dividem o mesmo digest, isto é, dois commits publicaram a
    MESMA imagem, byte a byte. Aí a resposta honesta é o conjunto: escolher a
    primeira da ordem do dicionário seria inventar um desempate que a listagem
    não autoriza.
    """

    shas: tuple[str, ...]
    digest: str
    #: Os digests de TODAS as entradas da listagem com aquele nome de tag. Mais
    #: de uma entrada significa que a listagem repetiu a tag — o sintoma de
    #: paginar uma lista que um push está mutando.
    entradas: tuple[str, ...]
    motivo: str

    def medida(self) -> str:
        """De onde a conclusão saiu. É isto que faz o próximo vermelho se explicar."""
        partes = [f"digest lido na tag móvel: {_curto(self.digest) or '(nenhum)'}"]
        if len(self.entradas) != 1:
            digests = ", ".join(_curto(d) for d in self.entradas) or "nenhum"
            partes.append(
                f"{len(self.entradas)} entradas da listagem carregam esse NOME "
                f"de tag ({digests})"
            )
        imutaveis = ", ".join(s[:9] for s in self.shas) or "nenhuma"
        partes.append(
            f"{len(self.shas)} tag(s) imutável(is) dividem esse digest: {imutaveis}"
        )
        return "; ".join(partes)


def _curto(digest: str) -> str:
    """`sha256:` + 12 hex, que é o que os logs de build imprimem."""
    return digest[:19] + "…" if len(digest) > 19 else digest


def read_published(tags: list[dict], moving_tag: str) -> Leitura:
    """Quais commits podem estar por trás da tag móvel — com a medida junto.

    ⚠️ Não escolhe em silêncio. Quando duas imutáveis dividem o digest, as duas
    voltam: a imagem é a mesma, então qualquer uma delas descreve fielmente o
    que está no ar, e quem decide é o confronto, que sabe o que perguntar.

    ⚠️ O digest da tag móvel continua saindo por ÚLTIMA-ESCRITA-VENCE, o mesmo
    critério do dicionário que estava aqui antes. É de propósito: instrumentar
    é medir o comportamento de hoje, não trocá-lo por outro antes de saber qual
    dos mecanismos está em jogo. `entradas` é o que denuncia o colapso.
    """
    entradas = tuple(
        t.get("manifest_digest") or "" for t in tags if t.get("tag") == moving_tag
    )
    digest = ""
    for valor in entradas:
        digest = valor or digest
    if not digest:
        return Leitura(
            (), "", entradas, f"a tag `{moving_tag}` não existe no registry"
        )

    shas: list[str] = []
    for t in tags:
        if t.get("manifest_digest") != digest:
            continue
        match = IMMUTABLE.match(t.get("tag") or "")
        if match and match["tag"] == moving_tag and match["sha"] not in shas:
            shas.append(match["sha"])
    if not shas:
        return Leitura(
            (),
            digest,
            entradas,
            f"a tag `{moving_tag}` aponta para {digest}, e nenhuma tag "
            f"`{moving_tag}-<sha>` aponta para o mesmo digest — impossível provar "
            "qual commit está no ar",
        )
    return Leitura(tuple(shas), digest, entradas, "")


def _divergencia(esperado: str, publicado: str, ref: str, repo: Path) -> str:
    """A queixa contra UM candidato, ou "" se ele honra a invariante."""
    if not is_ancestor(esperado, publicado, repo):
        return (
            f"publicado {publicado[:9]}, que NÃO contém {esperado[:9]} — a "
            "última mudança deste componente não está no ar"
        )
    if not is_ancestor(publicado, ref, repo):
        return (
            f"publicado {publicado[:9]}, que não é ancestral do topo — o "
            "ambiente vivo está servindo algo que não veio do `main`"
        )
    return ""


def audit(
    tags: list[dict],
    *,
    ref: str,
    per_app: bool,
    repo: Path,
    groups: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    """Devolve (divergências, notas). Divergências vazias = o vivo bate com o `main`.

    As notas existem para o caso que passa mas merece ser visto: várias
    imutáveis dividindo um digest é dois commits publicando a MESMA imagem, e
    isso é desperdício de build e de registry mesmo quando a invariante está
    honrada.
    """
    paths = component_paths(groups)
    operator_surfaces = [s for members in groups.values() for s in members]
    tag_de = {c["name"]: c["tag"] for c in build_matrix(list(paths), groups)}

    problemas: list[str] = []
    notas: list[str] = []
    for name, patterns in paths.items():
        # ⚠️ Com OPERATOR_PER_APP_IMAGES desligado, as imagens por app param de
        # ser publicadas de propósito (rede de rollback da ADR-030 vencida).
        # Cobrar delas aí seria gate vermelho por decisão da casa.
        if not per_app and name in operator_surfaces:
            continue
        esperado = last_commit_touching(patterns, ref, repo)
        if esperado is None:
            continue  # nada no histórico tocou esse componente; nada a cobrar
        leitura = read_published(tags, tag_de[name])
        if not leitura.shas:
            problemas.append(
                f"{name}: {leitura.motivo} (o `main` pede {esperado[:9]}) "
                f"[{leitura.medida()}]"
            )
            continue
        queixas = [_divergencia(esperado, sha, ref, repo) for sha in leitura.shas]
        if len(leitura.shas) > 1:
            notas.append(
                f"{name}: {len(leitura.shas)} commits publicaram a MESMA imagem "
                f"({', '.join(s[:9] for s in leitura.shas)} → "
                f"{_curto(leitura.digest)}) — build e publicação repetidos"
            )
        if not all(queixas):
            # A imagem é idêntica nos candidatos: se ALGUM deles honra a
            # invariante, o que está no ar a honra. Não é escolher o mais
            # conveniente, é reconhecer que os bytes são os mesmos.
            continue
        problemas.append(f"{name}: {queixas[0]} [{leitura.medida()}]")
    return problemas, notas


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

    problemas, notas = audit(
        tags,
        ref=args.ref,
        per_app=args.per_app == "true",
        repo=Path(args.repo),
        groups=load_groups(Path(args.groups_json)),
    )
    for nota in notas:
        print(f"::notice::{nota}", file=sys.stderr)
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
