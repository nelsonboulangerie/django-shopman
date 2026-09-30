# 01 — Por que o Storefront está lento

**Árvore:** `.dsh-worktrees/go-live-acceleration` (origin/main = `f0ffd02fde765493d734bae93a72bb361ed28fcf`, 2026-09-29; `git status --porcelain` vazio → o lido é o do HEAD).
**Escopo:** superfície de cliente — `surfaces/storefront-nuxt` (SSR/Nitro/BFF) + API Django `shopman/storefront` (`/api/v1/`), projeções em `shopman/storefront/presentation/`.
**Método:** leitura estática (`read`/`grep`/`glob`), `git log/show/merge-base` read-only, e os números já medidos e registrados em `docs/plans/WP-PERFORMANCE-2026-09.md` e `docs/plans/WP-PROGRESSIVE-SSR-SSE-CONTINUITY.md`. **Nada foi editado além deste arquivo.**
**Não medi ao vivo:** não rodei `pytest`/`manage.py` (toca banco) nem `curl` contra produção. Os números de latência abaixo são os **já registrados** nos documentos do repo, com a data de cada medição — não são medições minhas.
**Legenda:** [FATO] verificado no código/saída · [INFERÊNCIA] dedução minha · [NÃO VERIFICADO] não confirmei · [DELEGADO] veio de auditoria delegada com o mesmo padrão de evidência (path:linha), spot-checada por mim nos pontos que decidiram prioridade.

> **Irmão deste relatório:** `03-continuum-impacto.md` cobre o `/menu` e o piloto Continuum em profundidade (medições ao vivo, polls de 30 s, borda Cloudflare). Aqui o foco é a **home** e a arquitetura de render comum a todas as rotas; onde os dois se tocam, aponto para lá em vez de repetir.

---

## 0. Evidência ao vivo (2026-09-29 ~16:20 UTC) — medida pelo dono, contra o alpha vivo

**Não é minha medição.** São os números que decidem o ranking deste relatório; eu não medi ao vivo (§6.4).

| Endpoint | TTFB agora | Corpo | Baseline do repo (17/09) | Δ |
|---|---|---|---|---|
| `GET api./api/v1/storefront/menu/` (8 amostras) | **2,87–4,39 s** | 136.692 B | 0,93–1,39 s | **~2,5× pior** |
| `GET api./api/v1/storefront/home/` (5 amostras) | **3,24–3,51 s** | 18.808 B | 1,03–1,88 s | **~2× pior** |
| `GET api./api/v1/catalog/products/` | 2,09–2,34 s | 10.916 B | 0,76–1,12 s | ~2× pior |
| `GET www./` (SSR da home, 5 amostras) | **3,91–4,35 s** | 143.216 B | 2,10–3,00 s | ~1,5× pior |
| `GET gestor./` (shell de operador) | 0,39–0,50 s | — | 0,33–0,67 s | **estável** |
| `GET pdv./` (shell de operador) | 0,35–0,38 s | — | 0,33–0,67 s | **estável** |
| `GET api./health/live/` | 0,27–0,32 s | — | 0,35–0,48 s | melhorou (P1 do WP foi feito) |
| `GET api./health/ready/` | 0,41–0,70 s | — | 0,44–0,84 s | melhorou |

E o `Server-Timing` do `menu/` — o único endpoint que hoje se explica (instrumentado em 28/09):

```
projection;dur≈2500-3585   availability;dur≈1491-1947   personalization;dur≈39-127
shadow;dur=0.00            db;dur≈493-882
```

### 0.1 O que a evidência decide

1. **A lentidão está concentrada no storefront, não na plataforma.** Os dois shells de operador não regrediram (0,35–0,50 s) e os dois health checks **melhoraram**. O container `web` (que serve `api.`) está saudável para tudo que não é o caminho de leitura da loja. [FATO]
2. **A regressão é de 2–2,5× e é recente** (17/09 → 29/09). O corpo do `menu/` cresceu 103 KB → **136,7 KB (+33%)** — mas +33% de catálogo não explica +150% de tempo, a menos que o custo seja **por SKU** e não por request. §A0.2 e §5.4.
3. **`shadow;dur=0.00` prova que o shadow do Continuum não roda** — coerente com `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED=false` (`.do/app.alpha-subdomains.yaml:367-370`). O shadow não é o custo. [FATO]
4. **A soma não fecha no banco.** `db` é a soma do tempo de **todas** as queries do request e representa **20–25%** de `projection`. O resto é CPU do processo e I/O que não é SQL. §A0.
5. **O estágio de disponibilidade é o maior bloco único**: `availability` ÷ `projection` = **52–60%**. É lá que a prioridade começa. §A0.

### 0.2 O que a evidência ao vivo NÃO diz

- **Não mede o BFF.** As amostras de `menu/` e `home/` saíram direto do `api.`; `bff;dur` não aparece nelas.
- **Não separa os estágios do SSR da home.** Mas limita o conjunto: o SSR (3,91–4,35 s) está apenas **0,67–0,84 s** acima do `home/` da API (3,24–3,51 s), e esse delta é o teto somado de BFF + `build_shell` + `build_site` + render + gzip. Ou seja: **shell, site e BFF juntos custam menos de 0,85 s**, e a duplicação do shell (§A1) vale uma fração disso.
- **Não diz se `availability` é CPU ou I/O não-SQL.** Está instrumentado no log (§A0, "como medir") — mas não foi lido.

---

## 1. Resumo executivo

- **Pela evidência ao vivo, a causa dominante é o estágio de disponibilidade do cardápio** — `availability;dur` 1,49–1,95 s, **52–60%** do `projection` do `/storefront/menu/` — e **o banco responde por só 20–25% dele** (`db;dur` 0,49–0,88 s). O fan-out do SSR, o BFF e a ausência de cache continuam reais, mas vêm **depois** em impacto. [FATO + aritmética em §A0]
- Cada página da loja dispara **2 a 4 chamadas HTTP ao Django durante o SSR**, e elas **não são paralelas**: o `app.vue` faz `await` do shell *antes* de a página existir, e a página então faz o seu próprio `await`. São duas ondas. [FATO no código; INFERÊNCIA sobre o efeito na ordem de render]
- **A home duplica trabalho — mas isso é secundário em milissegundos.** `build_home()` **continua chamando `build_shell()` internamente** (`presentation/home.py:377`) enquanto `app.vue:25` já buscou `/storefront/shell/`: o shell é construído **2×**, a sacola **2×** e a FAQ pública **3×** por page load (§A1). A evidência ao vivo limita o peso — ver §0.2. [FATO]
- **`Server-Timing` existe, mas não cobre a home.** Só `menu/`, `catalog/` e `continuum/…` emitem; `home/`, `shell/`, `cart/`, `checkout/`, `tracking/`, `products/<sku>/` e toda a conta **não**. É exatamente onde o tempo é gasto, e é o motivo pelo qual o achado A1 **não é mensurável em produção hoje**. [FATO]
- **Cache: nenhuma camada cobre HTML nem a API pública.** Não existe `cache_page`, `cached_property`, `cachedEventHandler` nem storage Nitro. No Django só há 4 caches, todos fora do caminho da home (`A3`). [FATO]
- **Regressão de 2–2,5× desde 17/09, medida ao vivo em 29/09** e concentrada no storefront: `menu/` 0,93–1,39 → **2,87–4,39 s**; `home/` 1,03–1,88 → **3,24–3,51 s**; SSR da home 2,10–3,00 → **3,91–4,35 s**. Operador (0,35–0,50 s) e health checks (0,27–0,32 s) **não regrediram**. Piso de rede ≈ 0,30 s. Metas declaradas: SSR ≤ 1,2 s, API ≤ 0,6 s. (§0)
- **Há N+1 reais e pontuais** que sobreviveram ao expurgo de 01/08: o pior é `order.items.count()` por pedido no histórico da conta (**~53 queries** para `/account/orders/`), e o histórico é a tela que o cliente reabre. [DELEGADO, com o fix já escrito no repo]
- **E há I/O de gateway dentro de um GET de leitura:** `GET /tracking/<ref>/` chama `ensure_payment_intent` → `payment_service.initiate(order)` para pix sem QR — **em todo request**, numa tela com SSE + poll. Otimizar query ali não resolve nada. [DELEGADO]
- **Imagens:** **8,9 MB** de `webp/jpg` servidos crus de `public/`, sem `@nuxt/image`, sem `srcset` fora do hero, sem `width`/`height`; 1,04 MiB órfãos. Não é o gargalo de TTFB, é o de LCP. [FATO]
- **Muito já foi feito e está mergeado** (N+1 do catálogo 111→40 queries e plano de escala; shell separado; `/health/live` que eliminou 5.760 renders de SSR/dia). O que **não** foi feito é o P6 do `WP-PERFORMANCE`: cache da leitura pública. [FATO]
- Ranking de suspeitos com como medir cada um: **§5**.

---

## 2. Arquitetura de render (o caminho real)

```
navegador ──HTTPS──► Cloudflare ──► Nitro (storefront-nuxt, SSR)
                                        │
                                        │ $fetch same-origin → server/api/v1/[...path].ts
                                        │                      (allowlist) → proxyDjangoApi
                                        │
                                        └──$fetch HTTP──► api.boulangerie.com.br (Django)
                                                              │
                                                              └── presentation/*.py → ORM
```

- O SSR **não fala direto com a API pública**: toda chamada passa pelo BFF Nitro. [FATO] `app/composables/useShopmanApiPath.ts:3-7` + `app/utils/shopmanApi.ts`; rota catch-all em `server/api/v1/[...path].ts:5-12`.
- O BFF é um **proxy HTTP completo**: allowlist de prefixos (`server/utils/storefrontApiAllowlist.ts:1-16`), repasse de cookie/XFF/segredo de proxy, checagem de path traversal e de CSRF (`server/utils/djangoProxy.ts:120-243`). [FATO]
- O BFF chama o Django **pela URL pública** (`NUXT_DJANGO_BASE_URL` → `api.boulangerie.com.br`): cada chamada de SSR sai do container, atravessa a borda e volta. [FATO documentado] `WP-PERFORMANCE-2026-09.md` `3.7 e `5-P4.
- **Toda resposta do BFF sai com `cache-control: private, no-store`** — `server/utils/djangoProxy.ts:145`. Nada vindo de `/api/**` pode ser cacheado por borda ou navegador. [FATO]

