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

## E repergunta antes de gritar

A medida respondeu: em 18/09/2026 a guarda corria de 67 s a 114 s depois de a
tag móvel ter sido empurrada, e lia a listagem `/tags` ainda no estado anterior
ao push. Quatro corridas vermelhas seguidas, nenhuma com componente realmente
para trás — e a remediação que a própria mensagem sugeria (republicar) não podia
consertar nada, porque não havia o que republicar.

Então divergência na primeira leitura não é veredito: a guarda repergunta, até
`--reconfirmacoes` vezes a cada `--espera` segundos, e só acusa o que
sobreviver. Isso NÃO é paciência com divergência de verdade, que atravessa
qualquer espera — é recusar-se a confundir "o registry ainda não me contou" com
"o componente ficou para trás". A linha final diz quantas leituras a divergência
atravessou, que é a diferença entre afirmar e supor.

## A tag móvel se lê na DISTRIBUIÇÃO, não na listagem

A repergunta consertou o atraso de segundos, e 22/09/2026 mostrou o atraso de
horas. Desde 00:17 UTC, todo push no `main` ficou vermelho acusando `hub-nuxt`
para trás ("publicado fc29a0c30, que NÃO contém 8d4ed17c9"), e não estava. A
listagem de tags da API da DO (`GET /v2/registry/<r>/repositories/<repo>/tags`,
a mesma do `doctl registry repository list-tags`) mostrava a tag móvel `hub` em
`sha256:5b01d7ac…`, atualizada 00:09:22 e PARADA assim por oito horas, apesar de
cinco pushes posteriores dela. A API de distribuição — `HEAD
registry.digitalocean.com/v2/<r>/<repo>/manifests/hub` — respondia
`sha256:0dd7b725…`, o mesmo digest de `hub-806f5281c…`; e a listagem de
MANIFESTS trazia esse digest com as imutáveis novas. Só a entrada da tag MÓVEL
na listagem de tags estava velha. A repergunta de quatro minutos não alcança
um cache de oito horas, e a remediação sugerida (republicar) foi rodada às
07:31 e não mudou nada — não havia o que republicar.

Então o digest da tag móvel vem agora de onde o App Platform PUXA: o endpoint de
distribuição, com bearer token do `GET /v2/registry/auth` (Basic com o próprio
token da DO). É essa a verdade do ambiente vivo, por definição — a listagem é
um índice, e índice pode atrasar. A listagem continua servindo para o que só
ela faz: mapear digest → imutáveis `<tag>-<sha>`, que nascem uma vez e não
mudam de valor. Cada linha declara a FONTE do digest; se a distribuição falhar
(rede, auth), a guarda cai para a listagem e diz isso na própria linha, com o
erro — nunca em silêncio, porque aí o vermelho volta a poder ser do índice.

Uso:

    DO_TOKEN=... python scripts/check_registry_drift.py
    DO_TOKEN=... python scripts/check_registry_drift.py --reconfirmacoes 0
    python scripts/check_registry_drift.py --registry-json tags.json  # offline

Saídas:
  0  tudo que o `main` pede está publicado
  1  DIVERGÊNCIA provada — há componente para trás, nomeado na saída
  2  não deu para PERGUNTAR (credencial, rede, resposta ilegível)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
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
#: De onde o App Platform puxa. É aqui que a tag móvel diz a verdade.
DISTRIBUTION = "https://registry.digitalocean.com/v2"
#: Manifest e índice, OCI e Docker: sem o tipo certo no `Accept`, o registry
#: pode converter e devolver o digest de OUTRA representação da mesma imagem.
MANIFEST_ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)
FONTE_DISTRIBUICAO = "distribuição (HEAD do manifest, o que o App Platform puxa)"
FONTE_LISTAGEM = "listagem /tags da API da DO"

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


