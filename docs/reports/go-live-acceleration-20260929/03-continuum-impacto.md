# 03 — Continuum no `/menu`: o sistema ficou mais lento e instável?

**Árvore:** `.dsh-worktrees/go-live-acceleration` (origin/main = `f0ffd02fde765493d734bae93a72bb361ed28fcf`, 2026-09-29 15:36 UTC; `git status --porcelain` vazio → o conteúdo lido é o do HEAD).
**Escopo:** piloto Continuum 0.2 do snapshot estrutural do cardápio (`/menu` do storefront).
**Método:** leitura estática + `git log`/`grep`/`curl` read-only + uma medição de bancada em processo (Django test runner, sem escrever arquivo) e sondagens HTTP **de leitura** contra o host público. Nada foi editado além deste arquivo.
**Legenda:** [FATO] verificado no código/saída de comando · [INFERÊNCIA] dedução minha · [NÃO VERIFICADO] não consegui confirmar.

---

## 1. Resumo executivo

1. **PROCEDE — e a causa não é "o request extra", é a amplificação e o primeiro quadro vazio.** O endpoint estrutural, quando quente, é barato (medido ao vivo: `projection;dur=172,94 ms`, `db;dur=7,89 ms`, 1 query). O que ficou caro é o **conjunto**: dois loops de polling de 30 s por aba aberta (um deles **inédito**, o do catálogo canônico), uma reconstrução completa do cardápio a cada janela de reconciliação (medida ao vivo em **2,1 s a 3,8 s**), e um `/menu` que **é servido sem nenhum preço** — os preços só chegam depois de hidratar e de um fetch extra no cliente.
2. **[FATO] Hoje está LIGADO no site público.** O spec `.do/app.alpha-subdomains.yaml` é o app `shopman-nelson`, cujo domínio PRIMARY é `www.nelsonboulangerie.com.br` (`.do/app.alpha-subdomains.yaml:1,13-16`). Nele: `SHOPMAN_CONTINUUM_CATALOG_SNAPSHOT_ENABLED=true`, `SHOPMAN_CONTINUUM_KILL_SWITCH=false`, `NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED=true` (`:367-382`, `:906-911`). Confirmado ao vivo: o endpoint responde `200` com `content-length: 33265` em `https://api.boulangerie.com.br/...` e o HTML de `/menu` contém o payload do snapshot.
3. **[FATO] O `/menu` de produção é servido sem preço.** HTML de `https://www.nelsonboulangerie.com.br/menu` = 171.386 bytes, com **44** ocorrências de `Confirmando preço e disponibilidade` (o placeholder por card) e **zero** ocorrências de `base_price_q`. Preço/estoque/sacola dependem do fetch canônico que só acontece depois da hidratação (`surfaces/storefront-nuxt/app/pages/menu.vue:41-51`).
4. **[FATO] O polling de 30 s dobrou.** `useContinuousProjection` já tinha o poll de 30 s do snapshot (`app/composables/useContinuousProjection.ts:91-101`); o commit `02b4f1487` ("expose Continuum end to end", 28/09 13:25) **adicionou** um segundo poll de 30 s para o catálogo canônico (`app/pages/menu.vue:260-267`, chamado em `:391`). `git log -S "scheduleCanonicalRefresh"` só encontra esse commit — antes do Continuum não havia poll algum nessa página.
5. **[FATO] Reconstrução de read model é caríssima quando dispara.** Nas sondagens ao vivo, um hit real de origem que reconstruiu custou `projection;dur=3787,23 / availability;dur=2229,48 / db;dur=998,26` (ms) e outra `2092,10 / 1054,09 / 438,55`. E o read model reconstrói **antes de qualquer lock** (`shopman/storefront/continuum.py:251-260`), então requests concorrentes reconstroem em paralelo. O container `web` é **1 instância de 1 vCPU/1 GiB** e serve também `api./admin./gestor./pdv./kds./prod.` (`.do/app.alpha-subdomains.yaml:834-839`, `:106-190`).
6. **[FATO] Custo com a flag desligada não é zero:** 7 models do catálogo com `post_save`/`post_delete` + 1 `m2m_changed` chamando `transaction.on_commit(mark_catalog_structure_dirty)` — **um UPDATE por escrita de catálogo**, sempre (`shopman/storefront/apps.py:54-78`); e a instrumentação `capture_catalog_timing` instala um `connection.execute_wrapper` em **toda** request de menu/catálogo, sem flag (`shopman/storefront/observability.py:50-67`, introduzida em `0863be932`).
7. **Veredito curto:** [FATO] o caminho de request ficou estritamente mais pesado e o primeiro quadro perdeu conteúdo; [INFERÊNCIA] a "instabilidade" relatada casa com três mecanismos concretos — dois polls sem backoff por aba, reconstruções de 2-4 s no caminho de um container compartilhado com toda a suíte de operador, e um `/menu` que renderiza sem preço até o cliente buscar. **Não há evidência de que o Continuum esteja errado em repouso; há evidência clara de que ele está caro em movimento.**
8. **⚠️ Correção de atribuição (ver Adendo, medições ao vivo de 29/09 16:20-17:42 UTC):** o Continuum **não** explica a latência por requisição do storefront (o `menu/` ao vivo leva 2,55-2,67 s de TTFB com `shadow;dur=0.00`, e o bloco dominante é a régua canônica de disponibilidade, que precede o piloto). O que ele explica é a **carga** (duas projeções canônicas de ~2,35 s por minuto por aba aberta) e o **primeiro quadro sem preço**. O item 7 acima continua válido para esses dois; leia o Adendo antes de concluir causalidade sobre os 2,5-4,4 s.

---

## Adendo — evidência ao vivo de 29/09 (16:20–17:42 UTC): correção de atribuição

Este adendo corrige e qualifica o resumo acima. Ele é posterior à redação do corpo do relatório e usa (a) a bateria de medições de TTFB contra produção e (b) uma re-medição minha em 29/09 17:41–17:42 UTC.

### Ad-1 — O que `shadow;dur=0.00` PROVA e o que NÃO prova [FATO]

**Prova:** que o estágio `shadow` não acumulou tempo nessas requisições. É consistente com `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED='false'` (`.do/app.alpha-subdomains.yaml:367-370`, desligado desde `bf6e60843`, 28/09 13:31) e com o bloco que só existe sob a flag (`shopman/storefront/api/surface.py:477-485`).

**Não prova — e é o ponto importante:** o campo é **incondicional**. `CatalogTiming.server_timing()` sempre emite os cinco nomes, com `.get(name, 0.0)` (`shopman/storefront/observability.py:26-33`):

