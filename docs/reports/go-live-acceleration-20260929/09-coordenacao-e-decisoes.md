# 09 — Coordenação entre agentes e decisões perdidas

- **Baseline auditada:** worktree `.dsh-worktrees/go-live-acceleration`, branch `dsh/go-live-acceleration-20260929`, HEAD `f0ffd02fde765493d734bae93a72bb361ed28fcf` (2026-09-29 15:36:00Z).
- **`origin/main` no início da auditoria:** `f0ffd02fd`. **Durante a auditoria avançou para `ccf68564c`** (2026-09-29 16:12:02Z, +14 commits, "Merge pull request #1259 from nelsonboulangerie/codex/go-live-activation-ledger-20260929"). Onde a diferença importa, está dito.
- **Natureza:** análise somente leitura. Nenhum arquivo do repositório foi alterado além deste relatório.
- **Limite de verificação:** `gh` está sem autenticação (`gh pr list` → `HTTP 401: Requires authentication`), então **estado de PR não foi verificado**. Tudo que depende de `gh` está marcado [NÃO VERIFICADO].
- Legenda: **[FATO]** verificado em código/saída de comando · **[INFERÊNCIA]** dedução · **[NÃO VERIFICADO]** não consegui confirmar.

---

## 1. Resumo executivo

A queixa é real e está medida: **o repositório cresceu 22 worktrees e 33 branches locais em um dia**, depois de um WP de higiene (R7) ter declarado o inventário "recapturado". Hoje são **77 worktrees**, **894 branches locais**, **694 remotas**, **115 branches fora de `origin/main` carregando 1.093 commits**, das quais **72 têm patch não equivalente** (trabalho único, não absorvido) e **76 nem existem no remoto**. Seis worktrees estão sujas, incluindo o checkout principal — que está **2.884 commits atrás** de `origin/main` e carrega, não rastreado, arquivo que pertence à árvore de outro branch.

O modelo de coordenação **já foi tentado, e bem desenhado**: um programa R0–R8 com *leases* de arquivo, um hook de `Stop` que impede a sessão de encerrar com trabalho dormente, e `make inflight` que mede o que está em voo. O problema é que **nenhum desses mecanismos é um registro com estado no repositório**: os leases existem como desenho num documento (`GO-LIVE-RECOVERY-EXECUTION-PROGRAM-2026-09-28.md` §6) e **nenhum arquivo de registro de lease foi encontrado**; o que existe é vigilância de saída, não *claim* de entrada.

Do lado das decisões perdidas, encontrei **10 casos concretos e verificáveis** — e o padrão é constante e pior do que "esqueceram": **o registro de decisão não é a verdade**. Um inventário de 18 fallbacks perigosos tem **12 itens marcados ⬜**, dos quais **9 realmente abertos sem dono** e **3 já corrigidos no código** — e **zero linhas** na matriz que se declara "única fonte operacional de estado de go-live"; ou seja, **o inventário erra nas duas direções ao mesmo tempo**; **dois planos que já estão implementados e mergeados continuam marcados "não iniciado"** no índice; **dois ADRs implementados no código continuam "Proposto"**; e existem **dois ADR-026 e dois ADR-029** — a numeração, que o próprio README declara ser "endereço", colidiu. Pior: **acabaram de entrar em `main` dois documentos que cada um se declara o ledger canônico único, sem se citarem, sem nenhum índice apontar para um deles e sem gate de drift sobre ele** — enquanto o próprio ledger novo diz "Não mantenha outro ledger em paralelo".

O caminho de correção não é "escrever mais regra": é **transformar o que já existe em estado verificável por máquina** — registro de claim com área, ledger de decisão com dono e data de revisão, e extensão do gate `make canonical-docs` que já roda no CI para conferir os dois.

---

## 2. Achados

### Parte A — Mapa da concorrência

#### A1. Inventário de worktrees: 77, quatro origens distintas [FATO]

`git worktree list | wc -l` → **77**.

| Origem | Caminho | Quantidade |
|---|---|---:|
| Codex (dentro do repo) | `.codex-worktrees/` | 31 |
| Codex (fora do repo) | `~/.codex/worktrees/` | 30 |
| Claude | `.claude/worktrees/` | 13 |
| DSH | `.dsh-worktrees/` | 1 |
| Canônico | `.canonical-worktrees/django-shopman-main` (`main`, `991f92fe6`) | 1 |
| Checkout principal | `/Dev/Claude/django-shopman` | 1 |

Comando: `git worktree list | awk '{print $1}' | sed -e 's|.*/\.codex/worktrees/.*|codex-home|' … | sort | uniq -c`.

Uma worktree está com **lock ativo**: `.claude/worktrees/agent-a26dbd987c188f75c`, branch `claude/detalhe-do-pedido-lacunas` [FATO — aparece como `locked` na saída de `git worktree list`].

**Comparação com a baseline R7** (`docs/reports/GO-LIVE-R7-REPOSITORY-HYGIENE-EVIDENCE-2026-09-28.md:14-21`): a fase final de R7 registrou **55 worktrees** e **861 branches locais** em 2026-09-29 04:39 UTC. Hoje: **77 worktrees** e **894 branches locais**. **[FATO]** — ou seja, **+22 worktrees e +33 branches locais em ~11 horas**, no mesmo dia em que o WP de higiene foi declarado executado.

#### A2. Branches: 894 locais, 694 remotas [FATO]

- `git branch | wc -l` → **894**; `git branch -r | wc -l` → **694**.
- Por prefixo: `claude/` **486**, `codex/` **243**, `golive-rebase/` 18. As 147 restantes não têm prefixo de fornecedor: **128 são efêmeras de subagente** (`worktree-*`, das quais **124** no formato `worktree-agent-<hash>`), mais nomes soltos (`main`, `dsh`, `fix`, `coord`, `trabalho`, `backup`, `adv`, `verifica-main`, `whatsapp-*`).
- Distribuição por data do último commit: pico de **126 em 2026-09-24**, 34 em 2026-09-29. Branches paradas desde agosto: **13** (2 em 18/08, 1 em 22/08, 2 em 25/08, 3 em 27/08, 4 em 28/08, 1 em 29/08).

#### A3. Trabalho dormente: 115 branches fora do main, 1.093 commits, 72 com patch único [FATO]

Comandos e saída:

```
$ ... if ! git merge-base --is-ancestor "$b" origin/main; then git rev-list --count origin/main.."$b"; fi ...
branches_not_ancestor=115 total_commits_ahead=1093

$ ... if ! git merge-base --is-ancestor "$b" origin/main && não existe refs/remotes/origin/"$b" ...
76

$ ... plus=$(git cherry origin/main "$b" | grep -c '^+'); [ "$plus" -gt 0 ] ...
72
```

