# Tarefa 12 — Risco de regressão: onde a suíte protege e onde ela não protege

> Árvore: `.dsh-worktrees/go-live-acceleration` em `origin/main` = **`f0ffd02fd`** (2026-09-29).
> Toda evidência é leitura estática ou comando read-only. Nada foi editado além deste arquivo.
> Comandos de coleta no apêndice (§7). Marcadores: **[FATO]** verificado · **[INFERÊNCIA]** dedução · **[NÃO VERIFICADO]** não confirmei.

---

## 1. Resumo executivo

**A suíte é grande, rápida por teste e cobre muito mais do que o CLAUDE.md declara — e ainda assim deixa passar quatro classes de regressão silenciosa, todas no caminho do dinheiro.**

1. **Volume.** [FATO] **23.045 testes** coletados em 12 pacotes + 3 apps Django + `tools/` (medido com `--collect-only`), em **1.103 arquivos** `test_*.py` e **484 arquivos** de teste Nuxt. O `CLAUDE.md` diz "~6.500: ~2.200 cores + ~4.250 framework"; a realidade é **3,5× maior** — o número está errado e é usado para decidir orçamento de CI.

2. **A CI é lenta por UM motivo, e ele é medível.** [FATO] O `Runtime Gate` leva **23 a 31 min** de parede e é ele que define o relógio do PR. O caminho crítico é `Testes (test-shop)`: **20,3 / 29,8 / 28,4 / 22,9 min** em quatro execuções medidas via `gh run view`. Logo atrás, `Backstage rest` (13,6–22,4 min). **`test-shop` e `test-storefront` são os únicos alvos de teste sem `-n auto`** (`Makefile:191-201`); o `test-backstage` roda os **7.239** testes dele em paralelo. O gargalo é uma decisão de uma linha, não a suíte.

3. **O que a CI protege muito bem.** [FATO] O backend de pagamento é a área mais densa do repositório: `test_payment_webhooks.py` (1.588 linhas, 40+ testes nomeados de idempotência/disputa/estorno), `test_payment_efi_adapter.py` (740 linhas), `test_payment_timeout_gateway_check.py` (17 testes de "gateway mudo não inventa pagamento"), `test_webhook_claim_race.py` e `test_pos_cash_ledger.py` — estes dois últimos **só rodam contra PostgreSQL real** e o gate que os executa **reprova em qualquer skip**. Não é aqui que o dinheiro vaza.

4. **Onde a suíte NÃO protege — quatro buracos concretos, em ordem de risco:**

   - **B1 — O contrato FE↔BE do PDV e do carrinho/checkout é manual.** [FATO] Existem dois mecanismos de contrato (snapshot JSON e TS gerado) e eles cobrem **10 de ~50 projections**. O **PDV é o caso pior**: `posContract.ts` tem **14 linhas** e cobre só a versão do intent e três enums; a forma da projection do PDV (`app/types/pos.ts`, **345 chaves**) é escrita à mão e **nenhum gate a liga ao backend**.
   - **B2 — Nenhum browser automatizado executa uma venda no PDV, nem um pagamento.** [FATO] O gate de browser do Omotenashi **só navega e audita o DOM** (overflow, controle fora de tela, exceção de runtime); não clica em nada. `pos-nuxt` tem 4 specs Playwright e o `vitest` **exclui `tests/e2e/**`**; nenhum workflow roda `npm run test:e2e` para pos/kds/orders/hub/storefront.
   - **B3 — A suíte alpha do storefront, que é a única que percorre o fluxo inteiro, não roda na CI.** [FATO] `surfaces/storefront-nuxt/tests/e2e/alpha/specs/` tem 5 specs (smoke, happy-path, personas, cenários, edge-cases) e **nenhum workflow os invoca**; e o `criticalFlow.spec.ts` do próprio app está `test.skip(true)` permanente.
   - **B4 — O smoke pós-deploy não toca em dinheiro.** [FATO] `alpha-smoke.yml` faz 4 asserções: `/ready/`, cardápio ≥30 SKUs, `POST /checkout/` anônimo → 403, SSR da home. **Zero** asserção sobre pagamento, PDV, caixa ou fechamento.

5. **O que hoje deixaria uma regressão silenciosa passar** (detalhe em §2.7): *renomear uma chave da projection do PDV* — BE + testes BE + fixtures do vitest, tudo verde, e o tile do balcão renderiza vazio. É literalmente o defeito que o mecanismo de contrato compartilhado foi criado para fechar (auditoria de 26/08, citada no cabeçalho de `test_shared_projection_contracts.py`), fechado para o storefront e **deixado aberto para o PDV**.

---
## 2. Achados

### 2.1 Mapa de volume — quantos testes, e onde

**[FATO]** Medido com `.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider` e `PYTHONPATH` apontando para a worktree (o `.venv` da raiz tem editable installs apontando para o checkout principal — sem `PYTHONPATH` a coleta quebra com `ImportError: cannot import name 'QUALITY_GRADE_ALLOWLIST_METADATA_KEY'`).

| Suíte | Arquivos `test_*.py` | Testes coletados |
|---|---:|---:|
| `shopman/shop/tests` | 445 (+16 `integration`, +4 `e2e`) | **10.508** (de 10.539; 31 desselecionados por `-m 'not browser'`) |
| `shopman/backstage/tests` | 320 | **7.239** |
| `shopman/storefront/tests` | 80 (+40 `api`, +32 `web`, +9 `security`, +9 `e2e`) | **2.219** |
| `packages/*` (12 pacotes) | 146 (+2 em `contrib/`) | **2.909** |
| `tools/pos-counter-agent` | 1 | **170** |
| **Total Python** | **1.103** | **23.045** |

Por pacote: guestman 510 · craftsman 446 · doorman 347 · orderman 313 · stockman 295 · offerman 281 · payman 191 · refs 177 · utils 147 · buyman 87 · cashman 81 · fiscalman 34.

**[FATO]** Frontend — arquivos `.test.ts`/`.spec.ts` (fora de `node_modules`):

| Superfície | Arquivos | e2e Playwright | roda na CI? |
|---|---:|---:|---|
| `storefront-nuxt` | 118 | 9 | vitest+lint+typecheck **sim**; `test:e2e` **não**; `pwa.spec.ts` sim (job PWA) |
| `pos-nuxt` | 100 | 4 | vitest+lint+typecheck **sim**; `test:e2e` **não** |
| `operator-kit` | 89 | 0 | sim |
| `orders-nuxt` | 55 | 5 | vitest+lint+typecheck sim; `test:e2e` **não** |
| `marketing-nuxt` | 52 | 2 | **sim, cadeia completa** (e2e + a11y + visual + security + audit) |
| `production-nuxt` | 46 | 3 | **sim** (job "Produção — matriz Playwright AA") |
| `kds-nuxt` | 9 | 2 | vitest sim; `test:e2e` **não** |
| `hub-nuxt` | 6 | 4 | vitest sim; `test:e2e` **não** |
| `purchase-nuxt` | 6 | 0 | sim |
| `bi-nuxt` | 3 | 0 | sim |
| `operator-router` | 0 | 0 | sim (`npm test`, só com mudança de contrato de grupo) |

**Impacto.** O CLAUDE.md e o orçamento de CI estão calibrados sobre um número 3,5× menor que o real. **Confiança: alta** (comando reproduzível).