```python
names = ["projection", "availability", "personalization", "shadow", "db"]
return ", ".join(f"{name};dur={self.durations_ms.get(name, 0.0):.2f}" for name in names)
```

Experimento que fecha a questão (bancada, 29/09): trocando `capture_catalog_timing` por um no-op — de modo que **nenhum estágio roda** — o header continua saindo `projection;dur=0.00, availability;dur=0.00, personalization;dur=0.00, **shadow;dur=0.00**, db;dur=0.00`. Ou seja: `shadow;dur=0.00` aparece mesmo quando absolutamente nada foi medido. **Ele é constante de formato, não evidência sobre a flag.**

`shadow;dur=0.00` **não** prova, e não pode ser citado como prova de, que:
- o Continuum está desligado (não está — ver Ad-3);
- o endpoint estrutural está desligado (está ligado: `200`, `content-length: 33265`, `continuum-sequence: 00000000000000000001`, medido por mim às 17:41 UTC);
- o consumidor Nuxt está desligado (está ligado: o HTML de `/menu` contém o payload do snapshot — 2 ocorrências de `storefront-menu-continuum-v0.2` às 17:41);
- os dois polls de 30 s por aba sumiram (continuam no código — `menu.vue:260-267`, `useContinuousProjection.ts:91-101` — e a flag que os liga é `true`);
- as reconstruções de 2-4 s do snapshot não estão competindo por CPU com o caminho canônico (elas acontecem, só não dentro *desta* requisição);
- **e sobretudo: nada sobre os 2,35 s de `projection` do `menu/`.** O shadow nunca foi mais que 1 query + uma comparação de digest; desligá-lo remove ~14-30 ms (medido na 2ª amostra do piloto), não 2,3 s.

### Ad-2 — O Continuum NÃO explica a latência por requisição do storefront [FATO]

Re-medição minha, 29/09 17:42 UTC, `GET /api/v1/storefront/menu/` (sem cookie, sem query; `cf-cache-status: BYPASS` → hit real no Django):

| Amostra | TTFB | Body |
|---|---:|---:|
| 1 | 2,602 s | 136.706 B |
| 2 | 2,552 s | 136.706 B |
| 3 | 2,667 s | 136.706 B |

`server-timing: projection;dur=2349.70, availability;dur=1436.90, personalization;dur=29.75, shadow;dur=0.00, db;dur=526.86`

Quatro provas de que esse tempo **não** vem do Continuum:

1. **O commit do Continuum na projeção canônica só acrescentou cronômetros.** `git show 0863be932 -- shopman/storefront/presentation/catalog.py`: envolve em `catalog_stage("personalization")` chamadas que **já existiam** (`OmotenashiContext.from_request`, `session_pricing_hints`, `customer_pricing_hints`, `_cart_qty_by_sku`, `_favorite_skus`, `notify_subscribed_skus`, `_session_key`, `_active_food_prefs` — estas quatro últimas apenas **hoisted** de dentro da chamada de `_build_items`), e envolve `_availability_states` em `catalog_stage("availability")`. Nenhuma query, nenhum cálculo novo no caminho canônico.
2. **A instrumentação do Continuum só existe em duas views.** `grep capture_catalog_timing` → `shopman/storefront/api/surface.py:459` (menu/catálogo) e `shopman/storefront/api/continuum.py:102` (endpoint estrutural). A home **não** tem nenhuma: medido em bancada, `GET /api/v1/storefront/home/` volta **sem** header `Server-Timing`. E a home regrediu de 1,03-1,88 s (17/09) para 3,24-3,51 s — porque a home chama o **mesmo** `build_catalog` (`shopman/storefront/presentation/home.py:379`).
3. **O custo da instrumentação é medido e é de milissegundos.** Bancada, menu canônico, 5 amostras, com e sem `capture_catalog_timing`/`log_catalog_observation`: com instrumentação 18,9-36,0 ms; sem, 12,8-23,7 ms → **~5-12 ms por request** no seed (24 queries), ~0,2-0,5 ms por query do `execute_wrapper`. Contra 2.349 ms de `projection` ao vivo, é ~0,5%. [INFERÊNCIA] escala para algo entre 20 e 50 ms num cardápio com ~96 queries — ainda irrelevante para 2,3 s.
4. **O bloco dominante é canônico.** `availability` responde por **61%** do `projection` (1.436,90 de 2.349,70 ms) e é a régua de disponibilidade do cardápio (`presentation/catalog.py:457-464` → `catalog_context.availability_for_skus` → `stockman.services.availability.availability_for_skus` + `waitlist.next_batch_availability_for_skus`), trabalho que **precede** o Continuum. O Continuum é o que fez esse número **aparecer** (antes de 28/09 ninguém media estágio nenhum), não o que o produziu.

**Sobre a contribuição do banco:** o `menu/` emite ~30 queries (bancada, catálogo de 1 SKU — o custo é quase fixo, não por item) e `db;dur=526,86 ms` ao vivo → ~17 ms por query. [INFERÊNCIA] boa parte dos 527 ms é latência de ida-e-volta por query, não SQL pesado — o que torna "menos queries" uma alavanca real, mas ainda assim 0,5 s de 2,35 s.

### Ad-3 — Confirmação das flags (29/09 17:41 UTC) [FATO]

| Ambiente | O que é | Flags | Prova |
|---|---|---|---|
| **Vivo (alpha)** — app `shopman-nelson`, serve `www.nelsonboulangerie.com.br`, `api.`, `admin.`, `gestor.`, `pdv.`, `kds.`, `prod.`… | o único ambiente em execução | `SHADOW=false`, **`SNAPSHOT=true`**, `KILL_SWITCH=false`, `RECONCILE=300000`, **`NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED=true`** | spec `.do/app.alpha-subdomains.yaml:1,13-63,367-382,906-911` + `curl` 17:41: endpoint `200`/`33265 B`/`sequence 1`; HTML de `/menu` `171.387 B` com 2 marcadores do payload, **44** placeholders de preço e **0** `base_price_q` |
| **Produção** — `.do/app.subdomains.yaml` | **blueprint; não existe app** | as quatro flags Django são `"false"` e o consumidor Nuxt é `"false"` | `docs/runbooks/conferir-spec-digitalocean.md:158-163`: *"Não existe app de produção na DigitalOcean, então **não há drift a medir** ali: o arquivo é blueprint, com `STORE_DOMAIN` no lugar do domínio real, e `make deploy-spec-drift spec=.do/app.subdomains.yaml` não tem app vivo contra o que comparar"*; domínios placeholder em `.do/app.subdomains.yaml:54-95`; flags em `:367-384,700-705` |