---


## 3. Achados

### A0 — De onde vem o tempo: a aritmética dos estágios [ALTO] [FATO + INFERÊNCIA]

**Como ler o `Server-Timing`.** Os cinco nomes são *buckets* **aninhados**, não irmãos — `observability.py:26-33` e `:39-47`:

```
projection            <- surface.py:460, envolve TODO o build_catalog
  ├── personalization <- catalog.py:241 e :256
  ├── availability    <- catalog.py:457, envolve _availability_states
  └── (o resto do build_catalog)
db                    <- NÃO é irmão: é a SOMA do tempo de SQL de todo o request
                         (connection.execute_wrapper, observability.py:55-61)
```

**Com os números ao vivo** (`projection` 2500–3585, `availability` 1491–1947, `personalization` 39–127, `db` 493–882 ms):

| Leitura | Valor | Como chego nele |
|---|---|---|
| `availability` ÷ `projection` | **52–60%** | o estágio de disponibilidade é o maior bloco do cardápio |
| `db` ÷ `projection` | **20–25%** | o banco está longe de ser o gargalo |
| `availability` − `db` (limite GENEROSO: todo o SQL atribuído à disponibilidade) | **≥ 1,0–1,1 s** | não é SQL |
| `projection` − `availability` − `personalization` | 0,4–2,1 s | o resto do `build_catalog` |

**Conclusão:** em `catalog.py:457` o estágio gasta **~1,5–1,9 s, dos quais no máximo ~0,5–0,9 s são banco**. O resto é CPU do processo Python e I/O que **não passa** por `connection.execute_wrapper` — e o processo roda em **1 vCPU compartilhada** com Admin e os hosts de operador (`WP-PERFORMANCE` §2.5). [INFERÊNCIA: a partição CPU vs I/O não-SQL **não está instrumentada**; como separar, no fim desta seção]

**O que exatamente roda ali** — o caminho completo, com path:linha:

```
catalog.py:457   with catalog_stage("availability"):
catalog.py:458       _availability_states(products, channel_ref, own_holds, low_stock_threshold)
catalog.py:611           listing_sellable_map(skus, channel_ref)                    -> 1 query
catalog.py:614           _batch_availability(skus, channel_ref)
catalog.py:712               -> catalog_context.availability_for_skus(...)          catalog_context.py:619
catalog_context.py:645           -> stockman.availability_for_skus(...)             ~7 sitios de query
catalog_context.py:656           -> waitlist.next_batch_availability_for_skus(...)  2a passada
catalog.py:620           bundle_availability_for_skus(...)                        -> 3a passada, se houver bundle
catalog.py:630-656       for p in products: _resolve_availability / pause_and_notifiability
                         availability_with_own_hold                                -> Python por SKU
```

Três coisas nesse caminho merecem nome — e **nenhuma é o banco**:

1. **Até três passadas de disponibilidade por request.** `stockman.availability_for_skus` (`packages/stockman/shopman/stockman/services/availability.py:352`) é uma passada em lote, mas com **~7 sítios de query** (`validator.validate_skus`, `validator.get_sku_infos`, `Batch.filter` 1–2×, `Quant.filter` 2–3×, `Hold.filter`; contagem por leitura de `:352-565`). Sobre ela: `waitlist.next_batch_availability_for_skus` (`shop/services/waitlist.py:73-135`) **chama a mesma função de novo, uma vez por data candidata de fornada futura** (`waitlist.py:124-133`); e `bundle_availability_for_skus` (`catalog_context.py:772`) faz **outra passada completa**, com um `for sku in bundle_skus` que expande bundle a bundle (`:786-790`). [FATO]
   ⚠️ O multiplicador da fila depende de `waitlist.is_enabled` — **default `enabled=False`** (`waitlist.py:21, 53-55`), e com a fila desligada `promise_horizon` devolve hoje e a função **sai antes de qualquer query** (`waitlist.py:93-94`). **Não verifiquei o valor no alpha** (§6.2-Q10). Se estiver ligada, o custo é multiplicativo no número de datas de fornada — e é a primeira coisa a checar.

2. **Loop Python por SKU dentro do estágio.** `catalog.py:630-656` percorre os produtos resolvendo disponibilidade, pausa e notificabilidade com `Decimal` (`_resolve_availability:780`, `pause_and_notifiability:576`, `availability_with_own_hold`). É **O(produtos) de CPU pura** — e é isto que faz **+33% de catálogo poder virar mais que +33% de tempo**. [FATO no código; INFERÊNCIA na magnitude]

3. **Dois lookups de `Channel` por request, sem cache.** `is_channel_active` (`shop/services/channel_switch.py:215-219`) faz `Channel.objects.filter(ref=...).only(...).first()` a **cada** chamada, e `build_shell` chama `accepting_orders` (`home.py:354`, ligado em 22/09 por `da87edb48`); `ChannelConfig.for_channel(str)` faz `Channel.objects.get(ref=...)` (`shop/config.py:442`), chamado em `catalog.py:239`. [FATO]
   → **Esta é a origem dos 100.974 seq scans/dia em `shop_channel` (tabela de 6 linhas)** que o `WP-PERFORMANCE` §3.8 registrou como *"causa não identificada"*. Custa pouco por si, mas aparece em todo request e polui as estatísticas do planner.

**Como separar CPU de SQL — o instrumento já existe e ninguém leu.** `surface.py:495-513` emite `storefront_catalog_observation` com `query_count`, `projection_ms`, `availability_ms`, `personalization_ms`, `db_ms` e `response_bytes`, no logger `shopman.storefront.continuum`, **allowlisted** (sem payload, SKU, sessão ou pessoa — `observability.py:70-99`).

```bash
# É só ler o log do alpha. A leitura decide a prioridade inteira:
doctl apps logs <web-app-id> --type run | grep storefront_catalog_observation
# Caso A: availability_ms alto + query_count baixo + db_ms baixo  => CPU por SKU
#          (a conversa é workers/vCPU e cortar passadas, NÃO índice)
# Caso B: query_count alto (dezenas)                              => 2a/3a passada ligada
#          (checar waitlist.is_enabled e bundles no cardápio)
# Caso C: db_ms ~= availability_ms                                => banco de verdade
#          (pg_stat_statements, P0 do WP-PERFORMANCE)
```

---

### A1 — A home constrói o shell duas vezes e a sacola duas vezes [ALTO] [FATO]

**Onde:** `shopman/storefront/api/surface.py:279-291` (Home), `:302-317` (Shell), `shopman/storefront/presentation/home.py:376-402`.

```python
# home.py:376-379
def build_home(request, *, cart_has_items=None) -> HomeProjection:
    shell = build_shell(request, cart_has_items=cart_has_items)   # <- reconstroi o shell inteiro
    last_ref, last_items = _reorder_context(request)
    catalog = build_catalog(channel_ref=STOREFRONT_CHANNEL_REF, request=request)
```

E as duas views montam a sacola de forma independente:

```python
# surface.py:285-291 — StorefrontHomeView.get
cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
home = build_home(request=request, cart_has_items=cart.items_count > 0 and not cart.is_empty)
return Response({"home": projection_data(home), "cart": projection_data(cart)})

# surface.py:308-317 — StorefrontShellView.get
cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
shell = build_shell(request=request, cart_has_items=...)
return Response({"shell": projection_data(shell), "cart": projection_data(cart)})
```

O cliente busca **as duas**: `app/app.vue:25` (`await useStorefrontShell()`) e `app/pages/index.vue:22` (`await useStorefrontHome()`).

**Consequência por page load na home** (cada linha é um HTTP separado BFF→Django):

| Trabalho | `/shell/` | `/home/` | `/site/` | Total |
|---|:--:|:--:|:--:|:--:|
| `build_cart()` | 1× | 1× | — | **2×** |
| `build_shell()` | 1× | 1× | — | **2×** |
| `build_catalog()` | — | 1× | — | 1× |
| `build_public_faq()` (`public_information.py:102-130`) | 1× (dentro do shell) | 1× (idem) | 1× (`site.py:199`) | **3×** |
| `Shop.load()`, `_shop_status()`, `_format_opening_hours()`, `OmotenashiContext.from_request()`, `browser_api_key()`, `accepting_orders()` | 1× | 1× | parcial | **2–3×** |

`build_shell` foi escrito exatamente para ser a projeção leve compartilhada por toda rota — docstring em `home.py:275-280`: *"Deliberately excludes build_catalog and _reorder_context. Those are home-page concerns and are orders of magnitude more expensive…"*. O comentário está certo sobre o catálogo, mas **o shell continuou dobrado na única rota onde ele já foi buscado pelo `app.vue`**. [FATO]

**Impacto:** ~2× o custo de tudo que não é catálogo, na rota de entrada da loja. Nas rotas internas (`/menu`, `/sacola`, `/finalizar`, `/pedido/…`) o mesmo trabalho roda **1×**.
**Confiança:** alta no código. O ganho em ms é [INFERÊNCIA] — depende do custo de `build_shell`, que **não** tem `Server-Timing` (`A4`).
**Nota:** o `identity.py:20-34` memoiza o customer em `vars(request)` — **por request**. Os três são requisições Django distintas, então o memo não atravessa. [FATO]

