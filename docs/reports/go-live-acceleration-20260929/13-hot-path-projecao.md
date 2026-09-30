# 13 — O hot path da projeção do cardápio: por que `GET /api/v1/storefront/menu/` custa ~3 s

**Árvore canônica:** `.dsh-worktrees/go-live-acceleration` (origin/main = `f0ffd02fde765493d734bae93a72bb361ed28fcf`, 29/09/2026 15:36 UTC; `git status --porcelain` vazio).
**Banco de bancada:** `/tmp/dsh_prof/prof.sqlite3` (criado por mim com `manage.py migrate` + `manage.py seed` a partir da worktree). Nada do repositório foi editado além deste arquivo.
**Legenda:** `[FATO]` verificado em código com `arquivo:linha` ou em saída de comando · `[INFERÊNCIA]` dedução minha, com a conta à mostra · `[NÃO VERIFICADO]` não consegui confirmar.

---

## 1. Resposta curta

1. **A projeção do cardápio faz 93 consultas e responde 135 KB para 44 cards. Nenhuma das duas coisas é necessária.** `[FATO]` (medido na bancada; o próprio repositório já escreve "96-query catalog rebuild" em `shopman/storefront/continuum.py:196`).
2. **O estágio `availability` (1,2–1,4 s em produção) é o mesmo cálculo caro feito QUATRO vezes por request, e o custo dele é O(número de linha de `stockman_quant`), não O(número de SKUs).** `[FATO]` Medido: com 322 quants o estágio custa 26 ms; com 2.472 quants, 121 ms — e as 4 chamadas que o compõem custam 50,2 + 48,9 + 25,5 + 4,4 ms.
3. **`home/` paga a construção INTEIRA do cardápio para guardar 3 cards.** `[FATO]` `build_home()` chama `build_catalog()` (`shopman/storefront/presentation/home.py:379`): 97 consultas, 67,9 ms locais, contra 4 consultas e 2,4 ms do `shell/` — que existe exatamente para não fazer isso.
4. **O loop de preço por SKU (`catalog.py:471`) é O(N) mas trivial: 45 chamadas custam 0,39 ms e ZERO consultas.** `[FATO]` Não é o gargalo. As promoções já vêm pré-carregadas no contexto.
5. **A projeção NÃO mudou de código entre 17/09 e 29/09.** `[FATO]` `git diff 836066e1c..HEAD` em `catalog.py`/`catalog_context.py`/`availability.py` só mostra instrumentação de tempo e uma função nova não usada pelo cardápio. A piora de ~2x é **dado + carga + contenção**, não regressão de código:
   - o cardápio servido cresceu ~33% (103 KB → 136,7 KB; ~33 → 44 cards);
   - as tabelas de estoque crescem a cada dia de produção e a disponibilidade as lê **inteiras, 4 vezes por request**;
   - o mesmo container `web` (1 vCPU **compartilhada**, 1 GiB) passou a servir, por aba aberta de `/menu`, **dois polls de 30 s** que reconstroem o catálogo canônico (`useContinuousProjection.ts:91-101` + `menu.vue:260-267`, este último introduzido em `02b4f1487`) e reconstruções do snapshot a cada 5 min (`continuum.py:251-260`).
6. **`shadow;dur=0.00` NÃO prova que o shadow não rodou: o campo é incondicional** (`observability.py:26-33`). `[FATO]` Prova, isso sim, é `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED='false'` no spec do alpha (`.do/app.alpha-subdomains.yaml:367-370`).
7. **O maior ganho disponível não é otimizar Python: é parar de recalcular.** `[FATO]` No **mesmo app, mesma borda, mesma família de endpoint**, o snapshot estrutural responde **0,151 s em HIT de Cloudflare** contra **2,59 s em MISS** (`cache-control: public, max-age=30, s-maxage=30`, `vary: Accept`). O `menu/` responde `cache-control: private`, `vary: Accept, Cookie`, `set-cookie: csrftoken` → `cf-cache-status: BYPASS`. O alvo de < 0,6 s é alcançável hoje, sem tocar em uma linha de Python.

---

## 2. Como medi

### 2.1 Bancada (local, reprodutível)

```bash
WT=/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration
PY=/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python
PP="$WT:$WT/packages/buyman:$WT/packages/cashman:$WT/packages/craftsman:$WT/packages/doorman:$WT/packages/fiscalman:$WT/packages/guestman:$WT/packages/offerman:$WT/packages/orderman:$WT/packages/payman:$WT/packages/refs:$WT/packages/stockman:$WT/packages/utils:/tmp/dsh_prof"
cd $WT && PYTHONPATH="$PP" DATABASE_URL='' DJANGO_SETTINGS_MODULE=settings_prof $PY manage.py migrate --noinput
cd $WT && PYTHONPATH="$PP" DATABASE_URL='' DJANGO_SETTINGS_MODULE=settings_prof $PY manage.py seed
```

`settings_prof` é um módulo em `/tmp/dsh_prof` que herda `config.settings_test` e aponta `DATABASES` para `/tmp/dsh_prof/prof.sqlite3` (o `.venv` da raiz tem editable installs apontando para a árvore principal; com `PYTHONPATH` na frente, os módulos resolvem para a worktree — conferido imprimindo `shopman.offerman.__file__`).