Ou seja: **"está desligado em produção" é uma afirmação vazia hoje** — não há produção. O que existe é o alpha servindo os domínios públicos, com o piloto ligado de ponta a ponta. (`docs/runbooks/backup-e-restore.md:32-33` lista um cluster `shopman-headless-postgres` como "Produção", o que indica um banco provisionado; **não** encontrei app de produção — [NÃO VERIFICADO] se esse cluster está em uso.)

### Ad-4 — Veredito corrigido

| Pergunta | Resposta |
|---|---|
| O Continuum explica a **latência por requisição** do storefront (2,5-4,4 s no `menu/`, 3,2-3,5 s na `home/`)? | **NÃO** [FATO]. O código do Continuum não roda nessas requisições além dos cronômetros (Ad-2.1-2.3), a home regrediu sem nenhuma instrumentação (Ad-2.2), e o bloco dominante é a régua canônica de disponibilidade (Ad-2.4), que precede o piloto. |
| O Continuum explica a **carga** sobre o storefront? | **SIM, parcialmente** [FATO + INFERÊNCIA]. Cada aba aberta em `/menu` passou a pedir **duas** projeções canônicas por minuto (`menu.vue:260-267`), e cada uma custa ~2,35 s de CPU ao vivo → **~4,7 s de CPU por minuto por aba ≈ 7,7% do container** (1 vCPU, `.do/app.alpha-subdomains.yaml:834-839`), que também serve `api./admin.` e todos os hosts de operador. Antes do Continuum a mesma projeção era pedida **uma vez por visualização**. [INFERÊNCIA] ~12 abas simultâneas saturam o container — e esse é o cenário que produz "lento e instável" sem aparecer em nenhuma medição de requisição isolada. Somam-se as reconstruções de 2-4 s do endpoint estrutural no mesmo container. |
| O Continuum explica o que o **cliente vê**? | **SIM** [FATO]. Primeiro quadro sem preço (44 placeholders, 0 `base_price_q`, medido às 17:41) + 2 fetches recorrentes por aba sem backoff. Determinístico e atribuível ao piloto. |
| `shadow;dur=0.00` prova alguma coisa sobre as flags? | **NÃO** [FATO]. É campo incondicional do formatador (Ad-1). |

**O que falta medir para fechar a causa da regressão 17/09 → 29/09** (não é o Continuum, e não sei ainda o que é): perfil por SKU dentro de `_availability_states` com o cardápio real — separar `listing_sellable_map`, `availability_for_skus` (stockman), `bundle_availability_for_skus` e `waitlist.next_batch_availability_for_skus`. Candidato datado e concreto: `68d3b3209` (24/09 21:37, *"A caixa física é estoque limitado e restringe a venda do kit"*), que **devolveu a embalagem à expansão do kit** (`shopman/shop/adapters/catalog.py`, `expand_bundle` deixa de filtrar `metadata__kit_packaging`), passou `as_component=True` por componente (`shopman/shop/services/availability.py`) e faz `_check_bundle` chamar `check()` **por componente** — [INFERÊNCIA] um N+1 por kit, entrado **depois** do baseline de 17/09. Não medi; é hipótese com data, arquivo e linha, não conclusão.

---

## 2. Achados

### A1 — O que o Continuum ADICIONA ao caminho de request do `/menu` [FATO]

**Antes** (`git show 02b4f1487 -- surfaces/storefront-nuxt/app/pages/menu.vue`): SSR fazia `GET /api/v1/storefront/menu/` (catálogo + sacola + preço) e a página nascia completa. Nenhum poll.

**Depois** (com `continuumEnabled`), por **visita** a `/menu`:

| # | Request | Quem dispara | Evidência |
|---|---|---|---|
| 1 | SSR: `GET /api/v1/storefront/continuum/v0.2/catalog-structure/` (via BFF Nitro) | `await useContinuousProjection` | `menu.vue:28-37`; `useContinuousProjection.ts:28-39` |
| 2 | BFF → Django, hop de rede público (`https://api.boulangerie.com.br`) | `proxyPublicContinuumCatalog` | `server/utils/continuumSnapshot.ts:48-56`; `.do/app.alpha-subdomains.yaml:895-900` |
| 3 | Cliente: `GET /api/v1/storefront/catalog/` (canônico, preço/estoque) | hidratação, porque o SSR não trouxe preço | `menu.vue:41-51` |
| 4 | **Poll de 30 s do snapshot** | `useContinuousProjection` timer | `useContinuousProjection.ts:91-101` |
| 5 | **Poll de 30 s do catálogo canônico** ← inédito | `scheduleCanonicalRefresh` | `menu.vue:260-267, 391` |

Portanto, por aba aberta no `/menu`: **4 requests/minuto recorrentes** (2 tipos × 2/min) que não existiam antes, mais 1 request por visita. O SSR continua fazendo 1 fetch (o snapshot **substitui** o `/menu/`), mas a página **deixa de nascer com preço**.

**Impacto:** volume recorrente proporcional a abas abertas × tempo de permanência — justamente o comportamento de quem está montando um pedido no celular.
**Confiança:** [FATO].

---

### A2 — Custo por request, medido (bancada + produção) [FATO]

Bancada: `DJANGO_SETTINGS_MODULE=config.settings_test DATABASE_URL='' PYTHONPATH=<worktree + packages/*>` com o `.venv` da raiz, runner do Django e `_seed_surface` (seed de teste, cardápio pequeno). Comando reproduzível no fim da seção.

| Cenário | Queries | Tempo (ms) | Bytes |
|---|---:|---:|---:|
| snapshot quente (head fresca + cache hit) | **1** | 1,0 | 1.938 |
| snapshot frio (primeira materialização) | 37 | 575,5 | 1.938 |
| snapshot com reconciliação vencida | 29 | 8,7 | 1.938 |
| snapshot com `reconcile_after_ms=0` (default antigo) | 29-33 | ~9 | 1.938 |
| catálogo canônico (`/catalog/`) | 24 | 10,4 | 2.104 |
| menu canônico (`/menu/`, com sacola) | 24 | 8,4 | 3.639 |
| menu canônico com shadow ligado | 25 | 8,9 | 3.639 |
| snapshot com kill switch | 0 (`404`) | 1,5 | 42 |
| menu canônico com kill switch | 24 | 8,3 | 3.639 |
| snapshot com `Cookie` presente | 0 (`400`) | — | 76 |

Produção (sondagens `curl` de leitura; headers reais):