---

### 2.2 O Makefile — o que `make test`, `make test-framework`, `make admin` e `make lint` realmente rodam

**[FATO]** Leitura de `Makefile`:

- `make test` (`Makefile:81`) = `test-refs test-utils test-offerman test-stockman test-craftsman test-orderman test-payman test-guestman test-doorman test-buyman test-fiscalman test-cashman test-framework test-counter-agent`. **Não inclui nenhuma superfície Nuxt.** Não inclui `test-migrations`, `test-constraints`, `test-surface-versions`, `test-surface-registry`, `test-silent-swallow`, `admin`, `test-runtime`, `canonical-docs`, `test-deploy-selection`, `test-workflow-budgets`. Ou seja: **`make test` verde não é "PR verde"** — 9 gates obrigatórios ficam de fora.
- `make test-framework` (`Makefile:148`) = `test-shop test-storefront test-backstage`. Os dois primeiros **sem `-n auto`**; o terceiro com.
- `make admin` (`Makefile:643-650`) = `check_unfold_canonical.py --maturity` + 3 testes (`test_unfold_canonical_templates`, `test_admin_operational_integration`, `test_admin_smoke`).
- `make lint` (`Makefile:602-603`) = `admin` + `ruff check packages/ shopman/shop/ config/`. **Não passa ruff em `shopman/storefront/` nem em `shopman/backstage/`**. A CI usa outro comando (`.venv/bin/ruff check .`, `runtime-gate.yml:51`) — logo **órgão lintado na CI e não lintado no fluxo local**, a assimetria que produz "verde aqui, vermelho lá".

**Impacto.** Dois footguns de operador: `make test` verde ≠ PR verde; `make lint` deixa passar o que a CI reprova. **Confiança: alta.**

---

### 2.3 Guardrails/gates — inventário completo, o que cada um impede, e se roda na CI

**[FATO]** 21 scripts em `scripts/check_*.py`. Onde cada um roda:

| Gate | Arquivo | Impede | Roda na CI? |
|---|---|---|---|
| Unfold canônico | `check_unfold_canonical.py` | classe Unfold copiada, componente incluído direto, overlay novo, página Admin fora do contrato, versão instalada ≠ inventário | **sim** — job `Admin/Unfold gate` (`make admin`) |
| Registro de superfícies | `check_surface_registry.py` | superfície nova ausente do Dependabot, dos specs `.do/`, do `SURFACES`, do router, do Dockerfile, do CSRF de dev | **sim** — job `Versões das superfícies` |
| Versões das superfícies | `check_surface_versions.py` | faixa **e** lock diferentes entre os 10 apps | **sim** — mesmo job |
| Meia-correção | `check_silent_swallow.py` | arquivo que **grita e engole no mesmo arquivo** (escopo = diff do PR) | **sim** — job próprio, check obrigatório |
| ADR-015 | `check_adr015.py` | pós-tag: migração só append-only; `DEPRECATED` sem prazo válido | **sim** — job `Quality` |
| Arquivo legal | `check_legal_archive.py` | reescrita/remoção de versão legal já publicada | **sim** — job `Quality` |
| Migrations | `check_migrations.py` | `makemigrations --check` + `migrate` de banco zerado + grafo consistente (+ expand-contract pós-tag) | **sim** — job `Quality` e `Production Contract` |
| Constraints | `check_constraints.py` | pacote instalado pela imagem sem pin exato | **sim** — job `Quality` |
| Docs canônicos | `check_canonical_docs.py` | verdade de go-live divergindo de código/workflows/targets | **sim** — job `Quality` |
| Teto de job | `check_workflow_budgets.py` | `timeout-minutes` do job menor que a espera declarada (o defeito do alpha-smoke 06–08/09) | **sim** — job `Quality` |
| Seleção de deploy | `test_deploy_component_selection.py` | run cancelado deixando componente sem imagem (defeito de 17/09) | **sim** — job `Quality` |
| Drift do registry | `check_registry_drift.py` | componente publicado atrás do `main` | **sim** — job `drift` do `Deploy Images` |
| Contrato de produção | `check_production_contract.py` | flags de mock/test affordance em produção; rede bloqueada | **sim** — workflow `Production Contract` |
| Runtime real | `check_runtime_gate.py` + `run_runtime_tests.py` | PostgreSQL+Redis ausentes; **qualquer skip** no subconjunto pós-Postgres (56 arquivos) | **sim** — job `PostgreSQL + Redis runtime stress gate` |
| Reentrância do seed | `check_seed_reentrancy.py` | `seed --flush` estourando em banco com curadoria | **sim** — job Browser QA do Omotenashi |
| Marketing | `check_marketing_docs.py` + `export_marketing_client --check` | rotas/probes/docs/OpenAPI/cliente TS com drift | **sim** — job `Quality` |
| Readiness | `check_release_readiness.py` | perfis pilot/alpha/production | **sim** (non-strict) — job Browser QA |
| Menu | `check_menu_smoke.py` | catálogo servido abaixo do piso | **sim** — pós-deploy (`alpha-smoke`) |
| Drift do spec DO | `check_do_spec_drift.py` | env que existe só no app vivo e sumiria no `apps update` | **NÃO** — só local, exige `doctl` (`Makefile:369-373` diz "NÃO é alvo de CI") |
| Vocabulário (tela) | `test_vocabulario_de_tela.py` | "aparelho" em `shopman/`, `packages/`, `config/` | **sim** — suíte backstage |
| Vocabulário (surfaces) | `operator-kit/tests/guardrails.vocabulary.test.ts` | "aparelho" nos 8 apps de operador + layer + router | **sim** — job `operator-kit` |
| A11y / copy / lint | `operator-kit/tests/guardrails.*.test.ts` | truncamento de copy, a11y do AppBar, orientação, lint do kit | **sim** — job `operator-kit` |

**[FATO]** Não existe `test-coverage` na CI: `Makefile:410-413` define `make test-coverage` (backstage com piso de 75%), mas nenhum workflow o chama. A CI usa o **`Coverage Gate`** combinado (`runtime-gate.yml:413-462`).

**[FATO]** O `Coverage Gate` tem dois furos de escopo visíveis no próprio workflow:
- `pyproject.toml:93-94` → `[tool.coverage.run] source = ["shopman"]`. **`packages/` está fora**: os **2.909 testes** do Core (payman, stockman, cashman, orderman…) não contribuem nem são medidos pelo piso de 75%.
- `runtime-gate.yml:448-449` → `count=$(find coverage-data ... | wc -l); test "$count" = "4"`. Obra só dos 4 shards (`test-shop`, `test-storefront`, `backstage-seed`, `backstage-rest`) — coerente com o `source`, mas confirma que o Core fica de fora por desenho.

**Impacto.** O piso de cobertura de 75% **não protege nada de `packages/`**, onde mora `payman` (intents, transações, reconciliação). **Confiança: alta.**

---
### 2.4 Contratos de superfície — o que o front e o back combinam, e o que isso pega num PR

**[FATO]** Existem **dois** mecanismos, e eles são bons — mas cobrem 10 de ~50 projections.

