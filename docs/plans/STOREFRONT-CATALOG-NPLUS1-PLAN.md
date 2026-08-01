# STOREFRONT-CATALOG-NPLUS1-PLAN — o menu em ~10 queries, não 347

**Status:** aberto (2026-08-01). Motivado pela investigação de performance
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
`customer_group`/`customer_segment`, `fulfillment_type` e `session_total_q`
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