| Observação | Valor ao vivo |
|---|---|
| Hit de origem que reconstruiu (17:07:5x) | `projection;dur=3787,23, availability;dur=2229,48, personalization;dur=9,10, shadow;dur=0,00, db;dur=998,26`, `continuum-age-ms: 38` |
| Outro hit de origem que reconstruiu | `projection;dur=2092,10, availability;dur=1054,09, db;dur=438,55`, `continuum-age-ms: 34` |
| Hit de origem **quente** (17:18:47, head com 144 s) | `projection;dur=172,94, availability;dur=0,00, db;dur=7,89`, `continuum-age-ms: 144250` |
| Corpo | `content-length: 33265` bytes, `etag: "sha256-Ttu6GbM8a7MjNSL4olq0hJuOb5l2Tivy9RGdBu9af50"`, `continuum-sequence: 00000000000000000001`, `continuum-epoch: e_32d4af6638324004bf50786e9940f77b` |
| `/menu` (HTML) | `status=200 bytes=171386 ttfb=0,732 s total=0,835 s` |

Leituras: (a) o caminho quente é barato em queries, mas **não** em CPU — 173 ms de `projection` com `db` de 7,89 ms aponta para o custo de CPU do caminho quente: `validate_message_limits` faz uma **caminhada recursiva em Python por todo o JSON** (`continuum.py:298-326`), sobre uma mensagem de 33 KB; (b) o caminho que reconstrói custa **2 a 4 segundos** de servidor, com 0,4-1,0 s só de banco; (c) a escala do cardápio real é ~4× o seed de teste (o próprio código comenta "96-query catalog rebuild", `continuum.py:196`) — logo a bancada **subestima** proporcionalmente.

Comando da bancada (sem criar arquivo; via `stdin`):
```bash
cd <worktree> && PYTHONPATH="<worktree>:<worktree>/packages/*" \
  DJANGO_SETTINGS_MODULE=config.settings_test DATABASE_URL='' \
  /Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python - <<'PY'
# django.setup() -> setup_test_environment() -> get_runner(settings).setup_databases()
# _seed_surface(); CaptureQueriesContext em GET do snapshot e do catálogo, por cenário
PY
```

**Confiança:** [FATO] para todos os números (as sondagens de produção foram GET, sem cookie, sem query string, em número pequeno).

---

### A3 — Reconstrução de read model: quando dispara e onde [FATO]

- `current_or_build_head` lê a cabeça (1 query); se `dirty` **ou** `reconciliation_due`, chama `build_catalog` (a projeção canônica inteira) — `shopman/storefront/continuum.py:251-260`.
- `reconciliation_due` = `verified_at is None or configured <= 0 or head_age_ms >= configured` — `continuum.py:183-199`. No spec atual, `SHOPMAN_CONTINUUM_RECONCILE_AFTER_MS=300000` (`.do/app.alpha-subdomains.yaml:379-382`).
- O sinal de catálogo só marca `dirty=True` por `transaction.on_commit`, e é "caminho rápido, não fronteira de durabilidade" (`continuum.py:289-295`; `apps.py:39-78`).
- `materialize_catalog_structure` só pega o lock **depois** de construir: `with transaction.atomic(): CatalogStructureHead.objects.select_for_update().get_or_create(...)` — `continuum.py:224-248`. A construção (`build_catalog`) acontece **fora** do lock, em `continuum.py:258`.
- Medição ao vivo: o limiar efetivo em produção é **> 144 s** (um hit de origem com `continuum-age-ms: 144250` **não** reconstruiu). Isso é compatível com os 300000 ms do spec — ou seja, **a correção `8e8328c62` (30 s → 300 s) está no ar**.
- Mesmo assim, duas reconstruções de 2-4 s foram observadas em ~10 minutos porque o endpoint só recebe hit de origem esporadicamente (o Cloudflare absorve o resto — ver A8) e **cada hit de origem depois da janela reconstrói**.

**Impacto:** o custo não é por request, é por *janela*: picos de 2-4 s de CPU no container que também serve toda a suíte de operador. Como não há lock antes da construção, N requests concorrentes no mesmo instante reconstroem N vezes ([INFERÊNCIA] o Cloudflare amortiza parte disso hoje; sem ele, ou com `Accept` variando, o herd chega inteiro no Django).
**Confiança:** [FATO] para o mecanismo e para os tempos; [INFERÊNCIA] para a magnitude do herd.

---

### A4 — Polling de 30 s com jitter: existem DOIS loops, e um deles é novo [FATO]

- Snapshot: `setTimeout(pollMs * (0.9 + Math.random() * 0.2))`, mínimo 5.000 ms, `pollMs: 30_000` (`useContinuousProjection.ts:92-101`; `menu.vue:35`). Só refaz o fetch se `document.visibilityState === 'visible'`; `visibilitychange` também dispara um refresh (`:102-105`).
- Canônico: `scheduleCanonicalRefresh()` com o **mesmo** jitter de ±10 % sobre 30 s, só quando `continuumEnabled`, agendado no `onMounted` (`menu.vue:260-267, 391`). `refreshCanonical` é `useFetch` em `/api/v1/storefront/catalog/` com `credentials: 'include'` (`menu.vue:47-51`) — ou seja, **leva sessão do cliente e roda a projeção canônica inteira** (24 queries no seed; mais em sessão logada com favoritos/contexto de preço).
- **Nenhum dos dois tem backoff, teto de tentativas ou desligamento por erro**: se o endpoint cair, o poll continua indefinidamente a cada 30 s.
- O jitter de ±10 % sobre uma grade de 30 s é pequeno (30 s ±3 s): as abas de uma rede de celulares sincronizadas pelo mesmo carregamento tendem a coincidir — o que importa exatamente no instante da reconciliação (A3).

**Impacto:** [FATO] +2 requests/30 s por aba; [INFERÊNCIA] é o componente que mais escala com uso real e o melhor candidato a "parece mais lento depois das atualizações".
**Confiança:** [FATO] para o código; [INFERÊNCIA] para o efeito agregado.

---

### A5 — Estado ATUAL das flags, por ambiente, e onde isso é provado [FATO]

**Ambiente vivo (é este que serve a loja):** `.do/app.alpha-subdomains.yaml` — `name: shopman-nelson` (`:1`), domínios `www.nelsonboulangerie.com.br` (PRIMARY), `nelsonboulangerie.com.br`, `boulangerie.com.br`, `api.`, `admin.`, `gestor.`, `pdv.`, `kds.`, `prod.`, `compras.`, `central.`, `mkt.`, `bi.`, `backup.` (`:13-63`); `SHOPMAN_ENVIRONMENT=staging` (`:359-362`).