**(a) Snapshot JSON BE↔FE** — `contracts/projections/` tem **4 arquivos**:
`storefront_catalog.json`, `storefront_product_detail.json`, `storefront_site.json`, `marketing_v2.schema.json`.
O lado Django (`shopman/storefront/tests/test_shared_projection_contracts.py:66-89`) serializa a projection real e compara **byte a byte** com o snapshot (datas normalizadas em `<today>`/`<tomorrow>`/`<datetime>`); o lado Nuxt (`surfaces/storefront-nuxt/tests/projectionContracts.test.ts:18-36`) importa **o mesmo arquivo** e o atribui aos tipos TS — o typecheck do Surfaces Gate reprova o rename. É o único mecanismo que **atravessa a fronteira com o mesmo artefato**.
O próprio doc declara a fatia: `docs/reference/projection-contracts.md:62-64` — *"Fatia atual: storefront_catalog, storefront_product_detail e marketing_v2. Candidatas seguintes: order_tracking, pos (comanda/checkout), kds, order_queue."*

**(b) TS gerado + teste de drift** — 7 arquivos, **todos** com teste de drift no lado Django:

| Gerado | Fonte | Teste de drift |
|---|---|---|
| `surfaces/pos-nuxt/app/generated/posContract.ts` (**14 linhas**) | `shop/services/pos_intent.py` | `shopman/shop/tests/test_pos_schema_export.py` |
| `surfaces/orders-nuxt/app/generated/ordersContract.ts` (754) | `backstage/projections/order_queue.py` +5 | `backstage/tests/test_orders_schema_export.py` |
| `surfaces/kds-nuxt/app/generated/kdsContract.ts` (127) | `projections/kds.py` | `test_kds_schema_export.py` |
| `surfaces/production-nuxt/app/generated/productionContract.ts` (1051) | `projections/production.py` | `test_production_schema_export.py` |
| `surfaces/production-nuxt/app/generated/recipeBookContract.ts` (224) | `projections/recipe_book.py` | `test_recipe_book_schema_export.py` |
| `surfaces/bi-nuxt/app/generated/biContract.ts` (574) | `projections/bi_*.py` | `test_bi_schema_export.py` |
| `surfaces/marketing-nuxt/app/generated/marketingClient.ts` (314) | projection v2 | `test_marketing_projection_v2.py` **+** `export_marketing_client --check` no job `Quality` |

**[FATO]** Os apps **consomem** esses tipos gerados (`orders-nuxt/app/types/orders.ts:15`, `kds-nuxt/app/types/kds.ts:15`, `production-nuxt/app/types/production.ts:28`, `bi-nuxt/app/types/bi.ts:46`, `production-nuxt/app/types/recipeBook.ts:19`, `marketing-nuxt/app/types/campaign.ts:3`) — o mecanismo morde de verdade nesses seis.

**[FATO]** **Mas não no PDV.** `posContract.ts` são **14 linhas**: a versão do intent, três enums (métodos, coleções de pagamento, canais de recibo). A **forma da projection do PDV não é gerada**: `surfaces/pos-nuxt/app/types/pos.ts` declara **345 chaves à mão** (`Action`, `POSProductProjection`, workspace de pagamento, caixa, fechamento…). Nenhum teste de `shopman/backstage/tests` importa esse arquivo, e nenhum teste de drift o compara com `shopman/backstage/projections/pos.py`.

**[FATO]** A mesma lacuna existe no **carrinho/checkout/pagamento/acompanhamento do storefront**: `surfaces/storefront-nuxt/app/types/shopman.ts` (672 chaves) é escrito à mão; os 3 snapshots cobrem catálogo, PDP e site — **não** `cart.py`, `checkout.py`, `payment`, `order_tracking.py`. Há `test_serializer_projection_contract.py` (paridade **serializer DRF ↔ dataclass**, dentro do Django) e vários `test_projections_*` (asserções escritas à mão) — nenhum deles liga ao arquivo TS.

**Impacto.** Rename de chave "completo" (BE + teste BE + fixture do vitest, tudo no mesmo PR) passa por todos os gates e quebra só na tela — exatamente o defeito de 26/08. **Confiança: alta.**

---

### 2.5 Testes de frontend — o que cada app cobre, com destaque para e2e

**[FATO]** O `vitest` de cada app **exclui `tests/e2e/**`** explicitamente (ex.: `surfaces/pos-nuxt/vitest.config.ts`, projeto `unit`, `exclude: [... "tests/e2e/**" ...]`). E a CI roda apenas `npm test` (= `vitest run`), `npm run lint --if-present` e `npm run typecheck --if-present` (`surfaces-gate.yml:115-132`).

**[FATO]** Consequência, por app, dos specs Playwright que **existem e não rodam**:
- `pos-nuxt/tests/e2e/`: `customer-display.spec.ts`, `guards.spec.ts`, `resilience.spec.ts` — nunca executados por workflow nenhum.
- `orders-nuxt/tests/e2e/` (5), `kds-nuxt/tests/e2e/` (2), `hub-nuxt/tests/e2e/` (4) — idem.
- `storefront-nuxt/tests/e2e/`: `guards.spec.ts`, `resilience.spec.ts` — idem (só `pwa.spec.ts` roda, no job `PWA — storefront`).

**[FATO] Storefront tem e2e? Sim — em Python, e roda na CI.** O job `Storefront E2E (Playwright)` do `Omotenashi Gate` roda `make storefront-e2e` → `scripts/run_storefront_e2e.sh` → `.venv/bin/python -m pytest shopman/shop/tests/e2e/test_storefront_e2e.py -m browser` (627 linhas, 18 testes). **Medido: 5,93 min.**

O que ele cobre de fato:
- menu → PDP (preço + botão) → carrinho com a linha do produto (`test_01`–`test_03a`), com asserção **positiva** do nome do produto;
- `test_04` — checkout anônimo responde 200 e mostra o gate de login;
- `test_07`/`test_08` — tracking com grant sobre **pedidos do seed** (não criados no teste);
- `test_11_live_pickup_order_reaches_operator_queue` — **o mais forte do repositório**: cliente real (Playwright) percorre menu → PDP → sacola → OTP de debug → checkout (retirada → quando → PIX → revisão → enviar) e o pedido é conferido na **API crua do backstage**. Só não valida pagamento: o PIX é mock em DEBUG e o teste declara isso na docstring (`test_storefront_e2e.py:496-501`).

**[FATO]** O que **não** roda: `surfaces/storefront-nuxt/tests/e2e/alpha/specs/` — 5 specs (01-smoke, 02-happy-path, 03-personas, 04-scenarios, 05-edge-cases) com `playwright.config.ts` apontando para `STOREFRONT_URL`. Nenhum `.yml` de `.github/workflows/` menciona `alpha/specs`, o `playwright.config` da suíte alpha nem o `test:e2e` do storefront. A única menção fora da própria pasta é um plano concluído e o `alpha-smoke.yml`, que só faz `curl`. **A suíte do fluxo completo do cliente é manual.**

**[FATO]** E dentro do app, `surfaces/storefront-nuxt/tests/e2e/criticalFlow.spec.ts:14`:

```ts
test.describe('fluxo crítico (requer Django real)', () => {
  test.skip(true, 'requer backend com dados semeados — reviewer local')
```

O README da pasta (`tests/e2e/README.md`) confirma: "Fluxo crítico com dados (`criticalFlow.spec.ts` — reviewer local) … Marcado `skip` por padrão."

**Impacto.** O fluxo de venda do PDV e o fluxo de pagamento do cliente **não têm verificação de browser automatizada**. O que existe pega layout e "a página subiu", não "a venda fechou". **Confiança: alta.**

