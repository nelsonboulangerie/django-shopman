# 08 — Fricção de CI, merge e deploy (medida no código)

- **Árvore analisada:** `.dsh-worktrees/go-live-acceleration`, `origin/main` = `f0ffd02fde765493d734bae93a72bb361ed28fcf` (2026-09-29 15:36 UTC).
- **Modo:** somente leitura. Nenhum arquivo alterado além deste relatório.
- **Marcadores:** `[FATO]` = verificado no código/saída de comando · `[INFERÊNCIA]` = dedução minha · `[NÃO VERIFICADO]` = não consegui confirmar.
- **Onde não consegui olhar:** `gh` está com token inválido nesta máquina (`gh auth status` → *The token in default is invalid*), então **não li a branch protection viva nem durações reais de runs**. Os números de duração vêm de medições **registradas no próprio repositório**, com `arquivo:linha`.

> ⚠️ O briefing da tarefa cita `runtime-gate.yml` com 277 linhas, `omotenashi-gate.yml` com 301 e `surfaces-gate.yml` com 86. Os arquivos reais têm **557 / 304 / 352** linhas (`wc -l`), e há **10 workflows**, não 5. O briefing está desatualizado; este relatório usa os números medidos.

---

## 1. Resumo executivo

1. **O custo de CI por merge é ~2× o custo de CI por PR** — e isso é deliberado. Seis workflows disparam em `pull_request` **e** em `merge_group`, então a mesma árvore passa duas vezes por um fan-out de **47 execuções de job por evento** (`[FATO]`, contagem sobre os YAML). O merge group é quem dá a garantia; o run de PR hoje é uma segunda cópia inteira dela.
2. **Nada é escopado por caminho nos gates caros.** Um PR que só mexe em `shopman/backstage/` roda a matriz inteira de 10 apps Nuxt, 8 builds de imagem Docker, 5 builds Nuxt de produção e o browser QA Omotenashi. O padrão de escopo **já existe** no repositório (`operator-groups-gate.yml`) — só não foi aplicado nos três gates grandes.
3. **`make install` roda 13× por evento e ~26× por merge** (`[FATO]`), a ~3 min cada (custo declarado em `runtime-gate.yml:240` e `:292`) → **~78 min-runner por merge só instalando dependência Python**, e 3 desses minutos estão dentro do caminho crítico do Runtime Gate.
4. **`npm ci` roda 46× por evento e ~92× por merge** (`[FATO]`), incluindo a mesma `operator-kit` instalada **18 vezes por evento**.
5. **9 builds Docker frios por PR** (`[FATO]`): 1 da imagem `web` (`runtime-gate.yml:477`) e 8 por app (`surfaces-gate.yml:216`), **sem `cache-from`/`cache-to` e sem buildx** — o único build com cache é o do deploy.
6. **O cache do GitHub Actions está acima do teto** — 12,28 GB em 166 entradas contra o limite de 10 GB do repositório (`WP-PERFORMANCE-2026-09.md:64`), o que faz o GitHub **despejar cache por LRU**: boa parte dos `cache: pip`/`cache: npm` é fria por construção.
7. **O deploy tem p50 de 5,5 min e p90 de 10 min** do push à versão no ar (`WP-PERFORMANCE-2026-09.md:60`, 14 dias, n=193), com 391 deployments em 7 dias sendo **184 cancelados e 39 em erro** (:61-63).
8. **Ganho realista e sem perder garantia:** PR de ~15-25 min para ~6-8 min (feedback), merge queue estável em ~12-15 min (a garantia continua inteira na fila), e commit→produção de p50 ~32-55 min para ~20-25 min. `[INFERÊNCIA]` — ver §5.
9. **A maior parte disso já está diagnosticada e proposta** em `docs/plans/WP-PERFORMANCE-2026-09.md` (§2.2, gargalo 5, proposta P5). O que falta é uma frente **de CI**, que não existe em nenhum plano do repositório (`grep` por *moroso/lentidão/CI lenta/acelerar CI` em `docs/plans`, `docs/reports`, `docs/runbooks`: **não encontrado**).
10. **Quatro jobs rodam vermelho-irrelevante ou duas vezes:** `make test-migrations` roda em `quality` **e** no Production Contract; 282 testes do Admin rodam em `admin-gate` **e** no shard `test-backstage-rest`; 49 testes do `quality` rodam também no `test-shop`; e o `admin-csp` executa em todo PR **sem ser obrigatório** (`docs/runbooks/branch-protection-pendencias.md:28-39`).

---

## 2. Achados

### A1 — Todo gate roda duas vezes (PR + merge group) `[FATO]`

```
runtime-gate.yml:3-15      on: pull_request + merge_group (sem push, de propósito)
surfaces-gate.yml:12-28    on: pull_request + merge_group
omotenashi-gate.yml:9-21   on: pull_request + merge_group
production-contract.yml:3-6 on: pull_request + merge_group
operator-groups-gate.yml:13-16 on: pull_request + merge_group
security-gate.yml:3-10     on: pull_request + merge_group + push + schedule
```

Contagem de execuções de job por evento (parse dos YAML com PyYAML, matrizes multiplicadas):

| Workflow | jobs declarados | execuções por evento |
|---|---:|---:|
| `surfaces-gate.yml` | 5 | **22** (app-quality ×10, pwa-quality ×9, marketing, produção, versões) |
| `runtime-gate.yml` | 9 | **13** (tests ×4, backstage shards ×2, +7 singulares) |
| `operator-groups-gate.yml` | 4 | 5 (2 imagens de grupo; 4 ficam `skipped` quando o escopo não é relevante) |
| `omotenashi-gate.yml` | 3 | 3 |
| `security-gate.yml` | 2 | 3 (CodeQL python + js/ts + agregador) |
| `production-contract.yml` | 1 | 1 |
| **Total por evento** | | **47** |

`[INFERÊNCIA]` multiplicando por 2 (PR head + merge group): **~94 execuções de job por merge**. O Security Gate ainda paga uma terceira passada em `push: main` (`security-gate.yml:6-7`) — os outros gates cortaram exatamente isso e documentaram por quê (`runtime-gate.yml:9-13`).

### A2 — Instalação de dependências: 13 `make install` e 46 `npm ci` por evento `[FATO]`

`make install` (Makefile:29-70; instala 13 pacotes com `pip install -e` + `pip install --upgrade pip`):

| Arquivo:linha | Job | Execuções |
|---|---|---:|
| `runtime-gate.yml:48` | `quality` | 1 |
| `runtime-gate.yml:273` | `admin-gate` | 1 |
| `runtime-gate.yml:320` | `tests` (matriz 4) | 4 |
| `runtime-gate.yml:374` | `tests-backstage-shards` (matriz 2) | 2 |
| `runtime-gate.yml:548` | `runtime-security-reliability` | 1 |
| `omotenashi-gate.yml:91,218,284` | 3 jobs | 3 |
| `production-contract.yml:80` | 1 job | 1 |
| | **por evento** | **13** |

Custo unitário declarado no próprio código: `runtime-gate.yml:238-240` — *"Sem `make install`: o gate é `ast` + `re` da biblioteca padrão… Instalar a suíte aqui custaria **3 min** para provar o que 2 segundos provam"*; e `runtime-gate.yml:291-292` — *"O job cobre **install (~3 min)** + step"*. `[INFERÊNCIA]` 13 × 3 min = **~39 min-runner por evento**, **~78 por merge**.

`npm ci` (`[FATO]`, contando as condições `if` de cada matriz):

- `surfaces-gate.yml`: `app-quality` ×10 → kit 8 (`:108`) + app 10 (`:112`) = 18; `pwa-quality` ×9 → kit 8 (`:176`) + app 9 (`:180`) = 17; `marketing-complete` 2 (`:252,255`); `production-browser` 2 (`:330,333`) → **39**.
- `omotenashi-gate.yml`: kit 1 (`:96`) + 5 apps em laço (`:101-103`) + storefront 1 (`:286`) → **7**.
- `operator-groups-gate.yml`: 0 (`operator-router` não tem dependências, `:77`).
- **por evento: 46** → `[INFERÊNCIA]` **92 por merge**.

Cache existe (`cache: pip` em 5 jobs do runtime-gate + 3 do omotenashi + 1 do production-contract; `cache: npm` em 4 jobs do surfaces + 2 do omotenashi) — `[FATO]`. **Não existe um único `actions/cache`** em `.github/workflows/` (`grep`: nenhum resultado), então nada cacheia `~/.cache/ms-playwright`, `.nuxt`, nem um venv preparado.

### A3 — Nada é escopado por caminho nos gates caros `[FATO]`

```
surfaces-gate.yml:3-7   "Roda em TODO pull_request, sem paths filter" (com o motivo certo
                        documentado: required check que não reporta trava o merge)
runtime-gate.yml:3-15   sem paths
omotenashi-gate.yml:9-21 sem paths
production-contract.yml:3-6 sem paths
```

Consequência medida: um PR que toca só `shopman/backstage/projections/*.py` paga, no mesmo evento, **39 npm ci + 10 vitest/typecheck/lint de apps Nuxt + 9 builds Nuxt de produção + 8 builds Docker + 5 downloads de browser + 3 seeds**. `[INFERÊNCIA]` 15-30 min-runner desperdiçados por PR que não toca Nuxt nenhum.

**O padrão correto já está no repositório** e não foi aplicado aos três gates grandes: `operator-groups-gate.yml:8-11` declara o filtro de caminho **e diz por que ele só é seguro porque o workflow não é check obrigatório**; `:23-57` calcula o escopo do diff; `:161-183` é o **agregador com nome estável** que sempre reporta e reprova se o trabalho aplicável falhou. É a receita pronta.

### A4 — 9 builds Docker frios por PR `[FATO]`

```
runtime-gate.yml:477   docker build --tag django-shopman:ci .            (imagem web, 1×)
surfaces-gate.yml:216  docker build -f surfaces/Dockerfile.surface …    (8× — todos menos storefront)
```

Nenhum dos dois usa `docker/setup-buildx-action` nem `cache-from`/`cache-to` (`grep` por `cache-from`: só `deploy-images.yml:217-218` e `operator-groups-gate.yml:117-118`). Pior: `surfaces/Dockerfile.surface:23` roda `npm ci` **dentro do build** e `:27-33` roda `npm run build` — ou seja, cada um dos 8 builds refaz instalação e build Nuxt do zero, num runner que já fez `npm ci` dois passos antes. `[INFERÊNCIA]` 2-5 min por build → **20-45 min-runner por evento**, ×2 no merge.

### A5 — `OPERATOR_PER_APP_IMAGES: "true"` publica 8 imagens que **nenhum spec vivo referencia** `[FATO]`

`deploy-images.yml:55-79` mantém a flag ligada como *rede de rollback da ADR-030*, com prazo escrito: **desligar a partir de 2026-10-01** (`:62`). O comentário reconhece que, desde 17/09 15:54 UTC, *"nenhuma tag por app voltou a causar implantação — nunca"* (`:69`).

`.do/app.alpha-subdomains.yaml` (o app vivo `shopman-nelson`) referencia **apenas quatro tags** — `web` (`:889`), `storefront` (`:931`), `operator-floor` (`:1084`), `operator-office` (`:1173`) — e tem **8 blocos `deploy_on_push: {enabled: true}`** (`:890, 932, 1085, 1174, 1200, 1215, 1230, 1252`). Nenhuma tag por app (`pos`, `kds`, `orders`, `production`, `hub`, `marketing`, `bi`, `purchase`) aparece.

Ou seja: 8 builds + 8 tags publicadas por push que toca `operator-kit`/`operator-router`, para imagens **sem consumidor**. `[FATO]` `scripts/deploy_components.py:350-351` já sabe desligá-las (`--per-app false`).

### A6 — Um único push de tag `web` move 5 componentes do spec `[FATO]`

```
.do/app.alpha-subdomains.yaml:889  tag: web   → service web
:1199 tag: web  (:1197)             → directive-worker
:1214 tag: web  (:1212)             → maintenance-worker
:1229 tag: web  (:1227)             → ifood-poll-worker
:1251 tag: web  (:1249)             → release   (check --deploy, migrate, setup_groups, bootstrap)
```

`[INFERÊNCIA]` republicar `web` (qualquer merge que toque `packages/**`, `shopman/**`, `config/**`, `tools/**`, `Dockerfile` — `scripts/deploy_components.py:81-90`) move 4 workers + o job de release junto, e o `release` roda migração. É consistente com o medido: **391 deployments em 7 dias, 184 cancelados, 39 em erro, todos `release: DeployContainerExitNonZero`** (`WP-PERFORMANCE-2026-09.md:61-63`).

### A7 — O `.do/app.subdomains.yaml` (produção) **não usa DOCR** `[FATO]`

```
.do/app.subdomains.yaml:611-616   - name: web / git: repo_clone_url … branch: main / dockerfile_path: Dockerfile
grep -c "deploy_on_push" .do/app.subdomains.yaml → 0
grep -n  "image:" .do/app.subdomains.yaml        → nenhum
```

O blueprint de produção constrói **a partir do git**, não puxa imagem pronta. `[INFERÊNCIA]` aplicá-lo reintroduz exatamente a "fila compartilhada de builders da DO" que o `deploy-images.yml:3-9` foi escrito para tirar da equação, e faria os 9 componentes construírem a cada push no `main` — sem seleção por path e sem GHA cache. Hoje isso não está no ar (o R8 confirma que o app vivo é o alpha, `docs/reports/2026-09-29-r8-cutover-preflight.md:6,46`), mas é um risco de cutover, não uma otimização.

### A8 — Redundância de trabalho idêntico entre gates `[FATO]`

| O que | Onde roda 1 | Onde roda 2 | Volume duplicado |
|---|---|---|---|
| `make test-migrations` | `runtime-gate.yml:126-127` | `production-contract.yml:107` | 2× por evento (`scripts/check_migrations.py`: `makemigrations --check` + `migrate` de banco zero sobre 290 arquivos de migração) |
| 3 arquivos de teste do Admin | `Makefile:648` (`make admin`, no `admin-gate`) | `Makefile:248` (`test-backstage-rest`) | **282 testes** medidos por `--collect-only` |
| 3 arquivos do `quality` | `runtime-gate.yml:139-142` | `Makefile:193` (`test-shop` ×4 na matriz) | **49 testes** medidos |
| `make install` | 13 jobs | — | ver A2 |
| `seed --flush` | `run_omotenashi_browser_ci.sh:90` | `run_admin_csp_gate.sh:96`, `run_storefront_e2e.sh:68` + `omotenashi-gate.yml:140` (2ª passada deliberada) | **4 seeds por evento** |

Os 282 testes do Admin são o caso mais claro: são **paralelos**, então o relógio não muda, mas `test_admin_operational_integration.py` tem 43.869 bytes e roda em dois jobs.

### A9 — Suíte coletada hoje: 23.050 testes `[FATO]` (medido nesta árvore)

```
PYTHONPATH=<worktree>:packages/* DJANGO_SETTINGS_MODULE=config.settings_test \
  python -m pytest <dir> --collect-only -q

shopman/shop/tests        → 10508/10539 coletados (31 desselecionados) em 7,91 s
shopman/storefront/tests  → 2219 coletados em 3,64 s
shopman/backstage/tests   → 7239 coletados em 6,01 s
tools/pos-counter-agent   → 170 coletados em 0,22 s
packages/** (12 cores)    → 2914 coletados em 4,74 s
```

Total `make test` = **23.050 testes**. `[FATO]` o runbook de branch protection registra *"7.780 testes coletados"* em 05/09/2026 (`docs/runbooks/branch-protection-pendencias.md:18`) — a suíte **triplicou** em 24 dias, e o desenho do gate (2 jobs de instalação por shard, 5 shards) não foi revisto desde então.

### A10 — O que `make test` e `make admin` rodam, e o que se sabe de tempo `[FATO]`

`make test` (`Makefile:81`) encadeia 15 alvos **em série**: 12 pacotes do Core (`Makefile:100-146`), depois `test-framework` = `test-shop` + `test-storefront` + `test-backstage` (`Makefile:148`), depois `test-counter-agent`. Nenhum usa `-x`, de propósito (`Makefile:84-99`).

Tempos **registrados** no repositório (não medidos por mim — não rodei a suíte, a worktree não tem `.venv`):

| Evidência | Valor |
|---|---|
| `Makefile:74-77` | *"~1 min de cores + ~12 de framework"* |
| `Makefile:206-208` | job `test-backstage` (install+step) **12min26s / 12min55s / 12min42s**; `test-shop` 4min25s / 5min26s / 5min06s |
| `Makefile:210-213` | os 7 arquivos de seed valem **62% do relógio** do backstage (mas são só 21 testes — `--collect-only` acima) |
| `runtime-gate.yml:278-281` | antes da matriz: *"13 alvos encadeados… o gate inteiro levava **18 min**"* |
| `docs/runbooks/branch-protection-pendencias.md:71` | *"numa suíte de **~13 minutos**"* |

`make admin` (`Makefile:643-650`) = `scripts/check_unfold_canonical.py --maturity` + `pytest` de 3 arquivos (**282 testes**). É o passo inteiro do job `admin-gate`, que também paga `make install`.

### A11 — Browsers baixados 5× por evento, sem cache `[FATO]`

```
surfaces-gate.yml:187   npx playwright install --with-deps chromium       (pwa-quality/storefront)
surfaces-gate.yml:259   npx playwright install chromium                   (marketing, macOS)
surfaces-gate.yml:340   npx playwright install --with-deps chromium webkit(production-browser, 2 engines)
scripts/run_admin_csp_gate.sh:92    python -m playwright install chromium (admin-csp)
scripts/run_storefront_e2e.sh:64    python -m playwright install chromium (storefront-e2e)
omotenashi-gate.yml:83-85           browser-actions/setup-chrome@v2      (Omotenashi)
```

Nenhum `actions/cache` para `~/.cache/ms-playwright`. `[INFERÊNCIA]` 1-3 min por job, 6 jobs por evento.

### A12 — Serialização do deploy: 1 assento de espera, runs mortos com 0 jobs `[FATO]`

`deploy-images.yml:48-50` usa `concurrency: deploy-images` com `cancel-in-progress: false`. O comentário (`:34-47`) e `scripts/deploy_components.py:19-29` registram a medição: **das 431 execuções, 9 canceladas, todas com zero jobs**, todas pela fila de merge — o GitHub guarda **um** assento de espera e mata o que já esperava:

```
#814  6388d96b6  nasceu 23:44:20Z   success  (web, pos-nuxt, operator-floor)
#815  2ab8ec5d6  cancelado 23:44:21Z, 0 jobs   ← 11 arquivos de surfaces/pos-nuxt/** não foram construídos
#816  5d3b19cc7  terminou 23:48:33Z
#814 começou a rodar 23:48:37Z  → esperou 4min17s na fila
```

O conserto de **correção** já está feito (base = último deploy bem-sucedido, `deploy-components.py:31-55` + job `drift`, `deploy-images.yml:315-381`). O conserto de **tempo** não: a leva de 3 merges custou ~4 min de espera ao terceiro e uma reconstrução completa.

### A13 — `push: main` do Security Gate é a terceira passada `[FATO]`

`security-gate.yml:6-7` roda CodeQL (2 linguagens) em `pull_request`, `merge_group` **e** `push: main`, além do `schedule` semanal (`:8-9`). `runtime-gate.yml:9-15` documenta a decisão oposta para os gates — *"Rodar de novo depois do merge era a terceira passagem da mesma suíte no mesmo código: gastava runner e disputava fila com os PRs de verdade, sem provar nada"*. CodeQL é o job mais caro do repositório fora do Surfaces Gate (`timeout-minutes: 30`, `:24`).

### A14 — `admin-csp` roda em todo PR e não bloqueia `[FATO registrado]`

`docs/runbooks/branch-protection-pendencias.md:28-39`: *"o job `Admin CSP (production settings)` (…`omotenashi-gate.yml:169`) … roda em todo PR — e **não está na lista de contextos obrigatórios**. É o único gate do repositório nessa situação."* Custo pago, proteção zero. A recomendação do próprio runbook é torná-lo obrigatório (custo zero).

Mesmo runbook, `:12-16`: **21 checks obrigatórios**, `enforce_admins: true`, `required_status_checks.strict: false` (medido em 05/09/2026 via `gh api …/branches/main/protection`). `[NÃO VERIFICADO]` o número hoje (token inválido) e `[NÃO VERIFICADO]` a lista nominal — ela **não está versionada em nenhum arquivo do repositório**; só o runbook a descreve.

### A15 — Configuração de merge queue: só a convenção, não o arquivo `[FATO]`

Não existe arquivo de configuração de merge queue no repositório (é configuração do GitHub). O que há é evidência convergente:

- os 6 workflows com `merge_group:` e o comentário *"Sem este gatilho os checks obrigatórios nunca rodam no merge group e a fila trava para sempre"* (`runtime-gate.yml:5-7`, repetido em `surfaces-gate.yml:14-16`, `omotenashi-gate.yml:11-13`);
- `docs/runbooks/branch-protection-pendencias.md:73-82`: *"este repositório **usa merge queue**. A fila já testa o resultado do merge… e sem serializar"*;
- `docs/reports/2026-09-29-r8-cutover-preflight.md:44`: *"Merge-group do SHA: Runtime, Surfaces, Omotenashi, Security, Production Contract e Operator Groups verdes"*;
- `AGENTS.md`: *"push no `main` é o deploy, 6 min"* e `make inflight` como inventário da esteira.

**Conclusão `[INFERÊNCIA]`:** a fila está ligada, exige os mesmos 21 contextos, e é ela — não o `strict: false` — que dá a garantia de "testado na árvore que pousa". Isso é o alicerce da proposta de §5: **a garantia já mora na fila; o run de PR pode ser otimizado para virar feedback.**

### A16 — Custos de US$ e de fila fora do Linux `[FATO]`

`surfaces-gate.yml:218-223`: o job **Marketing — cadeia completa** roda em `macos-15` (runner macOS custa ~10× o minuto do Linux no GitHub) e executa **15 passos**, incluindo `npm run test:visual` (regressão visual por screenshot). Ele fica na matriz de todo PR.

---

## 3. O que já existe e funciona (não reinventar)

1. **Parallelização dos testes do Python já foi feita e está medida.** `runtime-gate.yml:278-285` tirou a suíte de dentro do `quality` e a pôs numa matriz: o gate caiu de **18 min** para o tempo do alvo mais lento. `Makefile:203-248` dividiu o backstage em 2 shards (seed/resto) com união+disjunção por construção e `-n auto` (`Makefile:226-232`, provado por coleta: 16 + 2417 = 2433).
2. **Os jobs independentes já não encadeiam.** `runtime-gate.yml:467-470` e `:498-504` documentam que `docker-image` e `runtime-security-reliability` rodam **sem `needs: quality`**, e que encadear empurrava ~5 min para o fim do caminho crítico.
3. **O agregador com nome estável já existe.** `runtime-gate.yml:341-411`: os shards correm em jobs não obrigatórios e um agregador com o **nome antigo** (`Testes (test-backstage)`) reprova por eles, com `if: always()` e comparação `= "success"` — exatamente para que `skipped` não seja lido como verde.
4. **O escopo por caminho, com agregador, já existe.** `operator-groups-gate.yml`: `scope` (`:23-57`) → jobs pesados condicionais (`:62, 85`) → `contract` (`:161-183`) que sempre reporta.
5. **Cobertura combinada de 4 shards com piso de 75%.** `runtime-gate.yml:413-462`, com asserção dura de que os 4 artefatos chegaram (`:448-449`).
6. **Deploy seletivo por path, medido contra o último deploy bem-sucedido**, com tabela única de caminhos compartilhada com o confronto do registry (`scripts/deploy_components.py:80-174, 248-266`), manifesto com digest obrigatório (`deploy-images.yml:252-313`) e job de drift (`:315-381`).
7. **Cache GHA no build de imagem de deploy**, com `max-parallelism = 2` por OOM de 7 GB (`deploy-images.yml:177-186, 217-218`).
8. **`cache: pip` / `cache: npm` já estão ligados** com `cache-dependency-path` explícito nos locks (`surfaces-gate.yml:100-102`, `omotenashi-gate.yml:75-81`).
9. **Smoke pós-deploy que pergunta ao vivo** em vez de dormir, com teto validado por gate aritmético (`alpha-smoke.yml:170-199`, `scripts/check_workflow_budgets.py`).
10. **Cultura de medir com evidência datada** — quase todo número deste relatório saiu de comentário de código com medição registrada.
11. **Exclusões de path que não geram imagem** (teste/README/doc) para não publicar imagem idêntica (`deploy_components.py:106-129`).

---

## 4. Lacunas / riscos

1. **`[FALTA] Frente de CI.** Não há plano, WP ou runbook sobre tempo de pipeline: `grep` por *moroso|lentidão|CI lenta|acelerar|gargalo* em `docs/plans`, `docs/reports`, `docs/runbooks` devolve só desempenho de runtime (`WP-PERFORMANCE-2026-09`) e UX. O `WP-DELIVERY-SECURITY-AND-CI-CLOSURE-2026-09-28.md` só **adiciona** gates (`:51`: "Não reduzir nem pular gate existente").
2. **A lista de checks obrigatórios não é versionada.** Só o runbook de 05/09 a menciona. Sem ela, qualquer renomeação de job vira trava permanente — o repositório já documenta esse modo de falha três vezes (`runtime-gate.yml:214-216, 341-347`; `docs/runbooks/branch-protection-pendencias.md:48-50`).
3. **Cache acima do teto** (12,28 GB > 10 GB): o GitHub despeja por LRU, então os caches que existem são **frios justamente quando mais importam** (rajada de PRs). É a explicação mais provável para o `install ~3 min` conviver com `cache: pip` ligado. `[INFERÊNCIA]`.
4. **Custo de CI não tem dono nem orçamento visível.** `grep` por minutos/runner nos docs: nenhum. `WP-DO-ECONOMIA-2026-09.md:359` cita o billing do Actions apenas como "não consultado".
5. **`OPERATOR_PER_APP_IMAGES` vence em 01/10** (`deploy-images.yml:62`): data a 2 dias do baseline desta análise. Se ninguém desligar, o desperdício vira permanente por inércia (é o padrão de falha que o próprio arquivo descreve).
6. **Risco de degradar garantia ao "otimizar".** Qualquer proposta de escopo por caminho precisa do agregador de nome estável; a alternativa (deixar job sumir) já custou caro aqui duas vezes (check ausente trava a fila; `skipped` lido como verde — `runtime-gate.yml:348-350, 405-411`).
7. **`[NÃO VERIFICADO]`** durações reais atuais de cada workflow (sem token do `gh`); `[NÃO VERIFICADO]` se `Admin CSP (production settings)` já virou obrigatório depois de 05/09; `[NÃO VERIFICADO]` se a matriz de 10 apps do Surfaces Gate tem algum app que ainda não existe em produção (`registry.json` foi lido apenas parcialmente).

---

## 5. Fluxo atual, passo a passo (com cada espera)

### 5.1 Diagrama textual

```
 ┌─ COMMIT / PUSH DA BRANCH ─────────────────────────────────────────────────────────┐
 │  ~5 s                                                                             │
 └───────────────────────────────────────────────────────────────────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │  ABERTURA/RE-ENTRADA DE PR              │  `pull_request`
              │  fan-out de 47 execuções de job         │
              │  (Runtime 13 · Surfaces 22 · Omotenashi │
              │   3 · ProdContract 1 · OperatorGroups 5 │
              │   · Security 3)                         │
              └────────────────────┬────────────────────┘
                                   │
   ┌── Runtime Gate ───────────────┴──────────────────────────────────────────────┐
   │ quality(1)  admin-gate(1)  tests(4 shards)  backstage-shards(2)              │
   │ docker-image(1)  runtime-PG/Redis(1)  silent-swallow(1)  → coverage-gate     │
   │ Cada job paga make install (~3 min). Caminho crítico ≈ 10-13 min.  ⏱        │
   └──────────────────────────────────────────────────────────────────────────────┘
   ┌── Surfaces Gate ─────────────── 22 jobs ─────────────────────────────────────┐
   │ app-quality ×10: (kit npm ci + app npm ci) → vitest → lint → typecheck       │
   │ pwa-quality ×9: kit npm ci + app npm ci → Nuxt build → PWA gate              │
   │                 → (storefront: playwright) → docker build ×8 (FRIO, sem cache)│
   │ marketing-complete: macOS-15, 15 passos incl. regressão visual               │
   │ production-browser: playwright chromium+webkit                              │
   │ 39 npm ci · 10 Nuxt builds · 8 docker builds. Caminho crítico ≈ 15-25 min ⏱ │
   └──────────────────────────────────────────────────────────────────────────────┘
   ┌── Omotenashi Gate ── 3 jobs ─────────────────────────────────────────────────┐
   │ browser-QA: install 3 min + 6 npm ci + 5 Nuxt builds + seed --flush          │
   │             + matriz Omotenashi em Chrome headless --strict                  │
   │ admin-csp: install + migrate + seed + collectstatic + Playwright (não bloqueia)│
   │ storefront-e2e: install + npm ci + Nuxt build + seed + Playwright            │
   │ Caminho crítico ≈ 12-20 min ⏱                                                │
   └──────────────────────────────────────────────────────────────────────────────┘
   ┌── Production Contract (1 job, install + contrato + test-migrations) ≈ 5-8 min ┐
   ┌── Security Gate (CodeQL py + js/ts) ≈ 8-15 min ⏱ ← costuma ser o 2º mais lento┐
   ┌── Operator Groups Gate (normalmente "not applicable"; ~+10-20 min se aplicável)┐

              ESPERA TOTAL NO PR ≈ tempo do workflow mais lento  ⏱ ~15-25 min
                                   │
              ┌────────────────────┴────────────────────┐
              │  gh pr merge → MERGE QUEUE              │  `merge_group`
              │  A MESMA ÁRVORE PASSA DE NOVO POR TUDO: │
              │  +47 execuções, +13 make install,       │
              │  +46 npm ci, +9 docker builds           │
              │  ⏱ +15-25 min  ← o maior desperdício    │
              │  (é aqui que mora a garantia real)      │
              └────────────────────┬────────────────────┘
                                   │
                    PR ENTRA NO main (squash)
                                   │
   ┌── deploy-images.yml ──────────┴──────────────────────────────────────────────┐
   │ concurrency: deploy-images, cancel-in-progress: false → SERIAL               │
   │ • espera pelo run anterior ............................ 0-4,3 min  (medido) │
   │ • changes: checkout fetch-depth 0 + gh api do último      ~20-40 s          │
   │   deploy bem-sucedido + deploy_components.py                                │
   │ • build-push matriz (só os componentes tocados)                              │
   │   run p50 140 s · p90 279 s (14 d, n=233)                                   │
   │   ⚠ OPERATOR_PER_APP_IMAGES=true → publica 8 imagens SEM consumidor          │
   │ • manifest (digest obrigatório) + drift (registry × main)                    │
   └───────────────────────────────┬─────────────────────────────────────────────┘
                                   │  push de tag no DOCR
   ┌── DigitalOcean App Platform ───┴────────────────────────────────────────────┐
   │ deploy_on_push ×8 blocos no spec vivo; tag `web` casa 5 componentes         │
   │ (web + 3 workers + release).                                               │
   │ deployment criado → ACTIVE: p50 181 s · p90 235 s (14 d, n=250)            │
   │ Exemplo real: criado 04:25:44Z → ACTIVE 04:31:54Z (6 min 10 s)             │
   │ 7 dias: 391 deployments · 184 cancelados · 39 em erro (todos no `release`) │
   └───────────────────────────────┬─────────────────────────────────────────────┘
                                   │
   ┌── alpha-smoke.yml (workflow_run) ───────────────────────────────────────────┐
   │ baixa o manifesto, PERGUNTA ao DO se o deployment ficou ACTIVE (teto 900 s) │
   │ + 4 asserções HTTP: /ready/, menu/, checkout 403 canônico, SSR da home      │
   └─────────────────────────────────────────────────────────────────────────────┘

 ⏱ PUSH NO main → VERSÃO NO AR:  p50 329 s (5,5 min) · p90 606 s (10 min)
    (WP-PERFORMANCE-2026-09.md:60 — 14 dias, n=193)
 ⏱ COMMIT → PRODUÇÃO (estimativa somada): p50 ~32-55 min   [INFERÊNCIA]
```

### 5.2 Gargalos, em ordem

| # | Gargalo | Ordem de grandeza | Evidência |
|---|---|---:|---|
| 1 | Segunda passagem inteira pela merge queue | +15-25 min | 47 jobs ×2; `runtime-gate.yml:3-15` |
| 2 | Surfaces Gate sem escopo (22 jobs, 8 docker frios, macOS) | 15-25 min | `surfaces-gate.yml:67-216, 218-223` |
| 3 | Omotenashi + Storefront E2E + Admin CSP (6 builds Nuxt + 4 seeds + browsers) | 12-20 min | `scripts/run_omotenashi_browser_ci.sh:88-168` |
| 4 | Runtime Gate (backstage como caminho crítico) | 10-13 min | `Makefile:206-208` |
| 5 | Deploy: fila serial + build + DO + smoke | 5,5-10 min | `WP-PERFORMANCE-2026-09.md:57-60` |
| 6 | `make install` 26× por merge, 3 min cada | ~78 min-runner | `runtime-gate.yml:240,292` |
| 7 | `npm ci` 92× por merge | ~70-140 min-runner | contagem em A2 |

---

## 6. Desperdícios concretos, com evidência e ganho estimado

Os ganhos estão em **min-runner por evento/merge** quando o trabalho é paralelo (não muda o relógio) e em **min de relógio** quando está no caminho crítico. Marquei cada um.

| # | Desperdício | Evidência | Ganho estimado |
|---|---|---|---|
| D1 | **43 jobs caros sem escopo de caminho** (10 apps Nuxt, browser QA, contratos) rodam em PR que não toca Nuxt | A3 | −10 a −15 min de relógio no PR típico; −200 a −400 min-runner/evento `[INFERÊNCIA]` |
| D2 | **`make install` 13×/evento** (26/merge), 3 min cada, com `pip install --upgrade pip` e 13 `pip install -e` | A2, `Makefile:36,57-69` | −2 a −3 min de relógio (install está dentro dos jobs longos); −60 min-runner/merge |
| D3 | **9 builds Docker frios por PR**, sem buildx e sem cache; `npm ci` + `npm run build` repetidos dentro do build | A4, `surfaces/Dockerfile.surface:23,27-33` | −5 a −15 min de relógio (pwa-quality); −20 a −45 min-runner |
| D4 | **8 imagens por app publicadas sem consumidor** (`OPERATOR_PER_APP_IMAGES=true`, vence 01/10) | A5 | −8 builds por push que toca operator; menos tags/digests/runs |
| D5 | **Cascata de deployments**: 391/7 d, 184 cancelados, 39 em erro; tag `web` move 5 componentes | A6, `WP-PERFORMANCE:61-63` | P5 já proposto: 9-11 deployments → 1; menos `release`/migração por merge |
| D6 | **Cache GHA acima do teto** (12,28 GB > 10 GB) → despejo LRU → caches frios | `WP-PERFORMANCE:64` | higiene; devolve parte dos −3 min do D2 |
| D7 | **331 testes (282 + 49) + 1 migração-de-zero rodando 2× por evento** | A8 | −331 testes duplicados; −1 `migrate` sobre 290 arquivos de migração |
| D8 | **Browsers baixados 5-6× por evento sem `actions/cache`** | A11 | −5 a −15 min-runner/evento; −1 a −3 min no caminho crítico |
| D9 | **CodeQL roda 3× por merge** (PR + fila + `push: main`) | A13 | −1 job duplo por merge (−8 a −15 min-runner) |
| D10 | **`admin-csp` roda em todo PR e não bloqueia** | A14 | custo pago sem proteção; conserto = torná-lo obrigatório (custo zero) |
| D11 | **Assento único da `concurrency` do deploy mata runs com 0 jobs** e a recuperação reconstrói | A12 | −4 min de espera por leva de merges; −reconstruções |
| D12 | **Marketing completo em runner macOS** (10× o minuto) em todo PR, com regressão visual | A16 | custo direto; −5 a −15 min-runner-equivalente |
| D13 | **Serialização: `make test` local encadeia 15 alvos** (só afeta dev) | A10 | −tempo de loop local |
| D14 | **`seed --flush` 4× por evento** | A8 | −3 seeds; o seed é caro por medição (21 testes = 62% do relógio) |

---

## 7. Proposta de pipeline alvo (mais rápido, sem perder garantia)

**Princípio que o próprio repositório já adotou:** a garantia mora na **merge queue** (`branch-protection-pendencias.md:73-82`); o run de PR é **feedback**. A otimização não é "pular", é (a) **não escopar nada fora do diff**, (b) **não rodar a mesma coisa duas vezes no mesmo evento**, (c) **cachear o que é cacheável**, (d) **encurtar o caminho crítico**.

### 7.1 Camada A — no PR, bloqueante, alvo ≤ 6-8 min

Um job `scope` (diff contra a base, como `operator-groups-gate.yml:23-57`) alimenta:

| Check (nome estável) | O que roda | Escopo |
|---|---|---|
| `Quality + deploy contract` | ruff, `makemigrations --check`, drift de docs/ADR-015/legal, budgets, seleção de deploy, silent-swallow, `check --deploy` | **sempre** |
| `Testes` (shards) | cores + shop + storefront + backstage | **sempre** (é o que responde em minutos; já é matriz) |
| `Surfaces Gate` | versões + registro | **sempre** (segundos, leem JSON) |
| `Vitest/typecheck/lint` por app | só os apps **tocados** pelo diff | path |
| `Docker (web)` | build + asserção do agente do balcão | só se `Dockerfile`, `tools/**`, `pyproject.toml`, `constraints.txt` mudaram |
| `Docker (surfaces)` | build da receita de deploy | só se `surfaces/**` ou `Dockerfile.surface` mudaram |
| `Browser QA` (Omotenashi strict) | só se `surfaces/**`, `shopman/storefront/**`, `shopman/shop/**` mudaram | path |
| `Admin CSP` | **promover a obrigatório** (custo zero, recomendação já escrita) | sempre, ou path (`admin_console`, templates) |

**Como não perder garantia:** o check **não desaparece** quando fora de escopo — o job roda e reporta verde com "not applicable" pelo agregador (padrão `operator-groups-gate.yml:161-183`). A garantia é condicional ao diff, que é a única coisa honesta: um gate Nuxt não prova nada sobre um PR que não toca Nuxt.

### 7.2 Camada B — no merge_group, bloqueante, alvo ≤ 12-15 min

**Tudo, uma vez, na árvore exata que pousa** — é aqui que a garantia fica inteira:
- suíte Python completa (cores + shop + storefront + backstage shards) + `runtime-security-reliability` (Postgres+Redis) + coverage ≥ 75%;
- Production Contract + `test-migrations` (rodando **só aqui**, não em `quality`);
- Omotenashi browser strict + Storefront E2E + Admin CSP, sem escopo (o merge group não tem "path irrelevante");
- Surfaces: todos os 10 apps, PWA, build de imagem;
- Operator Groups: como já é hoje.

### 7.3 O que vira **não-bloqueante** (com prazo e forma)

| Item | Destino | Por quê é seguro |
|---|---|---|
| Marketing — cadeia completa (macOS, regressão visual) | **nightly + label `full-ui`** | regressão visual é ruído de rasterização; o runbook de retratos já diz que baseline só regera quem tem o browser da CI |
| Produção — matriz Playwright AA | **nightly + label** | matriz de viewport/AA não guarda dinheiro |
| `orders-isolated-capacity` | já é (`push` de branch morta + dispatch) | — |
| CodeQL no `push: main` | **remover** (fica PR + fila + semanal) | a fila testou a mesma árvore; 3ª passada não prova nada |

### 7.4 O que **paraleliza** / **encurta caminho crítico**

1. **Tirar `make install` do caminho crítico**: um job `prepare` por workflow que instala uma vez e publica o venv (ou um wheelhouse + `pip install --no-index`) como artefato; os shards consomem. Alternativa mais barata: **um wheel por pacote** (`packages/*` são 12 editables: hoje cada `make install` reconstrói os 12) e `pip install --no-deps --no-index`.
2. **Kit Nuxt instalado 18×/evento** → uma vez, com artefato `node_modules` do `operator-kit` (ou `npm ci --prefer-offline` no job + `cache: npm` apontando só para o lock do kit).
3. **`docker`**: `setup-buildx-action` + `cache-from/cache-to: type=gha,scope=<componente>` em **todos** os builds de PR (hoje só o deploy tem), com `mode=min` para não inflar o cache já estourado.
4. **Nuxt build**: os 10 builds de `pwa-quality` + 5 do Omotenashi + 1 do E2E = 16 builds de produção por evento. Escopar por path derruba a maioria; onde sobrar, reaproveitar o `.output` via artefato entre `npm run build` (surfaces) e o `docker build` (que hoje reconstrói).
5. **Deploy**: implementar **P5 do `WP-PERFORMANCE-2026-09.md:283-298`** (um deployment por run, via `doctl apps create-deployment` no job `manifest`, com `deploy_on_push` desligado) — é a proposta que a casa já escreveu e mediu. Desligar `OPERATOR_PER_APP_IMAGES` em 01/10 (`deploy-images.yml:62`) e apagar as 8 tags por app.
6. **Agregar a leva**: com a base já corrigida, um segundo merger em <2 min ainda espera o primeiro. Enquanto P5 não entra, aceitar a espera (é a serialização correta), mas **avisar no PR** em vez de deixar o run em branco.

### 7.5 Ordem sugerida (impacto × esforço)

| Ordem | Ação | Esforço | Ganho |
|---|---|---|---|
| 1 | Promover `admin-csp` a obrigatório (recomendação já escrita) | XS | proteção, custo zero |
| 2 | `cache-from/cache-to` nos 9 builds de PR + podar cache GHA (`mode=min`) | S | −5 a −15 min/PR |
| 3 | Path scoping + agregador nos 4 gates grandes (copiar `operator-groups-gate.yml`) | M | −10 a −15 min/PR |
| 4 | Tirar `test-migrations` e os testes duplicados de `quality`; `make install` por artefato | S | −3 min críticos, −60 min-runner/merge |
| 5 | Browsers em `actions/cache`; remover CodeQL do `push: main` | XS | −5 a −15 min-runner/evento |
| 6 | `OPERATOR_PER_APP_IMAGES=false` + P5 (um deployment por run) | S-M | cascata 9-11 → 1; −erros do `release` |
| 7 | Marketing/Produção browser para nightly + label | S | custo macOS fora do PR |
| 8 | Frente formal de CI com orçamento medido (o que falta: **dono**) | M | evita regressão do ganho |

### 7.6 Metas propostas (comparáveis com o que já está medido)

| Métrica | Hoje | Alvo |
|---|---|---|
| Wall clock do PR (feedback) | ~15-25 min `[INFERÊNCIA]` | ≤ 8 min |
| Wall clock da merge queue (garantia) | ~15-25 min `[INFERÊNCIA]` | ≤ 15 min |
| `make install` por merge | 26 | ≤ 5 |
| `npm ci` por merge | 92 | ≤ 20 |
| Builds Docker frios por PR | 9 | ≤ 2 |
| Deployments por run de deploy | até 11 (`WP-PERFORMANCE:171`) | 1 |
| commit → produção | p50 ~32-55 min `[INFERÊNCIA]` | p50 ≤ 20 min |

---

## 8. Perguntas abertas / o que não consegui verificar

1. **`[NÃO VERIFICADO]` Duração real de cada workflow hoje.** `gh` está com token inválido (`gh auth status`), então não pude rodar `gh run list --json`. **O primeiro passo de quem pegar isto é medir**: `gh run list --workflow runtime-gate.yml --limit 50 --json conclusion,createdAt,updatedAt` (idem para os outros 5), e corrigir as estimativas de §5.
2. **`[NÃO VERIFICADO]` A lista nominal dos 21 checks obrigatórios** e se `admin-csp` já foi promovido. Só o runbook de 05/09 a menciona; **nada disso está versionado**. Recomendo versionar (um `scripts/check_branch_protection.py` que compare o esperado com o `gh api`) — é o único jeito de renomear job sem travar a fila.
3. **`[NÃO VERIFICADO]` Custo em dólar/minuto de runner.** Ninguém mediu (`WP-DO-ECONOMIA-2026-09.md:359`). Sem isso, os ganhos ficam em min-runner, que é o que dá para provar com o repositório.
4. **`[NÃO VERIFICADO]` Se o `cache: pip` está de fato acertando.** Exige ler o run (`Post job cleanup` / "Cache restored from key"). A hipótese D6 (cache acima do teto → LRU) é `[INFERÊNCIA]` forte, não fato.
5. **`[NÃO VERIFICADO]` Quantos dos 10 apps de `app-quality` são tocados por um PR médio.** Exige histórico de runs; daria o número exato do ganho de D1.
6. **Pergunta de decisão:** mover os gates de browser (Omotenashi/E2E/Admin CSP) para **"só no merge group, sempre"**, deixando o PR com um subconjunto rápido, é uma escolha de política — hoje o PR roda tudo. Minha recomendação é **não** mover por evento, e sim **escopar por diff** (mantém a semântica "se você tocou, você roda"), mas a decisão é do dono.
7. **Pergunta de decisão:** desligar `OPERATOR_PER_APP_IMAGES` **antes** de 01/10 (prazo escrito em `deploy-images.yml:62`) e apagar as 8 tags por app — exige confirmar que nenhum spec vivo as referencia (confirmei no spec versionado do alpha; `[NÃO VERIFICADO]` no spec vivo, exige `doctl`).
8. **Não encontrado:** qualquer benchmark, runbook ou plano de tempo de CI. Procurei em `docs/plans`, `docs/reports`, `docs/runbooks`, `docs/guides`, `docs/engineering` por *moroso, lentidão, CI lenta, acelerar, gargalo, relógio, levou, dura*. O único documento com números de deploy é `WP-PERFORMANCE-2026-09.md` (runtime, não CI).