| Variável | Valor no spec | Linha |
|---|---|---|
| `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED` | `'false'` | `:367-370` |
| `SHOPMAN_CONTINUUM_CATALOG_SNAPSHOT_ENABLED` | **`'true'`** | `:371-374` |
| `SHOPMAN_CONTINUUM_KILL_SWITCH` | `'false'` | `:375-378` |
| `SHOPMAN_CONTINUUM_RECONCILE_AFTER_MS` | `'300000'` | `:379-382` |
| `NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED` (storefront-nuxt) | **`'true'`** | `:906-911` |

**Prova independente de que está ligado:** `curl -D-` em `https://api.boulangerie.com.br/api/v1/storefront/continuum/v0.2/catalog-structure/` devolve `HTTP/2 200`, `content-length: 33265`, `continuum-stream: s_shopman_storefront_catalog_structure_v1`; e o HTML de `/menu` contém `storefront-menu-continuum-v0.2` (2×) e `continuum.projection.snapshot.v0.2` (1×). Sem as flags ligadas, o endpoint devolveria `404` (`shopman/storefront/api/continuum.py:90-91`) e a página não teria o payload.

**Template de produção (não é um deployment):** `.do/app.subdomains.yaml` — `name: shopman-headless`, domínios com placeholder `STORE_DOMAIN` (`:47-95`), `SHOPMAN_ENVIRONMENT=production` (`:363-366`). Nele as quatro flags Django são `"false"` e o `NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED` é `"false"` (`:367-384`, `:700-705`). **Ou seja: "produção está desligada" é verdade sobre o template, e não sobre o site que o dono usa.** Essa é a confusão mais perigosa deste relatório: o ambiente chamado "Live de teste" no relatório do piloto atende o domínio público.

**Default do código:** tudo nasce desligado — `config/settings.py:164-193`; `continue` no consumidor: `surfaces/storefront-nuxt/nuxt.config.ts:47-51` (`continuumCatalogEnabled: false`).

**Confiança:** [FATO].

---

### A6 — Custo que sobrevive com a flag DESLIGADA (e com o kill switch armado) [FATO]

| Item | Existe? | Evidência | Custo |
|---|---|---|---|
| Import do módulo | sim | `shopman/storefront/api/surface.py:27` importa `compare_shadow, head_age_ms, shadow_enabled` no topo; `continuum.py:19` importa o model | irrelevante |
| Tabela nova | sim | `shopman/storefront/migrations/0011_catalog_structure_head.py`; model em `shopman/storefront/models/continuum.py:14-39` | 1 linha; nenhuma leitura quando desligado (`continuum.py:43-50`) |
| **Signals de escrita** | **sim, sempre** | `apps.py:54-78`: `Product, Listing, ListingItem, Collection, CollectionItem, AttributeDefinition, OmotenashiCopy` × (`post_save`, `post_delete`) + `Product.keywords.through` → `transaction.on_commit(mark_catalog_structure_dirty, robust=True)`; o handler faz `UPDATE ... SET dirty=true` (`continuum.py:289-295`) | **1 UPDATE extra por escrita de catálogo**, com ou sem flag. Em `seed`/import de catálogo isso é uma amplificação proporcional ao número de escritas. [INFERÊNCIA] em produção orgânica o custo é desprezível (edições raras) |
| **Instrumentação por request** | **sim, sempre** | `surface.py:459`/`:495-513` e `api/continuum.py:102-144` chamam `capture_catalog_timing`/`log_catalog_observation`; `observability.py:50-67` instala `connection.execute_wrapper` | 1 callback Python por **query** da request + 1 linha INFO por request de menu/catálogo. [INFERÊNCIA] ~microssegundos por query (baixo), mas é código novo no caminho quente que **não obedece a flag nenhuma** — `observability.py` nasceu em `0863be932` (28/09 06:35), junto com o Continuum |
| Cron / comando / worker | **não** | `grep -rn continuum shopman/` não acha management command; o único script é `scripts/evaluate_continuum_shadow.py` (avaliador de log, roda sob demanda) | zero |
| Middleware / auth | **não** | o endpoint é `View` cru, `http_method_names=["get","head"]`, sem sessão (`api/continuum.py:84-91`) | zero |
| Shadow | não (desligado) | `surface.py:477` `if collection is None and shadow_enabled()` | zero — mas note: **sem a flag, a request paga o dict inteiro de `log_catalog_observation` mesmo assim** (`:495-513`) |

**Confiança:** [FATO] para a existência e o gatilho; [INFERÊNCIA] para a magnitude relativa.

---

### A7 — O `/menu` SSR perdeu o preço: o custo maior é de percepção [FATO]

- `canonicalOnServer = import.meta.server && (!continuumEnabled || !structureCatalog.value)` (`menu.vue:41`): com o snapshot utilizável, o SSR **não** busca o canônico.
- `catalogFromStructureSnapshot` materializa os itens com `base_price_q: 0`, `price_display: ''`, `availability: 'available'`, `can_add_to_cart: false` (`app/presentation/continuumCatalog.ts:73-93`).
- O card mostra um placeholder no lugar do preço (`app/components/ProductListItem.vue:46`) e a página mostra o alerta "Confirmando o cardápio" (`menu.vue:556-566`, com o botão "Tentar de novo" em `:563`).
- **Medido no HTML de produção:** 44 placeholders, 1 alerta, **0** `base_price_q` — o HTML público do cardápio não contém preço algum.
- Também entra no payload SSR o objeto do snapshot inteiro (o comentário em `useContinuousProjection.ts:23-25` assume isso); o corpo real tem 33.265 bytes → [INFERÊNCIA] ~33 KB a mais no HTML de `/menu` (total medido: 171 KB).

**Impacto:** o servidor responde no mesmo tempo (TTFB 0,73 s medido), mas o **conteúdo útil** chega um roundtrip inteiro depois da hidratação. Para o dono, isso é "o site ficou mais lento" sem nenhuma regressão de TTFB. Além disso, qualquer falha do fetch canônico deixa o cardápio **sem preço nenhum**, com um botão "Tentar de novo" (`menu.vue:547, 563`) — leitura direta de "instável".
**Confiança:** [FATO] para o HTML e o código; [INFERÊNCIA] para o efeito percebido.

---

### A8 — Cloudflare na frente do endpoint: cache de borda com `age` congelado [FATO]