**Como medir em produção:**
```bash
# 1. Provar que o shell e subconjunto do home, sem tocar no Django:
curl -s https://api.boulangerie.com.br/api/v1/storefront/shell/ | jq '.shell|keys'
curl -s https://api.boulangerie.com.br/api/v1/storefront/home/  | jq '.home|keys'
# 2. Contar queries por endpoint: o execute_wrapper de observability ja existe
#    (observability.py:50-67) mas nao esta ligado na home; a prova direta e
#    django.db.connection.queries num shell, ou pg_stat_statements (P0 do WP-PERFORMANCE).
# 3. No log do web (container unico): contar GETs por path por page load.
```

---

### A2 — Cascata serial de 2 estágios no SSR [ALTO] [FATO no código]

`app/app.vue:22-27`:
```ts
// Disparada antes do estado do shell, para as duas buscas correrem juntas.
const { site: siteSeo, ready: siteSeoReady } = useSiteSeo()        // :23  -- paralelas
const { data: shellState, refresh } = await useStorefrontShell()   // :25  --
await siteSeoReady                                                 // :27
```

Shell e site **correm juntos** — o comentário é verdadeiro e o código o cumpre. Mas `app.vue` é o componente raiz e faz `await` no seu próprio setup; `<NuxtPage />` (`app.vue:140`) só é criado depois. A página então dispara a **sua** busca — `index.vue:22`, `menu.vue:47`, `finalizar.vue:293`, `pedido/[ref]/index.vue:54`, `produto/[sku].vue:23` — todas com `await`. [FATO]

Logo o primeiro byte do documento espera **estágio 1 (shell+site) → estágio 2 (página)**. Não é paralelismo de 3–4 chamadas: são duas ondas. [INFERÊNCIA forte; ver `6-Q1` sobre streaming]

**Agravante:** `lazy: true` está em `useStorefrontHome.ts:30`, `finalizar.vue:297`, `pedido/[ref]/index.vue:56` e mais 12 páginas (travado em `tests/performanceGuardrails.test.ts:57-78`). `lazy` evita travar a **navegação cliente**; onde a página faz `await` explícito, o setup do SSR continua esperando. **Não confirmei o efeito exato de `lazy:true` + `await` sobre o Suspense do SSR** — `6-Q2.`

**Como medir em produção:**
```bash
# DevTools > Network em "Slow 4G": o request da pagina (home/) so comeca depois
# que /api/v1/storefront/shell/ termina. Essa ordem E o achado.
# No servidor, o BFF ja emite o estagio dele:
curl -sI https://www.nelsonboulangerie.com.br/ | grep -i server-timing    # bff;dur=...
# bff;dur pequeno + TTFB grande => o tempo e Django + rede, nao o proxy.
# Para isolar os estagios: TTFB de "/" (shell+site+home) contra "/sacola" (so shell+site).
```

---


### A3 — Zero cache na leitura pública [ALTO] [FATO]

**Django — o que NÃO é cacheado:** a leitura canônica inteira. Os caches existentes, **nenhum** no caminho da home:

| O que | Camada | TTL | path:linha |
|---|---|---|---|
| disponibilidade por SKU (`/availability/<sku>/`) | `django.core.cache` (Redis em prod) | **10 s** | `api/availability.py:163,179` |
| badges FOMO (`/fomo/<sku>/`) | idem | **10 s** (`CACHE_TTL_SECONDS`, `fomo.py:23`) | `api/fomo.py:61,70` |
| `Shop.load()` (singleton) | idem | **60 s** (`SHOP_CACHE_TTL`) | `shop/models/shop.py:13,28,486-490` |
| copy omotenashi | `_DB_CACHE` global de módulo | **sem TTL**, invalidado no save/delete | `shop/omotenashi/copy.py:1524-1554` |
| snapshot estrutural do catálogo | `django.core.cache` | **300 s** | `continuum.py:204,208` |

`cache_page`: **não encontrado** (grep em presentation + api + middleware). `cached_property`: **não encontrado** no storefront. `build_home`/`build_shell`/`build_catalog`/`build_cart`: sem cache. [FATO]

**Backend de cache** (`config/settings.py:495-540`): Redis (native `RedisCache`) **só se `REDIS_URL` estiver definido**; senão LocMem, que **não é compartilhado entre processos**. [FATO]

```python
# config/settings.py:530-535
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
```

**Nuxt — as três regras de `routeRules` não cobrem o que importa:** `nuxt.config.ts:58-71` define apenas `/` (`private, no-transform`, **sem `max-age`**), `/img/products/**` (1 ano, immutable) e `/sw.js`. Home, menu, sacola, checkout e pedido: **nenhuma regra**; `cachedEventHandler`/`defineCachedFunction`/`useStorage` em `server/`: grep = 0. [FATO]

**`ensure_csrf_cookie` em 6 views mata cache compartilhado:** `surface.py:278, 301, 450, 540, 568, 586` — home, shell, menu/catalog, produto, cart, checkout. Cada GET anônimo responde `Set-Cookie: csrftoken` e `Vary: Cookie`, o que impede qualquer borda de servir a mesma resposta a dois visitantes. [FATO] O `WP-PERFORMANCE` `3.6` registra o mesmo efeito observado ao vivo (`cache-control: private`, `Vary: Cookie`, `cf-cache-status: BYPASS`).

**Decisão já tomada que limita a solução.** Cachear a projeção do catálogo foi **explicitamente rejeitado** em 01/08/2026, em `docs/plans/completed/STOREFRONT-CATALOG-NPLUS1-PLAN.md`: *"build_catalog é profundamente personalizado… Cachear a projeção (Valkey) ou o HTML SSR (routeRules swr) vazaria preço/favoritos/carrinho de um cliente para outro"*. [FATO] A cerca vale além do catálogo: `build_shell` carrega `origin_channel`, `omotenashi.customer_name`, `marketing_prompt_pending` e `public_config.google_maps_api_key` — cachear a home tem o **mesmo** problema. **A cerca é: cachear estrutura pública, nunca estado de sessão.** O snapshot Continuum é a resposta arquitetural a essa cerca.

**Impacto:** cada visitante anônimo paga a reconstrução inteira. Com o `web` sendo **1 container de 1 vCPU/1 GiB** que também serve Admin e os 7 hosts de operador ([FATO] `WP-PERFORMANCE` `2.5`; `.do/app.alpha-subdomains.yaml:834-839`), é contenção direta entre loja e PDV/KDS.

**Como medir em produção:**
```bash
curl -sI https://www.nelsonboulangerie.com.br/                  | grep -iE 'cf-cache-status|cache-control|vary|set-cookie|age'
curl -sI https://api.boulangerie.com.br/api/v1/storefront/home/ | grep -iE 'cf-cache-status|cache-control|vary|age'
# Esperado hoje: cf-cache-status: BYPASS + set-cookie: csrftoken=...
# Redis ligado de verdade? (decide se CACHES e Redis ou LocMem)
#   doctl apps console <app> -- env | grep REDIS_URL
#   redis-cli INFO stats | grep keyspace     # hit ratio, se houver Redis
```

---

### A4 — `Server-Timing` não cobre a home, a sacola, o checkout nem o acompanhamento [ALTO — habilitador] [FATO]

**Definição única**, `shopman/storefront/observability.py:26-33`:

```python
def server_timing(self, *, include_bff: bool = False) -> str:
    names = ["projection", "availability", "personalization", "shadow", "db"]
```

- `projection` / `availability` / `personalization` / `shadow`: tempo de parede acumulado dos `with catalog_stage(...)` (`observability.py:39-47`).
- `db`: **soma** do tempo de *todas* as queries do request, por `connection.execute_wrapper` (`:55-61`). É tempo total, **não** contagem nem breakdown.
- **Query count não sai no header** — só no log: `surface.py:499` passa `query_count` para `log_catalog_observation`, não para o header.

**Onde é setado — só dois lugares:**

| path:linha | view | rotas |
|---|---|---|
| `api/surface.py:492` | `StorefrontMenuView` / `StorefrontCatalogView` | `/storefront/menu/[/<collection>/]`, `/storefront/catalog/` |
| `api/continuum.py:110,129` | `CatalogStructureSnapshotView` | `/storefront/continuum/v0.2/catalog-structure/` |

**Onde NÃO existe:** `StorefrontHomeView` (`surface.py:279-291`), `StorefrontShellView` (`:302-317`), `StorefrontSiteView` (`:342-357`), `StorefrontProductView` (`:541`), `StorefrontCartView` (`:569`), `StorefrontCheckoutView` (`:587`), `OrderTrackingView`, e toda a Conta. [FATO]

A anexação do estágio `bff` é feita no Nitro (`djangoProxy.ts:214-220`); `include_bff=True` **nunca é chamado no Django** (grep = 0). [FATO]

**Por que isto é achado de performance e não só de observabilidade:** o endpoint mais lento medido (`/storefront/home/`, 1,03–1,88 s) é justamente o que não tem instrumentação — então **A1 é indemonstrável em produção sem mexer em código**. A infra já existe: `capture_catalog_timing()` é um context manager de 18 linhas (`observability.py:50-67`) e `catalog_stage` sai cedo quando o `ContextVar` está vazio (`:40-47`), custo ~zero.

**Como medir em produção:**
```bash
curl -sI https://api.boulangerie.com.br/api/v1/storefront/menu/        | grep -i server-timing
curl -sI https://api.boulangerie.com.br/api/v1/storefront/home/        | grep -i server-timing  # hoje: vazio
curl -sI https://www.nelsonboulangerie.com.br/api/v1/storefront/shell/ | grep -i server-timing  # inclui bff;dur
# Log estruturado que JA existe, allowlisted (sem payload/SKU/pessoa):
#   logger "shopman.storefront.continuum" -> evento "storefront_catalog_observation"
#   campos: query_count, response_bytes, projection_ms, availability_ms, db_ms
# doctl apps logs <app-id> --type run | grep storefront_catalog_observation
```

---


### A5 — N+1 sobreviventes: o histórico da conta é o pior [ALTO] [DELEGADO]

#### A5.1 — `order.items.count()` por pedido [ALTA]

