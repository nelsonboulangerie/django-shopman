# UX-PROD-AF2 · Aproveitamento no B.I. e no livro de receitas

Branch `claude/ux-prod-af2-aproveitamento`, PR #1439.

Seguimento do PR #1433 (UX-PROD-AF). Decisão do dono (03/10/2026): o B.I. e o livro
de receitas trocam a CONTA de realizado ÷ planejado para realizado ÷ previsto e o
rótulo "Rendimento" para "aproveitamento", alinhados ao resto da Produção.

## A conta, antes e depois

Lote: planejado 12, previsto (`started_qty`) 10, realizado 9.

| | Antes | Depois |
|---|---|---|
| Aproveitamento | 9 ÷ 12 = 75% ("Rendimento") | 9 ÷ 10 = 90% ("Aproveitamento") |
| Perda (B.I.) | 12 − 9 = 3 | 10 − 9 = 1 |

A base é a do Craftsman (`WorkOrder.yield_rate`/`WorkOrder.loss`): previsto = quantidade
da abertura, ou o planejado quando ninguém a declarou; perda por lote, nunca negativa.
O previsto vem num prefetch dos eventos de abertura (a property do modelo faz uma
consulta por lote), lido pelos mesmos helpers da projeção da Produção
(`_wo_started_qty`, `_wo_started_assumed`).

## Inventário (arquivo → antes → depois)

| Arquivo | Antes | Depois |
|---|---|---|
| `backstage/projections/bi_production.py` | `yield_percent` = realizado ÷ planejado do dia; `loss` = planejado − realizado do dia; anterior idem | ÷ previsto; perda somada lote a lote (previsto − realizado); campos novos `started` (dia), `started_total` (anterior) e `batches_started_assumed` |
| `backstage/projections/bi_explore.py` | métrica `yield_percent` "Rendimento" = realizado ÷ planejado; `loss` = planejado − realizado | "Aproveitamento" = realizado ÷ previsto; `loss` = previsto − realizado (a chave `yield_percent` fica: identificador, como `yield_rate` no Core, e é a chave dos cenários salvos) |
| `backstage/projections/recipe_book.py` (`build_recipe_usage`) | `yield_pct` = realizado ÷ planejado; "rendimento médio" | realizado ÷ previsto; "aproveitamento médio", e "(previsto assumido em N de M)" quando houver; campo novo `started_assumed_batches` |
| `backstage/services/closing.py` (`aggregate_by_version`) | sem contagem de previsto assumido | chave `started_assumed` (o resumo persistido no `DayClosing` não muda: escolhe chaves explícitas) |
| `backstage/bi/scenarios.py` | entrada do cenário sem previsto | `started` no dia |
| `bi-nuxt/pages/index.vue` | "Rendimento do período/por dia" = realizado ÷ planejado (dizendo "÷ previsto"); tooltip "previsto" mostrava o planejado | "Aproveitamento do período/por dia" = realizado ÷ previsto de verdade; tooltip mostra o previsto; a dica do bloco diz quantos lotes tiveram o previsto assumido |
| `bi-nuxt/presentation/bi.ts` | exemplo "Rendimento por receita" | "Aproveitamento por receita"; `startedAssumedHint` |
| contratos gerados | | `biContract.ts` (`export_bi_schema`), `recipeBookContract.ts` (`export_recipe_book_schema`) |

Já estavam certos (÷ previsto) e não mudaram: relatórios da Produção (`yield_rate`,
`average_yield_rate`, `yield_avg`), alerta de aproveitamento baixo, `loss_display` do
Admin, CSV de relatórios.

## Travas

- `shopman/backstage/tests/test_vocabulario_abertura_fechamento.py`: métrica do B.I. se
  chama "Aproveitamento"; `bi_production.py`, `bi_explore.py` e `bi/scenarios.py` não
  dizem "rendimento"; o uso por versão diz "aproveitamento médio".
- `surfaces/bi-nuxt/tests/lotVocabulary.test.ts`: "rendimento" não volta ao bi-nuxt; o
  aproveitamento do período não divide pelo planejado.
- Testes da conta nova (previsto ≠ planejado): `test_bi_production.py`,
  `test_bi_explore.py`, `test_production_by_version.py` (inclui o previsto assumido).

## Fora de escopo, deliberadamente

- "Rendimento" da ficha técnica e da massa (comparação de versões, mapa código-cego,
  etiqueta de pesagem): intactos.
- Barra de progresso do dia no quadro da Produção (realizado ÷ planejado): é progresso
  ("quanto falta"), não indicador de lote.
- Perda "por defeito/grau" no explorador: vem das linhas de qualidade declaradas, não
  da conta.
- Cenários salvos por gestores com o nome "Rendimento…" são dado do usuário, não código.
- No B.I. o número é agregado (dia, receita, forno), não por lote: o previsto assumido é
  sinalizado como contagem na dica do bloco, não lote a lote.