**O banco de bancada tem dados de verdade** (não é o `db.sqlite3` vazio do repositório):

| inventário | valor | comparação com o vivo |
|---|---:|---|
| `offerman_product` | 131 (43 publicados) | menu vivo: 44 cards |
| `offerman_collection` ativas | 9 | menu vivo: 9 categorias |
| `offerman_listingitem` | 403 | — |
| `stockman_quant` | 327 (322 com `_quantity>0`) | **[NÃO VERIFICADO]** no alpha |
| `orderman_order` / `orderitem` | 4.659 / 9.298 (6.162 itens em 30 d) | WP §2.3 (17/09): 6.196 / 12.406 |
| corpo do `menu/` | **139.786 B** | vivo: **136.706 B** |

Ou seja: o catálogo local é representativo do vivo (mesma ordem de tamanho de payload e de cards). **O tempo absoluto não é** — sqlite local sem rede roda o mesmo request em 72 ms; em produção ele custa 2,46 s. O que transfere é a **estrutura** (contagem de consultas, chamadas repetidas, escalas) e a **razão** entre as etapas.

### 2.2 Produção (só GET, meu, 29/09/2026 ~14:40 UTC)

```bash
curl -s -D - -o /dev/null -w 'TTFB %{time_starttransfer}s\n' https://api.boulangerie.com.br/api/v1/storefront/menu/
```

---

## 3. O caminho real de `GET /api/v1/storefront/menu/`

### 3.1 Etapas cronometradas (o que o `Server-Timing` mede)

| # | onde | o que roda | estágio |
|---|---|---|---|
| 1 | `shopman/storefront/api/surface.py:459` | `capture_catalog_timing()` instala `connection.execute_wrapper` (`observability.py:50-67`) — conta **toda** consulta do request | — |
| 2 | `surface.py:460-467` | `build_catalog(channel_ref="web", request=request)` | `projection` |
| 3 | `surface.py:468-472` | `projection_data(catalog)` + `_cart_payload(request)` | `personalization` |
| 4 | `surface.py:477-485` | `compare_shadow(...)` — **só se `shadow_enabled()`** | `shadow` |
| 5 | `observability.py:55-61` | wrapper soma o tempo de cada `cursor.execute` | `db` |
| 6 | `surface.py:492` | `response["Server-Timing"]` | — |

`projection` engloba `availability` e `personalization`; `db` atravessa todos. As três chaves são **acumuladores**, não irmãs (`CatalogTiming.add` soma por nome).

### 3.2 Dentro de `build_catalog` (`shopman/storefront/presentation/catalog.py:220`)

| linha | etapa | ms local | consultas |
|---|---|---:|---:|
| `239` | `ChannelConfig.for_channel("web")` (cascata defaults→Shop→Channel) | — | 2 |
| `241-242` | `OmotenashiContext.from_request` (`catalog_stage("personalization")`) | — | ~1 |
| `244` | `_build_categories()` → `active_collections()` | 0,57 | 1 |
| `250` | `_fetch_products_by_collection()` → `catalog_context.published_products_by_collection` | **17,45** | **27** |
| `255` | `popular_skus(limit=5)` → `InsightService.favorite_product_samples` | — | 1 |
| `256-263` | `session_pricing_hints`, `customer_pricing_hints`, `_cart_qty_by_sku`, `_favorite_skus`, `notify_subscribed_skus`, `_active_food_prefs` | (no estágio `personalization`) | 0 (anônimo) |
| `286-300` | `_build_items(...)` | ~79 | ~62 |
| `302` | `_build_sections()` | 0,02 | 0 |
| `306` | `_build_dynamic_sections()` → 3 resolvers | **4,28** | **4** |
| `312-325` | `happy_hour_state()`, `_catalog_empty_state()`, `_search_empty_state()` (`resolve_copy`) | — | 0 |

### 3.3 Dentro de `_build_items` (`catalog.py:418`)

| linha | etapa | ms local | consultas |
|---|---|---:|---:|
| `440` | `own_holds_by_sku` (0 quando não há sessão) | — | 0 |
| `443` | `collection_refs_by_sku` | 2,35 | 1 |
| `446` | `primary_collection_by_sku` | 2,18 | 1 |
| `450` | `label_attributes_by_sku` (alérgenos + dieta + porções) | 0,48 | 0 |
| `453` | `listing_price_map` | 1,82 | 1 |
| `457-463` | **`catalog_stage("availability")` → `_availability_states`** | **33,8** | **52** |
| `468` | `_active_storefront_promotions` → `services.promotions.get_active_promotions` | 1,33 | 4 |
| `471-564` | **laço por produto** (45 voltas para 43 SKUs publicados — ver adiante): `contextual_price` + `_search_terms` + `_dietary_warnings` | 0,39 (só o preço) | **0** |

### 3.4 As consultas, agrupadas

**93 consultas** por request, nesta proporção:

| bloco | consultas | origem |
|---|---:|---|
| `published_products_by_collection` | **27** | 1 consulta de produto + prefetch `keywords` + prefetch `components` × **9 coleções ativas** (`catalog_context.py:305-328`) |
| `availability` | **52** | 4 chamadas do batch do Stockman (10 consultas cada) + `waitlist` (23) |
| promoções | 4 | `Promotion` + prefetch `channels` |
| coleções/preços/atributos | 4 | `collection_refs`, `primary_collection`, `listing_price_map`, listing_sellable |
| resolvers dinâmicos | 4 | `featured` (2), `fresh_from_oven` (1), `new_arrivals` (1) |
| canal/loja/cópia/sessão | ~5 | `Shop.load`, `Channel.get`, `OmotenashiCopy`, `CustomerInsight` |

**Sensibilidade ao número de coleções ativas** (43 produtos, mesma base):

```
colecoes= 9  menu= 71,7 ms  queries=93      colecoes= 3  menu= 41,0 ms  queries=76
colecoes= 6  menu= 57,8 ms  queries=86      colecoes= 0  menu=  2,4 ms  queries= 5
```

→ **≈ 3 consultas por coleção ativa**. Nove coleções custam 27 consultas para montar seções que o cliente poderia agrupar a partir do campo `category` de cada card.

---

## 4. O estágio `availability` (~1,8 s): onde o tempo vai

### 4.1 A cadeia, com `arquivo:linha`

```
catalog.py:457  catalog_stage("availability")
catalog.py:458  _availability_states(products, channel_ref, own_holds, low_stock_threshold)
catalog.py:609    listing_sellable_map(skus, channel_ref)                    → 1 consulta
catalog.py:612    _batch_availability(skus, channel_ref)
catalog.py:713      catalog_context.availability_for_skus(skus, channel_ref=...)
catalog_context.py:634        get_channel_scope(channel_ref)  → ChannelConfig.for_channel → 2 consultas
catalog_context.py:650        stockman.availability_for_skus(skus, target_date=HOJE)   ← BATCH 1
catalog_context.py:655        waitlist.next_batch_availability_for_skus(skus, ...)
waitlist.py:111                   Quant ... target_date (hoje, hoje+2] distinct        → 1
waitlist.py:124-137               para CADA data candidata:
waitlist.py:127                     stockman.availability_for_skus(remaining, target_date=data)  ← BATCH 2 e 3
catalog_context.py:661        merge por SKU
catalog.py:617-621  bundle_skus → bundle_availability_for_skus(...)
catalog_context.py:797        stockman.availability_for_skus(component_skus, target_date=HOJE)  ← BATCH 4
```

E `packages/stockman/shopman/stockman/services/availability.py:352` `availability_for_skus`, em cada uma das 4 chamadas:

| linha | consulta | 1 chamada |
|---|---|---:|
| `387` | `validator.validate_skus(skus)` → `offerman/adapters/sku_validator.py:64` `Product.objects.filter(sku__in=...)` | 1 |
| `388` | `validator.get_sku_infos(skus)` → `sku_validator.py:122` `Product.filter(sku__in).prefetch_related("collection_items__collection")` | 3 |
| `404` | `Batch.objects.filter(sku__in, expiry_date__lt)` | 1 |
| `410` | `Batch.objects.filter(sku__in, quality_grade_ref__in)` | 1 |
| `420` | `Quant.objects.filter(sku__in, target_date__gt=hoje, ...).distinct()` | 1 |
| `432` | `Quant.objects.filter(sku__in).distinct()` — **sem filtro de quantidade nem de data** | 1 |
| `435-447` | `Quant.objects.filter(sku__in, _quantity__gt=0, target_date<=target).select_related("position")` + `list(...)` | 1 |
| `454-462` | `Hold.objects.filter(quant_id__in).values("quant_id").annotate(Sum)` | 1 |
| | **total por chamada** | **10** |

### 4.2 As 4 chamadas, medidas

> ⚠️ Os blocos abaixo **se sobrepõem** e não se somam: `waitlist.next_batch_availability_for_skus` roda *dentro* de `catalog_context.availability_for_skus`, e `bundle_availability_for_skus` chama o batch do Stockman de novo. O total do estágio é a linha do `Server-Timing` (`availability;dur`), não a soma das linhas.

Com 322 quants (seed recém-criado):

```
catalog_context.availability_for_skus          2 chamadas   28,19 ms  q=45
    (45 SKUs, hoje)                                         25,14 ms  q=34
    (2 SKUs, hoje — componentes do bundle)                    3,05 ms  q=11
waitlist.next_batch_availability_for_skus      1 chamada    15,00 ms  q=23
stockman.availability_for_skus                 4 chamadas   25,83 ms  q=40
    (45 SKUs, 2026-09-29)   9,57 ms      (41 SKUs, 2026-09-30)   9,09 ms
    (20 SKUs, 2026-10-01)   4,43 ms      ( 2 SKUs, 2026-09-29)   2,74 ms
offerman.validate_skus                         4 chamadas    3,89 ms  q=4
offerman.get_sku_infos                         4 chamadas    9,49 ms  q=12
```

Com 2.472 quants (`bulk_create` de 50 quants por SKU publicados, dentro de transação revertida):

