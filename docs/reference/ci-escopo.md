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
| Shop heavy/rest, Backstage seed/heavy/rest, Coverage Gate | pulado (agregadores `Testes (test-shop)`/`(test-backstage)` verdes) | sempre |
| Docker deploy image, PostgreSQL + Redis runtime stress gate | pulado | sempre |
| Browser QA, Storefront E2E | pulado | sempre |
| Supply chain, PWA | pulado | sempre |

No PR, o leve das superfícies roda em Linux mesmo no app declarado em macOS: o macOS
só existe pelas baselines visuais e pelo WebKit, que ficam na fila.

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
