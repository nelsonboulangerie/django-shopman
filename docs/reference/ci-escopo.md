# Escopo da CI: leve no PR, pesado na fila

Decisão do dono, 17/11/2026 ("sim!"), proposta pela coordenação do go-live.

## Por quê

Cada PR rodava ~55 checks duas vezes: no `pull_request` e de novo no `merge_group`
da fila. Com muitas sessões abrindo PR ao mesmo tempo, o Surfaces Gate chegou a 72
min e a fila (`check_response_timeout_minutes: 60`) derrubou PRs por tempo. Um PR só
de documentação rodava as mesmas suítes de um PR do PDV.

Deixar a CI "para o final" não serve: push no `main` é deploy do alpha em 6 min, e o
que entra sem teste vai para o ar. A regra abaixo mantém o portão inteiro onde ele
importa, a fila, e tira do PR o que ele repetia.

## A regra

1. **No `pull_request` roda só o leve, e só o que o PR mexe.** O pesado roda no
   `merge_group`, que testa a árvore exata que pousa no `main`. Nada chega ao `main`
   sem a suíte inteira.
2. **Check obrigatório sempre reporta.** Os 29 contextos de
   [`.github/required-status-checks.json`](../../.github/required-status-checks.json)
   aparecem nos dois eventos. O que não roda no PR reporta verde ("pulado") com o
   **mesmo nome**; sem isso o PR espera para sempre um check que nunca vem. Nenhum
   workflow obrigatório usa `paths:` no gatilho, pelo mesmo motivo.
3. **Na dúvida, roda.** Evento que não é `pull_request`, lista de arquivos vazia,
   arquivo de infraestrutura ou pasta que a tabela não conhece ligam todo o leve. Um
   job de escopo que falha também não pula nada: só um `false` explícito pula.

## Quem decide o escopo

Cada workflow com filtro tem um job **Escopo do PR**, que chama a action local
[`.github/actions/ci-scope`](../../.github/actions/ci-scope/action.yml): o
`dorny/paths-filter` (v4.0.3, fixado por SHA) lista os arquivos do PR e
[`scripts/ci_scope.py`](../../scripts/ci_scope.py) os classifica (testes em
`scripts/tests/test_ci_scope.py`).

| Arquivo do PR | Classe | Liga no PR |
|---|---|---|
| `docs/**`, `evidence/**`, `prototypes/**`, qualquer `*.md` | documentação | só as travas sempre ligadas |
| `packages/**`, `shopman/**`, `config/**`, `tools/**`, `locale/**`, `manage.py` | Python | Testes (cores, storefront, counter-agent), Admin/Unfold, Admin CSP, Production Contract, CodeQL |
| `surfaces/<app>/**` | superfície | unit, component, lint e typecheck daquele app **e** do `operator-kit` (os guardrails do kit leem os apps irmãos), Production Contract, CodeQL |
| `.github/**`, `scripts/**`, `Makefile`, `Dockerfile`, `constraints.txt`, `.do/**`, raiz de `surfaces/`, pasta nova | infraestrutura | todo o leve, em todos os apps |

## O que roda onde

| Check | `pull_request` | `merge_group` |
|---|---|---|
| Ficou de fora declarado, Quality + deploy contract, Gate da meia-correção, Versões das superfícies, Contrato canônico das superfícies | sempre | sempre |
| Operator Groups Contract | escopo próprio (já existia) | sempre |
| Testes (test-cores / test-storefront / test-counter-agent), Admin/Unfold gate, Admin CSP | se mexeu Python | sempre |
| Production Contract, Security Gate (CodeQL) | se mexeu código | sempre |
| `operator-kit`, `<app>-nuxt` (Surfaces Gate) | leve, só nos apps tocados; os outros reportam verde | inteiro: navegador, visual, geometria, a11y, segurança, catálogo |
| Retratos macOS — `pos-nuxt` / `marketing-nuxt` (**não obrigatório**) | se tocou o app, a layer ou o contrato | não roda; noturno no `main` |
| Shop heavy/rest, Backstage seed/heavy/rest, Coverage Gate | pulado (agregadores `Testes (test-shop)`/`(test-backstage)` verdes) | sempre |
| Docker deploy image, PostgreSQL + Redis runtime stress gate | pulado | sempre |
| Browser QA, Storefront E2E | pulado | sempre |
| Supply chain, PWA | pulado | sempre |