```
sav.availability_for_skus: [(45, 50,23 ms, '2026-09-29'), (41, 48,91 ms, '2026-09-30'),
                            (20, 25,50 ms, '2026-10-01'), ( 2,  4,44 ms, '2026-09-29')]
menu: 148,1 ms  availability;dur=112,20  queries=93
```

**[FATO] O estágio é dominado por materialização de linhas em Python, não por SQL.** Nessa medição `db;dur` = 7,9 ms para o request inteiro, enquanto só as duas primeiras chamadas de disponibilidade custam 99 ms. O mesmo padrão aparece na bancada com 131 produtos: `list(Product.objects.all())` = **4,5 ms de parede contra 1,72 ms de `db;dur`**; com `prefetch_related("collection_items__collection")` = **7,7 ms contra 0,53 ms**. O `execute_wrapper` do Django envolve `cursor.execute`, não `fetchall`/conversão de linha — **`db;dur` não mede o custo de virar objeto Python**, que é onde o estágio mora.

### 4.3 A curva de sensibilidade (a prova de que é O(linhas))

```
quants ativos   322 → availability;dur =  26,0 ms
                537 → availability;dur =  33,3 ms
              1.182 → availability;dur =  65,6 ms
              2.472 → availability;dur = 121,1 ms
```

Linear em linhas vivas de `stockman_quant` (~0,044 ms por linha, com as 4 passagens). **Não é O(N de SKUs)**: o número de SKUs ficou constante nas quatro medições (43). O que muda é quantas linhas de estoque existem para eles.

O comentário do próprio Core ("few queries regardless of N", `availability.py:364`) é verdadeiro sobre **consultas** e enganoso sobre **custo**: são 10 consultas por chamada — só que são **4 chamadas** e cada uma materializa todas as linhas elegíveis de novo.

### 4.4 O que NÃO é a causa

- **Não é consulta sem índice.** `Quant` tem índice em `sku` (`quant.py:149`), `target_date` e `(position, target_date)`; `Batch` em `sku`, `expiry_date`, `quality_grade_ref` (`batch.py:139`); `Hold` em `quant`, `status`, `expires_at`, `sku` (`hold.py:144`); `Product.sku` e `Channel.ref` são `unique`. `[FATO]`
- **Não é N+1.** Todas as leituras são em lote (`sku__in`). `[FATO]`
- **Não é o `validate_skus`/`get_sku_infos`**: 13,4 ms por request (4 chamadas) — 12 consultas que re-instanciam os mesmos produtos 4 vezes, um quarto do estágio. Vale cortar, mas não explica 1,2 s.
- **A fila de espera explica quase metade**: desligando `waitlist.enabled` no canal `web` (transação revertida), o request cai de **93 → 71 consultas** e a disponibilidade de **31,0 → 15,4 ms** (`[FATO]`). Em produção isso é ~metade dos 1,2–1,4 s.

---

## 5. O estágio `db` (0,44–0,80 s ao vivo)

`db;dur` é a **soma** do tempo de execução das 93 consultas. `[FATO]` Ao vivo: 442 / 462 / 488 / 512 / 805 ms em cinco amostras; mediana ~490 ms → **~5,3 ms por consulta**, contra **0,08 ms por consulta** na bancada sqlite. É o retrato de 93 idas e voltas a um Postgres gerenciado com `max_connections=25` e pool de 5 (WP-PERFORMANCE §2.3).

Consultas que **crescem sem limite** e não têm índice adequado:

| consulta | onde | índice | observação |
|---|---|---|---|
| `OrderItem JOIN Order WHERE order.created_at >= now-30d GROUP BY sku ORDER BY COUNT(id) DESC LIMIT 20` | `dynamic_collections.py:113-120` (`FeaturedResolver`) | **não existe índice em `orderman_order.created_at`** — WP §2.3/§4 | roda em **todo** menu/home/catalog; cresce com o volume da loja |
| `SELECT DISTINCT sku FROM stockman_quant WHERE sku IN (...)` | `availability.py:432` (`tracked_skus`) | usa o índice de `sku`, mas **não filtra `_quantity>0` nem data** | varre **todo o histórico** daqueles SKUs, **4× por request**. Medido: com 4.627 linhas mortas, sem efeito; com 17.527, +14 ms |
| `CustomerInsight.objects.exclude(favorite_products={})[:200]` | `storefront_context.py:46` (`popular_skus`) | JSONField, sem índice possível | varre a tabela de insights a cada request |
| `WorkOrder WHERE status='finished' AND finished_at >= now-60min` | `dynamic_collections.py:162-167` (`FreshFromOvenResolver`) | índices em `(status, target_date)`, `(output_sku, status)`, `target_date` — **não em `finished_at`** | `[FATO]` pequeno hoje |

As demais consultas são index-backed; o custo delas é **a contagem**, não o plano.

---

## 6. O laço `for p in products` (`catalog.py:471`)

`contextual_price` por SKU — medido:

```
4.contextual_price (loop por SKU)   0,39 ms   calls=45   queries=0
```