Headers ao vivo: `cache-control: public, max-age=30, s-maxage=30, stale-if-error=120, stale-while-revalidate=120`, `vary: Accept`, `server: cloudflare`; `cf-cache-status` observado como `HIT`, `REVALIDATED`, `UPDATING` e `MISS`. O endpoint **é cacheado na borda**:

1. **A favor:** absorve a maior parte do polling do cliente antes de chegar ao Django (foi por isso que hits de origem foram raros nas sondagens). [INFERÊNCIA] sem isso o herd de A3/A4 chegaria inteiro.
2. **Contra:** o corpo cacheado carrega o `continuum-age-ms` do momento da geração e é servido com ele por até `stale-while-revalidate`. Vi três leituras idênticas (`age-ms: 54`, `projection;dur=3145,63`) com `cf-cache-status: HIT/UPDATING` e `age: 119`. Como o cliente calcula frescor por `elapsed = clock - validated_at + age_ms` (`useContinuousProjection.ts:85-88`), **ele pode acreditar que está fresco quando o dado de borda tem minutos de idade** — [INFERÊNCIA] a estrutura do cardápio pode ficar velha na tela sem que nada sinalize.
3. `Vary: Accept` é o **único** eixo de variação, por desenho (o endpoint recusa credenciais — A10), o que é correto para um recurso público.

**Confiança:** [FATO] para os headers; [INFERÊNCIA] para a consequência de frescor.

---

### A9 — Vetores concretos de instabilidade [FATO] + [INFERÊNCIA]

| Vetor | Mecanismo (código) | Leitura |
|---|---|---|
| **Fallback** | `menu.vue:41` volta ao canônico no SSR quando não há snapshot; `useContinuousProjection.ts:51-53` lança `continuum_snapshot_<status>` | [FATO] o fallback é real e o menu continua de pé. [INFERÊNCIA] ele **custa** o request jogado fora por página quando as flags divergem (A-risk abaixo) |
| **Divergência de flag entre Django e Nuxt** | `candidate_enabled()` (`continuum.py:43-45`) e `continuumCatalogEnabled` (`continuumSnapshot.ts:29-33`) são **independentes**; o kill switch só fecha o lado Django | [INFERÊNCIA] com kill switch armado e flag Nuxt ligada, o consumidor segue buscando um endpoint `404` a cada 30 s por aba, para sempre; SSR gasta um request e cai no canônico |
| **Equivocation** | `installCatalogStructureSnapshot` lança `continuum_equivocation` quando sequência igual + token/digest diferente (`continuumCatalog.ts:54-60`) | [FATO] falha aquele refresh; `cache.value` fica a anterior. [INFERÊNCIA] sem retry/backoff, o poll continua e a tela fica na estrutura antiga |
| **Descarte de regressão** | `if (incomingSequence < previousSequence) return current` — mantém a estrutura já instalada, **sem** erro (`continuumCatalog.ts:51-53`) | [FATO] qualquer rollback de banco (prática corrente neste repo: `pg_restore` do alpha) devolve uma sequência **menor** e o cliente **descarta para sempre** a versão restaurada, no mesmo epoch |
| **Epoch só roda quando a LINHA é criada** | `epoch = models.CharField(default=new_catalog_epoch)` (`models/continuum.py:23`), sem rotação em restore | [FATO] o relatório do piloto afirma que "remover a read model simula restore/failover e gera novo epoch" — verdade só para DROP da linha, **não** para `pg_restore` (que traz a linha velha com o epoch velho). [INFERÊNCIA] um restore deixa o cardápio congelado no estado pré-restore até a sequência reultrapassar |
| **Cache em memória / payload** | snapshot inteiro serializado no payload SSR (`useContinuousProjection.ts:23-25`); `cache.value` é `shallowRef` por instância | [FATO] +33 KB no HTML de `/menu` |
| **Sem timeout nos fetches** | `$fetch.raw` sem `timeout` (`useContinuousProjection.ts:32-39`; `continuumSnapshot.ts:48-56`) | [FATO] upstream pendurado = página presa em "Carregando o cardápio"; é o mesmo achado do relatório 05 |
| **Reconstrução sem lock** | `continuum.py:251-260` (constrói antes do `select_for_update` de `:225`) | [INFERÊNCIA] herd de reconstruções concorrentes de 2-4 s no mesmo container |
| **Erro do shadow** | `except Exception` engole e loga (`surface.py:486-489`) | [FATO] shadow não derruba o canônico (e hoje está desligado) |

---

### A10 — O endpoint recusa Cookie e query string [FATO]

`_has_credentials`: `Cookie`, `Authorization`, `Proxy-Authorization`, `X-SSL-Client-Cert` **ou qualquer query string** → `400` (`shopman/storefront/api/continuum.py:43-50, 96-97`; resposta `private, no-store`, `:32`). Prova ao vivo: `?probe=1` → `HTTP/2 400`, `content-length: 76`, `cf-cache-status: BYPASS`. Prova de bancada: cliente que antes visitou `/menu/` (que faz `ensure_csrf_cookie`) recebe `400` com **0 queries**.

**Impacto:** [INFERÊNCIA] é um modo de falha de um caractere de distância — qualquer proxy/CDN/consumidor que acrescente cookie ou parâmetro transforma o snapshot em `400` e o consumidor cai no fallback silenciosamente (sem alerta ao operador; só o log estruturado). Note que o Cloudflare **mascarou** isso nas sondagens com cookie (`cf-cache-status: HIT` devolveu `200` do cache, com o `Vary: Accept` que ignora Cookie).
**Confiança:** [FATO] para a regra e para as duas provas.

---

### A11 — Divergências de documentação/código que já custaram caro [FATO]

1. O relatório do piloto diz que o default de reconciliação é `30000` e "igual ao horizonte de frescor (30 s)" (`docs/reports/continuum-0.2-shopman-pilot-20260928.md:70-71, 85`), mas o código tem `300000` (`config/settings.py:175`) e o comentário logo acima ainda diz "o default acompanha fresh_for_ms" (`:172-174`). O `8e8328c62` mudou 30 s → 300 s e **não** corrigiu o comentário nem o relatório.
2. `docs/reports/...:75-76` afirma que remover a read model "simula restore/failover e gera novo epoch" — o mecanismo de epoch só roda na criação da linha (A9).
3. `docs/reports/...:206-207` justifica desligar o shadow ("elimina esse custo adicional do caminho canônico") — o que foi feito em `bf6e60843`; porém **o custo maior que o shadow introduziu não era o shadow**: era o par de polls + rebuild, que seguem ligados.

**Confiança:** [FATO].

---

### A12 — Rollout atual: quem usa e desde quando [FATO]