---

### 2.6 E2E — existe? roda na CI? quanto tempo leva?

**[FATO]** Sim, em três frentes distintas, todas no `Omotenashi Gate` (`omotenashi-gate.yml`), disparado em `pull_request` **e** `merge_group`:

| Job | O que roda | Tempo medido (job) | Parede do workflow |
|---|---|---:|---:|
| `Browser QA (Nuxt store + Django operator)` | `make omotenashi-browser-ci` — sobe Django + **5 superfícies Nuxt** (loja, orders, kds, production, pos) e navega a matriz `--strict` | **7,63 min** | |
| `Storefront E2E (Playwright)` | `make storefront-e2e` (`test_storefront_e2e.py`) | **5,93 min** | **7,73 min** |
| `Admin CSP (production settings)` | `make admin-csp-gate` (Django com `DEBUG=false` + Chrome caçando violação de CSP) | **5,93 min** | |

**[FATO]** O que o Browser QA realmente afirma — `scripts/run_omotenashi_browser_qa.mjs:559-568` é literalmente:

```js
if (navigationError) blockers.push("navigation-failed:" + navigationError);
if (audit.loginPage && !check.auth_gated) blockers.push("login-page");
if (audit.hOverflow) blockers.push("horizontal-overflow");
if (audit.offscreenControls.length) blockers.push("offscreen-controls");
if (evaluated.exceptionDetails) blockers.push("runtime-exception");
```

Ele **navega** (11 checks: 6 da loja + 5 de operador, incluindo `desktop.pos.counter`, `desktop.closing.day`, `desktop.cash_register.shift`) e audita o DOM. **Não há nenhum clique, nenhum preenchimento, nenhuma submissão.** É um gate de "as superfícies estão de pé e não vazam layout" — valioso, e honesto (o comentário em `scripts/run_omotenashi_browser_ci.sh:26-30` registra que até 20/08 os 6 checks de operador nasciam com URL vazia e eram pulados em silêncio) — mas **não é um teste funcional**.

**[FATO]** Parede total da CI em PR: o `Runtime Gate` (23–31 min) domina; todos os outros workflows cabem em paralelo dentro dele.

---
### 2.7 O que hoje deixaria passar uma regressão silenciosa no pagamento ou na venda

Seis cenários concretos, com o mecanismo de detecção (ou a ausência dele):

**B1 — Rename de chave da projection do PDV.**
[FATO] Renomeie `price_display` → `price_label` em `shopman/backstage/projections/pos.py:56` **junto** com o teste BE que hoje o nomeia (`shopman/shop/tests/test_pos_venda_por_peso.py:357`), a fixture do vitest (`surfaces/pos-nuxt/tests/composables/_posSaleHarness.ts:13`) e o tipo manual (`surfaces/pos-nuxt/app/types/pos.ts:21`). Resultado: **todos os gates verdes**. `posContract.ts` não contém esse campo; `PosProductTile.vue:81` renderiza vazio no balcão. É [INFERÊNCIA] a partir de [FATO] verificado (não executei o rename — seria escrita no repositório).
Escala do furo: [FATO] **74 das 345 chaves declaradas em `app/types/pos.ts` não são nomeadas por nenhum teste de `shopman/shop/tests` nem `shopman/backstage/tests`** (medido por script, §7.6). Método: busca do literal entre aspas ou de `.chave` no corpus de testes; **é heurística** — um teste que compare `asdict()` inteiro escapa dela.

**B2 — Venda no PDV com pagamento, em browser.**
[FATO] Não existe. Os 4 specs Playwright do `pos-nuxt` não rodam em workflow algum; o Browser QA do Omotenashi **não clica**. A cobertura de venda é toda Python (`shopman/backstage/tests/test_pos_*.py` — 60 arquivos) e vitest com fixtures manuais. Uma regressão que só apareça com DOM real (foco que não volta ao campo de troco, teclado numérico que não abre, split de pagamento que não fecha) não é vista por nenhum gate.

**B3 — Valor efetivamente cobrado, ponta a ponta.**
[FATO] O caminho é bem testado **em unidade/integração**: `test_payment_efi_amounts.py` trava a conversão BRL→centavos sem float (`int(float("4.35") * 100) == 434`, regressão real); `test_payment_webhooks.py` cobre idempotência de Stripe e Efí, disputa/chargeback, `efi_same_e2e_cannot_capture_another_txid`, `efi_in_progress_replay_returns_409`; `test_payment_timeout_gateway_check.py` tem 17 testes de "gateway mudo não inventa pagamento".
Mas **[FATO]** **nenhum gate compara o total do pedido com o valor autorizado no gateway em ambiente vivo**, e o smoke pós-deploy não toca em pagamento (`alpha-smoke.yml`, 4 asserções: `/ready/`, cardápio, `POST /checkout/`→403, SSR). Uma regressão de configuração (chave de produção trocada, webhook de outro merchant, valor enviado em reais em vez de centavos **no adapter real**) aparece só no primeiro cliente.

**B4 — Rename de chave do carrinho/checkout/acompanhamento do storefront.**
[FATO] Mesmo mecanismo do B1, no lado do cliente: `surfaces/storefront-nuxt/app/types/shopman.ts` (672 chaves) é manual e não é comparado com `shopman/storefront/presentation/{cart,checkout,order_tracking}.py`. As projections do dinheiro estão justamente **fora** dos 3 snapshots. [FATO] Medido: **263 das 672 chaves nunca são nomeadas** por nenhum teste Python de `shopman/storefront/tests` + `shopman/shop/tests` — mesmo método heurístico do B1, e aqui o número é inflado por copy/CTA (o que reduz o sinal, não a lacuna estrutural).

**B5 — Regressão de comportamento que depende de PostgreSQL.**
[FATO] Os jobs da matriz `tests` **não têm serviço de Postgres** (`runtime-gate.yml`, só o job `runtime-security-reliability` tem `services: postgres:16-alpine` + `redis:7-alpine`, linhas 506-532). Logo, em SQLite, todo teste marcado `requires_postgres` é **pulado**. A mitigação existe e é boa: `scripts/run_runtime_tests.py` lista **56 arquivos** que só rodam lá, **reprova em qualquer skip** (inclusive skip de módulo, via `SkipCollector`), e `shopman/shop/tests/test_runtime_gate.py` varre a árvore e **reprova quando um arquivo novo com o marcador nasce fora da lista**. [INFERÊNCIA] O risco residual é o teste que **não** usa o marcador mas depende de comportamento de Postgres (lock de linha, `ON CONFLICT`, semântica de JSONB) — roda em SQLite, verde, e mente.

**B6 — O gate da meia-correção é diff-scoped e de arquivo único.**
[FATO] `scripts/check_silent_swallow.py:28-31` — escopo é só o que o PR toca; a regra só dispara quando **o mesmo arquivo** tem um relato alto **e** um engolimento mudo. Um `except PaymentError: pass` novo num arquivo que nunca soube gritar **passa**. Estado atual medido com `--all` em `f0ffd02fd`: **6 arquivos, 10 sites** (contra 50 arquivos/94 sites em 05/09, segundo `docs/reference/silencio-inventario.md`) — e **nenhum deles está no caminho de pagamento** (`craftsman/contrib/demand/backend.py`, `backstage/projections/recipe_book.py` ×2, `shop/models/rules.py`, `shop/rules/engine.py` ×4, `shop/services/product_readiness.py`, `storefront-nuxt/app/plugins/errorReporter.client.ts`). O trabalho de 05/09 fechou a dívida do dinheiro.