**[FATO] É O(N), e é irrelevante.** 8,7 µs por item, **zero consultas**: `active_promotions` é carregado uma vez (`catalog.py:468`, 4 consultas para o cardápio inteiro) e passado no contexto; o backend `PromotionPricingBackend` (`shopman/shop/adapters/pricing.py`, ligado em `config/settings.py:1366`) só percorre as promoções pré-carregadas em memória; `list_unit_price_q` já vem pronto do `listing_price_map`, então `CatalogService.get_price` não chama `unit_price` (`offerman/service.py:142`).

O que sobra de trabalho por item no laço é `_search_terms` (`catalog.py:818`), `_dietary_warnings` e a construção do dataclass — cerca de **0,6 ms por item** na bancada (≈ 25 ms para 44 itens, dentro dos ~79 ms de `_build_items`). Em produção isso vale 150–250 ms dos 2,5 s. **Vale cortar (é fácil), mas está longe de ser a causa.**

**[FATO] O laço roda mais vezes do que existem produtos.** `all_products` acumula por grupo de coleção (`catalog.py:266-271`) e um produto que está em duas coleções é construído duas vezes: 45 chamadas de `contextual_price` para 43 SKUs publicados na bancada. O payload vivo confirma o desperdício — **44 cards em `items` para 40 SKUs distintos**. O `items` do snapshot estrutural do Continuum é um dicionário por SKU (`continuum.py:91-94`) e já colapsa isso.

---

## 7. A home: por que ela andou junto com o cardápio

```
build_home(request, cart_has_items)          home.py:376
  └── build_shell(request, ...)              home.py:377    1,4-3,2 ms   4 consultas
  └── _reorder_context(request)              home.py:378    (~0 anônimo)
  └── build_catalog(channel_ref="web", ...)  home.py:379   67,7 ms     93 consultas
  └── featured = (catalog.featured or catalog.items)[:3]    home.py:380
```

**[FATO]** `/api/v1/storefront/home/` custa **97 consultas e 67,9 ms** na bancada — o mesmo que `/menu/` (93 / 71,7 ms) — para devolver 18.821 B em vez de 136.706 B. Todo o catálogo é construído, com preço, disponibilidade, seções e dinâmicas, para guardar **três** cards.

Ao vivo, isso bate: `menu/` 2,41–3,21 s e `home/` 2,60–3,13 s. **A home não tem regressão própria; ela é o cardápio pagando imposto.** E o `shell/` — criado em 28/09 justamente para não pagar isso — custa 4 consultas e 2,4 ms na bancada, 0,48–0,87 s ao vivo.

O SSR da home do storefront (`www.`, 3,91–4,35 s) soma, em série, `shell/` (4 consultas) + `home/` (97) + `site/` (3) — `app.vue:25` aguarda o shell, a página aguarda `useStorefrontHome()`.

---

## 8. Arqueologia: o que mudou entre 17/09 e 29/09

### 8.1 O código do caminho quente NÃO mudou

```bash
git diff 836066e1c..HEAD -- shopman/storefront/presentation/catalog.py \
    shopman/shop/projections/catalog_context.py \
    packages/stockman/shopman/stockman/services/availability.py
```

- `catalog.py`: **+7/-4 linhas**, todas instrumentação (`catalog_stage("personalization")`, `catalog_stage("availability")`) vindas de `0863be932` (28/09) + uma troca de copy em `_unit_weight_label`. A ordem de execução é a mesma.
- `catalog_context.py`: **+27 linhas**, um dataclass `CommercialIdentity` + `commercial_identity()` **não usados pelo cardápio** (`b65ed9729`, 22/09).
- `availability.py`: **zero mudança** no intervalo (`git log` vazio desde 16/09).

**[FATO] Não existe regressão de código na projeção.** O que existe é custo de dados e de ambiente.

### 8.2 O que cresceu

| eixo | 17/09 | 29/09 | evidência |
|---|---|---|---|
| tamanho do payload do `menu/` | 103 KB | 136,7 KB (+33%) | WP-PERFORMANCE §2.1 × minha medição |
| cards servidos | ~33 (103.000/3.107 B por card) | **44** | `[INFERÊNCIA]` do payload vivo; o dataclass do card não ganhou campo no intervalo, então o crescimento é de itens |
| coleções ativas / seções | — | 9 / 10 | payload vivo |
| consultas por request | — | **93** (o repo escreve "96-query catalog rebuild", `continuum.py:196`) | bancada |
| linhas de `stockman_quant` | — | cresce a cada dia de produção | **[NÃO VERIFICADO]** no alpha; é a variável que mais pesa (§4.3) |
| `OrderItem` em 30 d | 12.406 (WP §2.3) | 6.162 no seed novo | a consulta do `featured` roda em todo request, sem índice de data |
| carga no container `web` | 1 poll de 30 s por aba (`useContinuousProjection.ts:91-101`) | **2 polls** (`menu.vue:260-267`, `02b4f1487`) + reconstruções de snapshot a cada 5 min | carga, não código do cardápio |

### 8.3 O que mudou no ambiente