`git log -S`/`git show <commit>:spec` sobre `.do/app.alpha-subdomains.yaml` (todos os horários -0300):

| Momento | Commit | Shadow | Snapshot | Kill | Reconcile | Nuxt |
|---|---|---|---|---|---|---|
| 28/09 08:37 | `5715ff3cf` | false | false | false | 30000 | — |
| 28/09 09:27 | `e14bb46ba` | **true** | false | false | 30000 | — |
| 28/09 10:34 | `f4baa5fe4` (rollback por orçamento: p95 94,3 ms / 6 queries) | false | false | **true** | 30000 | — |
| 28/09 11:27 | `15a9f91a8` | **true** | false | false | 30000 | — |
| 28/09 13:11 | `2ef7dccb1` | true | **true** | false | 30000 | — |
| 28/09 13:25 | `02b4f1487` | true | true | false | 30000 | **true** |
| 28/09 13:31 | `bf6e60843` | false | true | false | 30000 | true |
| 28/09 15:31 | `8e8328c62` (perf: shell antes do catálogo) | false | true | false | **300000** | true |
| 28/09 17:56 | `d5b112e24` (perf: montar menu antes do snapshot; `lazy: true`) | false | true | false | 300000 | true |
| 29/09 15:36 | `f0ffd02fd` (HEAD) | false | true | false | 300000 | true |

- **Rollout: 100 % do `/menu` do site público**, não há coorte, percentual nem canal — a flag é por ambiente (`.do/app.alpha-subdomains.yaml:906-911`).
- **A janela mais pesada** foi 28/09 13:11 → 15:31 (reconcile de 30 s **e** shadow no caminho canônico **e** consumidor ligado): ~2h20. As duas correções de performance (`8e8328c62` 15:31, `d5b112e24` 17:56) são do mesmo dia — [INFERÊNCIA] sintoma de que a lentidão já foi sentida em 28/09 e tratada às pressas.
- O que **não** foi corrigido nessas duas correções: os dois polls de 30 s e a perda de preço no primeiro quadro.

**Confiança:** [FATO].

---

## 3. O que já existe e funciona (não reinventar)

1. **Kill switch que domina as duas flags Django** — `candidate_enabled()` e `shadow_enabled()` retornam `False` com `kill_switch=True` (`continuum.py:43-50`); o endpoint volta a `404` com **0 queries** (medido).
2. **Fallback monolítico real** — `menu.vue:41-51`: sem snapshot, o SSR volta ao catálogo canônico. Nenhum caminho do Continuum pode impedir a compra.
3. **Caminho quente barato em banco** — 1 query medido em bancada; o próprio teste do repo exige `<= 2` e menos que o menu canônico (`shopman/storefront/tests/api/test_continuum_catalog.py:332-343`).
4. **Contrato público bem fechado** — credentialless, sem sessão, `Vary: Accept`, ETag forte, `304` sem regenerar corpo, limites que falham fechado (`api/continuum.py:62-129`; `continuum.py:314-326`).
5. **Observabilidade estruturada allowlisted**, sem payload/SKU/pessoa (`observability.py:70-99`), com `Server-Timing` propagado até o BFF (`continuumSnapshot.ts:11-25`).
6. **Amostragem do shadow já cumprida e o shadow desligado** (`bf6e60843`; `.do/app.alpha-subdomains.yaml:363-366`).
7. **Avaliador de log pronto** — `scripts/evaluate_continuum_shadow.py` com thresholds (0 divergência, p95 ≤ 25 ms, p95 ≤ 2 queries).

---

## 4. Lacunas / riscos

| # | Risco | Evidência | Severidade [INFERÊNCIA] |
|---|---|---|---|
| R1 | Dois polls de 30 s sem backoff por aba, para sempre | `menu.vue:260-267`; `useContinuousProjection.ts:91-101` | **Alta** — escala com uso, sem teto |
| R2 | `/menu` nasce sem preço; um fetch a mais depois da hidratação | HTML de produção: 44 placeholders, 0 `base_price_q`; `menu.vue:41` | **Alta** — é a queixa de "lentidão" mais provável |
| R3 | Reconstrução de 2-4 s sem lock, no container compartilhado com a suíte de operador | `continuum.py:251-260`; ao vivo: `projection;dur=3787,23` | **Alta** — pico, não média; degrada também PDV/KDS/gestor |
| R4 | Duas flags independentes (Django × Nuxt) para o mesmo piloto | `continuum.py:43-50`; `continuumSnapshot.ts:29-33` | Média — rollback parcial deixa o cliente batendo em `404` |
| R5 | Epoch não roda em restore; sequência menor é descartada para sempre | `models/continuum.py:23`; `continuumCatalog.ts:51-53` | Média — cardápio congelado após `pg_restore` |
| R6 | `age_ms` congelado no cache de borda embaralha o cálculo de frescor | Headers ao vivo (`cf-cache-status: HIT/UPDATING`) | Baixa/Média |
| R7 | Caminhada recursiva de ~100k nós por request (`json_shape`) | `continuum.py:298-326`; ao vivo: 173 ms de `projection` com `db` de 7,89 ms | Média — CPU por request, mesmo no caminho quente |
| R8 | Nenhum timeout nos fetches | `useContinuousProjection.ts:32-39` | Média (mesmo achado do relatório 05) |
| R9 | Custo sem flag: 1 UPDATE por escrita de catálogo + wrapper de query em toda request | `apps.py:54-78`; `observability.py:50-67` | Baixa em repouso, Média em `seed`/import |
| R10 | Drift de documentação (30 s × 300 s; "restore gera novo epoch") | `docs/reports/continuum-0.2-shopman-pilot-20260928.md:70-71, 75-76, 85` vs `config/settings.py:175` | Baixa, mas engana o próximo agente |

---

## 5. Recomendações acionáveis (ordenadas por impacto/esforço)