---

### 2.8 Performance/budget — existe proteção?

**[FATO]** `assertNumQueries` (método de `TestCase`): **0 ocorrências** no repositório. Mas o equivalente via fixture do pytest-django existe: `django_assert_num_queries` — **24 usos em 15 arquivos**:
`test_continuum_catalog.py`, `test_auth_adult_declaration.py`, `test_marketing_consent_contract.py`, `test_marketing_delivery_aggregate.py`, `test_audience_manual.py`, `test_delivery_readiness.py`, `test_health.py`, `test_template_context_performance.py`, `test_production_reports.py`, `test_marketing_projection_v2.py`, `test_dashboard_projection_performance.py`, `test_admin_merge_undo.py`, `test_api_marketing_surface.py`, `buyman/test_supplier_contacts.py`, `doorman/test_middleware.py`.

**[FATO]** **Nenhum deles está no caminho do dinheiro**: não há budget de queries para `storefront/presentation/cart.py`, `storefront/presentation/checkout.py`, `backstage/projections/pos.py` (o PDV carrega cardápio + comandas + caixa numa tela só) nem para o acompanhamento de pedido.

**[FATO]** Budget de latência: **um** — `shopman/storefront/tests/test_operational_budget.py`, `PUT /api/v1/cart/skus/<sku>/` 24 vezes, **p95 ≤ 1500 ms**, medido no **test client do Django** (a docstring do próprio print diz `"no browser/network/humans"`). Roda no `test-storefront` (não skipped).

**[FATO]** O único budget de capacidade de verdade — `docs/reports/execution/orders-20260910/do_capacity/accept.py`, p95 backend ≤ 500 ms e browser ≤ 1500 ms, com 60 amostras — está amarrado a um branch morto: `.github/workflows/orders-isolated-capacity.yml:4-11` →

```yaml
on:
  workflow_dispatch:
  push:
    branches: [codex/orders-operational-excellence-20260910]
    paths:
      - .github/workflows/orders-isolated-capacity.yml
      - docs/reports/execution/orders-20260910/do_capacity/**
```

Nunca dispara em PR nem em `main`. **É um laboratório, não um gate.**

**Impacto.** Não existe gate de performance na CI. N+1 que volta numa projection do PDV ou do checkout não é visto por nada. **Confiança: alta.**

---

### 2.9 Custo da CI, medido

**[FATO]** `gh run view <id> --json jobs` em execuções recentes de `merge_group` bem-sucedidas:

```
Runtime Gate (run 36596000493)   WALL 23,05 min
   22,38 min  success   Backstage rest
   20,32 min  success   Testes (test-shop)
   10,82 min  success   Backstage seed
    8,05 min  success   PostgreSQL + Redis runtime stress gate
    7,87 min  success   Testes (test-storefront)
    4,85 min  success   Testes (test-cores)
    4,25 min  success   Admin/Unfold gate
    3,58 min  success   Quality + deploy contract
    1,67 min  success   Docker deploy image
    1,65 min  success   Testes (test-counter-agent)
    0,53 min  success   Coverage Gate
    0,22 min  success   Gate da meia-correção
    0,03 min  success   Testes (test-backstage)   <- agregador

Repetição em outras três execuções (parede / caminho crítico):
  30,88 min — Testes (test-shop) 29,77 | Backstage rest 13,63
  29,45 min — Testes (test-shop) 28,43 | Backstage rest 22,33
  24,50 min — Testes (test-shop) 22,93 | Backstage rest 22,08
```

**[FATO]** `Omotenashi Gate` 7,73 min · `Surfaces Gate` 7,27 min (Marketing 7,08; Produção Playwright 3,17) · `Security Gate` 4,58 min (CodeQL) · `Production Contract` 2,27 min · `Operator Groups Gate` 0,35 min (jobs pulados por escopo).

**[FATO]** O `Makefile:154-189` já mede e documenta o problema do backstage (14 testes que chamam `seed` = 61,7% do relógio; `-n auto` levou o passo de 19min04s para 8min00s). O que **não** foi feito é a mesma coisa nos outros dois alvos.

**Impacto.** O gargalo é uma omissão de 2 palavras (`-n auto`) em `Makefile:193` e `Makefile:197`. **Confiança: alta.**

---

### 2.10 Ruído de coleta sob `-n` no `test-storefront`

[FATO] Rodando `coverage run -m pytest shopman/storefront/tests -q -n auto`, a coleta **falhou** em 7 workers:

```
ERROR gw4 - Different tests were collected between gw3 and gw4.
-shopman/storefront/tests/test_account_privacy.py::test_deletion_requires_uuid4_idempotency_key[23b750c0-bc2d-11f1-bb16-9a450c3370fc]
+shopman/storefront/tests/test_account_privacy.py::test_deletion_requires_uuid4_idempotency_key[23adbd1c-bc2d-11f1-9f6e-9a450c3370fc]
```

A causa está no arquivo: `shopman/storefront/tests/test_account_privacy.py:937` — `@pytest.mark.parametrize("bad_key", [..., str(uuid.uuid1())])`. `uuid1()` é tempo+MAC, avaliado **no import**, e difere por worker. [FATO] Repeti `--collect-only -n auto` **5 vezes** e não reproduzi; `-n auto --collect-only` passou também em `shopman/shop/tests` e `shopman/backstage/tests`. [INFERÊNCIA] a falha é intermitente e depende de os workers gerarem `uuid1` em instantes diferentes. **Consequência prática:** `-n auto` no `test-storefront` não pode ser ligado sem trocar `uuid1()` por um literal fixo. [NÃO VERIFICADO] se `shopman/shop/tests` tem a mesma armadilha — o grep por `uuid4()` em `parametrize` no `shop/tests` não achou padrão equivalente, mas o grep foi estreito.

**Confiança: alta** para a causa; **média** para a frequência.

---

## 3. O que já existe (e é bom)

Esta seção existe porque o pedido é "onde a suíte protege" — e ela protege muito.