`shopman/shop/projections/customer.py:108-118`:

```python
def _summaries_from_orders(orders) -> tuple[CustomerOrderSummary, ...]:
    return tuple(
        CustomerOrderSummary(
            ...
            item_count=order.items.count(),   # linha 115
        )
        for order in orders
    )
```

`history_summaries_for_customer` (`:64-66`) monta o queryset **sem** `prefetch_related`/`annotate` e fatia `qs[:limit]` → **um `SELECT COUNT(*)` por linha**.

Consumidores: `api/account.py:847` (`limit=50` → `GET /api/v1/account/orders/`); `presentation/account.py:322` (`limit=10` → `/account/summary/`); `presentation/order_history.py:100` (`limit=50`).
Custo [INFERÊNCIA a partir dos `limit`]: `/account/orders/` ≈ **1 + 50 + 2 ≈ 53 queries**; o ideal é ~4.
Agravante: `api/account.py:843-863` chama **três** serviços (`order_history_for_customer`, `order_count_for_customer` em `customer_orders.py:184`, `active_order_count_for_customer` em `:165`), cada um re-resolvendo o filtro de identidade e disparando o próprio `COUNT` com `.distinct()`.

**O fix já existe escrito ao lado:** `shop/services/order_composition.py:169-196` `effective_items_by_order_id` é a versão em duas consultas, com docstring explícita ("não pode pagar um `order.items.all()` por linha"). Aqui a saída mínima é `.annotate(item_count=Count("items"))`.

**Como medir** (sem deploy; discriminador exato):
```sql
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
WHERE query ILIKE '%COUNT(*) FROM "orderman_orderitem"%'
ORDER BY calls DESC LIMIT 5;
```

Uma linha com `calls` ≈ nº de pedidos por acesso é a assinatura. Comparar `calls` antes/depois de abrir `/conta` e `/account/orders/` isola a contribuição de cada tela. Trava antes do go-live: `assertNumQueries` em `shopman/storefront/tests/api/`.

#### A5.2 — `GET /tracking/<ref>/` faz I/O de gateway na leitura [ALTA — não é query]

`shopman/storefront/api/tracking.py:178-190` chama, **em cada GET**: `resolve_timeouts_if_due(order)` (`storefront/services/orders.py:110-114`, três resolvers que podem escrever), `reconcile_payment_with_gateway_if_due(order)` (`:104-107` → I/O externo) e `ensure_payment_intent(order)` (`shop/services/customer_orders.py:502-527`) — e a linha `:526` chama `payment_service.initiate(order)` para pedido pix com `intent_ref` mas **sem** `copy_paste`/`qr_code`. [DELEGADO]

Numa tela que tem SSE **e** poll de fallback, isso é custo fixo e não-trivial por request. **Otimizar query aqui não resolve nada.**

**Como medir:**
```bash
# 10 GETs seguidos; olhar a CURVA, nao a media
for i in $(seq 10); do curl -sS -o /dev/null -w '%{time_total} %{http_code}' "https://<host>/api/v1/tracking/<ref>/"; echo; done
# Cauda longa intermitente => o I/O de gateway acima.
# Tempo constante e alto com db;dur baixo => as queries do A5.3.
# Discriminador: SELECT ... FROM orderman_orderevent WHERE type='status_changed'
# no pg_stat_statements; o mesmo pedido deve produzir ~1 por status, nao 2.
```

#### A5.3 — Acompanhamento: a mesma query de evento repetida, e fulfillments lidos duas vezes [MÉDIA]

`shopman/shop/projections/order_tracking.py:1376-1397` — `_event_for_status` (`:1394`) dispara **1 query por chamada** sempre que o campo desnormalizado `{status}_at` está vazio. E ele é chamado **duas vezes pelos mesmos status**: em `_build_progress_steps` `:1260,1264,1267,1268,1269,1270` (até 6 queries) e de novo em `_step_was_reached` (`:1354-1373`, chamado no loop de `:1287`) — até 6 duplicadas. Além disso `_build_timeline` lê `order.fulfillments.all()` (`:1208`) e `_build_fulfillments` lê a **mesma tabela outra vez** (`:1477`), sem `prefetch`. Somando `_confirmation_deadline` (`:1613`) e `convenience_pending` (`:1817`), são ≈ **12–18 queries constantes** por pedido, com a mesma `SELECT` rodando duas vezes. [DELEGADO]

#### A5.4 — `_gone_products()`: 3 queries por ref, por SKU aposentado [MÉDIA]

`shopman/storefront/api/surface.py:379-395`: o loop `:390` chama `primeira_viva` (`:379`), que faz `get_active_collection` (`catalog_context.py:73-74`, 1 query) + `filter_by_collection` (`:286-293`, 2 queries) → **3 queries por ref**. Base: 2 queries (`products_queryset().values_list` em `:388` traz todos os SKUs para um `frozenset`). Rota: `GET /storefront/sku-redirects/` (`api/urls.py:109`). Unbounded no crescimento de `RetiredProduct`. [DELEGADO]
**Medir:** `curl -o /dev/null -w '%{time_total}'` em `/storefront/sku-redirects/`, cruzado com `SELECT count(*) FROM shop_retiredproduct;`.

#### A5.5 — PDP: ~15 queries para **um** produto [BAIXA]

`presentation/product_detail.py` tem **20 chamadas** a `catalog_context.*` (`:246,255,257,261,294,301,303,308,322,342,350,367,429,438,460,489,532,654,663,726`), cada acessor escalar = 1 query. Não é N+1 (é constante), mas é a página que mais round-trips paga por conteúdo — e a API em lote (`build_catalog_items_for_skus`) **já existe** e a PDP deliberadamente não a usa. [DELEGADO]

#### A5.6 — `ChannelConfig.for_channel` re-consulta `Channel` [BAIXA]

`shop/config.py:418-453` faz `Shop.load()` (cacheado, 60 s) **e** `Channel.objects.get(ref=...)` quando recebe string (`:442`). Chamado em `catalog.py:239`, `catalog.py:392`, `product_detail.py:252`, `checkout.py:436`. **O `checkout.py:435` está certo** — busca o objeto e passa, evitando a segunda query. É o padrão a copiar. [DELEGADO]

**Falsos positivos verificados e descartados** [DELEGADO]: `catalog.py:471` (`for p in products` — as chamadas internas são puras ou pré-carregadas); `presentation/account.py:306-309` (a função é o iterável); `public_information.py:128,146` (`filter()` fora do loop); `cart.py:348` (`image_by_sku` vem em lote de `cart.py:503-505`); `api/account.py:849` `_with_order_actions` (`account.py:213-217`, puro); `api/surface.py:388,434` (`values_list`, 1 query cada).

---

### A6 — Fan-out: a contagem exata de chamadas por página [MÉDIO-ALTO] [FATO]

Levantado em todos os `.vue`/`.ts` de `surfaces/storefront-nuxt/app/`. "SSR" = requisições disparadas durante o render do servidor.

| Rota | Chamadas no SSR | Quem dispara | Depois da hidratação |
|---|---|---|---|
| `/` (home) | **3**: `shell/`, `site/`, `home/` | `app.vue:23,25`; `index.vue:22` | `account/orders/active/` e, se houver ativo, `account/orders/?filter=ativos` (`index.vue:87,89`, `onMounted`) |
| `/menu` | **3**: `shell/`, `site/`, `continuum/.../catalog-structure/` — o canônico `catalog/` **não** roda no servidor quando o snapshot chega | `app.vue`; `menu.vue:29-37,41-51` | `catalog/` (canônico, lazy) + **2 polls de 30 s** — ver `03-continuum-impacto.md` |
| `/sacola` | **2**: `shell/`, `site/` | `app.vue` | `cart/` imediato no `onMounted` (`sacola.vue:36`) + poll de 30 s se houver hold (`:39-42`) |
| `/finalizar` | **3**: `shell/`, `site/`, `checkout/` | `app.vue`; `finalizar.vue:293` | `checkout/loyalty/` no toggle (`:112`), `checkout/draft/` no sync de endereço (`:833`), `checkout/` no commit (`:1180,1219`) |
| `/pedido/<ref>` | **3**: `shell/`, `site/`, `tracking/<ref>/` | `app.vue`; `pedido/[ref]/index.vue:54-57` | SSE `/sse/pedido/<ref>` + poll de fallback |
| `/produto/<sku>` | **3**: `shell/`, `site/`, `storefront/products/<sku>/` (+ `sku-redirects/` no 404) | `produto/[sku].vue:23,28` | — |

As contagens são [FATO]; a do `/menu` com Continuum é [INFERÊNCIA] sobre o valor da flag — que `03-continuum-impacto.md` `2` confirma **ligado** no alpha (`SHOPMAN_CONTINUUM_CATALOG_SNAPSHOT_ENABLED=true`, `NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED=true`, `.do/app.alpha-subdomains.yaml:367-382, 906-911`), com prova ao vivo.

**O problema não é o número de chamadas: é que elas são (a) em ondas seriais (`A2), (b) cada uma um round-trip HTTP completo BFF→Cloudflare→Django (`2), e (c) sem nenhuma sobreposição de trabalho entre si** — três `Shop.load()`/`OmotenashiContext` porque são três requisições Django distintas. [FATO]

**Como medir:** contar no log do `web` os GETs por path correlacionados por `X-Forwarded-For`/sessão numa janela de 2 s. Somar queries por página exige `pg_stat_statements` (P0 do `WP-PERFORMANCE`, ainda não instalado).

---


### A7 — `sitemap.xml` sem cache reconstrói o cardápio inteiro por hit [BAIXO-MÉDIO] [FATO]

`server/routes/sitemap.xml.ts:10-27`:

```ts
const menu = await $fetch<MenuResponse>(`${djangoBaseUrl}/api/v1/storefront/menu/`)
const items = menu?.catalog?.items || []
```