1. **Matar o poll canônico de 30 s do `/menu`** (ou jogá-lo para ≥5 min e só no `visibilitychange`). `menu.vue:260-267` é ~15 linhas; remove **metade** do volume recorrente adicionado pelo Continuum. É a maior razão impacto/esforço do relatório.
2. **Devolver o preço ao primeiro quadro.** Duas opções: (a) voltar o SSR a buscar o canônico (`canonicalOnServer = true`) mantendo o snapshot como fallback; (b) manter como está e assumir explicitamente que o cardápio abre sem preço. Hoje o `performanceGuardrails` **trava** a opção (a) (`surfaces/storefront-nuxt/tests/performanceGuardrails.test.ts:21-24`), então a decisão é de produto e precisa ser medida (TTFB ≠ conteúdo útil).
3. **Serializar a reconstrução:** lock (`SELECT ... FOR UPDATE SKIP LOCKED` na cabeça **antes** de construir, ou lock Redis) e/ou mover o rebuild para um management command no worker (`maintenance_worker`), deixando o request só ler. Mata o herd de R3.
4. **Um único interruptor para o piloto:** o kill switch deveria também desligar o consumidor (ou o runbook deve mandar desligar a flag Nuxt primeiro — ver 6). Barato e elimina R4.
5. **Cadência do poll do snapshot:** 30 s + ±10 % de jitter é agressivo para um dado estrutural que, por desenho, muda raramente (a sequência está em `1` desde a criação da linha). Migrar para SSE por stream (ADR-016 já prevê push sobre fetch canônico) ou alongar para 5-15 min.
6. **Corrigir o `age` no caminho de borda** (ou aceitar e documentar): mandar o `age` recalcular exige `Vary`/no-store no `Age`; o mínimo é reconhecer no contrato que o cliente pode estar calculando frescor sobre um `age` de cache.
7. **Rotacionar epoch em restore** (comando `manage.py` ou checagem de identidade do banco) e documentar o passo "apagar a linha da cabeça" no runbook de restore.
8. **Timeout nos dois fetches** do snapshot/canônico.
9. **Fixar os 300 s no comentário e no relatório do piloto** (drift A11).
10. **Não religar o shadow em produção**: o custo medido na primeira amostra (p50 30,4 ms / p95 94,3 ms / p95 6 queries, `docs/reports/...:175-180`) é exatamente o que o dono está sentindo agora.
11. **[Adendo] Perfilar `_availability_states` com o cardápio real** — é 61 % do tempo do `menu/` (1.436,90 de 2.349,70 ms) e não tem nada a ver com o Continuum. Sem isso, a causa da regressão 17/09 → 29/09 fica em aberto. Comece por `waitlist.next_batch_availability_for_skus`, `bundle_availability_for_skus` e pelo `68d3b3209` (kit + embalagem, 24/09).
12. **[Adendo] Fazer o container deixar de ser ponto único de falha de performance:** o `web` é 1 instância de 1 vCPU servindo loja + admin + 7 hosts de operador (`.do/app.alpha-subdomains.yaml:834-839`). Enquanto isso for verdade, qualquer custo de storefront é custo de operação — e o inverso.

---

## 6. Perguntas abertas / o que não consegui verificar

1. **[NÃO VERIFICADO] Métricas de produção** — não tenho acesso a `doctl apps logs` nem ao Grafana/Sentry deste ambiente. Os números que dou de produção são **headers HTTP de uma dúzia de GETs**, não p50/p95 de tráfego real. O avaliador existe (`scripts/evaluate_continuum_shadow.py`) mas o shadow está desligado — e sem shadow não há linha `shadow_*` para avaliar. **O caminho para medir de verdade é o log estruturado `storefront_catalog_observation` de `mode=baseline`** (`observability.py:70-99`), que roda em toda request de menu.
2. **[NÃO VERIFICADO] Se o deployment em execução aplicou o spec de 15:31 (300000 ms).** O único indício é indireto: um hit de origem com `age` de 144 s **não** reconstruiu → o limiar efetivo é > 144 s. Compatível com 300 s, incompatível com 30 s. Não consigo provar o valor exato sem `doctl` ou o log.
3. **[NÃO VERIFICADO] Quantos clientes/abas usam o `/menu` simultaneamente** — sem isso não sei se o herd de R3 chega a acontecer hoje. O Cloudflare (`cf-cache-status: HIT/UPDATING`) absorve muito; **quantos hits reais de origem por minuto o `web` recebe é a pergunta que decide a severidade de R1-R3.**
4. **[NÃO VERIFICADO] Semântica exata de `lazy` no SSR do Nuxt 4** para `useAsyncData` — não há `node_modules` na worktree, então não li o framework. O que é [FATO] independente disso: o HTML de produção **contém** o payload do snapshot e **não contém** preço, o que só é consistente com o snapshot resolvido no SSR e o canônico adiado para o cliente.
5. **[NÃO VERIFICADO] Se algum outro consumidor** (marketing, B.I., app de operador) bate no endpoint estrutural — não encontrei nenhum no `grep`, mas não varri o tráfego.
6. **[INFERÊNCIA] "Instável" pode ter causas fora do Continuum.** Não investiguei aqui `8e8328c62` (que mexeu em `app.vue`, `useShopSession`, `identity.py`, `home.py` — 27 arquivos) nem os relatórios irmãos 04/05/07/08/09 desta mesma pasta. O achado de que o `web` é um único container de 1 vCPU servindo loja + admin + 7 hosts de operador vale registrar em separado: qualquer pico no storefront degrada o PDV/KDS.

---

## Veredito

**PROCEDE — o sistema ficou mais pesado depois do Continuum, e há dois culpados distintos.**

- **[FATO] Procede no caminho de request.** +2 requests/30 s por aba (um deles um poll canônico que **não existia antes**), +1 request por visita, e um endpoint novo que reconstrói o cardápio inteiro quando a janela vence — ao vivo: **2,1 s a 3,8 s** de servidor por reconstrução, num container de 1 vCPU que também serve PDV, KDS, gestor e admin.
- **[FATO] Procede no que o cliente vê.** O `/menu` público é servido com **44 placeholders de preço e nenhum preço** no HTML; o conteúdo útil chega depois da hidratação, com um fetch a mais.
- **[FATO] NÃO procede culpar "o Continuum" de forma genérica.** O endpoint quente custa 1 query e ~173 ms de CPU; o contrato é fechado, o fallback funciona e o kill switch responde `404` em 0 queries. Parado, ele é barato.
- **[INFERÊNCIA] O que produz "lento e instável" é a amplificação**: dois timers de 30 s sem backoff, uma reconstrução de 2-4 s sem lock, e um primeiro quadro vazio. Os dois commits de perf de 28/09 (`8e8328c62` 15:31 e `d5b112e24` 17:56) mostram que o time já sentiu isso naquele dia e tratou dois sintomas — os polls e o primeiro quadro continuam de pé.
- **[FATO] Rollout:** 100 % do `/menu` do site público (`www.nelsonboulangerie.com.br`), no ar desde **28/09/2026 13:25 (-0300)** (`02b4f1487`), sobre um spec cujo `SHOPMAN_ENVIRONMENT` é `staging`. Não existe coorte, percentual nem canal — é ligado ou desligado por ambiente.