- **115** branches locais não são ancestrais de `origin/main` e somam **1.093 commits à frente**.
- **76** delas **não têm contraparte no remoto** — trabalho que só existe nesta máquina.
- **72** têm pelo menos um patch **não equivalente** (`git cherry` com `+`), isto é, trabalho único que squash/rebase não absorveu. Topo: `codex/shopman-legal-google-oauth-20260911` (19), `codex/review-pr614-storefront-reconcile-20260915` (19), `codex/pr614-storefront-integration-20260914` (19), `codex/pr614-pr634-composition-20260914` (19), `codex/pr614-main-pwa-integration-20260914` (19), `codex/mkt-blocker-audit-20260915` (19), `codex/marketing-final-integration-probe-20260914` (19).

**Leitura dos nomes [INFERÊNCIA, apoiada nos nomes e nas datas]:** as sete maiores são todas **sondas de integração/merge da mesma família (`pr614`, `marketing`, `legal-google-oauth`, `golive-merge-probe`, `adv/golive-merge-probe`)** — sete branches para o mesmo tema, cada uma com ~19 patches equivalentes entre si. É retrabalho medido, não impressão: **duas do mesmo dia (14/09) com o mesmo título de trabalho (`pr614-storefront-integration` e `pr614-pr634-composition`)**.

Também há **6 branches `codex/orders-validation-*`** (77, 71, 69, 67, 57, 44 commits) e **3 `golive-rebase/*`** — mesma família, nomes diferentes, nenhuma mergeada.

#### A4. Áreas quentes: as frentes que se cruzam [FATO por nome/data; INFERÊNCIA na leitura]

Branches com data 2026-09-29 (dia da auditoria) e mesmo tema, sem PR verificável: `codex/pos-orders-ux-20260929` + `codex/p1-pos-plan-reconciliation-20260929`; `codex/marketing-provider-catalog-ui-20260929` + `codex/marketing-v2-*` (9 branches de Marketing no total, sete originadas de 2026-09-28); `codex/proddata-foundation-20260929` + `codex/proddata-catalog-day1-audit-20260929` + `codex/proddata-import-provenance-20260929` + `codex/production-data-quality-wp-20260929`.

#### A5. Checkout principal: 2.884 commits atrás, carregando árvore alheia [FATO]

```
$ git -C /Users/pablovalentini/Dev/Claude/django-shopman rev-parse --abbrev-ref HEAD
codex/shopman-backstage-marketing-hardening
$ git -C … rev-parse HEAD   → b589e22c5
$ git -C … rev-list --count b589e22c5..origin/main   → 2884   (atrás)
$ git -C … rev-list --count origin/main..b589e22c5   → 0      (nada à frente: já mergeado)
```

`git status --short` no checkout principal (15 entradas, somente leitura):

```
 M .codex/config.toml
?? .alpha-tmp/  ?? .codex-worktrees/  ?? .dsh-worktrees/  ?? output/  ?? tmp/
?? docs/plans/MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md
?? docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md
?? docs/plans/WHATSAPP-LOGIN-UX-PLAN.md
?? docs/plans/backstage-app-audits-2026-08-29/
?? docs/reports/2026-08-28-prompt-claude-tudo.md  (e mais 3 de 08-28)
?? docs/reports/COORDENACAO-AVANCO-2026-09-13.md
?? docs/reports/COORDENACAO-ENTREGAS-2026-09-13.md
?? docs/reports/DECISAO-DEPLOY-2026-09-13.md
```

Os três `COORDENACAO-*/DECISAO-*` **são rastreados em `origin/main`** (`git ls-files docs/reports/ …` os lista; foram adicionados por `cf8d08b61 docs(reports): relatórios de coordenação e planos que só existiam em worktrees`) e **`cf8d08b61` não é ancestral de `b589e22c5`** [FATO]. Ou seja: os relatórios de coordenação estão fisicamente no checkout principal, mas pertencem à árvore de outro branch. **Este é o "chão compartilhado" descrito no CLAUDE.md acontecendo de novo, agora com documento de coordenação dentro.**

`git status --short` na worktree desta auditoria: **vazio** [FATO].

#### A6. O que já foi tentado (modelo de coordenação existente)

**Relatórios encontrados** (`ls docs/reports | grep -iE 'COORDENACAO|DECISAO|branch-cleanup|housekeeping'`):

| Documento | Linhas | O que registra |
|---|---:|---|
| `docs/reports/COORDENACAO-ENTREGAS-2026-09-13.md` | 127 | Fotografia de 13/09: 13 PRs abertos, 17 branches `codex/go-live-*` sem PR, fila de execução com donos propostos, **tabela "Decisões/permissões de Pablo"** com 5 decisões e a consequência de cada atraso, e a seção C explicitamente "adiada" |
| `docs/reports/COORDENACAO-AVANCO-2026-09-13.md` | 38 | Correções locais, 791 testes no PostgreSQL, 4 patches, "As decisões da seção C permanecem adiadas" |
| `docs/reports/DECISAO-DEPLOY-2026-09-13.md` | 68 | Decisão de publicação: merge centralizado, "Seção C permanece adiada", restrição iFood do dono (14/09) |
| `docs/reports/branch-cleanup-2026-04-28.md` | 52 | Limpeza de branches anterior |
| `docs/reports/housekeeping-2026-08-13.md` | 125 | Higiene anterior |
| `docs/plans/WP-REPOSITORY-WORKTREE-BRANCH-HYGIENE-2026-09-28.md` | 402 | WP R7 completo: 8 classes de worktree, invariantes, 12 proibições, gates H0–H4 |
| `docs/reports/GO-LIVE-R7-REPOSITORY-HYGIENE-EVIDENCE-2026-09-28.md` | 143 | Evidência de execução do R7: 60→56 worktrees, 861 branches, quarentena de 7 dias, matriz CSV |
| `docs/plans/GO-LIVE-RECOVERY-EXECUTION-PROGRAM-2026-09-28.md` | 412 | **O modelo mais completo:** 9 WPs (R0–R8), DAG de dependências, 8 ondas com gates W0–W7, **§6 "Leases de arquivos e superfícies"** com 13 leases nomeados, máquina de estados `REQUESTED/ACTIVE/HANDOFF/RELEASED/BLOCKED`, política de "um integrador por conflito" e 9 gates humanos H0–H8 |

#### A7. Existe mecanismo de claim/lock? **Não encontrado.** [FATO]

Procurei em `docs/`, `.claude/`, `.codex/`, `scripts/`, `Makefile`, `.github/`. O que existe:

| Mecanismo | Onde | O que faz | É claim? |
|---|---|---|---|
| `make inflight` | `Makefile:480`, `scripts/inflight.sh` (10.644 B) | **Inventário de saída**: worktrees sujas, branches sem PR, PRs verdes fora da fila. Cabeçalho do script: *"150 worktrees… medido em 16/09/2026"* | ❌ somente leitura |
| `make audit-branches` | `Makefile:477`, `scripts/audit-branches.sh` (7.949 B) | Branches remotas à frente do main | ❌ somente leitura |
| Hook de `Stop` | `scripts/esteira-stop-hook.sh` (6.323 B), registrado em `~/.claude/settings.json:137-144` | Bloqueia encerrar a sessão com arquivo não commitado, commit não empurrado, branch sem PR ou PR verde fora da fila. Bloqueia **uma vez por turno** | ❌ trava de **saída**, não reserva de **entrada** |
| `guard-paralelo.sh` | `~/.claude/hooks/guard-paralelo.sh` (7.542 B, 19/08); referenciado por `~/.claude/settings.json:130` | Bloqueia `checkout`/`reset --hard`/`rebase`/`merge`/`stash` no principal | ❌ é trava de comando, não claim |
| Leases do programa | `GO-LIVE-RECOVERY-EXECUTION-PROGRAM-2026-09-28.md` §6.1–6.3 | Formato `lease_id | paths | owner | branch | PR | adquirido_em | revisar_em | estado | evidência` | ❌ **desenho, sem registro** |
| Registro de lease em arquivo | — | `grep -rn 'lease_id' docs/ plans` → **1 ocorrência, a linha de template do próprio documento**. `grep -rl 'L-ENCOMENDAS\|L-MARKETING\|L-STOREFRONT' docs/` → **só o documento do programa** | ❌ **não existe** |
| `.claude/settings.json` | 47 linhas | Lista de permissões de comando | ❌ |
| `.codex/config.toml` | `approval_policy = "never"`, `sandbox_mode = "workspace-write"` | Política de aprovação do Codex. **O `git status` do checkout principal mostra ` M .codex/config.toml` — alterado e não commitado por outra sessão** | ❌ |

**Conclusão [FATO]:** não existe nenhum mecanismo de *claim* — nenhum arquivo, nenhum comando, nenhum hook que registre "esta área é minha até tal data". O *lease* foi projetado em 28/09 e **não foi materializado em nenhum arquivo**. Todo o aparato atual observa o repositório **depois** do fato.

---

### Parte B — Decisões perdidas (10 casos concretos)

#### B1. 12 fallbacks marcados ⬜ no inventário: 9 abertos sem dono, 3 já corrigidos — e zero linhas na matriz canônica [FATO]

**O que foi decidido:** `docs/plans/fallbacks-perigosos-go-live.md` inventaria 18 casos de degradação silenciosa para o permissivo em caminho de dinheiro, acesso ou fiscal, cada um com correção proposta. Legenda do próprio documento: *"⬜ aberto, vira frente própria"*.

**Evidência:** `grep -c '⬜' docs/plans/fallbacks-perigosos-go-live.md` → **14 marcas**, sendo **12 itens marcados ⬜** (1, 2, 4, 9, 10, 11, 12, 13, 14, 15, 16, 17) e 1 meio-fechado (18). Verifiquei o código em `origin/main` item por item — e **3 dos 12 já estão corrigidos**, o que é o achado mais forte desta seção: o inventário não é confiável nem para dizer o que falta.

| Item | Alegação | Estado no código hoje | Prova |
|---|---|---|---|
| 1 | `EFI_SANDBOX` nasce `true` | **ABERTO** | `config/settings.py:1904` — `os.environ.get("EFI_SANDBOX", "true")`; `shopman/shop/adapters/payment_efi.py:49` — `SANDBOX_URL if config.get("sandbox", True)` |
| 2 | `FOCUS_NFE_ENVIRONMENT` nasce `homologacao` | **ABERTO** | `config/settings.py:1795` — `os.environ.get("FOCUS_NFE_ENVIRONMENT", "homologacao").strip().lower() or "homologacao"` |
| 4 | adapter de e-mail devolve sucesso com backend de console | **CORRIGIDO — e o doc continua ⬜** | `shopman/shop/adapters/notification_email.py:178-184` — docstring: *"Isto já foi `bool(EMAIL_HOST or EMAIL_BACKEND)`, e era um fail-open caro"* |
| 9 | `allow_untracked` nasce `True` | **ABERTO** | `shopman/shop/config.py:190` — `allow_untracked: bool = True` |
| 10 | `preorder` nasce `True` | **ABERTO** | `shopman/shop/config.py:183` — `preorder: bool = True` |
| 11 | `_sku_known_to_catalog` degrada para `True` | **CORRIGIDO — e o doc continua ⬜** | `shopman/shop/services/stock.py:697-724` — o `except` agora faz `logger.warning(...)` e `return False` (fail-closed). O comentário no código registra a correção: *"Isto devolvia `True`… quem estava errado era o código"* |
| 12 | `_from_shop_integrations` engole erro de banco | **ABERTO** | `shopman/shop/adapters/__init__.py:93-95` — `except Exception: logger.debug("_from_shop_integrations: DB lookup failed…")` + `return None, False` |
| 13 | middleware 2FA deixa passar em `NoReverseMatch` | **CORRIGIDO — e o doc continua ⬜** | `shopman/backstage/middleware_2fa.py:29-30` e `:34-35` — agora devolve `HttpResponse(..., status=503)` |
| 14 | `notifications.get_backend(None)` resolve para console | **ABERTO** | `shopman/shop/notifications.py:36-37` — `if name is None: name = "console"` |
| 15 | `_external.inert()` devolve sucesso após `suppress()` | **ABERTO** | `shopman/shop/adapters/_external.py:42-43` — `if _suppressed_reason is not None: return True` |
| 16 | resolver fiscal degrada para "só se o operador pedir" | **ABERTO** | `shopman/shop/services/fiscal.py:98-101` — `except Exception: … return _default_emission_decision(order)` |
| 17 | `_payment_idempotency_key_reusable` devolve `True` na falha | **ABERTO** | `shopman/shop/services/payment.py:2073-2076` — `except Exception: logger.debug(...); return True` |

**Impacto:** os itens 1 e 2 são **perda de dinheiro e venda não declarada** — Pix cobrando num gateway que não recebe, e NFC-e emitida em homologação que **não existe no SEFAZ** (`docs/runbooks/ativar-sentry.md:113-114`: *"as NFC-e emitidas no alpha até hoje não existem no SEFAZ"*). Os itens 9 e 10 (defaults de `ChannelConfig`) são venda de estoque que não existe; o 11 era o mesmo risco e **já foi fechado**.

