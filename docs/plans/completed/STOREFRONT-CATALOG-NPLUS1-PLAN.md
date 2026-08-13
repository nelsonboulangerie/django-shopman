# STOREFRONT-CATALOG-NPLUS1-PLAN — o menu em ~10 queries, não 347

**Status:** ✅ executado (2026-08-01). O N+1 por SKU está morto — o custo do menu
agora é **O(coleções) + passes fixos de disponibilidade**, **plano em relação ao
número de produtos** (provado: 6 produtos → 27 queries; 66 produtos → 27 queries).
Ver "Resultado" no fim. Motivado pela investigação de performance
([project_storefront_performance_do_arch]) — o SSR da loja levava ~5,6s no staging;
a API `/api/v1/storefront/menu/` sozinha ~2,7s.

## O diagnóstico (medido)

`build_catalog(channel_ref="storefront")` dispara **347 queries** para montar o
menu (medido local: 193ms com PG local; ~2,7s no staging por causa da latência de
rede a cada round-trip ao PG gerenciado). Padrão clássico de **N+1** — as consultas
mais repetidas:

| repetições | tabela | origem provável |
|---|---|---|
| 58× | `offerman_product` | re-query lazy de produto no loop |
| 55× | `offerman_collection` | coleção por item |
| 54× | `offerman_collectionitem` | pertencimento a coleção |
| 52× | `offerman_productcomponent` | checagem de componentes de bundle |
| 51× | `storefront_promotion` | avaliação de promoção **por SKU** |
| 51× | `taggit_tag` | tags do produto (alvo de promoção por tag) **por SKU** |

`_build_items` (`shopman/storefront/presentation/catalog.py:394`) já batcheia
coleções, preços de listing e disponibilidade. O N+1 vem de dentro do loop
`for p in products:` que chama `catalog_context.contextual_price(p.sku, ...)` **por
produto** — e a engine de pricing (regras) consulta promoções + tags + componentes
a cada SKU.

## Por que NÃO é cache

`build_catalog` é **profundamente personalizado**: preço varia por
`price_tier`/`customer_segment`, `fulfillment_type` e `session_total_q`
(happy hour / D-1 / sessão), além de favoritos, quantidades no carrinho,
inscrições "me avise" e preferências alimentares. Cachear a projeção (Valkey) ou o
HTML SSR (routeRules `swr`) **vazaria preço/favoritos/carrinho de um cliente para
outro** — bug de correção E privacidade. O cache foi descartado por isso. O fix
correto é **eliminar o N+1**, que beneficia todos os clientes sem vazar estado.

## O plano (Core é sagrado — cuidado com a engine de pricing)

1. **Prefetch de tags** dos produtos numa query só (`prefetch_related` via taggit)
   e **passar as tags já carregadas** para o contexto de pricing, em vez de a engine
   buscar por SKU. Colapsa ~51 → 1.
2. **Bulk das promoções ativas** uma vez (todas as `Promotion` ativas do canal),
   passar o conjunto para a avaliação por SKU em memória. Colapsa ~51 → 1.
3. **Prefetch de componentes de bundle** (`ProductComponent`) para os bundles do
   lote numa query. Colapsa ~52 → 1.
4. **Matar as re-queries lazy** de `product`/`collection`/`collectionitem` no loop
   — provável acesso a FK/relação não-prefetchada; `select_related`/`prefetch_related`
   no queryset de `published_products_by_collection`.
5. **Alvo:** ~347 → ~10 queries. Medir com `CaptureQueriesContext` (o mesmo harness
   do diagnóstico) antes/depois.

## Guarda-corpos

- ⚠️ **Superfície de cliente com PREÇO**: um erro aqui mostra preço/promoção errada.
  Rodar TODA a suíte de catálogo + pricing (`make test-offerman`, testes de
  `storefront/presentation`, e os de `shop/rules/pricing`) e comparar a projeção
  byte-a-byte (mesmos itens, mesmos preços, mesmas badges) antes/depois num fixture
  rico (seed Cardápio 2027, com happy hour / grupo / segmento).
- A engine de pricing é Core (`shop/rules/`) — preferir **passar dados
  pré-carregados pelo contexto** a reescrever a engine. Se exigir mudar a assinatura
  de `contextual_price`, discutir (ADR-001 / respeito ao Core).
- Merecer sessão própria e focada (não fim de sessão longa) pelo risco.

## Já feito nesta frente (2026-08-01)