1. **Contrato de projection compartilhado é ouro** — o único mecanismo que atravessa BE↔FE com um artefato único e byte a byte (`contracts/projections/*.json` + `projectionContracts.test.ts`). O padrão já está escrito, documentado (`docs/reference/projection-contracts.md`) e **já foi estendido uma vez** (marketing v2). Falta aplicar ao resto.
2. **7 contratos TS gerados com teste de drift** (POS, orders, KDS, production, recipe book, BI, marketing). O de marketing é o mais forte: `--check` bloqueante no job `Quality`, além do teste.
3. **Gate de runtime pós-Postgres com tolerância zero a skip** — `scripts/run_runtime_tests.py` (56 arquivos: corridas de estoque, dinheiro, cupom, caixa, webhook) + `test_runtime_gate.py` que **reprova arquivo novo fora da lista**. Isso fechou um buraco real ("cinco corridas de dinheiro e estoque ficaram escritas e mortas").
4. **Pagamento é a área mais densa do repo**: ~200 testes só em `shop/tests/test_payment_*`, `test_webhook*`, `test_efi_*`, `test_stripe_*`, `test_refund_*`, `test_reconcile_payments*`, mais 191 em `packages/payman`.
5. **PDV tem a cobertura backend mais profunda** — 60 arquivos `test_pos_*.py` no backstage (caixa, gaveta, sangria, refund, troco, fiscal, comanda, takeover, link de pagamento, impressora) + 100 arquivos vitest no app.
6. **Gate da meia-correção funcionou**: de 50 arquivos/94 sites (05/09) para **6 arquivos/10 sites**, **zero no caminho do dinheiro**.
7. **Guardrails de coerência de repositório** (registro de superfícies, versões, canônico do Admin, ADR-015, arquivo legal, constraints, docs canônicos, orçamento de workflow) — todos bloqueantes, todos baratos (segundos, sem `npm ci`).
8. **Vocabulário e copy têm trava de verdade** — `test_vocabulario_de_tela.py` (1.951 arquivos) e `operator-kit/tests/guardrails.*.test.ts` (10+ arquivos), com exceções **declaradas por escrito**.
9. **`test_11_live_pickup_order_reaches_operator_queue`** — o e2e que mais se aproxima de "venda de verdade": o cliente cria o pedido pela UI e a verificação é a API crua do operador, independente da superfície.
10. **A CI roda em TODO PR, sem `paths:` filter** — e o comentário em `surfaces-gate.yml:4-8` explica por quê (required check que não reporta trava o merge para sempre). Consistente com a regra do `CLAUDE.md`.

---
## 4. Lacunas e riscos (priorizados por risco de dinheiro/operador)

| # | Lacuna | Risco | Evidência | Confiança |
|---|---|---|---|---|
| L1 | **Forma da projection do PDV não tem contrato gerado** — `pos.ts` é manual (345 chaves), `posContract.ts` tem 14 linhas só com enums | Rename/remoção de chave no cardápio, comanda, caixa ou pagamento **do balcão** passa verde e quebra na tela do operador | `posContract.ts`; `pos.ts`; ausência de teste que leia o TS | alta |
| L2 | **Nenhum browser executa venda + pagamento no PDV** e o Browser QA só navega | Regressão que só aparece com DOM real (foco do troco, split, teclado numérico, trava de gaveta) não é vista por gate nenhum | `run_omotenashi_browser_qa.mjs:559-568`; `vitest exclude tests/e2e/**`; nenhum workflow com `test:e2e` de pos | alta |
| L3 | **Suíte alpha do storefront não roda na CI** e `criticalFlow.spec.ts` está `skip` permanente | O fluxo completo do cliente (incluindo pagamento) só é exercitado por `test_11`, que usa pedido de retirada com PIX mockado | `alpha/playwright.config.ts`; grep de workflows = 0; `criticalFlow.spec.ts:14` | alta |
| L4 | **Carrinho/checkout/pagamento/acompanhamento do storefront fora dos snapshots de contrato** | Mesma classe do L1, do lado do cliente (a superfície que gera receita) | `contracts/projections/` tem 3 do storefront, nenhum é cart/checkout; `shopman.ts` manual | alta |
| L5 | **Smoke pós-deploy sem nenhuma asserção de dinheiro** | Deploy verde com pagamento quebrado no ambiente vivo; só o primeiro cliente descobre | `alpha-smoke.yml` (4 asserções) | alta |
| L6 | **Sem gate de performance/queries no caminho do dinheiro** | N+1 no PDV/checkout degrada a operação no balcão sem acender luz | 24 `django_assert_num_queries`, nenhum em cart/checkout/pos; capacity workflow amarrado a branch morto | alta |
| L7 | **`packages/` fora do piso de cobertura** | `payman` (intents, transações, reconciliação) não é medido | `pyproject.toml:93-94` `source = ["shopman"]`; `runtime-gate.yml:449` `test "$count" = "4"` | alta |
| L8 | **`test-shop` sem `-n auto` define o relógio** (20–30 min de 23–31) | Feedback lento ⇒ menos rigor do operador; é a dor declarada | `Makefile:193`; medições `gh run view` | alta |
| L9 | **`make test` verde ≠ PR verde** (9 gates fora) e **`make lint` não linta storefront/backstage** | Agente declara "pronto e verde" sem passar metade dos gates | `Makefile:81`, `Makefile:602-603` vs `runtime-gate.yml:51` | alta |
| L10 | **Gate da meia-correção é diff-scoped e de arquivo único** | `except PaymentError: pass` num arquivo novo passa | `check_silent_swallow.py:28-31` | alta |
| L11 | **Matriz roda em SQLite**; só 56 arquivos vão ao Postgres | Teste que depende de comportamento de Postgres sem o marcador roda verde e mente | `runtime-gate.yml:286-340` (sem `services:`); `run_runtime_tests.py` | média ([INFERÊNCIA] no risco residual) |
| L12 | **`check_do_spec_drift.py` é manual** (exige `doctl`) | O defeito de 05/09 (22 envs só no vivo, entre elas todo o e-mail e a emissão fiscal) pode repetir num `apps update` | `Makefile:369-373`; cabeçalho do script | alta |
| L13 | **Números canônicos desatualizados** (CLAUDE.md "~6.500"; `silencio-inventario.md` "7.780") | Orçamento de CI e decisões calibrados sobre número errado | §2.1 | alta |

---

## 5. Recomendações ordenadas por impacto × esforço

### Faixa A — ganho alto, esforço baixo (dias, não semanas)

**A1 — Ligar `-n auto` em `test-shop` e `test-storefront`.** *(impacto: alto · esforço: horas)*
`Makefile:193` e `Makefile:197`. [FATO] `--collect-only -n auto` passa nos dois. **Pré-requisito:** trocar `str(uuid.uuid1())` por literal fixo em `shopman/storefront/tests/test_account_privacy.py:937` (§2.10). **Regra de aceitação:** comparar **no CI** (nunca no relógio local — o próprio `Makefile:178-181` já registra 451s/1181s/1830s para a mesma configuração) contra a rodada em série, como foi feito para o backstage. Espera-se cortar o `Runtime Gate` de ~23–31 min para ~12–15 min sem perder um teste.

**A2 — Fazer `make test` incluir os gates baratos.** *(impacto: alto · esforço: horas)*
`test-migrations`, `test-constraints`, `test-surface-versions`, `test-surface-registry`, `test-silent-swallow`, `canonical-docs`, `test-deploy-selection`, `test-workflow-budgets`, `admin` — todos rodam em segundos/minutos e nenhum está no alvo do desenvolvedor. Alternativa melhor: um alvo `make gates` do qual `test` depende.
E: **`make lint` → `ruff check .`** (igual à CI) e **`make test` incluir `make surfaces`** (ou `make surfaces-types`, que é o barato e pega contrato divergente).

**A3 — Auditoria de contrato pós-deploy no `alpha-smoke`.** *(impacto: alto · esforço: dias)*
O smoke já sabe fazer `curl` e já tem o padrão de credencial de operador no repo. Acrescentar, **sem criar venda**:
- `GET /api/v1/backstage/pos/` autenticado → asserir que a resposta contém as chaves que `app/types/pos.ts` consome (lista curta e explícita: `products[0].price_q`, `price_display`, `cash_runtime`, `payment_methods`, `actions`);
- o mesmo para o checkout do storefront (`GET /api/v1/storefront/checkout/` autenticado em conta de teste) e para `GET /api/v1/storefront/cart/`;
- `GET /ready/` já existe; acrescentar um probe de "o adapter de pagamento responde" (existe `make smoke-gateways` com rollback — hoje é alvo manual).
Isso é a **camada que pega a regressão que a CI não pega**: a que só existe no ambiente vivo.