**Saldo do inventário [FATO]:** 9 itens realmente abertos (1, 2, 9, 10, 12, 14, 15, 16, 17) + 1 meio-fechado (18) + **3 itens com marca ⬜ desatualizada** (4, 11, 13).

**O que faz isto ser "decisão perdida" e não "trabalho em aberto":**
1. O documento **não tem dono, prazo nem rastreio de estado** — só o glifo ⬜.
2. **A matriz que se declara a fonte única não contém nenhum desses itens.** `grep -niE 'fallback|allow_untracked|inert\(|_external|preorder' docs/plans/GO-LIVE-READINESS-PLAN.md docs/runbooks/go-live-preflight.md docs/runbooks/go-live-cutover.md` → **2 ocorrências, ambas irrelevantes** (uma fala de "procedimento de fallback" de impressão, outra de "fallback e kill switch" genérico). O cabeçalho de `GO-LIVE-READINESS-PLAN.md:3-5` diz: *"**Única fonte operacional de estado de go-live.** Documentos de arquitetura, roadmap, credenciais e runbooks apontam para esta matriz; não mantêm cópias do status."* — e a matriz ignora 9 decisões de risco em aberto e 3 já resolvidas que continuam listadas como abertas.
3. O documento **não é tocado desde 2026-09-11** (`git log -1 --format='%ad' -- docs/plans/fallbacks-perigosos-go-live.md` → `2026-09-11`), 18 dias antes da auditoria — e as três correções que aconteceram depois (4, 11, 13) foram feitas **sem atualizar o inventário**.
4. **Nada verifica os glifos.** `docs/reference/silencio-inventario.md` (24.799 B) é a doutrina, `make test-silent-swallow` (`scripts/check_silent_swallow.py`, 20.343 B) é o gate — e nenhum dos dois lê o inventário.
5. E o doc **mente em duas direções**: itens 4, 11 e 13 já estão corrigidos no código e continuam ⬜.

**Confiança:** alta. Código e doc lidos linha a linha.

#### B2. Dois ledgers canônicos concorrentes, sem referência cruzada e sem índice [FATO]

**O que foi decidido:** `docs/runbooks/GO-LIVE-ACTIVATION-LEDGER-2026-09-29.md` (230 linhas) se autodeclara: *"Este e o registro canonico da passagem de cada WP e PR ate a operacao no ambiente Live. … **Nao mantenha outro ledger em paralelo.**"* Ele tem regra de conclusão (`DONE` só após merge + deploy + migration + flag + smoke + rollback), formato por PR (Owner, Merge, Deploy, Migration, Env/config/flag, Valor desejado, Dependência/gate, Smoke Live, Rollback, Evidência, Última atualização, Estado/DONE).

**Evidência do conflito:**
- No baseline desta auditoria (`f0ffd02fd`), **o ledger não existia em `main`**: `git show origin/main:docs/runbooks/GO-LIVE-ACTIVATION-LEDGER-2026-09-29.md` → **exit 128**. Ele vivia só em `codex/go-live-activation-ledger-20260929`, **8 commits à frente**.
- Ele entrou em `main` **36 minutos depois** do baseline: `ccf68564c` em 2026-09-29 16:12:02Z (`Merge pull request #1259 from nelsonboulangerie/codex/go-live-activation-ledger-20260929`).
- **Os dois se declaram fonte única e nenhum cita o outro.** `grep -niE 'readiness|GO-LIVE-READINESS' ` no ledger → só o título de seção "Production Operational Data Readiness". `grep -niE 'ledger|activation'` em `GO-LIVE-READINESS-PLAN.md` (em `ccf68564c`) → **zero**.
- **Nenhum índice aponta para o ledger**: `docs/runbooks/README.md`, `docs/plans/README.md` e `docs/README.md` em `ccf68564c` → **zero menções** a "ledger"/"activation".
- **O gate de documentação canônica não o conhece**: `scripts/check_canonical_docs.py:22-34` lista 11 `CANONICAL_DOCS`; o ledger **não está entre eles**. O gate roda no `runtime-gate.yml:93` a cada PR.

**Impacto:** duas listas de "o que está de fato no ar", com **estados diferentes para o mesmo PR** — a matriz diz `VERIFICADO` por cadeia de deploy/smoke; o ledger diz `IN_PROGRESS`/`DONE` por WP. Quem lê uma não sabe que a outra existe; o próprio ledger pede `DONE` com 6 etapas comprovadas enquanto a matriz exige `VERIFICADO` em 22 critérios distintos. É a queixa literal: **a decisão sobre "qual é o registro" ficou perdida no meio**.

**Confiança:** alta (comandos `git show` em dois commits + greps).

#### B3. `docs/plans/README.md` diz "não iniciado" para trabalho mergeado — WP-LOCK-01 [FATO]

**O que foi decidido:** o dono aprovou o WP-LOCK-01 em **17/09/2026** (`docs/plans/WP-LOCK-01-estacao-travada-nao-e-sessao-encerrada.md:5`: *"Aprovado pelo dono como WP próprio (17/09/2026), não iniciado"*), para separar "estação travada" de "sessão viva".

**O que o índice diz hoje:** `docs/plans/README.md:31` — *"Aprovado pelo dono como WP próprio (17/09), **não iniciado**. Travar o PDV é `logout()` e a sessão é uma para toda a zona… a causa segue."*

**Evidência de que a causa NÃO segue:**
- `shopman/backstage/api/operations.py:928-940`: `class OperatorLockView` — docstring *"Trava só a superfície pedida; a sessão compartilhada continua viva."*; chama `operator_session.lock_capability(request, perm)`. **Não há `logout(request)` nenhum no arquivo** (`grep -rn 'logout(request)' shopman/backstage/api/operations.py` → vazio).
- Implementado em `366c13b00 fix(backstage): scope station lock to operator capability`, **2026-09-29** — o mesmo dia da auditoria.

**Impacto:** dois agentes lendo o índice concluem que a frente está aberta. O WP é marcado "Severidade 🟠 Média hoje → 🔴 Alta" e "Dependências: nenhuma" — é exatamente o tipo de item que uma segunda sessão **reimplementa**. A implementação tem **12 dias de vida contra 0 dias de atualização do índice**.

#### B4. Mesmo defeito, segunda vítima — AVAILABILITY-ADMIN-PLAN [FATO]