def _pull_token(registry: str, repository: str, token: str) -> str:
    """Bearer de leitura para UM repositório, trocado pelo token da DO.

    O token da DO vai em Basic (usuário = senha = token), como o `docker login`
    do DOCR. ⚠️ Nenhum dos dois tokens sai em mensagem: o erro carrega a URL,
    que não tem segredo, e a exceção do urllib, que não carrega cabeçalho.
    """
    scope = f"repository:{registry}/{repository}:pull"
    url = (
        f"{API}/registry/auth?service=registry.digitalocean.com"
        f"&scope={urllib.parse.quote(scope, safe='')}"
    )
    basic = base64.b64encode(f"{token}:{token}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise NaoDeuParaPerguntar(f"auth do registry ({url}): {exc}") from exc
    bearer = payload.get("token") if isinstance(payload, dict) else None
    if not bearer:
        raise NaoDeuParaPerguntar("auth do registry respondeu sem `token`")
    return bearer


def _manifest_digest(registry: str, repository: str, tag: str, bearer: str) -> str:
    url = f"{DISTRIBUTION}/{registry}/{repository}/manifests/{tag}"
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"Authorization": f"Bearer {bearer}", "Accept": MANIFEST_ACCEPT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            digest = response.headers.get("Docker-Content-Digest") or ""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise NaoDeuParaPerguntar(f"HEAD {url}: {exc}") from exc
    if not digest.startswith("sha256:"):
        raise NaoDeuParaPerguntar(f"HEAD {url}: sem `Docker-Content-Digest`")
    return digest


class Distribuicao(NamedTuple):
    """O digest de cada tag móvel segundo a distribuição — e o que falhou.

    `falhas[tag]` é o motivo de a tag ter caído para a listagem. Ele viaja até
    a linha de erro: um vermelho medido no índice não pode se passar por um
    medido na fonte.
    """

    digests: dict[str, str]
    falhas: dict[str, str]


def fetch_distribution(
    registry: str, repository: str, moving_tags: list[str], token: str
) -> Distribuicao:
    """HEAD no manifest de cada tag móvel, com UM bearer para todas.

    Não levanta: falha de auth vira falha de todas as tags, falha de uma tag
    vira falha só dela. Quem decide o que fazer com isso é `audit`, que cai
    para a listagem e declara.
    """
    try:
        bearer = _pull_token(registry, repository, token)
    except NaoDeuParaPerguntar as exc:
        return Distribuicao({}, dict.fromkeys(moving_tags, str(exc)))
    digests: dict[str, str] = {}
    falhas: dict[str, str] = {}
    for tag in moving_tags:
        try:
            digests[tag] = _manifest_digest(registry, repository, tag, bearer)
        except NaoDeuParaPerguntar as exc:
            falhas[tag] = str(exc)
    return Distribuicao(digests, falhas)


class Leitura(NamedTuple):
    """O que a listagem disse sobre uma tag móvel — a MEDIDA, não só a conclusão.

    `shas` vazio = não deu para provar, e `motivo` diz por quê. Mais de um sha =
    várias imutáveis dividem o mesmo digest, isto é, dois commits publicaram a
    MESMA imagem, byte a byte. Aí a resposta honesta é o conjunto: escolher a
    primeira da ordem do dicionário seria inventar um desempate que a listagem
    não autoriza.
    """

    shas: tuple[str, ...]
    #: Os digests DISTINTOS que a tag móvel carregou na listagem. Mais de um
    #: significa que a listagem repetiu a tag com valores diferentes — o sintoma
    #: de paginar uma lista que um push está mutando. Medido em 19/09/2026: são
    #: 1206 tags em 7 páginas, então esse mecanismo não é hipotético.
    digests: tuple[str, ...]
    #: Quantas entradas da listagem carregavam aquele NOME de tag.
    entradas: int
    motivo: str
    #: De onde veio o digest da tag móvel — distribuição ou listagem, e, se
    #: listagem, por que a distribuição não respondeu.
    fonte: str = FONTE_LISTAGEM
    #: O que a LISTAGEM dizia da tag móvel quando a fonte foi a distribuição.
    #: Divergir dela é o sintoma de 22/09/2026, e fica à vista.
    na_listagem: tuple[str, ...] = ()

    def medida(self) -> str:
        """De onde a conclusão saiu. É isto que faz o próximo vermelho se explicar."""
        lidos = ", ".join(_curto(d) for d in self.digests) or "(nenhum)"
        if self.fonte == FONTE_DISTRIBUICAO:
            partes = [f"fonte: {self.fonte}; digest lido na tag móvel: {lidos}"]
            listados = ", ".join(_curto(d) for d in self.na_listagem) or "(nenhum)"
            if set(self.na_listagem) != set(self.digests):
                partes.append(
                    f"a listagem /tags dizia {listados} — índice atrasado, ignorado"
                )
        elif len(self.digests) > 1:
            partes = [
                f"a tag móvel veio em {self.entradas} entradas da listagem, com "
                f"digests DIFERENTES ({lidos}) — a listagem repetiu a tag"
            ]
        else:
            partes = [f"digest lido na tag móvel: {lidos}"]
        if self.fonte != FONTE_DISTRIBUICAO:
            partes.insert(0, f"fonte: {self.fonte}")
        imutaveis = ", ".join(s[:9] for s in self.shas) or "nenhuma"
        partes.append(
            f"{len(self.shas)} tag(s) imutável(is) dividem esse(s) digest(s): "
            f"{imutaveis}"
        )
        return "; ".join(partes)


def _curto(digest: str) -> str:
    """`sha256:` + 12 hex, que é o que os logs de build imprimem."""
    return digest[:19] + "…" if len(digest) > 19 else digest


def read_published(
    tags: list[dict], moving_tag: str, digest: str = "", fonte: str = FONTE_LISTAGEM
) -> Leitura:
    """Quais commits podem estar por trás da tag móvel — com a medida junto.

    ⚠️ Não escolhe em silêncio, em nenhuma das duas frentes.

    Quando duas imutáveis dividem um digest, as duas voltam: a imagem é a mesma,
    então qualquer uma delas descreve fielmente o que está no ar.

    E quando a LISTAGEM traz a mesma tag móvel duas vezes com digests
    diferentes, os dois digests entram — em vez de deixar a última entrada
    vencer, como fazia o `digest_por_tag` que estava aqui. Um digest que aparece
    sob aquele nome de tag foi, em algum momento, o valor daquela tag: ignorá-lo
    porque a paginação o colocou na página errada era exatamente o mecanismo que
    ninguém conseguia descartar. Com 1206 tags em 7 páginas (medido em
    19/09/2026), a lista muda debaixo da leitura com facilidade.

    Com `digest` (lido na distribuição), a listagem deixa de opinar sobre a tag
    móvel e só mapeia o digest para as imutáveis — o que ela lista sob o nome
    móvel vai para a medida, não para a conclusão.
    """
    carregados = [
        t.get("manifest_digest") or "" for t in tags if t.get("tag") == moving_tag
    ]
    listados = tuple(dict.fromkeys(d for d in carregados if d))
    if digest:
        fonte, digests = FONTE_DISTRIBUICAO, (digest,)
    else:
        digests = listados
    extra = {"fonte": fonte, "na_listagem": listados if digest else ()}
    if not digests:
        return Leitura(
            (),
            (),
            len(carregados),
            f"a tag `{moving_tag}` não existe no registry",
            **extra,
        )

    shas: list[str] = []
    for t in tags:
        if t.get("manifest_digest") not in digests:
            continue
        match = IMMUTABLE.match(t.get("tag") or "")
        if match and match["tag"] == moving_tag and match["sha"] not in shas:
            shas.append(match["sha"])
    if not shas:
        return Leitura(
            (),
            digests,
            len(carregados),
            f"a tag `{moving_tag}` aponta para {', '.join(digests)}, e nenhuma "
            f"tag `{moving_tag}-<sha>` aponta para o mesmo digest — impossível "
            "provar qual commit está no ar",
            **extra,
        )
    return Leitura(tuple(shas), digests, len(carregados), "", **extra)


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
    distribuicao: Distribuicao | None = None,
) -> tuple[list[str], list[str]]:
    """Devolve (divergências, notas). Divergências vazias = o vivo bate com o `main`.

    As notas existem para o caso que passa mas merece ser visto: várias
    imutáveis dividindo um digest é dois commits publicando a MESMA imagem, e
    isso é desperdício de build e de registry mesmo quando a invariante está
    honrada.

    `distribuicao` é a fonte do digest das tags móveis. Sem ela (modo offline),
    ou na tag em que ela falhou, vale a listagem — e a medida diz qual valeu.
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
        tag = tag_de[name]
        if distribuicao is not None and tag in distribuicao.digests:
            leitura = read_published(tags, tag, digest=distribuicao.digests[tag])
        elif distribuicao is not None:
            falha = distribuicao.falhas.get(tag, "tag não consultada")
            leitura = read_published(
                tags,
                tag,
                fonte=f"{FONTE_LISTAGEM} (a distribuição falhou: {falha})",
            )
        else:
            leitura = read_published(tags, tag)
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
                f"{', '.join(_curto(d) for d in leitura.digests)}) — build e "
                "publicação repetidos"
            )
        if not all(queixas):
            # A imagem é idêntica nos candidatos: se ALGUM deles honra a
            # invariante, o que está no ar a honra. Não é escolher o mais
            # conveniente, é reconhecer que os bytes são os mesmos.
            continue
        problemas.append(f"{name}: {queixas[0]} [{leitura.medida()}]")
    return problemas, notas


def _confrontar(tags: list[dict], distribuicao, args, groups: dict[str, list[str]]):
    return audit(
        tags,
        ref=args.ref,
        per_app=args.per_app == "true",
        repo=Path(args.repo),
        groups=groups,
        distribuicao=distribuicao,
    )


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
    parser.add_argument(
        "--reconfirmacoes",
        type=int,
        default=4,
        help="quantas vezes reperguntar ao registry antes de acusar divergência",
    )
    parser.add_argument(
        "--espera",
        type=float,
        default=60.0,
        help="segundos entre uma repergunta e a seguinte",
    )
    args = parser.parse_args(argv)

    groups = load_groups(Path(args.groups_json))
    offline = bool(args.registry_json)

    moving_tags = [c["tag"] for c in build_matrix(list(component_paths(groups)), groups)]

    def perguntar() -> tuple[list[dict], Distribuicao | None]:
        if offline:
            payload = json.loads(Path(args.registry_json).read_text(encoding="utf-8"))
            return (payload["tags"] if isinstance(payload, dict) else payload), None
        token = os.environ.get("DO_TOKEN", "").strip()
        if not token:
            raise NaoDeuParaPerguntar("DO_TOKEN ausente")
        tags = fetch_tags(args.registry, args.repository, token)
        distribuicao = fetch_distribution(
            args.registry, args.repository, moving_tags, token
        )
        for falha in dict.fromkeys(distribuicao.falhas.values()):
            print(
                f"::warning::distribuição do registry não respondeu ({falha}) — "
                "a tag móvel afetada foi lida na listagem /tags, que pode estar "
                "atrasada por horas",
                file=sys.stderr,
            )
        return tags, distribuicao

    # ⚠️ A repergunta NÃO é paciência com divergência de verdade — essa
    # atravessa qualquer espera. É o conserto do defeito medido em 18/09/2026:
    # a guarda corria 67 s a 114 s depois de a tag móvel ter sido empurrada, e
    # lia a listagem `/tags` ainda no estado anterior ao push. Quatro corridas
    # vermelhas seguidas, nenhuma com componente realmente para trás — e a
    # remediação que a mensagem sugeria (republicar) não podia consertar, porque
    # não havia o que republicar. Um vermelho que sobrevive a cinco leituras ao
    # longo de quatro minutos é afirmação, não sintoma de leitura precoce.
    tentativas = 0
    try:
        while True:
            tags, distribuicao = perguntar()
            problemas, notas = _confrontar(tags, distribuicao, args, groups)
            tentativas += 1
            if not problemas or offline or tentativas > args.reconfirmacoes:
                break
            print(
                f"::notice::divergência na leitura {tentativas} "
                f"({len(problemas)} componente(s)) — reperguntando ao registry "
                f"em {args.espera:.0f}s, porque listagem lida logo depois de um "
                "push já veio no estado anterior a ele",
                file=sys.stderr,
            )
            time.sleep(args.espera)
    except (NaoDeuParaPerguntar, KeyError, ValueError, OSError) as exc:
        print(f"::warning::não deu para perguntar ao registry: {exc}", file=sys.stderr)
        return 2

    for nota in notas:
        print(f"::notice::{nota}", file=sys.stderr)
    if not problemas:
        if tentativas > 1:
            print(
                f"registry bate com o `main` na leitura {tentativas}: a listagem "
                "estava atrás do push, não havia componente para trás."
            )
        else:
            print("registry bate com o `main`: nenhum componente ficou para trás.")
        return 0

    for linha in problemas:
        print(f"::error::{linha}")
    atrasados = ",".join(linha.split(":")[0] for linha in problemas)
    print(
        f"::error::COMPONENTE PARA TRÁS, e não é leitura precoce: a divergência "
        f"sobreviveu a {tentativas} leitura(s) do registry. Republique com: "
        f'gh workflow run deploy-images.yml --ref main -f components="{atrasados}"'
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