**A4 — Corrigir os números canônicos.** *(impacto: médio · esforço: minutos)*
`CLAUDE.md` ("~6.500") e `docs/reference/silencio-inventario.md` ("7.780"). Use a medição de §2.1 e o comando do §7.1.

### Faixa B — ganho alto, esforço médio (semanas)

**B1 — Estender o contrato compartilhado às projections do DINHEIRO, na ordem de risco.** *(impacto: muito alto · esforço: semanas)*
O padrão já existe e é bom; falta aplicar. Ordem sugerida (a mesma que `docs/reference/projection-contracts.md:63-64` já declara):
1. `pos` (cardápio + comanda + workspace de pagamento + caixa + fechamento) — **maior risco, maior volume de churn** (o `silencio-inventario` registra 25 commits `fix(` em `PosPaymentWorkspace.vue` em 6 semanas);
2. `storefront_cart` e `storefront_checkout`;
3. `storefront_order_tracking`;
4. `order_queue` (hoje protegido por TS gerado, mas sem snapshot de valores).

Como o PDV já tem o gerador (`export_pos_schema`), o caminho mais barato **não** é o snapshot JSON: é **fazer o `export_pos_schema` gerar as dataclasses da projection** (`POSProductProjection`, `OpenTab`, workspace de pagamento, `cash_runtime`) como os outros seis já fazem, e apagar o espelho manual de `app/types/pos.ts`. Um teste de drift entra no mesmo PR. **É uma tarde copiando o padrão de `export_orders_schema.py`.**

**B2 — Ligar os specs Playwright que já existem.** *(impacto: alto · esforço: dias)*
`pos-nuxt`, `orders-nuxt`, `kds-nuxt`, `hub-nuxt` têm **14 specs escritos e nunca executados**. Não é escrever teste: é adicionar um passo `npm run test:e2e` ao job da matriz em `surfaces-gate.yml`, como Marketing e Produção já fazem. Custo estimado: +2–3 min por app, em paralelo (o job PWA de cada app já roda em 2–3 min).

**B3 — Rodar a suíte alpha do storefront na fila, não só à mão.** *(impacto: alto · esforço: dias)*
`surfaces/storefront-nuxt/tests/e2e/alpha/specs/` já existe com `playwright.config.ts` próprio, `STOREFRONT_URL` parametrizada e `workers: 1` com pacing de OTP já implementado (`helpers.ts`). O lugar natural é um job do `alpha-smoke.yml` (pós-deploy, contra o ambiente vivo) ou um workflow agendado — **não** o gate de PR, para não pagar o custo em todo merge. É a única suíte que exercita o fluxo completo do cliente contra um ambiente real.

**B4 — Budget de queries no caminho do dinheiro.** *(impacto: médio-alto · esforço: dias)*
Usar o que já existe (`django_assert_num_queries`, 24 usos). Alvos: `build_pos()`, `build_open_tab()`, `storefront/presentation/cart.py`, `checkout.py`, `order_tracking.py`. É a proteção mais barata que existe contra N+1 — não custa tempo de CI (roda dentro de testes que já rodam).

**B5 — Piso de cobertura para `packages/`.** *(impacto: médio · esforço: horas)*
Adicionar os 12 pacotes ao `[tool.coverage.run] source` e publicar um segundo relatório com piso próprio (começar medindo, não impondo). Hoje o Core — onde mora `payman` — não aparece em número nenhum.

**B6 — Falhar a CI quando um contrato gerado ficar stale, por comando e não só por teste.** *(impacto: médio · esforço: horas)*
Só `export_marketing_client --check` roda como comando no job `Quality`. `export_pos_schema` **tem** `--check` implementado (`export_pos_schema.py:69-79`) e **nenhum workflow o chama**; os outros cinco não têm a flag. Padronizar: um passo `make contracts-check` no job `Quality` que roda os 7 com `--check`. É a diferença entre "um teste pega" e "o gate diz o comando".

### Faixa C — ganho real, esforço maior / exige decisão do dono

**C1 — Smoke de pagamento no alpha com valor controlado.** *(impacto: muito alto · esforço: semanas)*
Um fluxo sintético que cria um pedido de valor mínimo, paga no sandbox e **compara o valor autorizado com o total do pedido**, com rollback declarado. Exige decisão do dono (mexe em dinheiro e em credencial de gateway) e é o único item desta lista que fecha o B3 de verdade.

**C2 — Paralelismo e seleção por path, preservando o check obrigatório.** *(impacto: médio · esforço: médio)*
A CI hoje roda tudo em todo PR, sem filtro — e a razão está registrada (`surfaces-gate.yml:4-8`): required check que não reporta trava o merge. A saída que preserva a regra é **matriz por path com job agregador**, o mesmo desenho que `tests-backstage` já usa para os dois shards (`runtime-gate.yml:391-411`): o agregador mantém o NOME do check obrigatório e reprova por `needs.*.result`. Assim um PR que só toca `surfaces/` não paga os 23 min de Python, e o check obrigatório continua reportando.

**C3 — Ligar `check_do_spec_drift.py` a um gatilho.** *(impacto: médio-alto · esforço: médio · exige credencial)*
Hoje é manual. O job `drift` do `Deploy Images` já tem `DO_TOKEN` e já roda `check_registry_drift.py`; o mesmo job pode rodar `check_do_spec_drift.py` antes do update. [NÃO VERIFICADO] se o token do workflow tem escopo para ler o spec vivo.

---

## 6. Perguntas abertas

1. **Qual é o conjunto real de checks obrigatórios?** [NÃO VERIFICADO] `gh api repos/:owner/:repo/branches/main/protection` devolveu **401** (`gh auth status` reporta token inválido para `pablondrina`; `gh run list/view` funciona, o endpoint de proteção não). O comentário em `runtime-gate.yml:342-350` e `docs/reference/silencio-inventario.md` falam em "21 checks obrigatórios" e tratam o NOME do job como contrato — mas não consegui confirmar a lista nem `enforce_admins`. **Procurar em:** `gh api .../protection` com token válido, ou Settings → Branches na UI.

2. **A suíte alpha do storefront é para rodar em CI ou é deliberadamente manual?** [NÃO VERIFICADO] O `alpha/README.md` diz "roda contra o ambiente online de staging", o config tem `workers: 1` e pacing de 75 s entre logins (por causa do rate limit de 5/min do OTP), e nenhum workflow a chama. Pode ser decisão (custo/rate limit) ou esquecimento — não encontrei ADR nem comentário que decida.

3. **Por que `test-shop` e `test-storefront` ficaram sem `-n auto` enquanto o backstage ganhou?** [NÃO VERIFICADO] O `Makefile:151-189` documenta longamente o caso do backstage e **não menciona** os outros dois. Não achei registro de tentativa, medição ou impedimento. A hipótese do §2.10 (uuid1) explicaria o storefront, mas **não** o shop.

4. **`packages/` ficar fora do `source` de cobertura é decisão ou herança?** [NÃO VERIFICADO] Não encontrei ADR, comentário no `pyproject.toml` nem no workflow. Afeta 2.909 testes e todo o `payman`.