- **`3fdae7b0e` (19/09): Django 6.0.8 → 6.1.1** e `django-unfold` 0.92 → 0.107. `[FATO]` o commit existe; **o efeito na latência do cardápio é [NÃO VERIFICADO]** — não medi as duas versões.
- **Topologia inalterada**: `web` continua `apps-s-1vcpu-1gb` (**vCPU compartilhada**), 1 instância, servindo API + Admin + SSE de todos os subdomínios (`.do/app.alpha-subdomains.yaml:808-843`). O diff do spec no intervalo não mexe em `instance_size_slug`. `[FATO]`
- **`web.waitlist = {enabled: true, horizon_days: 2}`** já estava no seed em 17/09 (`seed_1709.py:5973-6018` e `seed_head.py:6131-6183`). **Não é regressão nova** — mas é um multiplicador permanente que o custo de 17/09 já pagava.
- **P1 do WP (health check barato) foi feito**, e é por isso que `health/live` **melhorou** (0,35–0,48 s → 0,27–0,32 s) e os shells de operador ficaram estáveis. Isso **reforça** o diagnóstico: a máquina não piorou — o trabalho pesado do storefront é que ficou mais pesado e mais concorrido.

### 8.4 Por que os shells de operador não regrediram

Custo medido na bancada: `shell/` = **4 consultas / 2,4 ms**; `site/` = 3 / 1,3 ms; `menu/` = 93 / 72 ms. Um endpoint de 5 consultas é imune a um fator de contenção de CPU; um de 93 consultas com 2.500 linhas materializadas não é. `[INFERÊNCIA]` consistente com a estabilidade medida em `gestor.`/`pdv.`.

### 8.5 O multiplicador prod/local, medido

| grandeza | bancada | produção | razão |
|---|---:|---:|---:|
| `menu/` total | 72 ms | 2.460 ms | **34×** |
| `availability` | 30 ms | 1.288 ms | **43×** |
| `personalization` | 5,3 ms | 27 ms | **5×** |
| `db` (93 consultas) | 7,5 ms | 490 ms | **65×** |
| `health/live` (0 consultas) | — | 280 ms | piso de rede |

Note que a razão **não é uniforme**: 5× no que é JSON em memória, 34–43× no que materializa linhas e faz consultas. Isso afasta a hipótese "a CPU do container é N× mais lenta" como explicação única e aponta para **custo por linha e por ida-e-volta**: são ~93 round-trips a ~5,3 ms e dezenas de milhares de instanciações de modelo por request.

---

## 9. `shadow;dur=0.00`: o que prova e o que não prova

- **[FATO] Não prova nada sobre a flag.** `CatalogTiming.server_timing()` emite os cinco nomes sempre, com `.get(name, 0.0)` (`observability.py:26-33`). Com o `capture_catalog_timing` trocado por um no-op, o header continua saindo com `shadow;dur=0.00`. É constante de formato.
- **[FATO] A prova está no ambiente:** `.do/app.alpha-subdomains.yaml:367-370` → `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED: 'false'`, com o comentário explícito "o shadow já cumpriu a amostragem e fica desligado para não onerar o menu canônico"; `kill_switch: 'false'`; `catalog_snapshot_enabled: 'true'`. O bloco que rodaria está em `surface.py:477-485`.
- **[FATO] Quanto custaria se estivesse ligado:** medi na bancada — `compare_shadow` = **14,3 ms** na primeira vez (head inexistente → materializa) e **2,9 ms** com head pronto, 1 consulta, snapshot de 33.984 B. Em produção, com a razão de 34×, isso seria ~100 ms por request. Não é hoje.
- **[INFERÊNCIA] O Continuum não é a causa da latência por request — mas é carga.** O endpoint estrutural está ligado e é consumido por todo `/menu` (`menu.vue:28-38`), com um poll de 30 s por aba, e o read model reconstrói com `build_catalog` completo quando o head passa de `reconcile_after_ms` (`continuum.py:196-199, 251-260`, 300.000 ms no alpha). Medido ao vivo: MISS 2,59 s → HIT 0,151 s.

---

## 10. Plano de otimização, em ordem

Coluna "prod" = estimativa usando a razão medida (§8.5) sobre o delta **medido** na bancada. Coluna "prova" é o comando/observation que fecha antes/depois.

### P1 — Servir a leitura anônima pela borda (`menu/`, `home/`, `catalog/`, `/catalog/products/`)

**Ganho: −2,2 a −3,0 s no TTFB do visitante** (de 2,46 s para ~0,15 s), provado no MESMO app: o snapshot estrutural responde **0,151 s com `cf-cache-status: HIT`** contra **2,59 s com MISS**, com `cache-control: public, max-age=30, s-maxage=30, stale-while-revalidate=120` e `vary: Accept` (`shopman/storefront/api/continuum.py:76-80`).
**O que fazer:** para GET anônimo (sem cookie de sessão/sacola), responder `Cache-Control: public, max-age=30, s-maxage=60, stale-while-revalidate=120`, tirar `Vary: Cookie` e parar de setar `csrftoken` em GET anônimo (hoje `ensure_csrf_cookie` está em `surface.py:278, 301, 450, 540, 568, 586`). É o P6 do WP-PERFORMANCE, agora com a prova de que funciona.
**Risco: médio.** Preço/estoque com até 30 s de atraso para quem está deslogado e sem sacola (a sacola já é `private`); nada de cache para quem tem sessão. Precisa de teste de contrato garantindo que nenhuma variação por sessão escape.
**Prova:** `curl -sD- -o/dev/null -w '%{time_starttransfer} %{size_download}\n'` + `cf-cache-status` antes/depois; `Server-Timing` ausente no HIT; taxa de HIT no painel da Cloudflare; contagem de consultas inalterada no MISS.