**O que o índice diz:** `docs/plans/README.md:70` — *"UI de calendário de funcionamento no Admin (WP-AV-1/2/3) — **não iniciado**."*

**Evidência de que foi feito:**
- O **próprio arquivo do plano** foi atualizado e diz `docs/plans/AVAILABILITY-ADMIN-PLAN.md:7`: **"## Estado atual (2026-09-29)"**, descrevendo a página `ShopOperationAdmin` com "ações de diálogo oficiais", tabela de fechamentos, painel de feriados, ranges de férias e horário especial.
- `git merge-base --is-ancestor origin/codex/availability-admin-20260929 origin/main` → **MERGED**; `git log origin/main..` → **0 commits**. `git log origin/main` mostra `c6f8ee126 Merge pull request #1253 from nelsonboulangerie/codex/availability-admin-20260929`.
- Código: `shopman/shop/admin/shop.py` — `opening_hours_*` (`:243-244`, `:1020-1048`), `shop.opening_hours` (`:208`).

**Impacto:** o plano e o índice discordam **sobre o mesmo assunto, no mesmo dia**, dentro do diretório que o gate `CANONICAL_DOCS` cobre. É a prova de que o problema não é "documentação velha" — é **duas fontes de estado sem dono e sem gate**.

#### B5. ADRs implementados no código, marcados "Proposto" desde 08/08 [FATO]

| ADR | Status no arquivo | Estado real do código |
|---|---|---|
| `adr-018-surface-is-channel-with-commerce-policy.md:3` | **`Proposto`**, 2026-08-08 (492 linhas) | **IMPLEMENTADO**: `shopman/shop/models/channel.py:27-37` — `class CommercePolicy(TextChoices)` com `DISPLAY = "display"`, cuja docstring cita *"(ADR-018 §3)"*. O model `Showcase` **não existe mais** (`grep -rn 'class Showcase' packages/ shopman/` → vazio; removido em `ca96c0546 feat(F4): o preço da vitrine vem do canal que ela aponta — Showcase morre`) |
| `adr-019-promotion-belongs-to-the-orchestrator.md:3` | **`Proposto`**, 2026-08-08 (371 linhas) | **IMPLEMENTADO**: a ADR existe para mover `Promotion`/`Coupon` de `storefront` para o orquestrador. Hoje: `shopman/shop/models/promotion.py:23` (`class Promotion`), `:144` (`class Coupon`), `shopman/shop/admin/promotion.py`. `shopman/storefront/models/` só tem `continuum.py, favorites.py, intents.py, stock_alerts.py` — **nada de promotions** |

**Impacto:** a ADR-018 é **citada como lei no próprio código** enquanto o cabeçalho dela diz "Proposto". Um leitor que siga o índice de ADRs conclui que a unificação de superfície/canal **não foi decidida** — e o CLAUDE.md do repo hoje depende dela. **Nada verifica status de ADR:** `grep -rn 'docs/decisions' scripts/*.py scripts/*.sh Makefile` → **1 único hit**, `scripts/check_adr015.py`, que só confere a policy da tag pós-go-live.

#### B6. Colisão de numeração de ADR: dois ADR-026 e dois ADR-029 [FATO]

`ls docs/decisions/ | grep -oE 'adr-[0-9]+' | sort | uniq -d` → `adr-026`, `adr-029`.

| Número | Arquivo A | Arquivo B |
|---|---|---|
| 026 | `adr-026-operator-surface-security-envelope.md` — **Aceito · 2026-09-09** | `adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md` — **Proposto (2026-09-03)** |
| 029 | `adr-029-marketing-fire-logical-rate-limit.md` — Aceito em 2026-09-11 | `adr-029-persistent-stock-alert-occurrences.md` — aceito, 2026-09-11 |

`docs/decisions/README.md` lista **os dois** sob `026` (linhas 47 e 67). O cabeçalho do próprio README (linhas 8-11) diz: *"**Numeração é endereço, não ordem de importância.** Nunca renumere: o número é citado em código, em outros ADRs, em PR e em memória de sessão."*

**A ambiguidade é real em uso.** Referências por número nu, sem link:

- `docs/plans/BI-JEV-PILOT.md:91` — "(ADR-026) mudam as regras" (concierge)
- `docs/plans/WP-DO-ECONOMIA-2026-09.md:273` — "**Envelope de segurança (ADR-026)**" (o outro)
- `docs/plans/WP-TELAS-DE-PAREDE.md:261, 287, 438, 460` — "ADR-026" pelo envelope (o outro)
- `docs/plans/NOTIFICATION-ROBUSTNESS-PLAN.md:3` — "a ADR-029 substitui…"
- `docs/plans/STOREFRONT-GAPS-ACTION-PLAN.md:93` — "Superado pela ADR-029 em 2026-09-11"
- `docs/plans/FOMO-MARKETING-SPECS.md:3` — "a ADR-029 substitui referências"

**Impacto:** o endereço da decisão está duplicado. Quem resolve "ADR-026" pelo número tem **50% de chance de cair na decisão errada** — e as duas são de assuntos que não se tocam (CSP de superfície vs. doutrina de concierge). Um dos dois pares foi criado no mesmo dia (029), o que sugere inserção concorrente. **Nenhum gate confere unicidade de número de ADR.**

#### B7. Uma decisão do dono enterrada num runbook de Sentry, sem dono, há 18 dias [FATO]

`docs/runbooks/ativar-sentry.md:104` — *"## ⚠️ A bomba do `FOCUS_NFE_ENVIRONMENT` — decisão pendente do dono"*, seguido de *"Fora do escopo do Sentry, mas encontrado na mesma auditoria e **sem lugar melhor para morar até você decidir**"* (`:106-107`).

O texto é explícito sobre o dano: *"Isso significa que **as NFC-e emitidas no alpha até hoje não existem no SEFAZ**. São válidas como exercício e inválidas como documento fiscal."* (`:113-114`), e *"Trocar para `producao` é decisão sua, e é de mão única"* (`:118`).

**Evidência de que a decisão não foi tomada:** o default continua `homologacao` (`config/settings.py:1795`) e o documento existe **para não se perder** — o autor escreveu isso literalmente. O item também é o nº 2 do inventário de fallbacks (B1), que também não tem dono. **A decisão está em três lugares (runbook de Sentry, inventário de fallbacks, matriz de credenciais) e em nenhum lugar com dono e data de revisão.**

#### B8. Três decisões do dono medidas em 05/09, paradas em documento sem dono [FATO parcial]

