# Contrato de release

Referência factual do WP-RELEASE-01 (`docs/plans/WP-RELEASE-01-versoes-de-apps-sem-quebra.md`).
Vale o que está no código; este arquivo diz onde cada coisa mora. A decisão de fundo
(construir uma vez, promover o mesmo digest; V1/V2 dentro da mesma superfície) está na
[ADR-043](../decisions/adr-043-build-once-promote-e-convivencia-v1-v2.md).

Estado: **R0, R1 e R2 entregues.** R3 em diante (rollback por release set, coortes V1/V2)
ainda não existe; onde este contrato fala delas, é o alvo, e está marcado. A R2 está pronta
no código, mas a produção só passa a existir como ambiente separado com os passos do dono em
[promover-release.md](../runbooks/promover-release.md#o-que-falta-para-ligar-ação-do-dono).

## Nomes

| Termo | O que é | Onde nasce |
| --- | --- | --- |
| **Componente** | Uma imagem deployável: `web`, `storefront-nuxt`, `operator-floor`, `operator-office`. | `scripts/deploy_components.py` (tabela de caminhos) + `surfaces/operator-router/groups.json` |
| **Release ID** | Nome de uma composição: `AAAAMMDD-HHMM-<sha curto>`, com a hora do **commit** em UTC. O mesmo commit dá sempre o mesmo ID. | passo `Release ID` do job `changes` em `.github/workflows/deploy-images.yml` |
| **Build SHA** | O commit completo (40 hex) do qual a imagem foi construída. | `github.sha` no mesmo workflow |
| **Build** | Imagem imutável, tag `<tag>-<sha>` + digest. | job `build-push` |
| **Release set** | Os quatro digests que compõem um ambiente. | `release_set` do manifesto do run (artefato `release-manifest`, 90 dias); durável de verdade só na R3 |
| **Candidato** | O release set de um commit do `main`, com digests imutáveis. | job `manifest` do Deploy Images |
| **Tag de produção** | `<tag>-prod` (`web-prod`, `storefront-prod`, `operator-floor-prod`, `operator-office-prod`). Só a promoção escreve. | `.github/workflows/promote-release.yml` |
| **Versão do app** | Geração de experiência (Marketing V1/V2). Não é SemVer e não é versão de API. | R4 |

Não há SemVer global: o deploy é contínuo e seletivo, e um `2.3.1` esconderia que cada
componente pode estar num commit diferente.

## Inventário (gerado, nunca escrito à mão)

```console
python scripts/release_inventory.py inventory
```

Sai de `groups.json` e da tabela do `deploy_components.py`, confrontados com o campo
`service` de `surfaces/registry.json`. Hoje:

- `web`: Django, API e workers (`web-operator`, `web-storefront`, `directive-worker`,
  `maintenance-worker`, `ifood-poll-worker` e o job `release` usam a mesma imagem);
- `storefront-nuxt`: a loja;
- `operator-floor`: PDV, Cozinha, Gestor de pedidos, Produção, Central;
- `operator-office`: Marketing, B.I., Compras.

A trava é `shopman/shop/tests/test_release_inventory.py`: reprova se registry, grupos e
deploy discordarem sobre quem serve cada superfície.

## Identidade na imagem (R1)

O `deploy-images.yml` passa três build args a todo Dockerfile, e cada um os vira `ENV` e
`LABEL` OCI **na última camada** (o valor muda a cada commit; mais acima ele invalidaria
o cache de pip, `npm ci` e `nuxt build`):

| Build arg / ENV | LABEL OCI | Valor |
| --- | --- | --- |
| `SHOPMAN_BUILD_SHA` | `org.opencontainers.image.revision` | commit completo |
| `SHOPMAN_RELEASE_ID` | `org.opencontainers.image.version` | Release ID |
| `SHOPMAN_RELEASE_COMPONENT` | `org.opencontainers.image.title` | nome do componente |

Build local sem esses args fica **sem identidade** (strings vazias), e o endereço diz
isso. Nenhum dos três é segredo nem pode virar segredo. A identidade não entra no bundle
do cliente: a tela pergunta ao próprio servidor (abaixo), e é o servidor que está no ar.

O manifesto do run (`published.json`) ganhou `release_id`, `git_sha` e `source_run` ao
lado de `sha`/`components`/`deployment`, que seguem sendo o contrato do alpha-smoke.

## Candidato, alpha e produção (R2)

Três estados de uma imagem, três tipos de tag:

| Tag | Quem escreve | Quem lê |
| --- | --- | --- |
| `<tag>-<sha>` (imutável) | Deploy Images, no build | manifesto, promoção, drift |
| `<tag>` (móvel do alpha) | Deploy Images, no build | o app alpha (spec vivo) |
| `<tag>-prod` | **só** o Promote Release, por retag | o app de produção |

**Manifesto do release** (`scripts/release_manifest.py release-set`, no job `manifest` do
Deploy Images, artefato `release-manifest`). Aditivo ao `published.json` de antes; o
alpha-smoke segue lendo `components`/`deploy_mode`:

```json
{
  "schema_version": 2,
  "release_id": "20261109-2057-8835050",
  "git_sha": "8835050…",
  "source_run": 42700750281,
  "deploy_mode": "single_deployment",
  "migration_graph_hash": "sha256:…",
  "release_set": {
    "web": {"tag": "web", "digest": "sha256:…", "immutable_tag": "web-82e829f…",
            "build_sha": "82e829f…", "release_id": "…", "built_in_this_run": false},
    "storefront-nuxt": {"…": "…"}, "operator-floor": {"…": "…"}, "operator-office": {"…": "…"}
  }
}
```

O build é seletivo, o release set não: componente que o run não construiu sai do registry
pela tag móvel (a mesma que o deployment do alpha resolve), com o commit lido da LABEL OCI
da R1 (`org.opencontainers.image.revision`) e conferido contra a tag imutável irmã. Falha
de registry aqui não derruba o alpha: vira `release_set_error`, e esse release não é
promovível. `migration_graph_hash` é o sha256 de toda migration versionada, para a R3.

**Papel do app.** `app_role()` lê o spec vivo: todo componente de imagem nas tags móveis
é `alpha`; todo nas `-prod` é `production`; qualquer mistura reprova. O Deploy Images não
cria deployment em app `production` (`deploy_mode: production_pinned`), e a promoção não
implanta em app que não seja `production` nem tenha `deploy_on_push`.

**Promoção** (`.github/workflows/promote-release.yml` + `scripts/promote_release.py`):
dispatch manual no `main`, `dry-run` por padrão; o job que escreve exige o GitHub
Environment `production` com revisor obrigatório e só `main`. Ordem: valida (ancestralidade,
manifesto, smoke do alpha verde depois daquele deploy, digests no registry, proteção) →
retag pelo digest, sem build → GitHub Deployment → deployment na DO até `ACTIVE` e
`/health/release` de cada componente igual ao `build_sha` promovido → smoke de produção.
Procedimento e o que falta ligar: [promover-release.md](../runbooks/promover-release.md).

## Endereço de versão

`GET /health/release` (com barra final no Django). Público, constante, `Cache-Control:
no-store`, sem banco, sem Django (no BFF), sem chamada a GitHub ou DigitalOcean.
Separado de `/health/live` e `/health/ready`: não é sonda de plataforma.

```json
{
  "schema_version": 1,
  "component": "operator-floor",
  "app": "pos",
  "release_id": "20261102-1403-caf4503",
  "build_sha": "caf450360…"
}
```

| Onde | Arquivo | `component` | `app` |
| --- | --- | --- | --- |
| Django (`api.`) | `packages/watchman/shopman/watchman/release.py` (`ReleaseIdentityView`), montado em `config/urls.py` | `web` | (ausente) |
| Apps de operador | `surfaces/operator-kit/server/routes/health/release.get.ts` + `server/utils/releaseIdentity.ts` | grupo | id do app |
| Loja | `surfaces/storefront-nuxt/server/routes/health/release.get.ts` | `storefront-nuxt` | `storefront` |

Valor fora do contrato (SHA que não tem 40 hex, Release ID fora do formato) é
respondido como vazio: número inventado é pior que "sem identidade".

**Header.** Com identidade, as respostas carregam `X-Shopman-Release: <release_id>`: todo
o BFF de operador (`server/plugins/release-header.ts`) e as respostas `/api/v1/` do Django
(`APIVersionHeaderMiddleware`). É o que o suporte lê na aba de rede.

**Tela.** `OperatorReleaseLabel` (operator-kit) escreve "Versão do serviço: <Release ID>"
numa linha discreta, hoje no rodapé do detalhe "Capacidade do serviço" do rail. Sem
identidade, a linha não aparece. A peça é isolada para o novo modelo de navegação
encaixá-la no selo sem mexer na leitura. A loja não mostra versão ao cliente.

## Sonda: o commit do `main` contra o vivo

`shopman.watchman.release.ReleaseIdentityCheck`, id `release_identity`, perfil `release`:

```console
WATCHMAN_EXPECTED_RELEASE_SHA=$(git rev-parse origin/main) \
WATCHMAN_RELEASE_URL_WEB=https://api.boulangerie.com.br/health/release/ \
WATCHMAN_RELEASE_URL_STOREFRONT=https://www.nelsonboulangerie.com.br/health/release \
WATCHMAN_RELEASE_URL_OPERATOR_FLOOR=https://pdv.boulangerie.com.br/health/release \
WATCHMAN_RELEASE_URL_OPERATOR_OFFICE=https://mkt.boulangerie.com.br/health/release \
.venv/bin/python manage.py watchman check --profile release --format json
```

O `settings` guarda só os NOMES das variáveis; endereço e commit esperado são de quem roda
a sonda (os hosts são da instância, não do código). Por componente:

| Resultado | Quando |
| --- | --- |
| `pass` | serve o commit esperado, ou nada que entra no componente mudou entre o vivo e o esperado |
| `fail` | resposta fora do contrato, imagem sem identidade, endereço servindo outro componente, ou commit atrás |
| `unknown` | sem endereço, rede fora, sem commit esperado, sem histórico do git |

O deploy é seletivo: push só de Django não reconstrói `operator-floor`. Por isso a
igualdade não basta, e a equivalência (`shopman/shop/watchman_release.py`) pergunta ao git
se algum arquivo do componente mudou entre os dois commits, com a mesma tabela de caminhos
do `deploy_components.py`. Precisa do histórico: no contêiner de produção a resposta é
`unknown`, nunca `pass`.

**Ainda não ligada a workflow.** Na promoção, a prova equivalente é o passo `verify` do
`promote_release.py`, que cobra igualdade com o commit promovido de cada componente (não
contenção: ali se sabe exatamente o que foi ao ar). Ligar a sonda ao alpha entra com a R5,
junto do smoke por app.

## Classes de risco do diff

```console
python scripts/release_inventory.py risk --base origin/main --head HEAD
```

Markdown pronto para o PR: componentes que o diff publica, classe mais alta, caminho
mínimo e rollback primário. A regra de caminho mora em `classify()`; a tabela é a do
plano (§5):

| Classe | Caminhos |
| --- | --- |
| Schema | `*/migrations/*.py` |
| Config/secret/topologia | `.do/**`, `.github/workflows/**` |
| operator-kit/router | `surfaces/operator-kit/**`, `surfaces/operator-router/**` |
| Mutation/efeito externo | `handlers/`, `adapters/`, `webhooks/` em Python |
| Dependência/runtime | `package.json`, `package-lock.json`, `constraints.txt`, `pyproject.toml`, `Dockerfile*` |
| Projection/API | `api/`, `projections/`, `presentation/`, `intents/` e demais Python de runtime |
| UI local | resto de `surfaces/*` fora de testes |

Ainda não comenta sozinho no PR: o comando é a saída, e ligar a um workflow é passo da R2.

## Coortes e flags (decisão para a R4)

Pela D5 do plano: a variante V1/V2 é resolvida no servidor/BFF, aderente à sessão, com
coortes nomeadas `off`, `internal`, `pilot`, `default` e kill switch sem deploy. Mora na
configuração canônica que já existe (`RuleConfig`, por loja, no banco), nunca em env,
`settings`, query string ou cookie editável (ADR-042 vale aqui também). Quem altera é
quem já administra `RuleConfig` no Admin; toda flag nasce `off` e declara dono,
justificativa e `remove_after`. Se a R4 provar que `RuleConfig` não atende, o gap vira
ADR antes de qualquer control plane novo.