## macOS fora do caminho obrigatório

Nenhum check obrigatório roda em macOS. Medido em 17/11/2026 em 36 grupos da fila:
`pos-nuxt` e `marketing-nuxt`, então em `macos-15`, esperavam 19 a 20 min por
máquina (mediana), até 88 e 126 min, e a fila derrubou PRs por tempo (#2589, #2531,
#2602, #2605) com todo o resto verde. O único motivo do macOS nesses dois apps é o
**retrato de pixel**, gravado no Chromium do `macos-15`. WebKit não entra: o único
app que o usa (`production-nuxt`) já roda em Linux com `--with-deps`, e a geometria
do PDV mede posição, não pixel.

- O app declara `visualRunner` em `surfaces/contracts.json`; `runner` próprio no
  check obrigatório é recusado pelo `surface_contract.mjs validate`.
- O check do app (`pos-nuxt`, `marketing-nuxt`) roda em Linux tudo menos o retrato:
  unit, component, lint, tipos, e2e, geometria, a11y e segurança.
- O retrato roda em **Retratos macOS — `<app>`** (`surfaces-visual-pinned.yml`), que
  **não é obrigatório**: no PR que toca o app, a layer ou o contrato (`paths:`), toda
  noite no `main` e à mão. Falha noturna abre ou comenta a issue "Retratos presos ao
  macOS reprovaram no main".
- O custo: uma regressão só de pixel nesses dois apps pode chegar ao `main` se o
  autor ignorar o vermelho do PR; a rodada noturna a acusa no dia seguinte. Gravar as
  baselines deles em Linux, como os outros apps, devolve o retrato ao caminho
  obrigatório, mas isso pede regerar e revisar o antes/depois com o dono.

## O custo que aceitamos

- **Defeito pesado aparece na fila, não no PR.** Baseline visual, browser QA ou shard
  do shop que quebra tira o PR da fila e ele volta. É mais lento que ver no PR, e
  continua impossível de chegar ao `main`.
- **Teste que lê documentação.** Algumas suítes Python e guardrails das superfícies
  leem `docs/` (vocabulário, runbooks, governança). Num PR só de docs eles rodam só
  na fila.
- Para ver o pesado antes da fila, rode o alvo local (`make test-shop`,
  `make test-backstage`, o `surface_contract.mjs run <app> <fase>`) ou dispare o
  workflow com `workflow_dispatch` quando ele tiver.

## Como mexer sem travar o repositório

- Job **matriz** que gera check obrigatório (`Testes (test-*)`, os apps de
  `surfaces/`) **não** pode ser pulado no `if:` do job: matriz pulada no nível do job
  reporta um check só, com o nome sem a matriz (`imagem ${{ matrix.group }}` é o
  exemplo vivo), e os obrigatórios nunca chegam. Pule nos **passos**.
- Job **sem matriz** pode ser pulado no `if:` do job: reporta "skipped" com o nome,
  e a proteção do branch lê como verde.
- Agregador (`Testes (test-shop)`, `Testes (test-backstage)`, `Security Gate`) aceita
  `skipped` **só** no `pull_request`; em qualquer outro evento continua reprovando.
- `python scripts/check_canonical_docs.py` confere que os 29 obrigatórios seguem
  produzidos em `pull_request` + `merge_group`.

## Cache dos navegadores mora no `main`

O cache do Actions é escopado por ref: um grupo da fila (`gh-readonly-queue/main/pr-N-<sha>`)
só lê cache do próprio ref e do `main`, e o Surfaces Gate não roda no `main`. Sem isso, todo
grupo baixava do zero os 140 MB de pacotes apt do WebKit do `production-nuxt` e, com o
espelho lento, estourava o teto (#2679, #2756, #2757, 19/11/2026). O
[`playwright-cache-main.yml`](../../.github/workflows/playwright-cache-main.yml) grava no
`main` as mesmas chaves que o Surfaces Gate restaura (no push que muda lock, script ou
contrato, de 6 em 6 horas e à mão), uma por combinação de `surface_contract.mjs matrix
browsers`. O Surfaces Gate só restaura; gravar no ref da fila enchia a cota sem servir a
ninguém.