`docs/runbooks/branch-protection-pendencias.md` — *"Branch protection do `main` — três decisões pendentes do dono"*, *"Estado medido em **05/09/2026** via `gh api …/protection`"*. As três: tornar obrigatório o check `Admin CSP (production settings)` (o único gate que roda e não bloqueia), `required_status_checks.strict`, e um terceiro item. O documento é explícito: *"Branch protection só muda pela mão dele, no GitHub — nenhum agente altera isto"*.

As três seções do documento são: **1.** `admin-csp` roda e não bloqueia (`:28`); **2.** `strict: false` — e 40+ worktrees em paralelo (`:54`); **3.** o gate da meia-correção, quando vira obrigatório (`:90`). A seção 2 é, ela mesma, uma decisão de coordenação não tomada — o `strict: false` é o que permite merge sobre base desatualizada com 40+ worktrees vivas.

**Idade:** 24 dias no baseline, sem campo de dono, sem `revisar_em`, sem nenhuma outra referência no repositório que eu tenha encontrado. **[NÃO VERIFICADO]:** não consegui confirmar se os três itens continuam abertos — `gh` está sem autenticação (`HTTP 401`), e a proteção de branch não é observável pelo clone. O que é [FATO] é que **o documento não tem mecanismo para dizer se envelheceu**, e que o item 1 (`admin-csp` fora dos obrigatórios) é verificável por qualquer um que leia `.github/workflows/omotenashi-gate.yml` — e a matriz de prontidão **não o menciona**.

#### B9. ADR-020: "rollout pendente" desde 10/09, sem critério de saída [FATO quanto ao registro]

`docs/decisions/adr-020-campaign-announces-it-does-not-sell.md:3` — *"**Status:** Aceito; implementação técnica local concluída em 2026-09-10, **rollout pendente**"*. 19 dias no baseline. `grep -rn 'ADR-020' docs/` mostra que o ADR é citado como lei em `CORE-BOUNDARIES-AUDIT.md` e em 5 pontos de `FOMO-MARKETING-SPECS.md`, **nenhum dos quais registra o estado do rollout**.

**Impacto:** "rollout pendente" não diz **o que falta** nem **quem decide**. Não há nenhuma linha sobre o rollout de ADR-020 em `GO-LIVE-READINESS-PLAN.md` nem no ledger de ativação. **[NÃO VERIFICADO]:** não medi o estado real do Marketing em ambiente vivo (exigiria acesso ao app e banco).

#### B10. Planos duplicados: dois documentos para o mesmo assunto, mantidos à mão [FATO]

`docs/plans/WP-PWA-EXECUCAO.md` (207 linhas) e `docs/plans/WP-PWA-CONFORMIDADE.md` (208 linhas) são **o mesmo assunto — conformidade PWA das superfícies, F0→F3**. Ambos abrem com o mesmo bloco de status:

```
$ diff <(sed -n '3,11p' docs/plans/WP-PWA-EXECUCAO.md) <(sed -n '3,11p' docs/plans/WP-PWA-CONFORMIDADE.md)
7,8c7,8
< > prova pendente não desfaz a publicação. F1–F3 continuam futuras e precisam de
< > autorização e brief atualizados contra `main`.
---
> > prova pendente não desfaz a publicação. F1–F3 continuam futuras e exigem brief
> > atualizado a partir de `main` antes de qualquer execução.
```

**Sete das nove linhas são idênticas; as duas divergentes dizem a mesma coisa com outras palavras.** Ambos começam com *"Estado atual (2026-09-15): **registro histórico; não executar como brief**"*. Nenhum documento fora deles os referencia (`grep -rn 'WP-PWA-EXECUCAO\|WP-PWA-CONFORMIDADE' docs/plans/*.md docs/runbooks/*.md` → só as duas linhas do `plans/README.md`).

**Impacto:** qualquer mudança de estado do PWA tem **dois lugares** para atualizar e nenhum é canônico. As duas linhas do índice (`README.md:45` e `:46`) também descrevem o mesmo estado em palavras diferentes.

**Contraexemplo verificado, que mostra que a casa sabe resolver isto [FATO]:** `docs/plans/MANYCHAT-CONVERSACIONAL-PLAN.md` foi **formalmente superado** por `WHATSAPP-CONCIERGE-PLAN.md`, e `docs/plans/README.md:67` registra isso com nome e motivo (*"**Superado** pelo WHATSAPP-CONCIERGE-PLAN (mesmas invariantes, mecanismo diferente); fica como registro"*). É o padrão certo — declarar a supersessão no índice. O par PWA é a mesma situação **sem** o registro.

**Fragmentação medida [FATO]:** o tema B.I. tem **7 planos** em `docs/plans/` (`BI-PLAN` 311, `BI-DATA-FOUNDATION-PLAN` 657, `BI-FORECAST-PLAN` 627, `BI-INSIGHTS-MAP` 1.116, `BI-JEV-PILOT` 91, `BI-QUESTION-CATALOG` 910, `BI-CONSUMPTION-PROFILES` 280 — **3.992 linhas**) que se citam como "irmãos" e mantêm cada um o seu bloco de status. E há **três planos "IRREPRESSIBLE-EXCELLENCE"** (Marketing, Production, PDV, ~2026-09-08), dois deles **não rastreados no checkout principal** (`?? docs/plans/MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`, `?? docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`).

---

## 3. O que já existe e funciona (não reinventar)

**[FATO] já está no `main` e operante:**