- ✅ Infra: probe do storefront-nuxt afrouxado (http_path `/`, timeout 5→20s,
  initial_delay 60, period 15) + instância 0.5GB→1GB — deploys deixam de ser sorte
  e o SSR ganha RAM/CPU. Aplicado no spec live (segredos preservados).
- ✅ Copy: estados de erro da loja fora da voz ("tropeço") reescritos.
- ✅ CI: teste tz-flaky do X/Z do PDV corrigido (fuso da loja fixo).
- ⏳ ESTE plano (N+1 do catálogo) — o ganho de fundo dos ~2,7s do Django.

## Resultado (2026-08-01)

Medido com `CaptureQueriesContext` num fixture rico (16 SKUs / 3 coleções, com
bundle, tags, e promoções por SKU/coleção/valor-fixo ativas). Steady-state
(caches quentes, como worker de produção):

| | queries (fixture 16 SKUs) |
|---|---|
| antes | **111** |
| depois | **40** (−64%) |

**Prova de que o N+1 morreu** (novo teste `test_query_count_does_not_scale_with_product_count`):
**6 produtos → 27 queries; 66 produtos (11×) → 27 queries.** Antes, cada SKU
adicionava ~4 round-trips (promoção + cupom + tag + `is_bundle`) + os re-fetches
de disponibilidade. As queries restantes escalam com o nº de coleções e os passes
fixos de disponibilidade, nunca por produto — extrapolando, o menu real (~59 SKUs)
deixa de fazer ~347 idas ao PG.

**Paridade byte-a-byte:** todos os campos semânticos da projeção (sku, nome,
`price_display`, `has_promotion`, `promotion_label`, `original_price_display`,
`availability`, badges, `can_add_to_cart`, seções, featured) **idênticos** antes/
depois. Única diferença: a **ordem** da lista `tags`/`search_terms` (índice de
busca, nunca preço/badge) passou a ser determinística (alfabética) — os conjuntos
são iguais.

### As 4 origens do N+1 e o fix (1 query cada)

1. **`taggit_tag` (16×)** — `product_tags(p)` → `keywords.all()` por produto.
   Fix: `prefetch_related("keywords")` em `published_products_by_collection`
   (`catalog_context`). `product_tags` agora ordena (determinismo).
2. **`storefront_promotion` + `storefront_coupon` (32×)** — `StorefrontPricingBackend`
   consultava as promoções ativas **por SKU**. Fix (ADR-001, dados pré-carregados
   pelo contexto, engine intacta): o builder carrega as promoções ativas **uma vez**
   (`_active_storefront_promotions`) e passa via `context["active_promotions"]`; o
   backend consome a lista pré-carregada (mantém o fallback de query para callers
   avulsos — PDP/cross-sell).
3. **`offerman_productcomponent` (17×)** — `p.is_bundle` = `components.exists()`
   por produto. Fix: `prefetch_related("components")` (o `.exists()` usa o cache do
   prefetch, zero query).
4. **re-queries lazy de `product`/`collectionitem` (~33×)** — a hipótese do plano
   (FK não-prefetchada no loop do builder) estava **errada**: a fonte real era o
   **Core do Stockman**. `availability_for_skus` (cujo docstring promete "few
   queries regardless of N") fazia `{sku: validator.get_sku_info(sku) for sku in
   skus}` — um `Product.objects.get` + lookup `is_primary` por SKU. Fix: método
   **batch** `get_sku_infos(skus)` no protocolo `SkuValidator` + adapters (offerman
   com prefetch iterado em Python — `.filter(is_primary=True)` re-consultaria e
   anularia o prefetch —, buyman, noop, e o `ComposedSkuValidator` que faz o
   merge). Completa o par que já existia para `validate_sku`/`validate_skus`;
   respeita o Core (não reinventa, segue o idioma batch existente).

### Testes
`make test-offerman` (273), stockman (230), buyman (9), storefront/web (413),
shop (1721), composed adapters (6, +1 novo p/ `get_sku_infos`), ruff — todos verdes.
Guardas de regressão: teto de queries no `test_measure_catalog_queries` e o teste
de escala acima.

### Ainda no radar (não-N+1, baixo retorno/risco)
O prefetch de `keywords`/`components` re-executa **por grupo de coleção** (o
`published_products_by_collection` emite uma query de produto por coleção). É
`O(coleções)`, não por-produto — não é o N+1 que travava o deploy. Colapsar num
único fetch-e-agrupa-em-Python mexeria na ordenação por coleção numa superfície de
**preço**; adiado por risco/retorno.
