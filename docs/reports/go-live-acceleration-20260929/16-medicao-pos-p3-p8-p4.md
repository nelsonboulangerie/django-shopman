# 16 — Produção depois de P3 + P8 + P4, e por que P7 e P9 não foram feitos

**Data:** 30/09/2026, 22:38–23:21 UTC. **Deploy medido:** `405e3f25-dae6-4f2b-a4ce-9a302daeca70`
(causa `manual`, ACTIVE às 23:17:00 UTC, criado pelo run `36789276203` do `deploy-images.yml` sobre o
merge `1a9e38c16` do #1295). Só GET, rota privada, `cf-cache-status: BYPASS`.
**Contexto:** `13-hot-path-projecao.md` (o diagnóstico) e #1295 (P3 + P8 + P4).

## 1. `GET /api/v1/storefront/menu/`: 5 amostras espaçadas de ~20 s, medianas

| | antes (22:38–22:39) | depois (23:18–23:20) | Δ |
|---|---:|---:|---:|
| TTFB | 2,63 s | 2,51 s | −0,12 s (−5%) |
| `projection;dur` | 2.292 ms | 2.155 ms | −137 ms (−6%) |
| `availability;dur` | 1.395 ms | 1.294 ms | −101 ms (ruído) |
| `db;dur` | 396 ms | 292 ms | −104 ms (−26%) |
| `query_count` (log `storefront_catalog_observation`) | **83** | **55** | **−28 (−34%)** |
| `response_bytes` (log) | 136.681 | 136.681 | idêntico |

Amostras cruas:

```
antes  TTFB 3,311 2,631 3,917 2,576 2,625 | projection 2930 2285 3492 2250 2292 | availability 1636 1328 1547 1289 1395 | db 461 358 804 363 396 | q 86 83 83 83 83
depois TTFB 2,530 3,026 2,491 2,209 2,513 | projection 2180 2664 2155 1885 2045 | availability 1394 1418 1294 1153 1211 | db 292 418 292 280 352 | q 55 55 56 55 55
```

O vivo faz **83** consultas, não as 93 da bancada: o catálogo do alpha tem outra forma. O `response_bytes`
igual byte a byte é a segunda prova de contrato, agora em produção (a primeira foi o diff de 14.513
campos na bancada, no #1295).

## 2. `home/` e `shell/`: 3 amostras depois do deploy

| | antes (30/09 ~22:02, 5 amostras) | depois (23:20–23:21, 3 amostras) |
|---|---:|---:|
| `home/` TTFB | 3,13 s | **1,16–1,52 s** (mediana 1,29 s) |
| `home/` `projection;dur` | 2.828 ms | **873–1.003 ms** |
| `home/` `availability;dur` | 1.545 ms | **235–257 ms** |
| `shell/` TTFB | 0,51–0,80 s | 0,55–1,23 s (a primeira amostra ainda aquecendo) |

**O P3 entregou o que o relatório 13 previa para a home (−1,8 s).** Para o `menu/`, P8 + P4 cortaram
34% das consultas, mas só ~6% do tempo.

## 3. O que sobra no `menu/`: disponibilidade

`availability;dur` ≈ 1,3 s = **60% da projeção**, e não se moveu. Não é consulta (o `db` inteiro do
request é 292 ms): é o cálculo repetido 4× por request e a materialização de linhas de `stockman_quant`
(relatório 13 §4). A próxima alavanca é o **P2**, que toca o Core e precisa de frente própria.

## 4. P7 — RECUSADO: muda a resposta para SKU esgotado

A proposta era `Quant.objects.filter(sku__in=skus, _quantity__gt=0)` em `tracked_skus`
(`packages/stockman/.../services/availability.py:432`).

- `is_tracked` quer dizer "o Stockman já controlou este SKU", não "tem saldo agora". Quant não é
  apagado: `_quantity` é o cache de Σ(moves), e um SKU que vendeu tudo fica com quant **zerado**.
- SKU **não** rastreado é aprovado **sem limite**: `available_qty = 999999`
  (`shopman/shop/services/availability.py:323`).
- Com o filtro, um SKU esgotado passa a não rastreado e **vende sem limite exatamente quando acabou**.

Provado na bancada (`CI` zerado por `stock.adjust`: rastreado hoje `True`, com o filtro `False`). A
prova virou trava: `shopman/shop/tests/test_sold_out_sku_stays_tracked.py`. Com o filtro aplicado
(teste de mutação local, revertido), **os dois testes reprovam**.

O custo do `tracked_skus` continua real (varre o histórico, 4× por request). A saída certa é da frente
do Core: por exemplo, um `EXISTS` por SKU, sem varrer todas as linhas, mantendo a resposta.

## 5. P9 — NÃO FEITO: o ganho medido não existe

O relatório 13 estimou 100–250 ms em produção para o laço por item (`_search_terms`,
`_dietary_warnings`, construção do card), pela conta de ~0,6 ms/item × 34. Medido com `cProfile` em 20
montagens do cardápio na bancada:

| função (por card) | 900 chamadas (20 cardápios × 45 cards) |
|---|---:|
| `contextual_price` | 10 ms |
| `_product_tags` | 8 ms |
| `_search_terms` | 6 ms |
| `_resolve_availability` | 3 ms |
| `_money`, `orderable_ceiling`, `_unit_weight_label`, `availability_with_own_hold` | < 3 ms somadas |

Isso dá **~1,5 ms por request** local (~0,03 ms/item), já com o overhead do profiler. Dentro do
`_build_items` (81 ms por cardápio sob profiler), **58 ms são disponibilidade** e o resto é consulta em
lote. Mexer no laço seria mudança sem ganho mensurável.

## 6. Fora de escopo, registrado

- Com sacola, `home/` e `menu/` fazem ~200 consultas (#1295): o custo está na projeção da sacola.
- `Marketing — cadeia completa` reprova em todos os PRs desde 30/09 ~22:00 por um alerta novo do npm
  (`brace-expansion`, GHSA-q2hr-2g5m-vwhr / GHSA-qhr7-859c-m2p7 / GHSA-6j4f-fj2g-mc7p) no audit do
  `operator-kit`. O check não é obrigatório, então não segura merge.
- #1291 está vermelho por causa própria: ele desliga `deploy_on_push`, e
  `shopman/shop/tests/test_nuxt_deploy_config.py:156` ainda exige o valor ligado.