1. **`make inflight`** (`Makefile:480`) — mede `🔴 SUJA`, `🔴 SEM PR`, `🔴 NÃO EMPURRADA`, `🟢 VERDE FORA DA FILA`, `🚦 NA FILA`, `🔴 VERMELHO`, `⚠️ CONFLITO`, `📝 DRAFT`, `✓ ENTREGUE`, com `NOISE` para separar artefato de dev. É o inventário de saída pronto; **falta só o de entrada**.
2. **`scripts/esteira-stop-hook.sh`** — a trava de turno, já registrada em `~/.claude/settings.json:137-144`. O desenho "bloqueia uma vez por turno" é correto e testado em produção desde 16/09.
3. **`scripts/check_canonical_docs.py`** — gate hermético, stdlib-only, roda no `runtime-gate.yml:93`. Já tem **exatamente** o formato que falta para o ledger: lista `CANONICAL_DOCS` (11 arquivos, incluindo `docs/plans/README.md`), `EXPECTED_TARGETS`, `EXPECTED_RUNBOOKS`, `FORBIDDEN_TEXT` (regex) e `SECRET_PATTERNS`. **É o lugar natural para nascer a validação do ledger e do claim.**
4. **`GO-LIVE-RECOVERY-EXECUTION-PROGRAM-2026-09-28.md` §6** — o desenho de *lease* já está escrito, com taxa de campos, 13 leases nomeados, 5 estados e 6 condições de handoff. **Falta só materializar em arquivo** — o desenho não precisa ser reinventado.
5. **`WP-REPOSITORY-WORKTREE-BRANCH-HYGIENE-2026-09-28.md`** — 8 classes de worktree (A–H), gate de arquivamento individual, 12 proibições, 12 evidências obrigatórias. É a doutrina de limpeza; o problema não é ela, é o volume reposto.
6. **`docs/plans/README.md`** — já é, de fato, o índice de estado dos planos (três seções: gate de go-live, ativos, backlog). É a **estrutura** de ledger que falta ser transformada em registro verificável.
7. **`GO-LIVE-READINESS-PLAN.md`** — a matriz canônica **funciona**: 22 critérios com `Estado/Ambiente/Fonte/Owner/Próximo evento`, carimbada em `2026-09-29T04:45:00Z`, com vocabulário fechado (`VERIFICADO/PENDENTE/BLOQUEADO/DESCONHECIDO/N/A`) e regra explícita de promoção (`:77-85`). **O erro não é o formato dela — é o escopo: ela cobre 22 critérios e ignora os 9 fallbacks em aberto, os 3 já corrigidos e o ledger novo.**
8. **`AGENTS.md` é symlink de `CLAUDE.md`** (`lrwxr-xr-x AGENTS.md -> CLAUDE.md`) — a regra já chega ao Codex sem duplicação. Boa decisão, mantida.

---

## 4. Lacunas / riscos

| # | Lacuna | Evidência | Risco |
|---|---|---|---|
| L1 | **Não há claim de entrada.** 77 worktrees, 894 branches, nenhum registro de "quem está em tal área" | A7 | Dois agentes na mesma área é o estado padrão, não a exceção |
| L2 | **O lease é desenho, não estado** | `grep 'lease_id'` → só o template | Um lease que não é arquivo não é verificável nem expira |
| L3 | **O volume se repõe mais rápido do que a limpeza** | R7: 55 worktrees/861 branches em 29/09 04:39 UTC → 77/894 hoje | R7 é um evento, não um regime |
| L4 | **O registro de decisão não é confiável nas duas direções** | B1 (itens 4 e 13 corrigidos, doc ⬜), B3 e B4 ("não iniciado" para mergeado), B5 ("Proposto" para implementado) | Quem confia no registro trabalha errado *e* desperdiça |
| L5 | **Endereço de decisão colidido** | B6 (2×026, 2×029) | Referência por número resolve para a decisão errada |
| L6 | **Dois ledgers canônicos, nenhum indexado, nenhum com gate** | B2 | A pergunta "o que está no ar?" tem duas respostas |
| L7 | **Decisão do dono sem dono nem prazo** | B7 (18 dias), B8 (24 dias), B9 (19 dias) | Envelhece em silêncio; foi o que o autor do B7 tentou evitar escrevendo "(sem lugar melhor para morar)" |
| L8 | **O checkout principal é `main` de 2.884 commits atrás e carrega árvore alheia** | A5 | Documento de coordenação já está lá sem rastreio |
| L9 | **Não há verificação de PR** | `gh` HTTP 401 (`gh pr list`); `scripts/inflight.sh:56,59,62` — `PRS="[]"; OPEN="[]"` e `\|\| echo '[]'` em cada chamada | [INFERÊNCIA, do script + do 401] `make inflight` — que depende de `gh` — roda **cego** hoje: `PRS="[]"`. O inventário de dormentes degrada exatamente quando é mais necessário, e nada na saída declara que degradou |

**Risco transversal [INFERÊNCIA]:** nenhuma dessas lacunas é de disciplina — são de **mecanismo**. O repositório já provou que escreve a regra certa (CLAUDE.md tem a seção "A ESTEIRA" e os leases estão desenhados). O que não existe é o **artefato com estado** que a regra possa consultar. Regra sem estado verificável é o que o próprio `esteira-stop-hook.sh:14-16` já diagnosticou: *"A regra já estava escrita e era ignorada. Regra sem trava é lembrete… Isto é a trava."* — a trava de saída existe; a de entrada não.

---

## 5. Recomendações acionáveis, ordenadas por impacto/esforço

**M1 — Ledger de decisões como arquivo único, validado por gate. (impacto: altíssimo · esforço: baixo)**

Criar `docs/coordination/DECISIONS.md` — append-only, uma linha por decisão, com campos obrigatórios:

```
id | data | decisão (1 frase) | dono | origem (doc/PR/ADR) | estado | evidência | revisar_em | encerrado_em
```

Vocabulário fechado de `estado`: `DECIDIDA` · `EM_EXECUCAO` · `EXECUTADA` · `ADIADA` · `SUPERSEDIDA` · `BLOQUEADA`. Regra dura: `revisar_em` é obrigatório enquanto o estado não é terminal.

- **Por que resolve:** os 10 casos do §2 viram linhas consultáveis. B7 (FOCUS_NFE) e B9 (ADR-020) ganham dono e data; B5 e B3/B4 param de mentir porque a linha é atualizada no mesmo commit que o código.
- **Por que é barato:** o formato já existe na prática em `GO-LIVE-READINESS-PLAN.md` (`Estado/Ambiente/Fonte/Owner/Próximo evento`) — é o mesmo desenho, num arquivo que cobre *decisões* em vez de *estado de ambiente*.
- **Onde plugar:** `scripts/check_canonical_docs.py` já valida `CANONICAL_DOCS` no CI (`runtime-gate.yml:93`). Acrescentar `DECISIONS.md` à lista e validar: campos obrigatórios presentes, vocabulário fechado, `id` único, `revisar_em` no passado ⇒ falha. **Nada de infra nova.**

**M2 — Claim de área, materializando o lease que já está desenhado. (impacto: altíssimo · esforço: médio)**

Criar `docs/coordination/IN-FLIGHT.md` (ou `.json`), com o registro da §6.1 do programa:

```
lease_id | áreas/globs | owner | branch | worktree | aberto_em | revisar_em | estado | evidência_de_liberação
```

Estados: `REQUESTED/ACTIVE/HANDOFF/RELEASED/BLOCKED` (já definidos no programa, `:199`). Regra: um glob com lease `ACTIVE` de escrita não aceita segundo owner.