### P2 — Um único cálculo de disponibilidade por request (o conserto estrutural)

**Ganho medido na bancada (com 2.472 quants):** disponibilidade **112,2 → ~40 ms**, consultas **93 → 70** só removendo as duas passagens extras do laço de datas; e **→ ~60 consultas** se o batch de componentes do bundle reusar o mesmo material (−10: a chamada de 2 SKUs do bundle). **Estimativa em produção: −0,9 a −1,3 s** no `menu/` e no `home/`.
**O que fazer (Core, `packages/stockman`):**
1. `waitlist.next_batch_availability_for_skus` (`waitlist.py:111-137`) faz **uma** consulta de quants futuros (`sku, target_date, batch, position, _quantity`) e agrega por (sku, data) em Python, com o mesmo `is_valid_for_date`/`expired_refs`/`held` — em vez de chamar `availability_for_skus` inteiro por data candidata.
2. O batch de componentes do bundle (`catalog_context.py:797`) reusa o resultado do batch principal quando o SKU já está nele, ou entra no mesmo lote.
3. Opcional e mais ambicioso: `availability_for_skus` aceita uma lista de datas e devolve um `{data: {sku: info}}` numa única varredura de quants.
**Risco: alto.** É o Core e é régua de promessa (oversell). `packages/stockman` já tem `tests/test_batch_consistency.py` afirmando batch ≡ por-SKU: usar como rede.
**Prova:** `Server-Timing` `availability;dur` antes/depois; contagem de consultas por request (teste de budget); digest do snapshot do Continuum (`catalog_structure_state_from_projection`) **inalterado** — ele existe e é oráculo de igualdade de estrutura; suíte `make test-stockman`.

### P3 — `home/` deixa de construir o catálogo inteiro

**Ganho medido:** `home/` **67,9 → 21,7 ms** e **97 → 43 consultas** (rail de 3 SKUs via `build_catalog_items_for_skus`). **Estimativa em produção: −2,0 a −2,5 s** no `home/` e na home SSR do storefront (3,91–4,35 s), que é a página mais cara do site.
**O que fazer:** `home.py:379` troca `build_catalog(...)` por uma leitura barata de "featured" (`catalog.items` não é usado para mais nada: `home.py:380` guarda só `[:3]`). Precisa de um `featured_items` que respeite `is_featured` = `popular_skus` — já é uma leitura isolada.
**Risco: médio-baixo.** O contrato do payload da home não muda (3 cards + shell + reorder); o risco é divergência de preço/disponibilidade entre o rail da home e o cardápio.
**Prova:** comparar o JSON de `home/` antes/depois (diff campo a campo), contagem de consultas (`django.test.utils.CaptureQueriesContext`), `Server-Timing` do `menu/` inalterado.

### P4 — `published_products_by_collection`: uma consulta em vez de nove

**Ganho medido:** **27 → 3 consultas**, 17,45 → ~4 ms. **Estimativa em produção: −0,15 a −0,25 s** (24 consultas × 5,3 ms) mais a instanciação repetida dos mesmos produtos.
**O que fazer (`catalog_context.py:305-328`):** uma consulta de produtos publicados no listing com `prefetch_related("keywords", "components", "collection_items__collection")`, e o agrupamento por coleção em Python (a ordem já vem de `CollectionItem.sort_order`). O `.distinct()` por coleção desaparece junto.
**Risco: baixo.** Ordenação e `distinct` são o ponto de atenção; o digest do Continuum é o oráculo.
**Prova:** contagem de consultas; `catalog_structure_state_from_projection` idêntico; teste de contrato da projeção (`shopman/storefront/tests/test_home_projection_contract.py`).

### P5 — Cortar a duplicação do payload do cardápio

**Ganho:** hoje o payload carrega **120 cópias de card** (44 em `items` + 76 dentro de `sections`), 85 KB de 135 KB — 63% do corpo é duplicação. Medido: `projection_data` + carrinho = 5,3 ms locais (≈ 27 ms ao vivo em `personalization;dur`). **Estimativa em produção: −100 a −200 ms** de JSON + rede, e −63% de bytes por visitante.
**O que fazer:** `sections` passa a carregar `skus` (o Continuum já faz exatamente isso em `catalog_structure_state_from_projection`, `continuum.py:99-106`) e o cliente resolve pelo mapa de `items`. **Mudança atômica BE+FE.**
**Risco: médio** (contrato consumido por `surfaces/storefront-nuxt`).
**Prova:** bytes do corpo antes/depois; teste de contrato do payload; smoke do /menu.

### P6 — Índice de data em `orderman_order` (P2 do WP-PERFORMANCE)