Sem `cachedEventHandler`, sem `Cache-Control`, sem ETag: **cada hit de crawler paga uma construção completa do catálogo** — e o endpoint chamado é `/storefront/menu/`, que inclui a sacola (`surface.py:456`, `include_cart = True`). [FATO]

**Medir:** `doctl apps logs <app-id> --type run | grep -c sitemap`, cruzado com hits do Search Console/Bing.

---

### A8 — Imagens: 8,9 MB crus, sem `@nuxt/image`, sem `srcset` [MÉDIO-ALTO para LCP] [FATO]

- **`@nuxt/image` não existe:** grep por `nuxt/image|NuxtImg|NuxtPicture` em `surfaces/storefront-nuxt/` = 0; ausente do `package.json` e do `package-lock.json`. Sem provider, sem IPX. [FATO]
- **A origem é uma URL única por produto, sem variante:** `Product.image_url` é `URLField` (`packages/offerman/shopman/offerman/models/product.py:164`); a projeção repassa cru (`presentation/catalog.py:530`, `presentation/product_detail.py:380`, `presentation/cart.py:499`) e o card faz `:src="item.image_url"` (`app/components/ProductTile.vue:36`). [FATO]
- **Tamanhos reais** (medidos no worktree):
  - `public/img/products/` — **51 arquivos, 6.080.576 B (5,80 MiB)**, média 119 KB; maior: `cgr2.webp` = **358.624 B**.
  - `public/img/home/` — **9 arquivos, 2.804.965 B (2,67 MiB)**; maior: `facade2.jpg` = **684.424 B**.
  - `public/` total = **18 MB** (dos quais `public/pwa/` = 8,7 MB, já fora do precache por decisão — `nuxt.config.ts:131`).
- **`srcset` existe uma única vez** em todo o app: `app/components/HomeHeroThing.vue:281` (par phone/wide hardcoded em `:42-45`). `width`/`height` = **zero ocorrências** (a proporção vem de `UiAspectRatio`, ex. `ProductTile.vue:34`). `fetchpriority="high"` só na PDP (`produto/[sku].vue:237,240`). O hero usa `eager` só no slide 0 (`HomeHeroThing.vue:286`). [FATO]
- **Achado contraintuitivo no hero:** em `HomeHeroThing.vue:42` o ramo *phone* é `facade6.webp` (**312.892 B**) e o *wide* é `facade2.webp` (**284.420 B**) — o `<source media="(min-width: 640px)">` entrega o arquivo **maior** no celular, que é o alvo. [FATO]
- **1,04 MiB em `public/img/home/` não é referenciado por nada:** `facade2.jpg` (684 KB) e `tempo-bem-vindo.jpg` (411 KB) — grep em `app/` = 0, e `public/` é copiado inteiro para o output. [FATO]
- **O CacheFirst do service worker provavelmente não protege nada:** a regra exige `url.origin === self.location.origin` (`nuxt.config.ts:142`), mas em produção as fotos vêm de `img.nelsonboulangerie.com.br` (`config/management/commands/seed.py:1834-1838`), **outra origem** — a regra nunca casa. [INFERÊNCIA a partir do código; NÃO VERIFICADO em produção]
- **`/img/home/**` não tem nem `routeRule` nem `runtimeCaching`:** nenhuma das duas camadas cobre o hero. [FATO]
- **`webp`/`jpg` não estão em `globPatterns`** (`nuxt.config.ts:125`), então nenhuma foto entra no precache; a navegação é `NetworkOnly` (`:135-140`). [FATO]

**Como medir em produção:**
```bash
curl -sI https://img.nelsonboulangerie.com.br/products/cgr2.webp | grep -iE 'content-length|cache-control'
# DevTools > Network > Img, emular iPhone (390px): card de ~380 px CSS puxando ~350 KiB confirma.
# DevTools > Application > Cache Storage: 'storefront-product-images' deve estar populado
# depois de navegar o cardapio. Vazio = o origin mismatch esta confirmado em producao.
# Orfaos: grep por facade2.jpg e tempo-bem-vindo.jpg em app/ (= 0 hoje).
```

---

### A9 — Bundle JS: shell inteiro no entry chunk, sem `<Lazy>` nem `import()` [MÉDIO] [FATO, tamanho NÃO VERIFICADO]

- **Não existem artefatos de build no worktree** (`node_modules/`, `.nuxt/`, `.output/` ausentes) → **tamanho real do bundle é [NÃO VERIFICADO]**. O que segue é inventário de imports, não bytes.
- **Não há `app/layouts/`** — o shell é `app/app.vue`, que renderiza 12 componentes auto-importados estaticamente: `NavigationFeedback` (`:125`), `ShopHeader` (`:138`), `ShopFooter` (`:142`), `AppBottomNav` (`:144`), `SearchOverlay` / `SubstituteSheet` / `OfflineBanner` / `PwaInstallInvite` / `PwaUpdateToast` / `MarketingPromptSheet` (`:146-154`), `EnvironmentRibbon` (`:160`), `UiSonner` (`:161`). [FATO]
- **`<ClientOnly>` atrasa a renderização, não o empacotamento:** grep por `<Lazy` e por `import(` dinâmico em `app/` = **0 ocorrências**. Os overlays entram no entry chunk junto com o resto. [FATO]
- **Dependências declaradas sem nenhum import em `app/`:** `qrcode`, `nostics`, `@internationalized/number`, `tailwind-merge` e **`motion-v`** (módulo registrado em `nuxt.config.ts:98`; `grep "<motion"` em `app/` = 0 — as 6 ocorrências de "motion" são a variante Tailwind `motion-reduce:`). [FATO]
- **`@nuxt/icon` com `clientBundle.scan: true` e `sizeLimitKb: 0`** (`nuxt.config.ts:233-238`): sem teto de tamanho, com **106 ícones `lucide:*` distintos / 377 ocorrências** em `app/` como candidatos ao bundle do cliente. KB: [NÃO VERIFICADO]. [FATO no config e na contagem]
- `reka-ui` aparece em **394 linhas** de import, quase todas em `app/components/Ui/**`; `v-calendar` só em `Ui/Datepicker.vue:21` e `Ui/Calendar.vue:23` (type-only). O efeito real depende do tree-shake. [NÃO VERIFICADO]

**Como medir:**
```bash
cd surfaces/storefront-nuxt && npm ci && npm run build
ls -lS .output/public/_nuxt | head -20      # maiores chunks
du -sh .output/public/_nuxt                 # total
```

---

### A10 — Gzip da home sincronizado no event loop, por visitante [MÉDIO-BAIXO] [FATO no código]