- **Por que resolve L1/L2:** transforma "eu avisei no chat" em estado verificável. Os sete `codex/pr614-*/marketing-*` de B... (A3) apareceriam como sete claims no mesmo glob — e o conflito fica **visível antes** do merge.
- **Barato de operar:** `make claim area=<glob> branch=<branch>` e `make release lease=<id>` — dois alvos novos no Makefile, ao lado de `inflight`/`audit-branches`.
- **Como vira trava, não lembrete:** estender `scripts/inflight.sh` (que já roda e já tem `NOISE`) para cruzar **worktree suja × lease**: arquivo sujo em glob com lease de outro owner = `🔴 COLISÃO`. E o `Stop hook` (`esteira-stop-hook.sh`, que já bloqueia) passa a exigir lease `ACTIVE` antes de permitir encerrar um turno com commit novo numa área compartilhada.

**M3 — Gate de coerência entre índice e código. (impacto: alto · esforço: baixo)**

Estender `check_canonical_docs.py` com a classe de achado que os casos B3/B4/B5 provam faltar:

- `docs/plans/README.md` afirma "não iniciado"/"não implementado" ⇒ falha se a branch citada for ancestral de `origin/main` (verificável com `git merge-base --is-ancestor`, stdlib `subprocess`, já usado no script).
- `docs/decisions/adr-*.md` com `Status: Proposto` ⇒ aviso se o arquivo de código citado no `Escopo` existir. Mais simples e determinístico: **exigir `adr-NNN` único** (`ls docs/decisions/ | grep -oE 'adr-[0-9]+' | sort | uniq -d` deve ser vazio) — **isso sozinho pega B6 hoje**.
- `docs/plans/fallbacks-perigosos-go-live.md`: cada `⬜` precisa de `id` de decisão correspondente em `DECISIONS.md` — **isso sozinho pega B1 hoje**.

**M4 — Encerrar a duplicação de ledger. (impacto: alto · esforço: muito baixo)**

Decidir e escrever: **(a)** o ledger de ativação cobre *estado por PR/WP no ambiente vivo*; a matriz `GO-LIVE-READINESS-PLAN` cobre *critérios de go-live*; nenhum dos dois é "a única fonte" do outro. **(b)** Acrescentar as referências cruzadas **nos dois arquivos** e a linha do ledger em `docs/runbooks/README.md` e `docs/README.md`. **(c)** Acrescentar o ledger à lista `CANONICAL_DOCS` do gate. Sem (c), a duplicação volta.

**M5 — Resolver as colisões de endereço. (impacto: médio-alto · esforço: baixo, uma vez)**

Dois ADR-026 e dois ADR-029: **não renumerar o que já é citado** (o README proíbe, com razão). Em vez disso, renomear o **título** para qualificar o domínio ("ADR-026 — Envelope de segurança (superfícies)" / "ADR-026 — Concierge"), corrigir as referências nuas listadas em B6 para link qualificado, e tornar o número único daqui pra frente pelo gate de M3.

**M6 — Devolver visão de PR ao `make inflight`. (impacto: médio · esforço: baixo)**

Hoje `gh` responde `401` e o script cai em `PRS="[]"`: o inventário de dormentes fica cego exatamente quando é necessário. `scripts/inflight.sh` já trata a ausência (`command -v gh`); falta **declarar o estado degradado no relatório** (ex.: `⚠️ SEM GH: PRs não verificados`) para que ninguém leia "sem PR" como fato quando é ausência de dado.

**M7 — O domicílio das decisões sem casa. (impacto: médio · esforço: muito baixo)**

B7, B8 e B9 são decisões que moram onde não foram tomadas. Regra de uma linha: *decisão pendente do dono mora no ledger (`DECISIONS.md`), e o documento que a encontrou só aponta para o `id`*. Mata o comentário do B7 — *"sem lugar melhor para morar até você decidir"* — nomeando o lugar.

**M8 — Checkout principal: parar de ser chão de outro branch. (impacto: médio · esforço: baixo)**

O principal está 2.884 commits atrás e com 8 documentos rastreados em `main` aparecendo como não rastreados. **[INFERÊNCIA]:** mover ou remover os untracked de outra frente (com os três `COORDENACAO-*/DECISAO-*` já rastreados em `main`, eles são cópia) e alinhar o principal a `origin/main` por fast-forward — **exige a palavra de quem tem a outra sessão aberta ali; não é decisão de agente.**

---

## 6. Perguntas abertas / o que não consegui verificar

1. **[NÃO VERIFICADO] Estado de qualquer PR.** `gh` sem autenticação (`HTTP 401: Requires authentication`, `gh pr list`). O §3 de `WP-REPOSITORY-WORKTREE-BRANCH-HYGIENE-2026-09-28.md:89-97` nomeia PRs #722, #1116, #1119, #1120, #1148 como pendentes de decisão; `GO-LIVE-READINESS-PLAN` não os cita; não pude confirmar se continuam abertos, fechados ou mergeados.
2. **[NÃO VERIFICADO] `branch-protection-pendencias.md`** (B8) — os três itens do dono continuam abertos? Depende de `gh api …/branches/main/protection`, indisponível.
3. **[NÃO VERIFICADO] Estado real do rollout de ADR-020** (B9) no ambiente vivo — exigiria acesso ao app e ao banco.
4. **Pergunta ao dono:** o **ledger de ativação** e a **matriz de prontidão** devem continuar separados (M4a), ou um absorve o outro? A decisão não é técnica: são duas perguntas diferentes ("o que está no ar" vs. "podemos virar a chave") que hoje ninguém declarou serem diferentes.
5. **Pergunta ao dono:** o claim de área (M2) deve **bloquear** (commit recusado sem lease) ou **avisar**? O `esteira-stop-hook` já escolheu bloquear para a saída; para a entrada, bloquear tem custo real num repositório com 77 frentes legítimas.
6. **Pergunta ao dono:** quem é o dono dos **9 itens realmente abertos** de `fallbacks-perigosos-go-live.md` (1, 2, 9, 10, 12, 14, 15, 16, 17)? Eles são de dinheiro (1, 2, 12, 17), de dado (9, 10) e de segurança (15). A ausência de dono é o achado; atribuí-lo é decisão dele.
7. **Onde procurei e não encontrei registro de lease/claim:** `docs/` (recursivo), `.claude/`, `.codex/`, `scripts/`, `Makefile`, `.github/workflows/`, e `git worktree list --porcelain`. Se existir fora do repositório (ex.: `~/.codex/` ou `~/.claude/`), não o vi — só li `~/.claude/settings.json` e `~/.claude/hooks/`.
8. **[FATO, e é uma condição da auditoria]** Enquanto eu auditava, `origin/main` avançou 14 commits e **mergeou o ledger** (B2) — e um relatório irmão (`04-bug-segundo-clique.md`) apareceu neste mesmo diretório às 13:53. A auditoria da concorrência é ela mesma concorrente: qualquer número deste relatório tem data.