**Ganho: não medido — [NÃO VERIFICADO]**, mas é a única consulta do caminho quente que faz scan completo de tabela que cresce com a loja (`dynamic_collections.py:113-120`), e roda em **todo** request de menu/home/catalog.
**O que fazer:** `AddIndexConcurrently` em `created_at` no Core, e `fomo.sold_today`/`demand/backend.py` trocando `__date=` por `__range`.
**Risco: baixo** (índice, sem campo novo — dentro da regra do CLAUDE.md).
**Prova:** `EXPLAIN` antes/depois; delta de `pg_stat_user_tables.seq_scan` em 24 h.

### P7 — Tirar o scan sem limite de `tracked_skus`

**Ganho: [NÃO VERIFICADO] no alpha**; medido na bancada: irrelevante com 4.627 linhas, +14 ms com 17.527. Cresce para sempre.
**O que fazer (`availability.py:432`):** `Quant.objects.filter(sku__in=skus, _quantity__gt=0)` ou um `EXISTS` por SKU — `is_tracked` só quer saber "existe saldo", não "existiu algum dia".
**Risco: baixo** (muda semântica num campo de leitura).
**Prova:** contagem de linhas varridas via `EXPLAIN (ANALYZE)`; teste de `is_tracked` no `packages/stockman`.

### P8 — `ChannelConfig.for_channel` memoizado por request

**Ganho medido:** 5 chamadas → **−5 consultas**; ~0,3 ms cada depois da primeira. **Em produção: −25 ms.** Barato de fazer, pequeno.
**Risco: baixo** — memo no `request` (não em módulo, para não congelar config entre requests).
**Prova:** contagem de consultas; teste que muda a config e confirma que o request seguinte vê o valor novo.

### P9 — Higiene do loop por item (só depois de P1–P4)

`_search_terms` gera 250 B por card (7,6% do payload) e `_dietary_warnings` roda por item dentro de `_build_items`. **Estimativa: 100–250 ms** em produção.
**Risco: baixo.** **Prova:** perfil por etapa (§3.3) antes/depois.

### Ordem recomendada

**P1 primeiro** (é o único que já tem prova de 0,151 s no ar e não mexe em regra de negócio), em paralelo com **P4 + P3** (baixo risco, ~0,3 s cada). **P2 depois**, com P6/P7 como migração de Core no mesmo PR. P5 e P9 por último.

Meta do alvo < 0,6 s: **P1 sozinho entrega** para o visitante anônimo (0,15 s em HIT). Para o visitante **com sacola** — que nunca vai poder usar cache público — a soma P2+P3+P4+P6+P9 leva a bancada de 72 ms para ~25-30 ms, e a produção de ~2,46 s para **~0,85–1,0 s** pela razão de 34×. Chegar a 0,6 s no caminho autenticado exige, além disso, cortar o número de round-trips (93 → ~35), não só o Python.

---

## 11. Dois defeitos laterais encontrados na leitura

1. **[FATO] O fallback do `FeaturedResolver` está quebrado e falha em silêncio.** `dynamic_collections.py:138` faz `qs.order_by("sort_order", "name")`, mas `Product` **não tem `sort_order`** → `FieldError`, engolido pelo `except` de `dyn.resolve` (`dynamic_collections.py:82-86`): a seção "Destaques" simplesmente desaparece e o erro só sai em `logger.exception`. Reproduzi com o catálogo reduzido (traceback completo em `dynamic_collections.py:138`). Quando esse caminho fosse alcançado de verdade, ele também faria `[p for p in qs if ...]` — **materializando a tabela de produtos inteira em Python**, o pior caso possível.
2. **[FATO] O funil não é o gargalo, a contagem de consultas é.** `availability_for_skus` do Stockman documenta "few queries regardless of N" e são 10 consultas por chamada; o custo está em chamá-la 4 vezes e em materializar as linhas 4 vezes. Qualquer otimização que só mexa em plano de consulta (índice) não move a agulha; o que move é reduzir passagens e round-trips.

---

## 12. O que não deu para medir, e por quê

| item | por quê |
|---|---|
| Linhas de `stockman_quant`/`stockman_batch`/`orderman_order` no alpha | não tenho credencial nem `psql`; só medi **indiretamente**, pela curva de sensibilidade §4.3. É a medição que mais fecharia o diagnóstico: `SELECT count(*) FILTER (WHERE _quantity>0) FROM stockman_quant;` |
| Contagem de consultas real do alpha por request | o `query_count` só sai no log `storefront_catalog_observation` (`surface.py:495-513`), que não é público. O repo registra "96-query catalog rebuild" (`continuum.py:196`), que casa com os 93 que medi |
| Efeito do Django 6.0.8 → 6.1.1 | exigiria rodar as duas versões |
| `pg_stat_statements`, `EXPLAIN` no Postgres do alpha | extensão não instalada (WP §2.3); não é acesso que eu tenha |
| Separação entre CPU, contenção e deserialização dentro dos 34× | só com APM ou `py-spy` no container do `web` |
| p95 com 20 amostras | fiz 3–8 por URL, para não gerar carga |