`server/plugins/homeCompression.ts:53-84` + `server/utils/homeCompression.ts:97-98`: no hook `render:response`, **só para `/` GET/HEAD 200 `text/html`**, o plugin bufferiza o HTML inteiro e roda `gzip` promisificado; remove o ETag (`:81`) e reescreve `Content-Length` (`:83`). [FATO] Como não há cache compartilhado (`A3), **todo visitante paga esse CPU** — em 1 vCPU compartilhada com Admin e operador. O `WP-PERFORMANCE` `2.1 mede o corpo da home SSR em 133 KB → 26,5 KB gzip, então o trabalho é sobre ~133 KB por render.

**Medir:** `curl -s -o /dev/null -D- -H 'accept-encoding: gzip' https://www.nelsonboulangerie.com.br/` e olhar `content-encoding`/`content-length`/`vary`; o CPU pelo painel *Insights* durante carga (hoje bloqueado: sem `monitoring:read`, `WP-PERFORMANCE` `7`).

---

### A11 — Middleware por request: barato, com duas exceções [BAIXO] [FATO]

**Django** (`config/settings.py:364-393`). O que toca I/O:

| Middleware | Custo real |
|---|---|
| `SessionMiddleware` (`:374`) | **1 leitura** de sessão por request; 1 escrita quando modificada |
| `CsrfViewMiddleware` (`:376`) | emite `Set-Cookie: csrftoken` nas 6 views com `ensure_csrf_cookie` (`A3`) |
| `AuthenticationMiddleware` (`:377`) | **1 query** (`request.user`) quando há cookie de sessão de usuário |
| `AuthCustomerMiddleware` (`:384`) | `packages/doorman/shopman/doorman/middleware.py:29-46`: sai **sem query** para anônimo; autenticado paga `CustomerUser.objects.filter(user=user).first()` (`:62`) + adapter (`:70`). Pula `/admin/`, `/api/v1/backstage/`, `/api/v1/storefront/continuum/` (`:19-23`) |
| `SessionRenewalMiddleware` (`:381`) | quase-zero: sai em `is_operator_session` falso (`backstage/services/operator_session.py:118-119`); máx. 1 gravação/dia para operador |
| `OnboardingMiddleware` (`:389`) | sai cedo fora de `/admin/` (`backstage/middleware.py:37-38`) |
| **`shopman/storefront/middleware.py` `ChannelParamMiddleware`** (`:388`) | `middleware.py:27-33`: corpo inteiro = `request.GET.get("channel")` + `request.session`. **Zero query.** Ressalva: está **depois** do `SessionMiddleware`, então a `:31` provoca 1 escrita — só na primeira visita com `?channel=` |
| `APIVersionHeaderMiddleware` (`:392`) | `shop/middleware.py:110-114`: `response["X-API-Version"] = 1`. Barato |
| `HistoryRequestMiddleware`, `MessageMiddleware`, `XFrameOptionsMiddleware`, `CSPMiddleware`, `WhiteNoise` | sem query em API (`WhiteNoise` só I/O de disco em `/static/`) |

**Custo fixo antes de a view começar (API autenticada):** ~3–4 queries. Para o visitante **anônimo** da loja: sessão (1 read) + `request.user`, sem `CustomerUser`. [DELEGADO]

**Exceção que merece atenção:** `djangoProxy.ts:58-82, 191-196` — em **método inseguro sem cookie `csrftoken`**, o BFF faz uma chamada **extra** ao Django (`GET /api/v1/storefront/cart/`) só para obter o CSRF. São **duas idas ao `api.` por mutação**. [FATO]

**Risco latente registrado (`A3`, item 4 da tabela):** `copy._DB_CACHE` é **global de processo** (`shop/omotenashi/copy.py:1524-1554`) — com N workers, o `invalidate_cache()` do signal limpa só o worker que salvou. Edição de copy no Admin pode não propagar até um restart. [DELEGADO: mecanismo FATO, consequência INFERÊNCIA]
Também [DELEGADO]: `build_copy(namespace)` (`shop/projections/copy.py:78-94`) itera **todas** as 354 chaves de `OMOTENASHI_DEFAULTS` e chama `resolve_copy` para cada uma — não custa query (o DB está memoizado), mas é CPU proporcional ao registry inteiro a cada projeção (`build_copy("TRACKING")` filtra 354 chaves para aproveitar 167 `TRACKING_*`).

---


## 4. O que já existe e funciona (não reinventar)

1. **N+1 do cardápio: morto, com prova.** `docs/plans/completed/STOREFRONT-CATALOG-NPLUS1-PLAN.md` — `build_catalog` foi de **111 → 40 queries** (fixture 16 SKUs), e o teste novo prova que o custo **não escala com produtos**: 6 produtos → 27 queries; 66 produtos → 27 queries. Guardas de regressão vivas: `shopman/storefront/tests/web/test_catalog_nplus1_measure.py:234` (`assert n <= 55`) e `:297` (`assert n_big - n_small <= 3`). As 4 origens eram: tags (taggit), promoções/cupons por SKU, `components.exists()` de bundle, e — a hipótese que estava **errada** — `availability_for_skus` no Core do Stockman, que fazia `get_sku_info` por SKU; o fix foi o método batch `get_sku_infos(skus)` no protocolo. [FATO]
2. **Shell desacoplado do catálogo — PR #1215**, merge commit `664a57b93`, commits `8e8328c62` (*"perf(storefront): liberar shell antes do catálogo"*, +340/−89, 27 arquivos) e `2edef9cda` (*"fix(storefront): tornar cache de identidade explícito"*). Criou `/api/v1/storefront/shell/` (`api/urls.py:101`), `build_shell()` e `useStorefrontShell.ts`; `/menu` migrou de `menu/` para `catalog/` com `include_cart = False` (`surface.py:524-527`), eliminando a reconstrução da sacola. [FATO]
3. **Health check que não renderiza a home.** `9db070e64` criou `surfaces/storefront-nuxt/server/routes/health/live.get.ts` (constante, sem Django); `.do/app.alpha-subdomains.yaml:828,838,919,1063,1075,1154,1164` usam `http_path: /health/live`. Isso mata as **5.760 renderizações de SSR/dia** que o `WP-PERFORMANCE` `3.1` identificou. [FATO]
4. **Instrumentação de catálogo.** `capture_catalog_timing()` + `catalog_stage()` (`observability.py:26-99`), com `Server-Timing` propagado até o BFF e log estruturado **allowlisted** (sem payload/SKU/pessoa). Falta só ligar na home. [FATO]
5. **Snapshot Continuum**, cacheado (Redis, TTL 300 s) com read model materializado (`CatalogStructureHead`) e ETag: `test_continuum_catalog.py:332-343` prova **≤ 2 queries** no caminho quente, estritamente menos que o menu canônico. `03-continuum-impacto.md` mediu ao vivo `projection;dur=172,94 ms`, `db;dur=7,89 ms`, 1 query. [FATO]
6. **Guarda-corpos de performance no frontend**, travados em teste: `tests/performanceGuardrails.test.ts` (shell independente da home; `:53-78` fixa `lazy: true` em 14 páginas e `sacola.vue` sem `await useFetch(cart)`). [FATO]
7. **Orçamento local de mutação**, medido e com teto no teste: p95 **28,98 ms** (SQLite) e **36,41 ms** (PostgreSQL), máximo 456 ms, budget 1500 ms — `shopman/storefront/tests/test_operational_budget.py:34-40` e `docs/reports/storefront-operational-20260910/continuation-postgres-budget.txt`. [FATO] O `WP-PERFORMANCE` usa a distância entre esses 36 ms e o ~1 s observado no ar como o alvo da investigação.
8. **Batching do cardápio já feito e comentado, não mexer** [DELEGADO]: `presentation/catalog.py:437-468` encadeia `own_holds_by_sku`, `collection_refs_by_sku`, `primary_collection_by_sku`, `label_attributes_by_sku`, `listing_price_map`, `_availability_states` (1 lote) e `_active_storefront_promotions`. Duas economias deliberadas a conhecer antes de mexer: `catalog.py:487` passa `list_unit_price_q=base_q`, fazendo `CatalogService.get_price` **pular** `unit_price()` (`packages/offerman/shopman/offerman/service.py:142-143`) e com ele as 2 queries de `_get_price_from_listing` (`:194-207`); e `catalog.py:468` injeta `context["active_promotions"]` de modo que `PromotionPricingBackend.get_price` (`shopman/shop/adapters/pricing.py:57-62`) **não** consulte.
9. **Batching no backbone de leitura** [DELEGADO]: `catalog_context.py:135` (`products_by_sku`), `:175`, `:305` (`published_products`, `prefetch_related("keywords","components")`), `:230,242,262,272` (`select_related`), `:353`, `:1011-1012`; `.only(...)` em `shop/projections/cart.py:356,375,397`, `checkout.py:67`, `order_tracking.py:916`; `suggestions.py:215,261,648`. **A camada `storefront/presentation/` e `storefront/api/` tem ZERO `select_related`/`prefetch_related`** — todo o batching vive em `shop/projections/` e nos packages. Isto é bom sinal (o app não faz lazy-loading de FK na projeção), mas significa que um N+1 novo ali não tem guarda local. [FATO, grep = 0]

---

## 5. Ranking de suspeitos por impacto provável no TPV percebido

Ordenado por **impacto ÷ esforço**. "TPV percebido" = tempo até a primeira tela útil na loja, no celular, medido de fora.

| # | Suspeito | Impacto | Esforço | Evidência |
|---|---|---|---|---|
| **1** | **Estágio `availability` do cardápio: até 3 passadas + loop Python por SKU** | **Altíssimo** — 1,49–1,95 s medidos; 52–60% do `projection` | **M–L** (mexe em disponibilidade de produto com preço/estoque) | §0, §A0 |
| **2** | **O resto do `build_catalog`** (`projection` − `availability` − `personalization` = 0,4–2,1 s) | Alto | M–L | §A0 |
| **3** | **CPU por SKU: o custo cresce com o catálogo, não com o request** — +33% de corpo desde 17/09 | Alto (define se +produto = +latência) | M (medir primeiro: §A0) | §0.1, §A0.2, §5.4 |
| **4** | **Ausência de cache na leitura pública + `ensure_csrf_cookie` bloqueando a borda** | Alto (custo por visitante e contenção do container único) | **M** (tem cerca de correção/privacidade) | §A3 |
| **5** | **`Server-Timing` ausente na home/shell/cart/checkout/tracking/conta** | Alto **como habilitador** — sem ele, os itens 1–3 daqui não se medem nas outras rotas | **XS** (a infra existe) | §A4 |
| **6** | **Dois lookups de `Channel` sem cache por request** (`is_channel_active`, `for_channel`) | Baixo por si; **explica 100.974 seq scans/dia** que o WP marcou como "causa não identificada" | **XS** | §A0.3 |
| **7** | **A home constrói shell 2× e sacola 2×** — real, mas limitada a <0,85 s pelo §0.2 | Médio-baixo | **XS–S** | §A1, §0.2 |
| **8** | **N+1 do histórico da conta** (`order.items.count()` por pedido, ~53 queries) | Alto na tela que o cliente reabre | **XS–S** (o fix já existe no repo) | §A5.1 |
| **9** | **I/O de gateway dentro do `GET /tracking/<ref>/`** | Médio-alto (rota com SSE + poll) | **M** (idempotência de pagamento) | §A5.2 |
| **10** | **Imagens cruas de 1200 px + 1,04 MiB órfãos + SW que não casa origem** | Médio-alto (LCP) | **S** a **M** | §A8 |
| **11** | **Cascata serial de 2 estágios no SSR** | Médio (limitada: o delta do SSR da home é 0,67–0,84 s) | **M–L** | §A2, §0.2 |
| **12** | **BFF→Django pelo host público (hairpin com TLS e borda)** | Médio (afeta todas as chamadas; **não medido** nestas amostras) | **M** (4 riscos) | §2 |
| **13** | **Bundle: shell inteiro no entry chunk, sem `<Lazy>`/`import()`, `sizeLimitKb: 0`, 5 deps mortas** | Médio (LCP/hidratação) | **S** | §A9 |
| **14** | **Acompanhamento: query de evento duplicada, fulfillments lidos 2×, PDP com ~15 queries** | Médio | **S–M** | §A5.3, §A5.5 |
| **15** | **`sitemap.xml` sem cache chamando o menu canônico** | Baixo-médio | **XS** | §A7 |
| **16** | **Gzip da home por visitante, no event loop** | Baixo-médio | **S** (some se o item 4 entrar) | §A10 |

**Nota de honestidade sobre o ranking:** os itens 1–3 são onde estão os segundos; a maior parte da minha análise estática (§A1–A11) descreve **trabalho que não precisava existir**, mas cujo valor absoluto em ms é menor. A evidência ao vivo reordenou este ranking — a versão anterior deste relatório punha a duplicação da home em primeiro lugar.

**Não é suspeito, e vale registrar:** o **BFF não é o vilão** — `WP-PROGRESSIVE` `3` mediu e concluiu *"O BFF não apareceu como o principal vilão; a projeção Django e o contrato agregador dominam o caminho"*. [FATO documental]

### 5.4 A regressão de 17/09 → 29/09: o que mudou no caminho de leitura

A evidência ao vivo mostra 2–2,5× de piora em 12 dias. O que os commits dizem sobre essa janela (`git log --since=2026-09-16 --until=2026-09-30`, HEAD `f0ffd02`), filtrando o caminho de leitura:

| Data | Commit | O que faz |
|---|---|---|
| 17/09 | `0fa3433a8` | *"a régua do esgotado honesto vira UMA função, com lote reutilizável"* — **cria** `_availability_states`, `_resolve_availability`, `pause_and_notifiability` (+141/−43 em `catalog.py`) |
| 22/09 | `da87edb48` | *"a home lê o toggle pelo lado de leitura"* — põe `accepting_orders()` (**1 query a `Channel`**) dentro do `build_shell` |
| 22/09 | `b55ce2050` | *"Canais: um toggle Ativo em todo card"* — a máquina do toggle |
| 28/09 | `0863be932` | **"add Continuum catalog shadow snapshot"** — cria `observability.py`, **`catalog_stage("availability")`** e `capture_catalog_timing` em `surface.py`; mexe 36 linhas de `catalog.py`; adiciona 7 hooks `post_save`/`post_delete` |
| 28/09 | `8e8328c62` | o split do shell (PR #1215) |
| 28/09 | `f4baa5fe4`, `5715ff3cf` | ajustes do Continuum |

[FATO] Duas consequências mudam a leitura da regressão:

1. **O `Server-Timing` nasceu em 28/09** (`git log -S 'capture_catalog_timing' -- shopman/storefront/api/surface.py` → só `0863be932`), e com ele o `catalog_stage("availability")`. O baseline de 17/09 **não tinha como se explicar** — não há série histórica de `availability_ms` para comparar. Qualquer atribuição da regressão a um commit é, hoje, [INFERÊNCIA].
2. **O catálogo cresceu 33%** (103 KB → 136,7 KB). Como o estágio `availability` é `O(produtos)` em CPU (§A0.2), **crescimento de catálogo cobra juros** — o que é uma explicação estrutural, não um commit culpado.

**Bisect honesto, sem adivinhação** — a ordem importa:

```bash
# 1) Ler a série que já existe no log (decide CPU vs banco vs passadas) — §A0.
doctl apps logs <web-app-id> --type run | grep storefront_catalog_observation

# 2) Variar o DADO antes de culpar código: o custo acompanha o nº de SKUs?
#    Comparar availability_ms e query_count em /menu/ (todos os SKUs) contra
#    /storefront/catalog/<uma-colecao>/ (subconjunto). Se availability_ms cair
#    proporcionalmente e query_count não, é CPU por SKU — e o suspeito é o dado
#    + o refactor de 17/09, não os commits de 28/09.

# 3) Só então isolar código, por um caminho sem worktree nem banco de produção:
#    ligar a fila e os bundles um de cada vez (waitlist.is_enabled, bundle no cardápio)
#    e ler o query_count do log. Cada passada extra tem assinatura própria.

# 4) pg_stat_statements (P0 do WP-PERFORMANCE, ainda não instalado) fecha o caso:
#    SELECT query, calls, total_exec_time FROM pg_stat_statements ORDER BY 3 DESC LIMIT 20;
```

---

### Como medir cada um em produção — receita única

```bash
# (0a) A leitura que decide tudo: o log que JA carrega CPU vs SQL por estagio.
#      NAO ha' nada a instrumentar — surface.py:495-513 ja emite isto no alpha.
doctl apps logs <web-app-id> --type run | grep storefront_catalog_observation
#   availability_ms alto + query_count baixo + db_ms baixo  => CPU por SKU  (§A0 caso A)
#   query_count alto (dezenas)                              => 2a/3a passada (§A0 caso B)
#   db_ms ~= availability_ms                                => banco         (§A0 caso C)

# (0) Linha de base externa, do Brasil, 20 amostras, p95. E o numero do SLO.
for u in https://www.nelsonboulangerie.com.br/ \
         https://www.nelsonboulangerie.com.br/menu \
         https://www.nelsonboulangerie.com.br/sacola \
         https://api.boulangerie.com.br/api/v1/storefront/home/ ; do
  echo "== $u"
  for i in $(seq 20); do
    curl -so /dev/null -w '%{time_starttransfer}\n' -H 'accept-encoding: gzip' "$u"; sleep 1
  done | sort -n | awk '{a[NR]=$1} END{printf "p50=%.3f p95=%.3f max=%.3f\n",a[int(NR*0.5)],a[int(NR*0.95)],a[NR]}'
done

# (1 e 3) Itens 1 e 3: ver Server-Timing e comparar shell vs home.
curl -sI https://api.boulangerie.com.br/api/v1/storefront/shell/ | grep -i server-timing
curl -sI https://api.boulangerie.com.br/api/v1/storefront/home/  | grep -i server-timing
# Depois de instrumentar: db;dur de home ~= db;dur de shell + catalogo.
# Se o shell aparecer duas vezes, projection;dur de home sera ~= 2x o de shell + catalogo.

# (2) Item 2: provar ausencia de cache e o Set-Cookie que a impede.
curl -sI https://www.nelsonboulangerie.com.br/ | grep -iE 'cf-cache-status|cache-control|vary|set-cookie|age'

# (4) Item 4: o N+1 do historico, pelo lado do banco.
#   SELECT query, calls FROM pg_stat_statements
#   WHERE query ILIKE '%COUNT(*) FROM "orderman_orderitem"%' ORDER BY calls DESC LIMIT 5;
#   Comparar calls antes/depois de abrir /conta e /account/orders/.

# (5) Item 5: a curva, nao a media, no acompanhamento.
for i in $(seq 10); do curl -sS -o /dev/null -w '%{time_total} %{http_code}\n' \
  "https://www.nelsonboulangerie.com.br/api/v1/tracking/<ref>/"; done

# (6) Item 6: a cascata, vista do navegador.
# DevTools > Performance em "Slow 4G": o request home/ comeca DEPOIS do fim de shell/.

# (7) Item 7: LCP e byte das fotos.
curl -sI https://img.nelsonboulangerie.com.br/products/cgr2.webp | grep -iE 'content-length|cache-control'
# Lighthouse mobile em /menu: "Properly size images" e "Serve images in modern formats".
# Application > Cache Storage: 'storefront-product-images' populado?

# (8) Item 8: o hairpin, medido de dentro do container (unica forma).
#   doctl apps console storefront-nuxt
#   for i in $(seq 20); do curl -so /dev/null -w '%{time_starttransfer}\n' \
#     https://api.boulangerie.com.br/api/v1/storefront/shell/; done
#   comparar com o mesmo curl no PRIVATE_URL do servico web.

# (9) Item 9: bundle.
cd surfaces/storefront-nuxt && npm ci && npm run build && ls -lS .output/public/_nuxt | head -20

# (11) Item 11: sitemap.
doctl apps logs <app-id> --type run | grep -c sitemap

# (13) Item 13: gzip.
curl -s -o /dev/null -D- -H 'accept-encoding: gzip' https://www.nelsonboulangerie.com.br/ \
  | grep -iE 'content-encoding|content-length|vary'
```

---


## 6. Lacunas, riscos e o que não consegui verificar

### 6.1 Riscos de agir errado

- **Cache é cerca, não oportunidade.** `STOREFRONT-CATALOG-NPLUS1-PLAN.md` rejeitou cachear `build_catalog` com motivo de correção e privacidade (preço por `price_tier`/`customer_segment`, favoritos, quantidades no carrinho). Cachear a home ou o shell tem o **mesmo** problema: `build_shell` inclui `origin_channel`, `omotenashi.customer_name`, `marketing_prompt_pending` e `public_config.google_maps_api_key`. **A cerca é: cachear estrutura pública, nunca estado de sessão.** [FATO]
- **O `web` é 1 vCPU/1 GiB para loja + Admin + 7 hosts de operador.** [FATO, `WP-PERFORMANCE` `2.5` e `.do/app.alpha-subdomains.yaml:834-839`] Qualquer ganho de CPU no storefront é ganho direto no PDV/KDS, e qualquer regressão também. Não trate o storefront como um app isolado.
- **Streaming muda o ranking.** Se o SSR já faz streaming (`experimental.renderStreaming`), o item 6 cai e os itens 1 a 3 sobem; se não faz, o item 6 é o maior. **Não consegui confirmar o default no Nuxt 4.5.2** — `6.2-Q`1.
- **Medir antes de otimizar as telas sem instrumentação.** Conforme `A4`, home, PDP, sacola, finalizar, acompanhamento e conta têm **zero** `Server-Timing`. Otimizar essas telas por intuição repete o problema que o `WP-PERFORMANCE` já nomeou — *"não é a máquina, é trabalho que não precisava existir"* — mas sem medir não se sabe **qual** trabalho.

### 6.2 O que não consegui verificar

| # | Pergunta | Por que não | Onde procurei |
|---|---|---|---|
| Q1 | **`experimental.renderStreaming` está ligado no Nuxt 4.5.2?** Decisivo para o peso do `A2`. | Sem `node_modules`/`.output` no worktree; `web_search` deu timeout (60 s). | `grep -rn` de "renderStreaming|experimental" em `surfaces/*/nuxt.config.ts` retorna vazio: nenhuma surface configura. Nuxt travado em **4.5.2** (`package.json:36`, `package-lock.json:14324-14327`). |
| Q2 | **`lazy: true` + `await` bloqueia o SSR?** | Sem o código do Nuxt para ler. | `useStorefrontHome.ts:30`, `finalizar.vue:297`, `pedido:56`; guarda em `performanceGuardrails.test.ts:53-79`. |
| Q3 | **Tamanho real do bundle e do precache** | Sem build. | `node_modules`, `.nuxt` e `.output` ausentes em `surfaces/storefront-nuxt/`. |
| Q4 | **Custo em ms de `build_shell` isolado** | Exatamente o que o `A4` diz não estar instrumentado. | `grep -n "Server-Timing" shopman/storefront/api/surface.py` -> só `:492` (menu). |
| Q5 | **Contagem de queries do `/storefront/home/`** | Não rodei teste (poderia tocar banco). | Só existem harness de `build_catalog` (`test_catalog_nplus1_measure.py`) e do snapshot (`test_continuum_catalog.py:332`). **Não há `assertNumQueries` para home, shell, cart ou checkout.** |
| Q6 | **Se o `$fetch` interno do SSR ao BFF é loopback HTTP ou in-process** | Sem o código do Nuxt. | `server/api/v1/[...path].ts`, `djangoProxy.ts`. Decide se há um hop de rede **a mais** além do hairpin BFF para Django. |
| Q7 | **Se as fotos em produção vêm do host `img.` ou de `images.unsplash.com`** | Exige ler o banco ou o HTML de produção. | `seed.py:1834-1848` mostra os dois caminhos; `.do/app.alpha-subdomains.yaml:68-75,804-806` mostra o ingress. |
| Q8 | **O `lazy` como garantia:** `performanceGuardrails.test.ts` prova a **presença** da string `lazy: true` por arquivo, não o efeito. É teste de forma, não de comportamento. | Leitura do teste. | `performanceGuardrails.test.ts:53-79`. |
| Q9 | **Números de queries do `A5`** (histórico cerca de 53, acompanhamento cerca de 12 a 18, PDP cerca de 15) | São [INFERÊNCIA] derivada de código [FATO] (`limit=50`, as chamadas de serviço, os `.count()`). Não executei nada contra banco, nem `shell`, nem `migrate`, nem teste. | `customer.py:108-118`, `api/account.py:843-863`, `order_tracking.py:1376-1397`, `product_detail.py`. Os comandos de confirmação estão em `A5.1` a `A5.4`. |
| Q10 | **A fila de espera (`waitlist`) está ligada no alpha?** Decide se há 2ª passada de disponibilidade (§A0.1). Default é `enabled=False` (`shop/services/waitlist.py:21`). | Não li config de produção além dos specs `.do/`; não há env `WAITLIST` neles. | `grep -n -i waitlist .do/*.yaml` → vazio; `shop/services/waitlist.py:40-70`; `config/settings.py` → vazio. Pode vir de `Shop.defaults`/`Channel.config` no banco — **exige leitura de dado**. |
| Q11 | **Qual caso do §A0 é o real: CPU, passadas extras, ou banco?** | Exige ler o log do alpha; não tenho acesso. | `logger:shopman.storefront.continuum` + `storefront_catalog_observation`, campos `availability_ms`/`db_ms`/`query_count` (`surface.py:495-513`). |
| Q12 | **Há bundle no cardápio do alpha?** Se houver, há uma 3ª passada de disponibilidade (§A0.1). | Exige ler dado de produção. | `catalog_context.bundle_availability_for_skus` (`:772`), chamado em `catalog.py:620` só para SKUs com `is_bundle`. |


---


### 6.3 Não encontrado (procurado e inexistente)

- **Nenhum `select_related` ou `prefetch_related` em `shopman/storefront/presentation/` nem em `shopman/storefront/api/`** — o grep por esses termos retorna **0 resultados**. As otimizações vivem em `shopman/shop/projections/catalog_context.py` (helpers batch: `products_by_sku:131`, `image_urls_by_sku:214`, `collection_refs_by_sku:224`, `primary_collection_id_by_sku:235`, `listing_price_map:331`, `listing_sellable_map:364`) e nos adapters dos packages. [FATO]
- **Nenhum `cache_page` no storefront.** [FATO] **Nenhum `cached_property`.** [FATO]
- **Nenhuma menção de latency ou lentidão em `docs/reports/` com medição de SSR fora do `WP-PERFORMANCE`.** O material vivo é: `docs/plans/WP-PERFORMANCE-2026-09.md` (367 linhas, medição de 17/09), `docs/plans/WP-PROGRESSIVE-SSR-SSE-CONTINUITY.md` `3` (medição de 27/09), `docs/plans/completed/STOREFRONT-CATALOG-NPLUS1-PLAN.md` (executado 01/08), `docs/reports/continuum-0.2-shopman-pilot-20260928.md`, `docs/reports/STOREFRONT-OPERATIONAL-EXCELLENCE-EXECUTION-2026-09-10.md`. [FATO]
- **A branch `codex/storefront-live-latency-20260928` está inteiramente em main.** O comando `git merge-base --is-ancestor` responde **sim**, e `git log origin/main..<branch>` e `git diff --stat origin/main...<branch>` saem **vazios, por construção**. Merge: `664a57b93` (PR **#1215**). **O vazio não é ausência de trabalho** — é trabalho já mergeado. [FATO]
- **Não existe SLO de frontend com LCP ou INP.** O único SLO de latência está no `WP-PERFORMANCE` `4` (TTFB) e no `6.2` do `STOREFRONT-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md` (budgets de interação: feedback menor ou igual a 100 ms, pendente acessível menor ou igual a 300 ms, mutação local p95 menor ou igual a 1,5 s, reconciliação consultável menor ou igual a 5 s). A percepção do cliente final, LCP e hidratação, continua **não medida**: o `WP-PERFORMANCE` `7` diz explicitamente que latência vista do navegador ficou fora do escopo de curl e que o harness Playwright do storefront pode medi-la. [FATO]
- **Não existe teste de contagem de queries para home, shell, cart ou checkout.** O grep por `assertNumQueries` e `CaptureQueriesContext` em `shopman/storefront/tests/` só encontra o harness de `build_catalog` e o do snapshot Continuum. [FATO]

---

### 6.4 Quem mediu o quê (limitação declarada)

- **A evidência ao vivo da §0 é do dono da tarefa**, medida em 2026-09-29 ~16:20 UTC contra o alpha. **Eu não a reproduzi** — não medi produção, não tenho acesso ao log do alpha nem ao banco.
- **Minhas medições são de leitura**: `read`/`grep`/`glob`, `git log/show/merge-base` read-only, `wc -c`, `du`. **Não rodei `pytest`, `manage.py` nem `curl`.**
- Os números de 17/09 e 27/09 vêm de `docs/plans/WP-PERFORMANCE-2026-09.md` e `docs/plans/WP-PROGRESSIVE-SSR-SSE-CONTINUITY.md`, citados com data.
- As seções de N+1 e de bundle/imagens marcadas **[DELEGADO]** vieram de auditoria delegada com o mesmo padrão de evidência; spot-checkei por conta própria o que decidia prioridade (zero `select_related` na camada storefront, `Server-Timing` em só 2 views, o middleware de `settings.py`, o fan-out por página, o `sitemap.xml` sem cache, os caminhos `/health/live`).
- **O que mudou com a evidência ao vivo:** o ranking da §5 foi reordenado (a duplicação da home caiu de 1º para 7º), a §0 foi acrescentada, e a §A0 (aritmética dos estágios) e a §5.4 (janela da regressão) são novas.

---

## 7. Próximos passos sugeridos (menor risco primeiro)

1. **Ler o log `storefront_catalog_observation` no alpha.** Custo zero, nenhum código, e é o que decide qual dos três casos do §A0 é o real. Sem isto, os passos 3 a 5 são chute.
2. **Checar as passadas extras de disponibilidade:** `waitlist.is_enabled` para o canal da loja (§6.2-Q10) e se há bundle no cardápio (§6.2-Q12). São a 2ª e a 3ª passada completa de `availability_for_skus` dentro do estágio mais caro (§A0.1) — e são as duas causas que **não** aparecem no banco.
3. **Cachear os dois lookups de `Channel`** (`is_channel_active`, `ChannelConfig.for_channel`). É `O(1)` de código e explica 100.974 seq scans/dia numa tabela de 6 linhas que o `WP-PERFORMANCE` §3.8 marcou como "causa não identificada" (§A0.3).
4. **Ligar `capture_catalog_timing()` em `StorefrontHomeView`, `StorefrontShellView`, `StorefrontCartView`, `StorefrontCheckoutView` e `OrderTrackingView`.** Mesmo context manager já usado no menu; sem isso os passos seguintes não têm como se medir nas outras rotas. (§A4)
5. **Atacar o estágio `availability` conforme o caso lido no passo 1** — cortar passadas redundantes e trabalho por SKU (caso A/B), ou `pg_stat_statements` + índice (caso C). É o item 1 do ranking e onde estão ~1,5–1,9 s medidos. Pela cerca do §A3, **nunca** cacheando projeção personalizada.
6. **Ligar `pg_stat_statements` e `log_min_duration_statement`** (P0 do `WP-PERFORMANCE`, ainda não feito — §2.3 daquele doc). É o que fecha o caso C e o N+1 do item 8.
7. **Tirar `ensure_csrf_cookie` do GET anônimo** de home, shell, menu e produto, e então cachear a **estrutura pública** do cardápio (nunca estado de sessão — a cerca do §A3). (§A3)
8. **`.annotate(item_count=Count("items"))` no histórico da conta**, com `assertNumQueries` como trava. O padrão batch já existe em `order_composition.py:169-196`. (§A5.1)
9. **Imagens:** remover os 1,04 MiB órfãos de `public/img/home/`, corrigir o ramo invertido do hero em `HomeHeroThing.vue:42`, e dar `routeRule` de cache ao caminho `/img/home/`. (§A8)
10. **Bundle:** tirar `qrcode`, `nostics`, `@internationalized/number`, `tailwind-merge` e `motion-v` do `package.json` se o uso zero se confirmar, e decidir o `sizeLimitKb` do `@nuxt/icon`. (§A9)
11. **`cachedEventHandler` com ETag em `sitemap.xml.ts`.** (§A7)
12. **Medir LCP e INP com o harness Playwright do storefront** antes de investir no item 11 do ranking (cascata e streaming): hoje não há nem linha de base de percepção.