5. **O `orders-isolated-capacity.yml` amarrado a `codex/orders-operational-excellence-20260910` é dívida ou intenção?** [INFERÊNCIA] Parece um laboratório que nunca foi promovido. Se for intenção, o budget de capacidade (p95 ≤ 500 ms) não tem dono; se for dívida, o caminho é mover o gatilho para `main`/`merge_group` com o mesmo cuidado de orçamento de job que o `check_workflow_budgets.py` já impõe.

6. **Existe um piso de tempo aceitável para a CI?** [NÃO ENCONTRADO] Procurei em `CLAUDE.md`, `docs/status.md`, `docs/ROADMAP.md`, `docs/plans/GO-LIVE-READINESS-PLAN.md` e nos comentários dos workflows. Há muitos orçamentos *por job* (`check_workflow_budgets.py`, `timeout-minutes`), nenhum orçamento *do gate*. Sem esse número, "a CI é lenta" não tem como virar critério.

---
## 7. Apêndice — comandos de coleta

Tudo abaixo é read-only. `ROOT` = `/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration`.

**7.1 Contagem de testes** (o CLAUDE.md manda usar `PYTHONPATH` explícito na worktree)

```bash
cd "$ROOT"
PY=/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python
PKGS=buyman:cashman:craftsman:doorman:fiscalman:guestman:offerman:orderman:payman:refs:stockman:utils
P="$ROOT"; for p in ${PKGS//:/ }; do P="$P:$ROOT/packages/$p"; done
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$P"

$PY -m pytest shopman/shop/tests       -q --collect-only -p no:cacheprovider  # 10508 (+31 deselected)
$PY -m pytest shopman/storefront/tests -q --collect-only -p no:cacheprovider  # 2219
$PY -m pytest shopman/backstage/tests  -q --collect-only -p no:cacheprovider  # 7239
for p in ${PKGS//:/ }; do (cd packages/$p && $PY -m pytest -q --collect-only -p no:cacheprovider); done
$PY -m pytest tools/pos-counter-agent  -q --collect-only -p no:cacheprovider  # 170
```

**7.2 Tempo de CI por job (medido, merge_group, sucesso)**

```bash
gh run list --workflow=runtime-gate.yml --event=merge_group --status=success --limit 4 \
  --json databaseId --jq '.[].databaseId' \
| while read r; do gh run view "$r" --json createdAt,updatedAt,jobs; done
# Redução usada: diferença entre completedAt e startedAt por job, ordenada desc.
```

**7.3 Inventário do silêncio (escopo repositório inteiro)**

```bash
cd "$ROOT" && python3 scripts/check_silent_swallow.py --all --json > /tmp/sw.json
# 6 arquivos, 10 sites em f0ffd02fd (exit=1)
```

**7.4 Budgets de query**

```bash
grep -rn "assertNumQueries" --include=*.py . | wc -l                          # 0
grep -rl "django_assert_num_queries" --include=*.py shopman packages | wc -l  # 15 arquivos / 24 usos
```

**7.5 Contratos gerados e quem os confere**

```bash
grep -rn "OUTPUT_RELATIVE_PATH" shopman/*/management/commands/export_*.py
grep -rln "app/generated" --include=*.py shopman/          # testes de drift
grep -rn "export_marketing_client" .github/workflows/*.yml Makefile
```

**7.6 Heurística das chaves não nomeadas (§2.7 B1 e B4)**

```python
import re, pathlib
root = pathlib.Path('.')
keys = set(re.findall(r'^\s{2}([a-z_][a-z0-9_]*)\??:',
                      (root/'surfaces/pos-nuxt/app/types/pos.ts').read_text(), re.M))
corpus = '\n'.join(p.read_text(errors='ignore') for p in
                   list(root.glob('shopman/backstage/tests/*.py')) + list(root.glob('shopman/shop/tests/*.py')))
never = [k for k in keys if ('"' + k + '"') not in corpus and ('.' + k) not in corpus]
# pos.ts: 345 chaves, 74 nunca nomeadas
# shopman.ts (storefront, contra storefront+shop tests): 672 chaves, 263 nunca nomeadas
```

**Limite do método:** é busca de literal. Um teste que compare a dataclass inteira (`asdict()`, `__dict__`) escapa da contagem, e o número do storefront é inflado por campos de copy/CTA — que também são contrato, mas de risco menor. O número serve para dimensionar a lacuna estrutural do §2.4, não para afirmar "esta chave está sem teste".

**7.7 O que eu procurei e NÃO encontrei**

- Nenhum workflow invoca `surfaces/storefront-nuxt/tests/e2e/alpha/specs/` nem o `npm run test:e2e` de storefront/pos/kds/orders/hub (`grep -rn "alpha/specs\|playwright.config\|test:e2e" .github/workflows/*.yml`).
- Nenhum `paths:` filter nos workflows de gate (só `orders-isolated-capacity.yml` e `deploy-images.yml` usam).
- Nenhum `assertNumQueries`.
- Nenhum budget de queries ou latência em `cart`/`checkout`/`pos`/`order_tracking`/`payment`.
- Nenhum ADR decidindo `source = ["shopman"]`, a ausência de `-n auto` em `test-shop`, ou o caráter manual da suíte alpha.
- Nenhum `services:` (Postgres/Redis) nos jobs da matriz `tests` do `runtime-gate.yml`.
- Branch protection e `DO_TOKEN`: não acessíveis desta sessão (401 / exige credencial).

---

## 8. Os três entregáveis, em uma linha cada

**(1) Mapa do que está coberto.** 23.045 testes (10.508 shop · 7.239 backstage · 2.219 storefront · 2.909 core · 170 agente do balcão) + 484 arquivos Nuxt. Tudo roda em todo PR, sem filtro de path, com 75% de piso de cobertura sobre `shopman/`. Pagamento, webhook, caixa, comanda, fiscal, IDOR, corrida pós-Postgres e vocabulário de tela estão densamente cobertos; catálogo, PDP, site, orders, KDS, produção e BI têm contrato BE↔FE com artefato único.

**(2) Buracos concretos, por risco de dinheiro/operador.** L1 contrato do PDV manual · L2 nenhum browser vende no PDV · L3 suíte alpha fora da CI · L4 carrinho/checkout fora dos snapshots · L5 smoke pós-deploy sem dinheiro · L6 nenhum budget de queries no caminho do dinheiro · L7 `packages/` fora da cobertura · L8 `test-shop` serial define o relógio da CI.

**(3) Camada de proteção que NÃO deixa a CI mais lenta.** A1 (`-n auto`, que **encurta** 8–16 min) · A2 (gates baratos no `make test`; `ruff check .`) · A4 (números canônicos) · B6 (`make contracts-check` no job `Quality` que já existe) · B4 (`django_assert_num_queries` dentro de testes que já rodam — custo zero) · B5 (segundo relatório de cobertura, sem novo job pesado) · A3 (asserção de contrato no `alpha-smoke` — pós-deploy, não paga PR) · C2 (matriz por path **com agregador**, preservando o nome do check obrigatório).

Nada disso exige suíte nova, runner novo ou tempo de PR maior. Os dois itens que exigem decisão do dono — C1 (smoke de pagamento com valor) e a promoção do gate de capacidade (pergunta 5) — são os únicos que custam dinheiro ou credencial.
